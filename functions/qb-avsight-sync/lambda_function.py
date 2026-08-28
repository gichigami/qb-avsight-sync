"""
AWS Lambda Function: QuickBooks-AvSight Sync
Syncs invoice and bill data between QuickBooks Online and Salesforce AvSight

This function is triggered by EventBridge (CloudWatch Events) on a schedule
"""

import json
import time
import boto3
import pandas as pd
from datetime import datetime, timezone, date
from typing import Any, Dict, List, Optional

# Local imports
from quickbooks_connector import QuickBooksConnector
from salesforce_connector import SalesforceConnector
from utils import (
    get_secret, update_secret, format_time,
    exact_time, find_order_number, save_daily_summary_to_s3,
    get_last_run_timestamp, save_last_run_timestamp,
    get_s3_bucket_name, send_auth_failure_alert,
)
from config import (
    get_salesforce_batch_size, get_results_directory,
    get_qb_redirect_uri, get_email_recipients,
    get_enable_incremental_sync,
    get_po_sync_enabled, get_po_sync_batch_size
)

# Field name constants
FIELD_PAYMENT_STATUS = 'Payment Status'
FIELD_BALANCE_DUE = 'Balance Due'
FIELD_TOTAL_AMOUNT = 'Total Amount'
FIELD_QUICKBOOKS_ID = 'QuickBooks ID'
FIELD_CUSTOMER_VENDOR = 'Customer/Vendor'
FIELD_ITEMS_DESCRIPTION = 'Items/Description'
FIELD_DATE = 'Date'
FIELD_DUE_DATE = 'Due Date'
FIELD_NUMBER = 'Number'
FIELD_ORDER = 'Order'
FIELD_PRIVATE_NOTE = 'Private Note'


def _log_bulk_results(label: str, results: Any, records_sent: List[Dict]) -> Dict[str, int]:
    """
    Inspect simple_salesforce bulk results and log success/failure counts.

    The existing call sites write `results` to a `/tmp` CSV but never check
    per-record `success`/`errors` — so silent SF write failures (validation
    rules, permission errors, trigger reverts) are invisible. This surfaces them.

    Returns counts dict `{success, failed, total}`.
    """
    counts = {"success": 0, "failed": 0, "total": 0}
    if not isinstance(results, list):
        print(f"  ⚠️ [{label}] Bulk result is not a list (type={type(results).__name__}); cannot inspect")
        return counts

    counts["total"] = len(results)
    error_samples: List[str] = []
    sample_failed_ids: List[str] = []
    for i, r in enumerate(results):
        if isinstance(r, dict) and r.get("success"):
            counts["success"] += 1
        else:
            counts["failed"] += 1
            if len(error_samples) < 5:
                errors = r.get("errors") if isinstance(r, dict) else None
                sent_id = records_sent[i].get("Id", "(no Id)") if i < len(records_sent) else "(idx out of range)"
                sample_failed_ids.append(sent_id)
                error_samples.append(f"{sent_id}: {errors}")

    print(f"\n📋 [{label}] Bulk result: {counts['success']} succeeded, {counts['failed']} failed (of {counts['total']})")
    if counts["failed"] > 0:
        print(f"  ⚠️ First {len(error_samples)} failures:")
        for line in error_samples:
            print(f"    {line}")
    return counts


def _upload_bulk_results_to_s3(label: str, results: Any) -> None:
    """
    Persist bulk-update results JSON to S3 for post-mortem.

    Pairs with `_log_bulk_results` — the CloudWatch summary tells you something
    is wrong, this gives you the full per-record detail to dig into.
    """
    try:
        bucket = get_s3_bucket_name()
        key = f"bulk-results/{date.today().isoformat()}/{exact_time()}_{label}.json"
        s3 = boto3.client("s3")
        s3.put_object(
            Bucket=bucket,
            Key=key,
            Body=json.dumps(results, default=str, indent=2).encode("utf-8"),
            ContentType="application/json",
        )
        print(f"  💾 [{label}] Full results saved to s3://{bucket}/{key}")
    except Exception as e:
        print(f"  ⚠️ [{label}] Failed to upload results to S3: {e}")


def _extract_line_items(lines: Optional[List], detail_type: str) -> List[str]:
    """
    Extract descriptions from line items
    
    Args:
        lines: List of line items
        detail_type: Type of line detail to filter for
        
    Returns:
        List of description strings
    """
    items_desc = []
    if lines:
        for line in lines:
            if line.get('DetailType') == detail_type:
                if 'Description' in line:
                    items_desc.append(line['Description'])
    return items_desc


def _determine_payment_status(balance: float) -> str:
    """
    Determine payment status from balance
    
    Args:
        balance: Outstanding balance amount
        
    Returns:
        'Paid' if balance is 0, 'Unpaid' otherwise
    """
    return 'Paid' if balance == 0 else 'Unpaid'


def _get_customer_vendor_name(record: Dict, ref_key: str) -> str:
    """
    Extract customer or vendor name from record
    
    Args:
        record: Invoice or bill record
        ref_key: 'CustomerRef' for invoices, 'VendorRef' for bills
        
    Returns:
        Customer/vendor name or 'Unknown'
    """
    if ref_key in record:
        return record[ref_key].get('name', 'Unknown')
    return 'Unknown'


def _normalize_date(date_val) -> str:
    """
    Convert date to YYYY-MM-DD string format for comparison

    Args:
        date_val: Date value (string, datetime, or None)

    Returns:
        Normalized date string in YYYY-MM-DD format, or empty string if None/NaN
    """
    if pd.isna(date_val) or date_val == '' or date_val is None:
        return ''
    # If it's already a string, try to extract date portion
    date_str = str(date_val)
    # Handle datetime strings like "2024-01-15T00:00:00.000Z" or "2024-01-15T00:00:00"
    if 'T' in date_str:
        date_str = date_str.split('T')[0]
    # Handle datetime objects (pandas Timestamp, datetime, etc.)
    if hasattr(date_val, 'date'):
        try:
            date_str = date_val.date().isoformat()
        except (AttributeError, ValueError):
            pass
    # Ensure it's in YYYY-MM-DD format (first 10 characters)
    if len(date_str) >= 10:
        return date_str[:10]
    return date_str


def _clamp_paid_date_to_created(paid_date, created_date) -> str:
    """
    Clamp a QB paid date upward to the SF invoice's CreatedDate.

    Salesforce's 'Validate Invoice Paid Date' record-triggered flow (BeforeSave)
    rewrites Invoice_Paid_Date__c to CreatedDate whenever the API value is
    earlier — by policy, an invoice cannot be reported as paid before it was
    created. Without this clamp, the sync writes the true QB payment date,
    the flow silently rewrites it, and the same ~1126 invoices get re-flagged
    every full sync (phantom updates).

    Returns '' if paid_date is null/empty (i.e., not yet paid in QB).
    Lexicographic comparison is safe because both sides are YYYY-MM-DD.
    """
    qb = _normalize_date(paid_date)
    if not qb:
        return ''
    sf = _normalize_date(created_date)
    if not sf:
        return qb
    return max(qb, sf)


