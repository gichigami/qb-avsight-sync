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
    
    def __init__(self, credentials: Dict[str, str]):
        """
        Initialize QuickBooks connector with credentials from Secrets Manager
        
        Args:
            credentials: Dict containing client_id, client_secret, refresh_token,
                        access_token, realm_id, and environment
        """
        self.client_id = credentials['client_id']
        self.client_secret = credentials['client_secret']
        self.access_token = credentials['access_token']
        self.refresh_token = credentials['refresh_token']
        self.realm_id = credentials['realm_id']
        self.environment = credentials.get('environment', 'production')
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
            
            # Return updated tokens so caller can save to Secrets Manager
            return True, {
                'access_token': tokens['access_token'],
                'refresh_token': tokens['refresh_token'],
                'realm_id': self.realm_id,
                'client_id': self.client_id,
                'client_secret': self.client_secret,
                'environment': self.environment,
                'updated_at': datetime.now().isoformat()
            }
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
                
                query = f"SELECT * FROM Invoice WHERE MetaData.LastUpdatedTime >= '{timestamp_str}' MAXRESULTS {max_results} STARTPOSITION {start_position}"
            else:
                query = f"SELECT * FROM Invoice MAXRESULTS {max_results} STARTPOSITION {start_position}"
            
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
                
                query = f"SELECT * FROM Bill WHERE MetaData.LastUpdatedTime >= '{timestamp_str}' MAXRESULTS {max_results} STARTPOSITION {start_position}"
            else:
                query = f"SELECT * FROM Bill MAXRESULTS {max_results} STARTPOSITION {start_position}"
            
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
