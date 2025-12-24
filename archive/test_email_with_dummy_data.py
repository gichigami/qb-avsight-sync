"""
Test script for end-of-day email function with dummy data from Salesforce

This script:
1. Queries Salesforce for recent Payment__c and inscor__Invoice__c records
2. Creates dummy S3 summary data with IDs
3. Tests the send_end_of_day_email function

Usage:
    python test_email_with_dummy_data.py                    # Test with today's date
    python test_email_with_dummy_data.py 2025-12-23        # Test with specific date
    python test_email_with_dummy_data.py --cleanup         # Clean up test data from S3
"""

import json
import sys
import boto3
from datetime import datetime, date, timedelta
from botocore.exceptions import ClientError
from utils import get_secret, send_end_of_day_email, get_s3_bucket_name
from salesforce_connector import SalesforceConnector
from config import get_email_recipients_daily_summary


def query_recent_salesforce_records(sf_credentials, limit=5):
    """
    Query Salesforce for recent Payment__c and inscor__Invoice__c records
    
    Args:
        sf_credentials: Salesforce credentials dictionary
        limit: Number of records to fetch per object type
        
    Returns:
        Dictionary with bills_update_ids, bills_insert_ids, invoices_update_ids
    """
    print("="*70)
    print("Querying Salesforce for recent records...")
    print("="*70)
    
    try:
        sf = SalesforceConnector(sf_credentials)
        sf.login()
        print("✅ Salesforce login successful")
        
        # Query recent Payment__c records (bills)
        print(f"\n📋 Querying {limit} recent Payment__c records...")
        bills_query = f"""
        SELECT Id, Name, Account__c, Balance_Due__c, Bill_Date__c, LastModifiedDate
        FROM Payment__c
        WHERE LastModifiedDate >= LAST_N_DAYS:30
        ORDER BY LastModifiedDate DESC
        LIMIT {limit * 2}
        """
        bills_df = sf.soql_to_df(bills_query)
        print(f"✅ Found {len(bills_df)} Payment__c records")
        
        # Split into update and insert (simulate)
        bills_update_ids = bills_df['Id'].head(limit).tolist() if len(bills_df) >= limit else bills_df['Id'].tolist()
        bills_insert_ids = bills_df['Id'].tail(limit).tolist() if len(bills_df) > limit else []
        
        # Query recent inscor__Invoice__c records
        print(f"\n📄 Querying {limit} recent inscor__Invoice__c records...")
        invoices_query = f"""
        SELECT Id, Name, inscor__Account__c, inscor__Invoice_Date__c, Invoice_Balance__c, LastModifiedDate
        FROM inscor__Invoice__c
        WHERE LastModifiedDate >= LAST_N_DAYS:30
        ORDER BY LastModifiedDate DESC
        LIMIT {limit}
        """
        invoices_df = sf.soql_to_df(invoices_query)
        print(f"✅ Found {len(invoices_df)} inscor__Invoice__c records")
        
        invoices_update_ids = invoices_df['Id'].tolist()
        
        print("\n" + "="*70)
        print("Query Results Summary:")
        print("="*70)
        print(f"Bills Update IDs: {len(bills_update_ids)}")
        print(f"Bills Insert IDs: {len(bills_insert_ids)}")
        print(f"Invoices Update IDs: {len(invoices_update_ids)}")
        
        return {
            'bills_update_ids': bills_update_ids,
            'bills_insert_ids': bills_insert_ids,
            'invoices_update_ids': invoices_update_ids
        }
        
    except Exception as e:
        print(f"❌ Error querying Salesforce: {e}")
        import traceback
        traceback.print_exc()
        return {
            'bills_update_ids': [],
            'bills_insert_ids': [],
            'invoices_update_ids': []
        }