def process_invoices(invoices: List[Dict], payment_dates: Optional[Dict[str, Optional[str]]] = None) -> pd.DataFrame:
    """
    Process invoice data into a structured format
    
    Args:
        invoices: List of invoice dictionaries from QuickBooks API
        payment_dates: Optional dict mapping invoice_id -> payment_date (YYYY-MM-DD format)
        
    Returns:
        DataFrame with processed invoice data (always has expected columns, even if empty)
    """
    invoice_data = []
    
    print(f"🔄 Processing {len(invoices)} invoices...")
    
    if payment_dates is None:
        payment_dates = {}
    
    for inv in invoices:
        customer_name = _get_customer_vendor_name(inv, 'CustomerRef')
        items_desc = _extract_line_items(inv.get('Line'), 'SalesItemLineDetail')
        balance = float(inv.get('Balance', 0))
        total = float(inv.get('TotalAmt', 0))
        payment_status = _determine_payment_status(balance)
        invoice_id = inv.get('Id', '')
        paid_date = payment_dates.get(invoice_id)

        # Extract P.O. Number from CustomField array (DefinitionId "1")
        qb_po_number = ''
        for cf in inv.get('CustomField', []):
            if cf.get('DefinitionId') == '1':
                qb_po_number = cf.get('StringValue', '')

        invoice_data.append({
            'Type': 'Invoice',
            FIELD_NUMBER: inv.get('DocNumber', ''),
            FIELD_DATE: inv.get('TxnDate', ''),
            FIELD_DUE_DATE: inv.get('DueDate', ''),
            FIELD_CUSTOMER_VENDOR: customer_name,
            FIELD_ITEMS_DESCRIPTION: '\n'.join(items_desc),
            FIELD_TOTAL_AMOUNT: total,
            FIELD_BALANCE_DUE: balance,
            FIELD_PAYMENT_STATUS: payment_status,
            FIELD_QUICKBOOKS_ID: invoice_id,
            'Paid_Date': paid_date if paid_date else None,
            'QB_PO_Number': qb_po_number,
            'SyncToken': inv.get('SyncToken', ''),
        })
    
    print(f"✅ Processed {len(invoice_data)} invoices")
    
    # Log payment date statistics
    invoices_with_paid_dates = sum(1 for item in invoice_data if item.get('Paid_Date'))
    if invoices_with_paid_dates > 0:
        print(f"📅 {invoices_with_paid_dates} invoices have payment dates from QuickBooks")
    
    # Always return DataFrame with expected columns, even if empty
    if invoice_data:
        return pd.DataFrame(invoice_data)
    else:
        # Return empty DataFrame with expected columns
        return pd.DataFrame(columns=[
            'Type', FIELD_NUMBER, FIELD_DATE, FIELD_DUE_DATE, FIELD_CUSTOMER_VENDOR,
            FIELD_ITEMS_DESCRIPTION, FIELD_TOTAL_AMOUNT, FIELD_BALANCE_DUE,
            FIELD_PAYMENT_STATUS, FIELD_QUICKBOOKS_ID, 'Paid_Date',
            'QB_PO_Number', 'SyncToken',
        ])


def process_bills(bills: List[Dict]) -> pd.DataFrame:
    """
    Process bill data into a structured format
    
    Args:
        bills: List of bill dictionaries from QuickBooks API
        
    Returns:
        DataFrame with processed bill data (always has expected columns, even if empty)
    """
    bill_data = []
    
    print(f"🔄 Processing {len(bills)} bills...")
    
    for bill in bills:
        vendor_name = _get_customer_vendor_name(bill, 'VendorRef')
        items_desc = _extract_line_items(bill.get('Line'), 'AccountBasedExpenseLineDetail')
        balance = float(bill.get('Balance', 0))
        total = float(bill.get('TotalAmt', 0))
        payment_status = _determine_payment_status(balance)
        
        bill_data.append({
            'Type': 'Bill',
            FIELD_NUMBER: bill.get('DocNumber', ''),
            FIELD_DATE: bill.get('TxnDate', ''),
            FIELD_DUE_DATE: bill.get('DueDate', ''),
            FIELD_CUSTOMER_VENDOR: vendor_name,
            FIELD_ITEMS_DESCRIPTION: '\n'.join(items_desc),
            FIELD_TOTAL_AMOUNT: total,
            FIELD_BALANCE_DUE: balance,
            FIELD_PAYMENT_STATUS: payment_status,
            FIELD_QUICKBOOKS_ID: bill.get('Id', ''),
            FIELD_PRIVATE_NOTE: bill.get('PrivateNote', '')
        })
    
    print(f"✅ Processed {len(bill_data)} bills")
    
    # Always return DataFrame with expected columns, even if empty
    if bill_data:
        return pd.DataFrame(bill_data)
    else:
        # Return empty DataFrame with expected columns
        return pd.DataFrame(columns=[
            'Type', FIELD_NUMBER, FIELD_DATE, FIELD_DUE_DATE, FIELD_CUSTOMER_VENDOR,
            FIELD_ITEMS_DESCRIPTION, FIELD_TOTAL_AMOUNT, FIELD_BALANCE_DUE,
            FIELD_PAYMENT_STATUS, FIELD_QUICKBOOKS_ID, FIELD_PRIVATE_NOTE
        ])

