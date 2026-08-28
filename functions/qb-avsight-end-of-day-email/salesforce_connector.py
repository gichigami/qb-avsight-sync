from simple_salesforce import Salesforce
import requests
import pandas as pd
from io import StringIO
from typing import Dict, Optional

class SalesforceConnector:
    """Salesforce connector for AvSight ERP system"""
    
    def __init__(self, credentials: Dict[str, str]):
        """
        Initialize Salesforce connector
        
        Args:
            credentials: Dict containing username, password, security_token, and instance_url
        """
        self.username = credentials['username']
        self.password = credentials['password']
        self.security_token = credentials['security_token']
        self.instance_url = credentials.get('instance_url', 
                                           'https://pioneer-aero.my.salesforce.com/')
        self.sf: Optional[Salesforce] = None

    def login(self) -> Salesforce:
        """
        Log in to Salesforce
        
        Returns:
            Salesforce connection object
        """
        sf = Salesforce(username=self.username, password=self.password, 
                      security_token=self.security_token)
        self.sf = sf
        return sf

    def get_report(self, report_id: str) -> pd.DataFrame:
        """
        Get a Salesforce report as a DataFrame
        
        Args:
            report_id: Salesforce report ID
            
        Returns:
            DataFrame containing report data
        """
        export = '?isdtp=p1&export=1&enc=UTF-8&xf=csv'
        sf_url = self.instance_url + report_id + export
        response = requests.get(sf_url, headers=self.sf.headers, 
                               cookies={'sid': self.sf.session_id})
        download_report = response.content.decode('utf-8')
        df = pd.read_csv(StringIO(download_report))
        return df

    def soql_to_df(self, query: str) -> pd.DataFrame:
        """
        Execute SOQL query and return results as DataFrame
        
        Args:
            query: SOQL query string
            
        Returns:
            DataFrame containing query results
        """
        data = self.sf.query_all(query)
        return pd.DataFrame(data['records'])
    
    def get_all_fields(self, object_name: str) -> pd.DataFrame:
        """
        Get all fields for a Salesforce object
        
        Args:
            object_name: Name of the Salesforce object (e.g., 'Payment__c')
            
        Returns:
            DataFrame containing all records with all fields
        """
        # First get field names
        fields = self.soql_to_df(f"SELECT FIELDS(ALL) FROM {object_name} LIMIT 1")
        # Handle empty dataframe case
        if fields.empty:
            return fields
        # Drop attributes column if it exists
        if "attributes" in fields.columns:
            fields = fields.drop(columns=["attributes"])
        field_list = fields.columns.tolist()
        # Then get all records with those fields
        return self.soql_to_df(f"SELECT {','.join(field_list)} FROM {object_name}")