def create_dummy_s3_summary(test_date, ids_data):
    """
    Create a dummy daily summary in S3 with the queried IDs
    
    Args:
        test_date: Date string in YYYY-MM-DD format
        ids_data: Dictionary with bills_update_ids, bills_insert_ids, invoices_update_ids
    """
    print("\n" + "="*70)
    print("Creating dummy S3 summary...")
    print("="*70)
    
    try:
        bucket_name = get_s3_bucket_name()
        s3_client = boto3.client('s3')
        key = f"daily-summaries/{test_date}/summary.json"
        
        # Create dummy summary structure
        daily_summary = {
            'date': test_date,
            'runs': [
                {
                    'timestamp': datetime.now().strftime('%Y-%m-%d_%H%M%S'),
                    'execution_time': '2m 30s',
                    'bills_update_count': len(ids_data['bills_update_ids']),
                    'bills_insert_count': len(ids_data['bills_insert_ids']),
                    'invoices_updated_count': len(ids_data['invoices_update_ids']),
                    'system_info': {
                        'environment': 'AWS Lambda',
                        'os': 'Linux',
                        'python_version': '3.11',
                        'hostname': 'test-lambda-function',
                        'lambda_function_name': 'qb-avsight-sync-test',
                        'lambda_region': 'us-east-1',
                        'lambda_memory_mb': 1024
                    },
                    'sync_type': 'full'
                },
                {
                    'timestamp': (datetime.now() - timedelta(hours=2)).strftime('%Y-%m-%d_%H%M%S'),
                    'execution_time': '1m 45s',
                    'bills_update_count': len(ids_data['bills_update_ids']) // 2,
                    'bills_insert_count': len(ids_data['bills_insert_ids']) // 2,
                    'invoices_updated_count': len(ids_data['invoices_update_ids']) // 2,
                    'system_info': {
                        'environment': 'AWS Lambda',
                        'os': 'Linux',
                        'python_version': '3.11',
                        'hostname': 'test-lambda-function',
                        'lambda_function_name': 'qb-avsight-sync-test',
                        'lambda_region': 'us-east-1',
                        'lambda_memory_mb': 1024
                    },
                    'sync_type': 'incremental'
                }
            ],
            'total_bills_updated': len(ids_data['bills_update_ids']),
            'total_bills_inserted': len(ids_data['bills_insert_ids']),
            'total_invoices_updated': len(ids_data['invoices_update_ids']),
            'total_runtime': '4m 15s',
            'bills_update_ids': ids_data['bills_update_ids'],
            'bills_insert_ids': ids_data['bills_insert_ids'],
            'invoices_update_ids': ids_data['invoices_update_ids']
        }
        
        # Save to S3
        json_data = json.dumps(daily_summary, default=str, indent=2)
        s3_client.put_object(
            Bucket=bucket_name,
            Key=key,
            Body=json_data.encode('utf-8'),
            ContentType='application/json'
        )
        
        print(f"✅ Created dummy summary at s3://{bucket_name}/{key}")
        print(f"   Bills Updated: {len(ids_data['bills_update_ids'])}")
        print(f"   Bills Inserted: {len(ids_data['bills_insert_ids'])}")
        print(f"   Invoices Updated: {len(ids_data['invoices_update_ids'])}")
        return True
        
    except Exception as e:
        print(f"❌ Error creating dummy S3 summary: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_email_function(test_date, smtp_creds, sf_creds):
    """
    Test the send_end_of_day_email function
    
    Args:
        test_date: Date string in YYYY-MM-DD format
        smtp_creds: SMTP credentials dictionary
        sf_creds: Salesforce credentials dictionary
    """
    print("\n" + "="*70)
    print("Testing send_end_of_day_email function...")
    print("="*70)
    
    try:
        # Get recipients
        recipients = get_email_recipients_daily_summary()
        print(f"Email recipients: {recipients}")
        
        # Call the email function
        result = send_end_of_day_email(
            date_str=test_date,
            smtp_config=smtp_creds,
            recipients=recipients,
            sf_credentials=sf_creds
        )
        
        if result:
            print("\n✅ Email function completed successfully!")
            print("   Check your email inbox for the test email.")
        else:
            print("\n⚠️  Email function returned False")
            
        return result
        
    except Exception as e:
        print(f"\n❌ Error testing email function: {e}")
        import traceback
        traceback.print_exc()
        return False


def cleanup_test_data(test_date):
    """
    Clean up test data from S3
    
    Args:
        test_date: Date string in YYYY-MM-DD format
    """
    print("="*70)
    print("Cleaning up test data from S3...")
    print("="*70)
    
    try:
        bucket_name = get_s3_bucket_name()
        s3_client = boto3.client('s3')
        key = f"daily-summaries/{test_date}/summary.json"
        
        s3_client.delete_object(Bucket=bucket_name, Key=key)
        print(f"✅ Deleted test data from s3://{bucket_name}/{key}")
        return True
        
    except ClientError as e:
        if e.response['Error']['Code'] == 'NoSuchKey':
            print(f"ℹ️  No test data found at s3://{bucket_name}/{key}")
            return True
        else:
            print(f"❌ Error cleaning up test data: {e}")
            return False
    except Exception as e:
        print(f"❌ Error cleaning up test data: {e}")
        return False


def main():
    """Main test function"""
    print("="*70)
    print("TEST: End-of-Day Email with Dummy Data from Salesforce")
    print("="*70)
    print(f"Test started at: {datetime.now().isoformat()}")
    print()
    
    # Check for cleanup flag
    if len(sys.argv) > 1 and sys.argv[1] == '--cleanup':
        test_date = sys.argv[2] if len(sys.argv) > 2 else date.today().isoformat()
        cleanup_test_data(test_date)
        return
    
    # Get test date (default to today)
    if len(sys.argv) > 1:
        test_date = sys.argv[1]
    else:
        test_date = date.today().isoformat()
    
    print(f"Test date: {test_date}")
    print()
    
    try:
        # Get credentials
        print("🔐 Retrieving credentials from Secrets Manager...")
        smtp_creds = get_secret('smtp/credentials')
        sf_creds = get_secret('salesforce/credentials')
        print("✅ Credentials retrieved")
        
        # Query Salesforce for recent records
        ids_data = query_recent_salesforce_records(sf_creds, limit=5)
        
        if not any(ids_data.values()):
            print("\n⚠️  No records found in Salesforce. Using empty test data.")
            print("   The email will still be sent but with no records.")
        
        # Create dummy S3 summary
        if not create_dummy_s3_summary(test_date, ids_data):
            print("\n⚠️  Failed to create S3 summary, but continuing with test...")
        
        # Test email function
        result = test_email_function(test_date, smtp_creds, sf_creds)
        
        print("\n" + "="*70)
        print("TEST COMPLETE")
        print("="*70)
        if result:
            print("✅ All tests passed!")
        else:
            print("⚠️  Some tests had issues - check output above")
        print(f"Test ended at: {datetime.now().isoformat()}")
        
    except Exception as e:
        print(f"\n❌ Test failed with error: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()