def sync_po_numbers_to_qb(qb, merged_invoices: pd.DataFrame,
                           batch_size: int = 200, dry_run: bool = False) -> Dict:
    """
    Sync Customer PO Numbers from Salesforce to QuickBooks.

    Compares inscor__Customer_PO_Number__c (SF) with QB_PO_Number (QB CustomField).
    Updates QB invoices where SF has a non-empty PO number that differs from QB.

    Args:
        qb: QuickBooksConnector instance
        merged_invoices: DataFrame with both SF and QB invoice data merged
        batch_size: Maximum number of QB invoices to update per run
        dry_run: If True, log mismatches but don't write to QB

    Returns:
        Dict with keys: synced, skipped, failed, failed_ids
    """
    results = {"synced": 0, "skipped": 0, "failed": 0, "failed_ids": []}

    if 'inscor__Customer_PO_Number__c' not in merged_invoices.columns:
        print("  ℹ️  inscor__Customer_PO_Number__c not in merged data, skipping PO sync")
        return results
    if 'QB_PO_Number' not in merged_invoices.columns:
        print("  ℹ️  QB_PO_Number not in merged data, skipping PO sync")
        return results

    # Find mismatches: SF has a value AND it differs from QB
    df = merged_invoices.copy()
    sf_po = df['inscor__Customer_PO_Number__c'].fillna('').astype(str).str.strip()
    qb_po = df['QB_PO_Number'].fillna('').astype(str).str.strip()
    has_sf_po = sf_po != ''
    differs = sf_po != qb_po
    mismatches = df[has_sf_po & differs]

    total_mismatches = len(mismatches)
    if total_mismatches == 0:
        print("  ✅ All PO numbers already in sync")
        return results

    batch = mismatches.head(batch_size)
    print(f"  📋 Found {total_mismatches} PO number mismatches, processing {len(batch)} this run")

    if dry_run:
        for _, row in batch.iterrows():
            doc = row.get(FIELD_NUMBER, row.get('Name', '?'))
            sf_val = str(row.get('inscor__Customer_PO_Number__c', '')).strip()
            qb_val = str(row.get('QB_PO_Number', '')).strip()
            print(f"    [DRY RUN] {doc}: QB='{qb_val}' → SF='{sf_val}'")
            results["skipped"] += 1
        return results

    for _, row in batch.iterrows():
        qb_id = str(row.get(FIELD_QUICKBOOKS_ID, ''))
        sync_token = str(row.get('SyncToken', ''))
        sf_val = str(row.get('inscor__Customer_PO_Number__c', '')).strip()
        doc = row.get(FIELD_NUMBER, row.get('Name', '?'))

        if not qb_id or not sync_token:
            results["skipped"] += 1
            continue

        success, msg = qb.update_invoice_po_number(qb_id, sync_token, sf_val)

        if not success and msg == "conflict":
            # SyncToken was stale — re-fetch and retry once
            print(f"    ⚠️ {doc}: SyncToken conflict, refetching...")
            fresh = qb.make_api_request(f'invoice/{qb_id}')
            if fresh and 'Invoice' in fresh:
                new_token = fresh['Invoice'].get('SyncToken', '')
                success, msg = qb.update_invoice_po_number(qb_id, new_token, sf_val)

        if success:
            results["synced"] += 1
            print(f"    ✅ {doc}: PO Number → '{sf_val}'")
        else:
            results["failed"] += 1
            results["failed_ids"].append(qb_id)
            print(f"    ❌ {doc}: failed ({msg})")

        time.sleep(0.15)  # Throttle to ~400 req/min (QB limit is 500/min)

    return results


