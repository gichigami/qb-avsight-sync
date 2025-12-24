"""
AWS Lambda Function: QuickBooks-AvSight Sync
Syncs invoice and bill data between QuickBooks Online and Salesforce AvSight

This function is triggered by EventBridge (CloudWatch Events) on a schedule
"""

import json
import time
import pandas as pd
from datetime import datetime, timezone
from typing import Dict, List, Optional

# Local imports
from quickbooks_connector import QuickBooksConnector
from salesforce_connector import SalesforceConnector
from utils import (
    get_secret, update_secret, format_time, 
    exact_time, find_order_number, save_daily_summary_to_s3,
    get_last_run_timestamp, save_last_run_timestamp
)
from config import (
    get_salesforce_batch_size, get_results_directory, 
    get_qb_redirect_uri, get_email_recipients,
    get_enable_incremental_sync
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


def process_invoices(invoices: List[Dict]) -> pd.DataFrame:
    """
    Process invoice data into a structured format
    
    Args:
        invoices: List of invoice dictionaries from QuickBooks API
        
    Returns:
        DataFrame with processed invoice data (always has expected columns, even if empty)
    """
    invoice_data = []
    
    print(f"🔄 Processing {len(invoices)} invoices...")
    
    for inv in invoices:
        customer_name = _get_customer_vendor_name(inv, 'CustomerRef')
        items_desc = _extract_line_items(inv.get('Line'), 'SalesItemLineDetail')
        balance = float(inv.get('Balance', 0))
        total = float(inv.get('TotalAmt', 0))
        payment_status = _determine_payment_status(balance)
        
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
            FIELD_QUICKBOOKS_ID: inv.get('Id', '')
        })
    
    print(f"✅ Processed {len(invoice_data)} invoices")
    
    # Always return DataFrame with expected columns, even if empty
    if invoice_data:
        return pd.DataFrame(invoice_data)
    else:
        # Return empty DataFrame with expected columns
        return pd.DataFrame(columns=[
            'Type', FIELD_NUMBER, FIELD_DATE, FIELD_DUE_DATE, FIELD_CUSTOMER_VENDOR,
            FIELD_ITEMS_DESCRIPTION, FIELD_TOTAL_AMOUNT, FIELD_BALANCE_DUE,
            FIELD_PAYMENT_STATUS, FIELD_QUICKBOOKS_ID
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
            FIELD_QUICKBOOKS_ID: bill.get('Id', '')
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
            FIELD_PAYMENT_STATUS, FIELD_QUICKBOOKS_ID
        ])

def main(qb_credentials: Dict, sf_credentials: Dict, smtp_credentials: Dict, context=None):
    """
    Main sync logic - fetches data from QuickBooks and updates Salesforce
    
    Args:
        qb_credentials: QuickBooks OAuth credentials from Secrets Manager
        sf_credentials: Salesforce login credentials from Secrets Manager
        smtp_credentials: SMTP email credentials from Secrets Manager
        context: Lambda context object (optional, for system info collection)
    """
    start_time = time.time()
    
    print("\n" + "="*70)
    print("🔄 STARTING QUICKBOOKS-AVSIGHT SYNC")
    print("="*70)
    
    # Initialize connectors
    print("\n📡 Initializing connectors...")
    qb = QuickBooksConnector(qb_credentials)
    sf = SalesforceConnector(sf_credentials)
    sf.login()
    
    # Check if incremental sync is enabled
    enable_incremental = get_enable_incremental_sync()
    last_run_timestamp = None
    
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
    invoices_df = process_invoices(qb.get_all_invoices(last_modified_since=last_run_timestamp))
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
            bills_df[FIELD_ORDER] = bills_df[FIELD_ITEMS_DESCRIPTION].apply(find_order_number)
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
            bills_df['Memo__c'] = bills_df[FIELD_ITEMS_DESCRIPTION]
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

        # Filter bills whose balance or total has changed since the last update
        if not bills_update.empty and 'Balance_Due__c' in bills_update.columns and 'Total_Amount__c' in bills_update.columns:
            mask = ((bills_update.Balance_Due__c != bills_update.Balance_Due__c_pay) |
                    (bills_update.Total_Amount__c != bills_update.Total_Amount__c_pay))
            bills_update = bills_update[mask][['Id', 'Balance_Due__c', 'Total_Amount__c',
                                               'QBO_Bill_ID__c', 'Due_Date__c', 'Bill_Date__c', 'Account__c', 'Memo__c']]
            bills_update_data = bills_update.fillna('').to_dict(orient='records')
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
            
            if not invoices.empty:
                invoices['Previous Balance'] = invoices.Invoice_Balance__c

                # Filter balances with discrepancies
                invoices = invoices[invoices[FIELD_BALANCE_DUE] != invoices['Invoice_Balance__c']].sort_values(FIELD_DATE)
                
                if not invoices.empty:
                    invoices = invoices[[FIELD_DATE, 'Name', 'Id', FIELD_BALANCE_DUE, 'Invoice_Balance__c',
                                        'Previous Balance', FIELD_PAYMENT_STATUS, 'inscor__Status__c', FIELD_QUICKBOOKS_ID]]
                    invoices['Invoice_Balance__c'] = invoices[FIELD_BALANCE_DUE]
                    invoices['inscorqb__QuickBooks_Id__c'] = invoices[FIELD_QUICKBOOKS_ID]

                    # Fix invoice status
                    invoices.loc[invoices.Invoice_Balance__c == 0, 'inscor__Status__c'] = 'Paid'
                    invoices.loc[invoices.Invoice_Balance__c > 0, 'inscor__Status__c'] = 'Sent'
                    # Include 'Name' (invoice number) and 'inscor__Account__c' for better identification in emails
                    # Check if inscor__Account__c exists in the merged invoices DataFrame
                    invoice_columns = ['Id', 'Name', 'Invoice_Balance__c', 'inscor__Status__c', 'inscorqb__QuickBooks_Id__c']
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
        if not invoices.empty:
            invoices.to_csv(f"{results_dir}/{exact_time()}_invoices.csv", index=False)
    except Exception as e:
        print(f"⚠️ Failed to export invoices CSV: {e}")
    
    # Send data to Salesforce
    if len(invoices_updated) > 0:
        results = sf.sf.bulk.inscor__Invoice__c.update(invoices_updated, batch_size=batch_size)
        try:
            pd.DataFrame(results).to_csv(f"{results_dir}/{exact_time()}_invoices_RESULTS.csv", index=False)
        except Exception as e:
            print(f"⚠️ Failed to export invoice results CSV: {e}")
    
    if len(bills_update_data) > 0:
        results = sf.sf.bulk.Payment__c.update(bills_update_data, batch_size=batch_size)
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
                         smtp_credentials, execution_time=execution_time,
                         invoice_dict=invoice_dict, payment_dict=payment_dict,
                         context=context, sync_type=sync_type,
                         last_run_timestamp=last_run_timestamp,
                         invoices_fetched=invoices_fetched,
                         bills_fetched=bills_fetched):
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
        # Fetch credentials from AWS Secrets Manager
        print("\n🔐 Retrieving credentials from Secrets Manager...")
        qb_creds = get_secret('quickbooks/credentials')
        sf_creds = get_secret('salesforce/credentials')
        smtp_creds = get_secret('smtp/credentials')
        
        # Run the main sync
        main(qb_creds, sf_creds, smtp_creds, context=context)
        
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
    
    
