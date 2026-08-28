"""
QuickBooks API Connector for AWS Lambda
Handles OAuth2 authentication and API requests to QuickBooks Online
"""

import requests
import json
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple
import pandas as pd


class QuickBooksConnector:
    """QuickBooks Online API connector with token refresh management"""
    
    # Constants
    MAX_TOKEN_RETRY_ATTEMPTS = 1
    
    def __init__(self, credentials: Dict[str, str], on_token_refresh=None):
        """
        Initialize QuickBooks connector with credentials from Secrets Manager

        Args:
            credentials: Dict containing client_id, client_secret, refresh_token,
                        access_token, realm_id, and environment
            on_token_refresh: Optional callback invoked with the new tokens dict
                        immediately after a successful token refresh. QuickBooks
                        rotates the refresh token on every refresh, so the caller
                        must persist it right away — waiting until the end of the
                        sync loses the rotated token if anything downstream throws.
        """
        self.client_id = credentials['client_id']
        self.client_secret = credentials['client_secret']
        self.access_token = credentials['access_token']
        self.refresh_token = credentials['refresh_token']
        self.realm_id = credentials['realm_id']
        self.environment = credentials.get('environment', 'production')
        self.on_token_refresh = on_token_refresh
        self._tokens_refreshed = False
        
        # Load max results from config
        from config import get_qb_max_results_per_page
        self.max_results_per_page = get_qb_max_results_per_page()
        
        # Set API URLs
        if self.environment == 'sandbox':
            self.base_url = 'https://sandbox-quickbooks.api.intuit.com'
        else:
            self.base_url = 'https://quickbooks.api.intuit.com'
            
        self.token_url = 'https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer'
    
    def refresh_access_token(self) -> Tuple[bool, Optional[Dict]]:
        """
        Refresh the access token using the refresh token
        
        Returns:
            Tuple of (success: bool, new_tokens: Dict or None)
        """
        headers = {
            'Accept': 'application/json',
            'Content-Type': 'application/x-www-form-urlencoded'
        }
        
        data = {
            'grant_type': 'refresh_token',
            'refresh_token': self.refresh_token
        }
        
        response = requests.post(
            self.token_url,
            headers=headers,
            data=data,
            auth=(self.client_id, self.client_secret)
        )
        
        if response.status_code == 200:
            tokens = response.json()
            self.access_token = tokens['access_token']
            self.refresh_token = tokens['refresh_token']
            self._tokens_refreshed = True
            
            print("✅ Token refreshed successfully")

            new_tokens = {
                'access_token': tokens['access_token'],
                'refresh_token': tokens['refresh_token'],
                'realm_id': self.realm_id,
                'client_id': self.client_id,
                'client_secret': self.client_secret,
                'environment': self.environment,
                'updated_at': datetime.now().isoformat()
            }

            # Persist the rotated token IMMEDIATELY. QuickBooks invalidates the
            # previous refresh token shortly after issuing a new one, so if we
            # only saved at the end of the sync a later crash would strand us
            # with a dead token in Secrets Manager (requires manual re-auth).
            if self.on_token_refresh:
                try:
                    self.on_token_refresh(new_tokens)
                except Exception as e:
                    print(f"  ⚠️ Failed to persist refreshed token immediately: {e}")

            # Also return updated tokens so callers can save if they prefer
            return True, new_tokens
        else:
            print(f"❌ Token refresh failed: {response.text}")
            return False, None
    
    def make_api_request(self, endpoint: str, params: Optional[Dict] = None, 
                        retry_count: int = 0) -> Optional[Dict]:
        """
        Make authenticated API request with proper retry logic
        
        Args:
            endpoint: API endpoint path
            params: Optional query parameters
            retry_count: Number of retry attempts (internal use)
            
        Returns:
            Response JSON as dictionary or None if request failed
        """
        if not self.access_token:
            raise Exception("Not authenticated - run authentication first")
        
        headers = {
            'Accept': 'application/json',
            'Authorization': f'Bearer {self.access_token}',
            'Content-Type': 'application/json'
        }
        
        url = f"{self.base_url}/v3/company/{self.realm_id}/{endpoint}"
        
        response = requests.get(url, headers=headers, params=params)
        
        if response.status_code == 401 and retry_count < self.MAX_TOKEN_RETRY_ATTEMPTS:
            # Token expired - refresh and retry once
            print("  ⚠️ Token expired, refreshing...")
            success, _ = self.refresh_access_token()
            if success:
                print("  ✅ Token refreshed, retrying request...")
                # Recursive call with incremented retry_count to prevent infinite loop
                return self.make_api_request(endpoint, params, retry_count=retry_count + 1)
            else:
                raise Exception("Failed to refresh token - need to re-authenticate")
        
        if response.status_code != 200:
            print(f"  ❌ Request failed: {response.status_code} - {response.text}")
            return None
        
        return response.json()

    def make_api_post_request(self, endpoint: str, json_body: Dict,
                              params: Optional[Dict] = None,
                              retry_count: int = 0) -> Optional[Dict]:
        """
        Make authenticated POST request (for creating/updating resources)

        Args:
            endpoint: API endpoint path
            json_body: Request body as dictionary
            params: Optional query parameters
            retry_count: Number of retry attempts (internal use)

        Returns:
            Response JSON as dictionary, or None if request failed.
            On stale SyncToken (QB error 5010 or HTTP 409), returns {"error": "conflict", ...}.
        """
        if not self.access_token:
            raise Exception("Not authenticated - run authentication first")

        headers = {
            'Accept': 'application/json',
            'Authorization': f'Bearer {self.access_token}',
            'Content-Type': 'application/json'
        }

        url = f"{self.base_url}/v3/company/{self.realm_id}/{endpoint}"

        response = requests.post(url, headers=headers, json=json_body, params=params)

        if response.status_code == 401 and retry_count < self.MAX_TOKEN_RETRY_ATTEMPTS:
            print("  ⚠️ Token expired, refreshing...")
            success, _ = self.refresh_access_token()
            if success:
                print("  ✅ Token refreshed, retrying request...")
                return self.make_api_post_request(endpoint, json_body, params, retry_count=retry_count + 1)
            else:
                raise Exception("Failed to refresh token - need to re-authenticate")

        # QB returns 400 with error code 5010 for stale SyncToken (not HTTP 409)
        if response.status_code in (400, 409):
            try:
                err_body = response.json()
                err_code = (err_body.get('Fault', {}).get('Error', [{}])[0]
                            .get('code', ''))
            except Exception:
                err_code = ''
            if response.status_code == 409 or err_code == '5010':
                print(f"  ⚠️ Conflict (stale SyncToken): {response.text[:200]}")
                return {"error": "conflict", "status_code": response.status_code}

        if response.status_code != 200:
            print(f"  ❌ POST request failed: {response.status_code} - {response.text[:300]}")
            return None

        return response.json()

    def update_invoice_po_number(self, invoice_id: str, sync_token: str,
                                  po_number: str) -> Tuple[bool, Optional[str]]:
        """
        Update the P.O. Number custom field on a QuickBooks invoice via sparse update.

        Args:
            invoice_id: QuickBooks invoice ID
            sync_token: Current SyncToken for optimistic concurrency
            po_number: The PO number value to set

        Returns:
            Tuple of (success, new_sync_token_or_error_message)
        """
        payload = {
            "Id": invoice_id,
            "SyncToken": sync_token,
            "sparse": True,
            "CustomField": [
                {
                    "DefinitionId": "1",
                    "Name": "P.O. Number",
                    "Type": "StringType",
                    "StringValue": po_number
                }
            ]
        }

        result = self.make_api_post_request('invoice', json_body=payload)

        if result is None:
            return False, "request_failed"

        if isinstance(result, dict) and result.get('error') == 'conflict':
            return False, "conflict"

        # Success — extract new SyncToken from response
        new_sync_token = result.get('Invoice', {}).get('SyncToken')
        return True, new_sync_token

    def get_all_invoices(self, last_modified_since: Optional[datetime] = None) -> List[Dict]:
        """
        Fetch all invoices with pagination
        
        Args:
            last_modified_since: Optional datetime to filter invoices modified since this time
        
        Returns:
            List of invoice dictionaries from QuickBooks API
        """
        all_invoices = []
        page = 1
        max_results = self.max_results_per_page
        
        if last_modified_since:
            print(f"📥 Fetching invoices modified since {last_modified_since.isoformat()}...")
        else:
            print("📥 Fetching all invoices...")
        
        while True:
            start_position = (page - 1) * max_results + 1
            
            # Build the query
            # OPTIMIZED: Select only needed fields instead of SELECT * to reduce payload size
            if last_modified_since:
                # Convert UTC datetime to ISO 8601 format with timezone for QuickBooks API
                # QuickBooks expects format like: 2024-01-15T10:30:00-08:00
                # We'll use the timezone from the datetime or default to UTC
                if last_modified_since.tzinfo is None:
                    qb_timestamp = last_modified_since.replace(tzinfo=timezone.utc)
                else:
                    qb_timestamp = last_modified_since.astimezone(timezone.utc)
                
                # Format as ISO 8601 with timezone offset (QuickBooks expects UTC with +00:00)
                # Format: YYYY-MM-DDTHH:MM:SS+00:00
                timestamp_str = qb_timestamp.strftime('%Y-%m-%dT%H:%M:%S+00:00')
                
                query = (f"SELECT Id, DocNumber, TxnDate, DueDate, CustomerRef, Line, "
                        f"Balance, TotalAmt, MetaData.LastUpdatedTime, CustomField, SyncToken "
                        f"FROM Invoice "
                        f"WHERE MetaData.LastUpdatedTime >= '{timestamp_str}' "
                        f"MAXRESULTS {max_results} STARTPOSITION {start_position}")
            else:
                query = (f"SELECT Id, DocNumber, TxnDate, DueDate, CustomerRef, Line, "
                        f"Balance, TotalAmt, MetaData.LastUpdatedTime, CustomField, SyncToken "
                        f"FROM Invoice "
                        f"MAXRESULTS {max_results} STARTPOSITION {start_position}")
            
            print(f"  Fetching page {page} (starting at position {start_position})...")
            data = self.make_api_request('query', params={'query': query})
            
            if not data or 'QueryResponse' not in data:
                print("  No more invoices found")
                break
                
            if 'Invoice' not in data['QueryResponse']:
                print("  No invoices in this page")
                break
                
            invoices = data['QueryResponse']['Invoice']
            all_invoices.extend(invoices)
            
            print(f"  Found {len(invoices)} invoices in page {page}")
            
            # Check if we got less than max_results, which means we're done
            if len(invoices) < max_results:
                break
                
            page += 1
        
        print(f"✅ Total invoices fetched: {len(all_invoices)}")
        return all_invoices
    
    def get_all_bills(self, last_modified_since: Optional[datetime] = None) -> List[Dict]:
        """
        Fetch all bills with pagination
        
        Args:
            last_modified_since: Optional datetime to filter bills modified since this time
        
        Returns:
            List of bill dictionaries from QuickBooks API
        """
        all_bills = []
        page = 1
        max_results = self.max_results_per_page
        
        if last_modified_since:
            print(f"📥 Fetching bills modified since {last_modified_since.isoformat()}...")
        else:
            print("📥 Fetching all bills...")
        
        while True:
            start_position = (page - 1) * max_results + 1
            
            # Build the query
            # OPTIMIZED: Select only needed fields instead of SELECT * to reduce payload size
            if last_modified_since:
                # Convert UTC datetime to ISO 8601 format with timezone for QuickBooks API
                # QuickBooks expects format like: 2024-01-15T10:30:00-08:00
                # We'll use the timezone from the datetime or default to UTC
                if last_modified_since.tzinfo is None:
                    qb_timestamp = last_modified_since.replace(tzinfo=timezone.utc)
                else:
                    qb_timestamp = last_modified_since.astimezone(timezone.utc)
                
                # Format as ISO 8601 with timezone offset (QuickBooks expects UTC with +00:00)
                # Format: YYYY-MM-DDTHH:MM:SS+00:00
                timestamp_str = qb_timestamp.strftime('%Y-%m-%dT%H:%M:%S+00:00')
                
                query = (f"SELECT Id, DocNumber, TxnDate, DueDate, VendorRef, Line, "
                        f"Balance, TotalAmt, MetaData.LastUpdatedTime "
                        f"FROM Bill "
                        f"WHERE MetaData.LastUpdatedTime >= '{timestamp_str}' "
                        f"MAXRESULTS {max_results} STARTPOSITION {start_position}")
            else:
                query = (f"SELECT Id, DocNumber, TxnDate, DueDate, VendorRef, Line, "
                        f"Balance, TotalAmt, MetaData.LastUpdatedTime "
                        f"FROM Bill "
                        f"MAXRESULTS {max_results} STARTPOSITION {start_position}")
            
            print(f"  Fetching page {page} (starting at position {start_position})...")
            data = self.make_api_request('query', params={'query': query})
            
            if not data or 'QueryResponse' not in data:
                print("  No more bills found")
                break
                
            if 'Bill' not in data['QueryResponse']:
                print("  No bills in this page")
                break
                
            bills = data['QueryResponse']['Bill']
            all_bills.extend(bills)
            
            print(f"  Found {len(bills)} bills in page {page}")
            
            if len(bills) < max_results:
                break
                
            page += 1
        
        print(f"✅ Total bills fetched: {len(all_bills)}")
        return all_bills
    
    def get_customer_info(self, customer_id: str) -> Optional[Dict]:
        """
        Get customer details
        
        Args:
            customer_id: QuickBooks customer ID
            
        Returns:
            Customer dictionary or None if not found
        """
        data = self.make_api_request(f'customer/{customer_id}')
        if data and 'Customer' in data:
            return data['Customer']
        return None
    
    def get_vendor_info(self, vendor_id: str) -> Optional[Dict]:
        """
        Get vendor details
        
        Args:
            vendor_id: QuickBooks vendor ID
            
        Returns:
            Vendor dictionary or None if not found
        """
        data = self.make_api_request(f'vendor/{vendor_id}')
        if data and 'Vendor' in data:
            return data['Vendor']
        return None
    
    def get_payments_for_invoices(self, invoice_ids: List[str], invoices: List[Dict]) -> Dict[str, Optional[str]]:
        """
        Get payment dates for given invoice IDs
        
        Queries QuickBooks Payment API to find payments linked to the specified invoices.
        Returns the date of the payment that zeroed the balance for each fully paid invoice.
        Only invoices with Balance == 0 will have a paid date assigned.
        
        Args:
            invoice_ids: List of QuickBooks invoice IDs
            invoices: List of invoice dictionaries from QuickBooks API (needed for TotalAmt and Balance)
            
        Returns:
            Dict mapping invoice_id -> payment_date_that_zeroed_balance (YYYY-MM-DD format) or None
        """
        if not invoice_ids:
            return {}
        
        # Build invoice lookup with TotalAmt and Balance
        invoice_lookup = {}
        for inv in invoices:
            inv_id = inv.get('Id')
            if inv_id:
                invoice_lookup[inv_id] = {
                    'total': float(inv.get('TotalAmt', 0)),
                    'balance': float(inv.get('Balance', 0))
                }
        
        # Collect payments per invoice: invoice_id -> list of (date, amount) tuples
        invoice_payments = {inv_id: [] for inv_id in invoice_ids}
        page = 1
        max_results = self.max_results_per_page
        zero_amount_lines_filtered = 0  # Per-line zero-amount skips. QB Payments with TotalAmt=0
        # are valid: they apply existing customer credit to an invoice, with Line.Amount > 0.
        
        print(f"📅 Fetching payment dates for {len(invoice_ids)} invoices...")
        
        # QuickBooks API has a limit on IN clause size, so we'll query all payments
        # and filter by invoice IDs in memory. Alternatively, we could batch invoice IDs.
        # For now, query all payments and filter.
        # OPTIMIZED: Select only needed fields instead of SELECT * to reduce payload size
        while True:
            start_position = (page - 1) * max_results + 1
            query = f"SELECT TxnDate, TotalAmt, Line FROM Payment ORDER BY Id ASC MAXRESULTS {max_results} STARTPOSITION {start_position}"
            
            print(f"  Fetching payments page {page} (starting at position {start_position})...")
            data = self.make_api_request('query', params={'query': query})
            
            if not data or 'QueryResponse' not in data:
                print("  No more payments found")
                break
                
            if 'Payment' not in data['QueryResponse']:
                print("  No payments in this page")
                break
            
            payments = data['QueryResponse']['Payment']
            print(f"  Found {len(payments)} payments in page {page}")
            
            # Process each payment to extract invoice references and amounts
            for payment in payments:
                txn_date = payment.get('TxnDate', '')
                total_amt = payment.get('TotalAmt', 0)
                linked_txns = payment.get('Line', [])
                
                # Skip if no date
                if not txn_date:
                    continue
                
                # Normalize date to YYYY-MM-DD format for consistent comparison
                normalized_txn_date = txn_date
                if normalized_txn_date and len(normalized_txn_date) > 10:
                    # Extract date portion if it includes time
                    normalized_txn_date = normalized_txn_date[:10]

                # Per-line processing. We do NOT skip based on Payment.TotalAmt because
                # QB creates valid TotalAmt=0 Payments to apply existing customer credit
                # to an invoice — those carry Line.Amount > 0 and are the very transactions
                # that zero out the invoice's balance.
                for line in linked_txns:
                    linked_txn = line.get('LinkedTxn', [])
                    if not isinstance(linked_txn, list):
                        linked_txn = [linked_txn]

                    # Line.Amount is the cash applied to this specific invoice. Skip the
                    # line (not the whole payment) if it's missing or non-positive.
                    line_amt_str = line.get('Amount')
                    if line_amt_str is None:
                        zero_amount_lines_filtered += 1
                        continue
                    try:
                        line_amt = float(line_amt_str)
                    except (ValueError, TypeError):
                        zero_amount_lines_filtered += 1
                        continue
                    if line_amt <= 0:
                        zero_amount_lines_filtered += 1
                        continue

                    for link in linked_txn:
                        if not isinstance(link, dict):
                            continue

                        txn_id = link.get('TxnId', '')
                        txn_type = link.get('TxnType', '')

                        # Only process Invoice links
                        if txn_type == 'Invoice' and txn_id in invoice_ids:
                            # Collect payment with date and amount
                            invoice_payments[txn_id].append((normalized_txn_date, line_amt))
            
            # Check if we got less than max_results, which means we're done
            if len(payments) < max_results:
                break
                
            page += 1
        
        # Calculate payment dates: find the payment that zeroed the balance
        payment_dates = {}
        for inv_id in invoice_ids:
            payments_list = invoice_payments.get(inv_id, [])
            
            if not payments_list:
                payment_dates[inv_id] = None
                continue
            
            # Sort payments chronologically by date
            payments_list.sort(key=lambda x: x[0])
            
            # Only calculate paid date for invoices with Balance == 0
            if inv_id in invoice_lookup:
                inv_info = invoice_lookup[inv_id]
                total = inv_info['total']
                current_balance = inv_info['balance']
                
                if current_balance == 0:
                    # Calculate running balance to find the payment that zeroed it
                    running_balance = total
                    zeroing_payment_date = None
                    
                    for pay_date, pay_amt in payments_list:
                        running_balance -= pay_amt
                        if running_balance <= 0:
                            zeroing_payment_date = pay_date
                            break
                    
                    payment_dates[inv_id] = zeroing_payment_date
                else:
                    # Invoice not fully paid, no paid date
                    payment_dates[inv_id] = None
            else:
                # Invoice not found in lookup, no paid date
                payment_dates[inv_id] = None
        
        # Log results
        invoices_with_paid_dates = len([v for v in payment_dates.values() if v])
        invoices_fully_paid = len([inv_id for inv_id in invoice_ids 
                                   if inv_id in invoice_lookup and invoice_lookup[inv_id]['balance'] == 0])
        print(f"✅ Found payment dates for {invoices_with_paid_dates} out of {invoices_fully_paid} fully paid invoices")
        if zero_amount_lines_filtered > 0:
            print(f"  ℹ️  Filtered out {zero_amount_lines_filtered} zero-amount payment lines (per-line check; payments with TotalAmt=0 but valid Line.Amount are kept)")
        
        # Log sample payment dates for verification
        sample_count = min(10, len([v for v in payment_dates.values() if v]))
        if sample_count > 0:
            print(f"📅 Sample payment dates retrieved:")
            count = 0
            for inv_id, pay_date in payment_dates.items():
                if pay_date and count < sample_count:
                    print(f"  Invoice {inv_id}: {pay_date}")
                    count += 1
        
        return payment_dates