def main(qb_credentials: Dict, sf_credentials: Dict, context=None, force_full_sync=False):
    """
    Main sync logic - fetches data from QuickBooks and updates Salesforce

    Args:
        qb_credentials: QuickBooks OAuth credentials from Secrets Manager
        sf_credentials: Salesforce login credentials from Secrets Manager
        context: Lambda context object (optional, for system info collection)
        force_full_sync: If True, skip incremental timestamp and do a full sync
    """
    start_time = time.time()
    
    print("\n" + "="*70)
    print("🔄 STARTING QUICKBOOKS-AVSIGHT SYNC")
    print("="*70)
    
    # Initialize connectors
    print("\n📡 Initializing connectors...")

    # Persist rotated QB tokens the instant they're refreshed. QuickBooks
    # invalidates the old refresh token shortly after issuing a new one, so
    # deferring the save to the end of main() risks stranding a dead token in
    # Secrets Manager if anything downstream throws (the 6/12 outage failure mode).
    def _persist_qb_tokens(new_tokens: Dict) -> None:
        credentials = {
            'client_id': new_tokens['client_id'],
            'client_secret': new_tokens['client_secret'],
            'access_token': new_tokens['access_token'],
            'refresh_token': new_tokens['refresh_token'],
            'realm_id': new_tokens['realm_id'],
            'environment': new_tokens['environment'],
            'redirect_uri': qb_credentials.get('redirect_uri', get_qb_redirect_uri()),
            'updated_at': new_tokens.get('updated_at', datetime.now().isoformat()),
        }
        update_secret('quickbooks/credentials', credentials)
        print("  💾 Rotated QuickBooks tokens persisted to Secrets Manager")

    qb = QuickBooksConnector(qb_credentials, on_token_refresh=_persist_qb_tokens)
    sf = SalesforceConnector(sf_credentials)
    sf.login()
    
    # Check if incremental sync is enabled
    enable_incremental = get_enable_incremental_sync()
    last_run_timestamp = None
    
    if force_full_sync:
        print("\n📥 FORCED FULL SYNC - ignoring incremental timestamp")
        enable_incremental = False

    if enable_incremental:
        print("\n🔄 Incremental sync enabled - checking for last run timestamp...")
        last_run_timestamp = get_last_run_timestamp()
        if last_run_timestamp:
            print(f"  Found last run timestamp: {last_run_timestamp.isoformat()}")
            print("  Will only fetch records modified since this time")
        else:
            print("  No previous timestamp found - fetching all records (first run)")
    else:
        print("\n📥 Full sync mode - fetching all records")
    
    # Fetch invoices and bills (with optional incremental filtering)
    invoices_raw = qb.get_all_invoices(last_modified_since=last_run_timestamp)
    
    # Get payment dates for invoices
    invoice_ids = [inv.get('Id') for inv in invoices_raw if inv.get('Id')]
    payment_dates = {}
    if invoice_ids:
        payment_dates = qb.get_payments_for_invoices(invoice_ids, invoices_raw)
    
    # Process invoices with payment dates
    invoices_df = process_invoices(invoices_raw, payment_dates=payment_dates)
    bills_df = process_bills(qb.get_all_bills(last_modified_since=last_run_timestamp))

    # Display summary
    print("\n" + "="*70)
    print("📊 FINANCIAL SUMMARY")
    print("="*70)

    if not invoices_df.empty:
        paid_invoices = invoices_df[invoices_df[FIELD_PAYMENT_STATUS] == 'Paid']
        unpaid_invoices = invoices_df[invoices_df[FIELD_PAYMENT_STATUS] == 'Unpaid']
        
        print("\n💰 INVOICES (Money Coming In):")
        print(f"  Total Invoices: {len(invoices_df)}")
        print(f"  Paid Invoices: {len(paid_invoices)}")
        print(f"  Unpaid Invoices: {len(unpaid_invoices)}")
        print(f"  Total Invoice Amount: ${invoices_df[FIELD_TOTAL_AMOUNT].sum():,.2f}")
        print(f"  Outstanding Receivables: ${invoices_df[FIELD_BALANCE_DUE].sum():,.2f}")

    if not bills_df.empty:
        paid_bills = bills_df[bills_df[FIELD_PAYMENT_STATUS] == 'Paid']
        unpaid_bills = bills_df[bills_df[FIELD_PAYMENT_STATUS] == 'Unpaid']
        
        print("\n💸 BILLS (Money Going Out):")
        print(f"  Total Bills: {len(bills_df)}")
        print(f"  Paid Bills: {len(paid_bills)}")
        print(f"  Unpaid Bills: {len(unpaid_bills)}")
        print(f"  Total Bill Amount: ${bills_df[FIELD_TOTAL_AMOUNT].sum():,.2f}")
        print(f"  Outstanding Payables: ${bills_df[FIELD_BALANCE_DUE].sum():,.2f}")

    if not invoices_df.empty and not bills_df.empty:
        print("\n📈 NET POSITION:")
        net_position = invoices_df[FIELD_TOTAL_AMOUNT].sum() - bills_df[FIELD_TOTAL_AMOUNT].sum()
        net_outstanding = invoices_df[FIELD_BALANCE_DUE].sum() - bills_df[FIELD_BALANCE_DUE].sum()
        print(f"  Net Total (Invoices - Bills): ${net_position:,.2f}")
        print(f"  Net Outstanding (Receivables - Payables): ${net_outstanding:,.2f}")

    print("\n" + "="*70)
    
    # Export all data to CSV files
    print("📁 Exporting to CSV files...")

    try:
        invoices_df.to_csv(f'{get_results_directory()}/quickbooks_invoices.csv', index=False)
        print("✅ Invoices exported to quickbooks_invoices.csv")
    except Exception as e:
        print(f"⚠️ Failed to export invoices CSV: {e}")

    try:
        bills_df.to_csv(f'{get_results_directory()}/quickbooks_bills.csv', index=False)
        print("✅ Bills exported to quickbooks_bills.csv")
    except Exception as e:
        print(f"⚠️ Failed to export bills CSV: {e}")

    # Unpaid items reports
    if not invoices_df.empty:
        unpaid_invoices = invoices_df[invoices_df[FIELD_PAYMENT_STATUS] == 'Unpaid']
        if not unpaid_invoices.empty:
            try:
                unpaid_invoices.to_csv(f'{get_results_directory()}/unpaid_invoices.csv', index=False)
                print(f"📝 {len(unpaid_invoices)} unpaid invoices exported to unpaid_invoices.csv")
            except Exception as e:
                print(f"⚠️ Failed to export unpaid invoices CSV: {e}")

    if not bills_df.empty:
        unpaid_bills = bills_df[bills_df[FIELD_PAYMENT_STATUS] == 'Unpaid']
        if not unpaid_bills.empty:
            try:
                unpaid_bills.to_csv(f'{get_results_directory()}/unpaid_bills.csv', index=False)
                print(f"📝 {len(unpaid_bills)} unpaid bills exported to unpaid_bills.csv")
            except Exception as e:
                print(f"⚠️ Failed to export unpaid bills CSV: {e}")

    print("\n✅ All exports complete!")
    
    # Check if we have any data to process
    has_bills = not bills_df.empty and FIELD_ITEMS_DESCRIPTION in bills_df.columns
    has_invoices = not invoices_df.empty and FIELD_NUMBER in invoices_df.columns
    has_data_to_process = has_bills or has_invoices
    po_sync_results = {"synced": 0, "skipped": 0, "failed": 0, "failed_ids": []}
    
    if not has_data_to_process:
        print("\nℹ️ No bills or invoices to process - skipping Salesforce data fetch")
        # Create empty DataFrames for downstream processing
        bills_update = pd.DataFrame()
        bills_insert = pd.DataFrame()
        bills_update_data = []
        bills_insert_data = []
        invoices_updated = []
        pay = pd.DataFrame()
        po = pd.DataFrame()
        ro = pd.DataFrame()
        invc = pd.DataFrame()
        acc = pd.DataFrame()
        vendor_dict = {}
        po_dict = {}
        ro_dict = {}
        acc_dict = {}
        invc_dict = {}
        pay_dict = {}
    else:
        # Extract Order number from Items/Description (only if bills_df is not empty)
        if has_bills:
            # Line descriptions are the primary source; the bill-level memo
            # (QB "PrivateNote") is the fallback — some AP-entered bills carry
            # the RO/PO reference only there.
            order_from_desc = bills_df[FIELD_ITEMS_DESCRIPTION].apply(find_order_number)
            if FIELD_PRIVATE_NOTE in bills_df.columns:
                order_from_note = bills_df[FIELD_PRIVATE_NOTE].apply(find_order_number)
                bills_df[FIELD_ORDER] = order_from_desc.combine_first(order_from_note)
            else:
                bills_df[FIELD_ORDER] = order_from_desc
        else:
            # Create empty Order column if bills_df is empty
            bills_df[FIELD_ORDER] = None

        # Import existing Salesforce records and create lookup dictionaries
        print("\n📥 Fetching Salesforce data...")
        
        pay = sf.get_all_fields('Payment__c')
        po = sf.get_all_fields('inscor__Purchase_Order__c')
        ro = sf.get_all_fields('inscor__Repair_Order__c')
        invc = sf.get_all_fields('inscor__Invoice__c')
        acc = sf.soql_to_df("SELECT Id, Name FROM Account")

        # Create lookup dictionaries (snake_case naming per PEP 8)
        vendor_dict = pd.concat([po[['Id', 'inscor__Vendor__c']], ro[['Id', 'inscor__Vendor__c']]])
        vendor_dict = dict(zip(vendor_dict.Id, vendor_dict.inscor__Vendor__c))
        po_dict = dict(zip(po.Name, po.Id))
        ro_dict = dict(zip(ro.Name, ro.Id))
        acc_dict = dict(zip(acc.Name, acc.Id))
        
        # Dictionaries for email hyperlinks
        invc_dict = dict(zip(invc.Id, invc.Name))
        pay_dict = dict(zip(pay.Id, pay.Name))
        
        # Reverse account dictionary to look up Account names from IDs
        acc_dict_reverse = dict(zip(acc.Id, acc.Name))

        
        # Format bills for Salesforce upload (only if bills_df is not empty)
        if has_bills:
            bills_df['Repair_Order__c'] = bills_df[FIELD_ORDER].map(ro_dict)
            bills_df['Purchase_Order__c'] = bills_df[FIELD_ORDER].map(po_dict)
            bills_df['Order__c'] = bills_df[FIELD_ORDER]
            bills_df['Account'] = bills_df[FIELD_CUSTOMER_VENDOR].apply(lambda x: x.replace("-V", ""))
            bills_df['Account__c'] = (bills_df.Purchase_Order__c.map(vendor_dict)
                                     .combine_first(bills_df.Repair_Order__c.map(vendor_dict))
                                     .combine_first(bills_df.Account.map(acc_dict)))
            bills_df['QBO_Bill_ID__c'] = bills_df[FIELD_QUICKBOOKS_ID]
            # Payment__c.Memo__c is a 512-char textarea; QB descriptions can be
            # longer and un-truncated values fail the whole record with
            # STRING_TOO_LONG (and would re-fail on every memo-change update).
            bills_df['Memo__c'] = bills_df[FIELD_ITEMS_DESCRIPTION].fillna('').astype(str).str.slice(0, 512)
            bills_df['Bill_Date__c'] = bills_df[FIELD_DATE]
            bills_df['Due_Date__c'] = bills_df[FIELD_DUE_DATE]
            bills_df['Total_Amount__c'] = bills_df[FIELD_TOTAL_AMOUNT]
            bills_df['Balance_Due__c'] = bills_df[FIELD_BALANCE_DUE]
            
            bills = bills_df[['Repair_Order__c', 'Purchase_Order__c', 'Order__c', 'Account__c',
                              'QBO_Bill_ID__c', 'Memo__c', 'Total_Amount__c', 'Balance_Due__c',
                              'Bill_Date__c', 'Due_Date__c']]
        else:
            # Create empty bills DataFrame with expected columns
            bills = pd.DataFrame(columns=['Repair_Order__c', 'Purchase_Order__c', 'Order__c', 'Account__c',
                                          'QBO_Bill_ID__c', 'Memo__c', 'Total_Amount__c', 'Balance_Due__c',
                                          'Bill_Date__c', 'Due_Date__c'])
            print("ℹ️ No bills to process (empty DataFrame)")
        
        # Check bills against existing pay records using QBO_Bill_ID__c as a key
        if not bills.empty and 'QBO_Bill_ID__c' in bills.columns:
            bills_update = bills.merge(pay, on='QBO_Bill_ID__c', suffixes=('', '_pay'))
        else:
            bills_update = pd.DataFrame()

        # Filter bills that need an update. Balance/total changes were the
        # original trigger; memo and order changes are included because
        # AP-automation bills arrive in QB with no line descriptions — the
        # "RO-xxxx"/"PO-xxxx" voucher text is added later, usually with no
        # balance change (the bill is entered at its final/paid balance).
        # Without these triggers such Payments kept a blank Memo__c/Order__c
        # forever (root cause of the Jan 2026 Order__c gap).
        if not bills_update.empty and 'Balance_Due__c' in bills_update.columns and 'Total_Amount__c' in bills_update.columns:
            amount_changed = ((bills_update.Balance_Due__c != bills_update.Balance_Due__c_pay) |
                              (bills_update.Total_Amount__c != bills_update.Total_Amount__c_pay))
            memo_changed = (bills_update.Memo__c.fillna('').astype(str)
                            != bills_update.Memo__c_pay.fillna('').astype(str))
            # Fill-only: derive Order for records that don't have one yet;
            # never overwrite or blank an existing Order__c (may be manually set).
            order_fillable = ((bills_update.Order__c.fillna('').astype(str) != '') &
                              (bills_update.Order__c_pay.fillna('').astype(str) == ''))
            mask = amount_changed | memo_changed | order_fillable
            bills_update = bills_update[mask][['Id', 'Balance_Due__c', 'Total_Amount__c',
                                               'QBO_Bill_ID__c', 'Due_Date__c', 'Bill_Date__c', 'Account__c', 'Memo__c',
                                               'Order__c', 'Repair_Order__c', 'Purchase_Order__c', 'Order__c_pay']]
            bills_update_data = []
            for rec in bills_update.fillna('').to_dict(orient='records'):
                prior_order = rec.pop('Order__c_pay', '')
                if prior_order or not rec.get('Order__c'):
                    rec.pop('Order__c', None)
                    rec.pop('Repair_Order__c', None)
                    rec.pop('Purchase_Order__c', None)
                else:
                    # Drop unresolved lookups rather than blanking them in SF
                    if not rec.get('Repair_Order__c'):
                        rec.pop('Repair_Order__c', None)
                    if not rec.get('Purchase_Order__c'):
                        rec.pop('Purchase_Order__c', None)
                bills_update_data.append(rec)
        else:
            bills_update = pd.DataFrame()
            bills_update_data = []
        
        try:
            if not bills_update.empty:
                bills_update.to_csv(f"{get_results_directory()}/{exact_time()}_bills_update.csv", index=False)
        except Exception as e:
            print(f"⚠️ Failed to export bills update CSV: {e}")

        # Filter bills that did not match existing records
        if not bills.empty and 'QBO_Bill_ID__c' in bills.columns and not pay.empty and 'QBO_Bill_ID__c' in pay.columns:
            bills_insert = bills[~bills.QBO_Bill_ID__c.isin(pay.QBO_Bill_ID__c)]
            bills_insert_data = bills_insert.fillna('').to_dict(orient='records')
        else:
            bills_insert = pd.DataFrame()
            bills_insert_data = []
        
        try:
            if not bills_insert.empty:
                bills_insert.to_csv(f"{get_results_directory()}/{exact_time()}_bills_insert.csv", index=False)
        except Exception as e:
            print(f"⚠️ Failed to export bills insert CSV: {e}")

        # Process invoices
        if has_invoices and not invc.empty and 'Name' in invc.columns:
            invoices = invoices_df.merge(invc, left_on=FIELD_NUMBER, right_on="Name")

            # Clamp QB paid dates to SF CreatedDate — SF's 'Validate Invoice Paid Date'
            # flow rewrites any earlier value, so writing un-clamped dates produced
            # ~1126 phantom updates per day. See _clamp_paid_date_to_created.
            if 'Paid_Date' in invoices.columns and 'CreatedDate' in invoices.columns:
                original = invoices['Paid_Date'].apply(_normalize_date)
                clamped = [
                    _clamp_paid_date_to_created(p, c)
                    for p, c in zip(invoices['Paid_Date'], invoices['CreatedDate'])
                ]
                clamped_count = sum(1 for o, n in zip(original, clamped) if o and o != n)
                invoices['Paid_Date'] = clamped
                invoices.loc[invoices['Paid_Date'] == '', 'Paid_Date'] = None
                if clamped_count > 0:
                    print(f"📅 Clamped {clamped_count} QB paid dates up to SF CreatedDate "
                          f"(policy: paid_date >= created_date)")

            # Sync PO Numbers from SF → QB (before balance/paid-date change detection)
            po_sync_results = {"synced": 0, "skipped": 0, "failed": 0, "failed_ids": []}
            if get_po_sync_enabled() and not invoices.empty and 'inscor__Customer_PO_Number__c' in invoices.columns:
                print("\n" + "="*70)
                print("📋 PO NUMBER SYNC (SF → QB)")
                print("="*70)
                po_sync_results = sync_po_numbers_to_qb(
                    qb, invoices, batch_size=get_po_sync_batch_size())
                print(f"  📊 Results: {po_sync_results['synced']} synced, "
                      f"{po_sync_results['skipped']} skipped, {po_sync_results['failed']} failed")

            if not invoices.empty:
                invoices['Previous Balance'] = invoices.Invoice_Balance__c

                # Check for balance changes
                balance_changed = invoices[FIELD_BALANCE_DUE] != invoices['Invoice_Balance__c']
                
                # Check for paid date changes
                paid_date_changed = pd.Series([False] * len(invoices), index=invoices.index)
                
                if 'Paid_Date' in invoices.columns and 'Invoice_Paid_Date__c' in invoices.columns:
                    # Normalize both dates to YYYY-MM-DD format before comparison
                    # This handles cases where Salesforce returns datetime strings like "2024-01-15T00:00:00.000Z"
                    # while QuickBooks returns simple date strings like "2024-01-15"
                    qb_paid_date = invoices['Paid_Date'].apply(_normalize_date)
                    sf_paid_date = invoices['Invoice_Paid_Date__c'].apply(_normalize_date)
                    
                    # Handle empty strings and None consistently - both should be treated as "no date"
                    # Convert empty strings to None for proper comparison
                    qb_paid_date_normalized = qb_paid_date.replace('', pd.NA)
                    sf_paid_date_normalized = sf_paid_date.replace('', pd.NA)
                    
                    # Compare dates, treating None/empty/NA as equal
                    # Only mark as changed if dates are different AND at least one is not null
                    paid_date_changed = pd.Series([False] * len(invoices), index=invoices.index)
                    for idx in invoices.index:
                        qb_val = qb_paid_date_normalized.loc[idx]
                        sf_val = sf_paid_date_normalized.loc[idx]
                        # Both are null/empty -> no change
                        if pd.isna(qb_val) and pd.isna(sf_val):
                            paid_date_changed.loc[idx] = False
                        # One is null, other is not -> change
                        elif pd.isna(qb_val) != pd.isna(sf_val):
                            paid_date_changed.loc[idx] = True
                        # Both have values -> compare
                        else:
                            try:
                                # Parse dates and compare with 1-day tolerance for timezone issues
                                from datetime import datetime as dt
                                qb_date = dt.strptime(qb_val, '%Y-%m-%d').date() if qb_val else None
                                sf_date = dt.strptime(sf_val, '%Y-%m-%d').date() if sf_val else None
                                
                                if qb_date and sf_date:
                                    date_diff = abs((qb_date - sf_date).days)
                                    paid_date_changed.loc[idx] = (date_diff > 1)
                                else:
                                    paid_date_changed.loc[idx] = (qb_val != sf_val)
                            except (ValueError, TypeError):
                                paid_date_changed.loc[idx] = (qb_val != sf_val)
                    
                    # Log statistics about paid date changes
                    if paid_date_changed.any():
                        print(f"\n📅 Paid Date Comparison:")
                        print(f"  {paid_date_changed.sum()} invoices have paid date changes detected")
                        # Log sample invoices with paid date changes
                        changed_invoices = invoices[paid_date_changed]
                        if not changed_invoices.empty and FIELD_NUMBER in changed_invoices.columns:
                            print(f"  Sample invoices with paid date changes:")
                            for idx, row in changed_invoices.head(5).iterrows():
                                qb_date = qb_paid_date.loc[idx]
                                sf_date = sf_paid_date.loc[idx]
                                print(f"    {row.get(FIELD_NUMBER, 'Unknown')}: QB='{qb_date}' vs SF='{sf_date}'")
                elif 'Paid_Date' in invoices.columns:
                    # QuickBooks has paid date but Salesforce doesn't -> changed
                    paid_date_changed = invoices['Paid_Date'].notna()
                    if paid_date_changed.any():
                        print(f"\n📅 Paid Date Comparison:")
                        print(f"  ⚠️ Invoice_Paid_Date__c field missing from Salesforce data")
                        print(f"  QuickBooks has paid dates for {paid_date_changed.sum()} invoices")
                
                # Filter invoices where balance OR paid date has changed
                invoices_to_update = balance_changed | paid_date_changed
                
                # Log statistics about what triggered the updates
                if invoices_to_update.any():
                    balance_only = (~paid_date_changed & balance_changed).sum()
                    paid_date_only = (paid_date_changed & ~balance_changed).sum()
                    both_changed = (paid_date_changed & balance_changed).sum()
                    total_to_update = invoices_to_update.sum()
                    print(f"\n📊 Invoice update breakdown:")
                    print(f"  Total invoices to update: {total_to_update}")
                    print(f"  Balance changed only: {balance_only}")
                    print(f"  Paid date changed only: {paid_date_only}")
                    print(f"  Both balance and paid date changed: {both_changed}")
                else:
                    print(f"\n📊 Invoice update breakdown:")
                    print(f"  No invoices need updating")
                
                invoices = invoices[invoices_to_update].sort_values(FIELD_DATE)
                
                if not invoices.empty:
                    # Include Paid_Date and Invoice_Paid_Date__c in the columns being processed
                    columns_to_select = [FIELD_DATE, 'Name', 'Id', FIELD_BALANCE_DUE, 'Invoice_Balance__c',
                                        'Previous Balance', FIELD_PAYMENT_STATUS, 'inscor__Status__c', FIELD_QUICKBOOKS_ID]
                    if 'Paid_Date' in invoices.columns:
                        columns_to_select.append('Paid_Date')
                    if 'Invoice_Paid_Date__c' in invoices.columns:
                        columns_to_select.append('Invoice_Paid_Date__c')
                    invoices = invoices[columns_to_select]
                    
                    invoices['Invoice_Balance__c'] = invoices[FIELD_BALANCE_DUE]
                    invoices['inscorqb__QuickBooks_Id__c'] = invoices[FIELD_QUICKBOOKS_ID]

                    # Fix invoice status
                    invoices.loc[invoices.Invoice_Balance__c == 0, 'inscor__Status__c'] = 'Paid'
                    invoices.loc[invoices.Invoice_Balance__c > 0, 'inscor__Status__c'] = 'Sent'
                    
                    # Map Paid_Date to Salesforce field
                    # Set Invoice_Paid_Date__c from QuickBooks Paid_Date (normalized to YYYY-MM-DD format)
                    # May be None/NaN to clear Salesforce value
                    if 'Paid_Date' in invoices.columns:
                        # Normalize the date to ensure consistent YYYY-MM-DD format for Salesforce
                        invoices['Invoice_Paid_Date__c'] = invoices['Paid_Date'].apply(_normalize_date)
                        # Convert empty strings back to None for Salesforce (empty string != None in Salesforce)
                        invoices.loc[invoices['Invoice_Paid_Date__c'] == '', 'Invoice_Paid_Date__c'] = None
                        # Log payment dates being sent to Salesforce
                        invoices_with_paid_dates = invoices[invoices['Invoice_Paid_Date__c'].notna()]
                        invoices_clearing_dates = invoices[invoices['Invoice_Paid_Date__c'].isna()]
                        if not invoices_with_paid_dates.empty:
                            print(f"\n📅 Payment dates to be updated in Salesforce ({len(invoices_with_paid_dates)} invoices):")
                            for idx, row in invoices_with_paid_dates.head(10).iterrows():
                                print(f"  Invoice {row.get('Name', 'Unknown')} (ID: {row.get('Id', 'Unknown')}): Paid Date = {row.get('Invoice_Paid_Date__c', 'N/A')}")
                        if not invoices_clearing_dates.empty:
                            print(f"\n🗑️  Payment dates to be cleared in Salesforce ({len(invoices_clearing_dates)} invoices):")
                            for idx, row in invoices_clearing_dates.head(10).iterrows():
                                print(f"  Invoice {row.get('Name', 'Unknown')} (ID: {row.get('Id', 'Unknown')}): Clearing paid date")
                    elif 'Invoice_Paid_Date__c' in invoices.columns:
                        # QuickBooks doesn't have Paid_Date but Salesforce does - clear it
                        # This happens when we detected a paid date change where SF has a value but QB doesn't
                        invoices['Invoice_Paid_Date__c'] = None
                    
                    # Include 'inscor__Account__c' for better identification in emails
                    # Note: 'Name' field is read-only in Salesforce, so we exclude it from updates
                    # Check if inscor__Account__c exists in the merged invoices DataFrame
                    invoice_columns = ['Id', 'Invoice_Balance__c', 'inscor__Status__c', 'inscorqb__QuickBooks_Id__c']
                    if 'Invoice_Paid_Date__c' in invoices.columns:
                        invoice_columns.append('Invoice_Paid_Date__c')
                    if 'inscor__Account__c' in invoices.columns:
                        invoice_columns.append('inscor__Account__c')
                    invoices = invoices[invoice_columns]
                    invoices_updated = invoices.to_dict(orient='records')
                else:
                    invoices_updated = []
            else:
                invoices_updated = []
        else:
            invoices = pd.DataFrame()
            invoices_updated = []
    
    results_dir = get_results_directory()
    batch_size = get_salesforce_batch_size()
    
    try:
        if 'invoices' in locals() and not invoices.empty:
            invoices.to_csv(f"{results_dir}/{exact_time()}_invoices.csv", index=False)
    except Exception as e:
        print(f"⚠️ Failed to export invoices CSV: {e}")
    
    # Send data to Salesforce
    if len(invoices_updated) > 0:
        results = sf.sf.bulk.inscor__Invoice__c.update(invoices_updated, batch_size=batch_size)
        _log_bulk_results("invoices_update", results, invoices_updated)
        _upload_bulk_results_to_s3("invoices_update", results)
        try:
            pd.DataFrame(results).to_csv(f"{results_dir}/{exact_time()}_invoices_RESULTS.csv", index=False)
        except Exception as e:
            print(f"⚠️ Failed to export invoice results CSV: {e}")

    if len(bills_update_data) > 0:
        results = sf.sf.bulk.Payment__c.update(bills_update_data, batch_size=batch_size)
        _log_bulk_results("bills_update", results, bills_update_data)
        _upload_bulk_results_to_s3("bills_update", results)
        try:
            pd.DataFrame(results).to_csv(f"{results_dir}/{exact_time()}_bill_update_RESULTS.csv", index=False)
        except Exception as e:
            print(f"⚠️ Failed to export bill update results CSV: {e}")
    
    # Initialize metadata dictionaries
    bills_insert_names = {}
    bills_insert_memos = {}
    bills_insert_account_names = {}
    bills_insert_sf_ids = {}  # Maps QBO_Bill_ID__c to Salesforce Id
    bills_update_names = {}
    bills_update_account_names = {}
    invoices_account_names = {}
    
    if len(bills_insert_data) > 0:
        results = sf.sf.bulk.Payment__c.insert(bills_insert_data, batch_size=batch_size)
        _log_bulk_results("bills_insert", results, bills_insert_data)
        _upload_bulk_results_to_s3("bills_insert", results)
        try:
            pd.DataFrame(results).to_csv(f"{results_dir}/{exact_time()}_bill_insert_RESULTS.csv", index=False)
        except Exception as e:
            print(f"⚠️ Failed to export bill insert results CSV: {e}")
        
        # Extract successful record IDs from bulk insert results and create QBO_ID to Salesforce ID mapping
        inserted_ids = []
        qbo_id_to_sf_id = {}  # Maps QBO_Bill_ID__c to Salesforce Id
        for i, r in enumerate(results):
            if isinstance(r, dict) and r.get('success') and r.get('Id'):
                sf_id = r['Id']
                inserted_ids.append(sf_id)
                # Match by position (bulk insert preserves order)
                if i < len(bills_insert_data):
                    qbo_id = bills_insert_data[i].get('QBO_Bill_ID__c', '')
                    if qbo_id:
                        qbo_id_to_sf_id[qbo_id] = sf_id
        
        # Query Salesforce to get Names, Memo__c, and Account__c for inserted bills
        if inserted_ids:
            try:
                # Quote IDs for SOQL query
                id_list = "','".join(inserted_ids)
                inserted_bills = sf.soql_to_df(f"SELECT Id, Name, Memo__c, Account__c FROM Payment__c WHERE Id IN ('{id_list}')")
                
                # Create mappings keyed by Salesforce ID
                bills_insert_names_by_id = dict(zip(inserted_bills.Id, inserted_bills.Name.fillna('')))
                bills_insert_memos_by_id = dict(zip(inserted_bills.Id, inserted_bills.Memo__c.fillna('')))
                bills_insert_account_ids_by_id = dict(zip(inserted_bills.Id, inserted_bills.Account__c.fillna('')))
                bills_insert_account_names_by_id = {bid: acc_dict_reverse.get(aid, '') for bid, aid in bills_insert_account_ids_by_id.items()}
                
                # Also create mappings keyed by QBO_Bill_ID__c for easier lookup in email generation
                bills_insert_names = {qbo_id: bills_insert_names_by_id.get(sf_id, '') for qbo_id, sf_id in qbo_id_to_sf_id.items()}
                bills_insert_memos = {qbo_id: bills_insert_memos_by_id.get(sf_id, '') for qbo_id, sf_id in qbo_id_to_sf_id.items()}
                bills_insert_account_names = {qbo_id: bills_insert_account_names_by_id.get(sf_id, '') for qbo_id, sf_id in qbo_id_to_sf_id.items()}
                
                # Also store Salesforce IDs mapping for email generation
                bills_insert_sf_ids = qbo_id_to_sf_id
            except Exception as e:
                print(f"⚠️ Failed to query inserted bills for metadata: {e}")
                import traceback
                traceback.print_exc()
                bills_insert_sf_ids = {}
    
    else:
        print(f"\nℹ️ No new bills to insert")
    # Create metadata for updated bills
    if len(bills_update_data) > 0:
        bills_update_names = {row['Id']: pay_dict.get(row['Id'], '') for row in bills_update_data}
        bills_update_account_ids = {row['Id']: row.get('Account__c', '') for row in bills_update_data}
        bills_update_account_names = {bid: acc_dict_reverse.get(aid, '') for bid, aid in bills_update_account_ids.items()}
    
    # Create metadata for invoices
    if len(invoices_updated) > 0:
        invoices_account_ids = {row['Id']: row.get('inscor__Account__c', '') for row in invoices_updated}
        invoices_account_names = {iid: acc_dict_reverse.get(aid, '') for iid, aid in invoices_account_ids.items()}
    
    end_time = time.time()
    execution_time = end_time - start_time
    execution_time = format_time(execution_time)
    
    # Save summary to S3 for end-of-day email
    print("\n" + "="*70)
    print("💾 SAVING DAILY SUMMARY TO S3")
    print("="*70)
    
    run_timestamp = exact_time()
    sync_type = 'incremental' if enable_incremental and last_run_timestamp else 'full'
    if save_daily_summary_to_s3(bills_update_data, bills_insert_data, invoices_updated,
                                 bills_insert_sf_ids,
                                 execution_time, run_timestamp, context=context,
                                 sync_type=sync_type):
        print("✅ Daily summary saved to S3 successfully!")
        print(f"   Run timestamp: {run_timestamp}")
        print("   Summary will be included in end-of-day email")
    else:
        print("⚠️ Failed to save daily summary to S3, but sync completed successfully")
    
    # Send immediate run summary email
    print("\n" + "="*70)
    print("📧 SENDING RUN SUMMARY EMAIL")
    print("="*70)
    
    from utils import send_email_summary
    invoice_dict = {
        'total': len(invoices_df),
        'paid': len(invoices_df[invoices_df[FIELD_PAYMENT_STATUS] == 'Paid']) if not invoices_df.empty else 0,
        'unpaid': len(invoices_df[invoices_df[FIELD_PAYMENT_STATUS] == 'Unpaid']) if not invoices_df.empty else 0
    }
    payment_dict = {
        'total': len(bills_df),
        'paid': len(bills_df[bills_df[FIELD_PAYMENT_STATUS] == 'Paid']) if not bills_df.empty else 0,
        'unpaid': len(bills_df[bills_df[FIELD_PAYMENT_STATUS] == 'Unpaid']) if not bills_df.empty else 0
    }
    
    # Determine sync type and get counts
    sync_type = 'incremental' if enable_incremental and last_run_timestamp else 'full'
    invoices_fetched = len(invoices_df) if not invoices_df.empty else 0
    bills_fetched = len(bills_df) if not bills_df.empty else 0
    
    if send_email_summary(bills_update, bills_insert, invoices_updated,
                         execution_time=execution_time,
                         invoice_dict=invoice_dict, payment_dict=payment_dict,
                         context=context, sync_type=sync_type,
                         last_run_timestamp=last_run_timestamp,
                         invoices_fetched=invoices_fetched,
                         bills_fetched=bills_fetched,
                         po_sync_results=po_sync_results):
        print("✅ Run summary email sent successfully!")
    else:
        print("⚠️ Failed to send run summary email, but sync completed successfully")
        
    print("\n" + "="*70)
    print("✅ QUICKBOOKS SYNC COMPLETE")
    print("="*70)
    
    # Save current run timestamp if incremental sync is enabled
    if enable_incremental:
        print("\n💾 Saving current run timestamp for next incremental sync...")
        current_timestamp = datetime.now(timezone.utc)
        if save_last_run_timestamp(current_timestamp):
            print(f"  ✅ Timestamp saved: {current_timestamp.isoformat()}")
        else:
            print("  ⚠️ Failed to save timestamp, but sync completed successfully")
    
    if hasattr(qb, '_tokens_refreshed') and qb._tokens_refreshed:
        print("\n🔄 Updating QuickBooks tokens in Secrets Manager...")
        new_credentials = {
            'client_id': qb.client_id,
            'client_secret': qb.client_secret,
            'access_token': qb.access_token,
            'refresh_token': qb.refresh_token,
            'realm_id': qb.realm_id,
            'environment': qb.environment,
            'redirect_uri': qb_credentials.get('redirect_uri', get_qb_redirect_uri()),
            'updated_at': datetime.now().isoformat()
        }
        update_secret('quickbooks/credentials', new_credentials)
        



