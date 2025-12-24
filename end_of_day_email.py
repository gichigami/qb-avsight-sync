"""
AWS Lambda Function: End-of-Day Email Sender
Sends a daily summary email with all QuickBooks sync changes accumulated throughout the day

This function should be triggered by EventBridge (CloudWatch Events) once per day
Recommended schedule: Daily at 6:00 PM EST (or your preferred end-of-day time)
"""

import json
from datetime import datetime, date, timedelta
from utils import get_secret, send_end_of_day_email, get_s3_bucket_name, debug_print
from config import get_email_recipients_daily_summary


def lambda_handler(event, context):
    """
    AWS Lambda entry point - called by EventBridge scheduler at end of day
    
    Args:
        event: EventBridge event data
        context: Lambda context object
        
    Returns:
        Response dictionary with status code and body
    """
    print("="*70)
    print(f"End-of-Day Email Lambda invoked: {datetime.now().isoformat()}")
    print("="*70)
    
    try:
        debug_print(f"Lambda handler called with event: {json.dumps(event) if event else 'None'}")
        debug_print(f"Context function name: {context.function_name if context else 'None'}")
        
        # Get the date from event or use today
        # EventBridge can pass a date parameter if needed
        date_str = None
        if event and 'date' in event:
            date_str = event['date']
            debug_print(f"Date from event: {date_str}")
        else:
            # Default to today, but you might want yesterday if running early morning
            date_str = date.today().isoformat()
            debug_print(f"No date in event, using today: {date_str}")
        
        print(f"\n📅 Processing daily summary for: {date_str}")
        
        # Get SMTP credentials from Secrets Manager
        print("\n🔐 Retrieving SMTP credentials from Secrets Manager...")
        debug_print("Calling get_secret('smtp/credentials')...")
        try:
            smtp_creds = get_secret('smtp/credentials')
            debug_print(f"SMTP credentials retrieved. Keys: {list(smtp_creds.keys()) if smtp_creds else 'None'}")
        except Exception as secret_err:
            debug_print(f"Error retrieving SMTP credentials: {secret_err}")
            raise
        
        # Get Salesforce credentials from Secrets Manager
        print("\n🔐 Retrieving Salesforce credentials from Secrets Manager...")
        debug_print("Calling get_secret('salesforce/credentials')...")
        try:
            sf_creds = get_secret('salesforce/credentials')
            debug_print(f"Salesforce credentials retrieved. Keys: {list(sf_creds.keys()) if sf_creds else 'None'}")
        except Exception as secret_err:
            debug_print(f"Error retrieving Salesforce credentials: {secret_err}")
            raise
        
        # Get recipients from .config file (daily summary list)
        debug_print("Getting recipients from config...")
        try:
            recipients = get_email_recipients_daily_summary()
            debug_print(f"Recipients retrieved: {recipients}")
        except Exception as config_err:
            debug_print(f"Error getting recipients: {config_err}")
            raise
        
        # Send the end-of-day email
        print(f"\n📧 Sending end-of-day email for {date_str}...")
        debug_print(f"Calling send_end_of_day_email with date_str={date_str}, smtp_config provided, recipients={recipients}, sf_credentials provided")
        email_result = send_end_of_day_email(date_str=date_str, 
                                smtp_config=smtp_creds,
                                recipients=recipients,
                                sf_credentials=sf_creds)
        debug_print(f"send_end_of_day_email returned: {email_result}")
        
        if email_result:
            print("✅ End-of-day email sent successfully!")
            
            return {
                'statusCode': 200,
                'body': json.dumps({
                    'message': f'End-of-day email sent successfully for {date_str}',
                    'timestamp': datetime.now().isoformat()
                })
            }
        else:
            debug_print("send_end_of_day_email returned False, returning 500 error")
            return {
                'statusCode': 500,
                'body': json.dumps({
                    'message': f'Failed to send end-of-day email for {date_str}',
                    'timestamp': datetime.now().isoformat()
                })
            }
        
    except Exception as e:
        print(f"\n❌ END-OF-DAY EMAIL FAILED: {str(e)}")
        
        import traceback
        traceback.print_exc()
        
        return {
            'statusCode': 500,
            'body': json.dumps({
                'message': 'End-of-day email failed',
                'error': str(e),
                'timestamp': datetime.now().isoformat()
            })
        }


# For local testing
if __name__ == "__main__":
    print("⚠️  Running in local test mode")
    print("Make sure you have AWS credentials configured")
    
    # Test with today's date
    test_event = {'date': date.today().isoformat()}
    lambda_handler(test_event, None)