def lambda_handler(event, context):
    """
    AWS Lambda entry point - called by EventBridge scheduler
    
    Args:
        event: EventBridge event data
        context: Lambda context object
        
    Returns:
        Response dictionary with status code and body
    """
    print("="*70)
    print(f"Lambda invoked: {datetime.now().isoformat()}")
    print("="*70)
    
    try:
        # Check sync_mode from EventBridge event payload
        sync_mode = event.get('sync_mode', 'incremental') if event else 'incremental'
        force_full_sync = sync_mode == 'full'
        print(f"📋 Event sync_mode: {sync_mode}, force_full_sync: {force_full_sync}")

        # Fetch credentials from AWS Secrets Manager
        print("\n🔐 Retrieving credentials from Secrets Manager...")
        qb_creds = get_secret('quickbooks/credentials')
        sf_creds = get_secret('salesforce/credentials')

        # Run the main sync
        main(qb_creds, sf_creds, context=context, force_full_sync=force_full_sync)
        
        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': 'QuickBooks-AvSight sync completed successfully',
                'timestamp': datetime.now().isoformat()
            })
        }
        
    except Exception as e:
        print(f"\n❌ SYNC FAILED: {str(e)}")

        import traceback
        traceback.print_exc()

        # Alert (once/day) when the failure is a dead QuickBooks refresh token —
        # this silently stalls all syncs until someone re-authenticates.
        error_text = str(e)
        if 'refresh token' in error_text.lower() or 'invalid_grant' in error_text.lower():
            try:
                send_auth_failure_alert(error_text)
            except Exception as alert_err:
                print(f"⚠️ Failed to dispatch auth-failure alert: {alert_err}")

        # Return 200 to prevent Lambda retry (avoid duplicate syncs)
        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': 'Sync failed',
                'error': str(e),
                'timestamp': datetime.now().isoformat()
            })
        }


# For local testing
if __name__ == "__main__":
    print("⚠️  Running in local test mode")
    print("Make sure you have AWS credentials configured")
    lambda_handler({}, None)
    
    
