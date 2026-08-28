"""
Utility functions for QB-AvSight sync
Includes email notifications, time formatting, and AWS Secrets Manager operations
"""

import boto3
import json
import os
import platform
import sys
import zipfile
import io
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from email.utils import make_msgid
from datetime import datetime, date, timezone
from typing import Dict, Optional, List, Any
from botocore.exceptions import ClientError
import re
import pandas as pd
from pioneer_email.templates import qb_sync_summary, qb_eod_summary

# Conditional DEBUG logging - only prints if DEBUG_LOGGING environment variable is set to 'true'
DEBUG_LOGGING = os.environ.get('DEBUG_LOGGING', 'false').lower() == 'true'

def debug_print(message: str):
    """
    Conditional DEBUG logging - only prints if DEBUG_LOGGING environment variable is set to 'true'
    This reduces CloudWatch Logs costs by preventing verbose DEBUG output in production
    
    Args:
        message: Debug message to print (only if DEBUG_LOGGING is enabled)
    """
    if DEBUG_LOGGING:
        print(f"[DEBUG] {message}")


def get_secret(secret_name: str, region_name: str = 'us-east-1') -> Dict:
    """
    Retrieve a secret from AWS Secrets Manager
    
    Args:
        secret_name: Name of the secret (e.g., 'quickbooks/credentials')
        region_name: AWS region where secret is stored
        
    Returns:
        Dictionary containing the secret values
    """
    client = boto3.client('secretsmanager', region_name=region_name)
    
    try:
        response = client.get_secret_value(SecretId=secret_name)
        
        if 'SecretString' in response:
            return json.loads(response['SecretString'])
        else:
            raise Exception(f"Binary secret not supported: {secret_name}")
            
    except ClientError as e:
        error_code = e.response['Error']['Code']
        
        if error_code == 'ResourceNotFoundException':
            raise Exception(f"Secret {secret_name} not found")
        elif error_code == 'DecryptionFailureException':
            raise Exception(f"Can't decrypt secret {secret_name}")
        elif error_code == 'InternalServiceErrorException':
            raise Exception(f"Internal server error for secret {secret_name}")
        else:
            raise e


def update_secret(secret_name: str, secret_dict: Dict, 
                 region_name: str = 'us-east-1') -> Dict:
    """
    Update a secret in AWS Secrets Manager
    Used for rotating QuickBooks refresh token
    
    Args:
        secret_name: Name of the secret to update
        secret_dict: Dictionary containing the updated secret values
        region_name: AWS region where secret is stored
        
    Returns:
        Response from AWS Secrets Manager
    """
    print(f"🔄 Updating secret: {secret_name}")
    client = boto3.client('secretsmanager', region_name=region_name)
    
    try:
        response = client.update_secret(
            SecretId=secret_name,
            SecretString=json.dumps(secret_dict)
        )
        print(f"✅ Updated secret: {secret_name}")
        return response
    except ClientError as e:
        print(f"❌ Failed to update secret {secret_name}: {e}")
        raise e


def format_time(seconds: float) -> str:
    """
    Format seconds into human-readable time string
    
    Args:
        seconds: Time in seconds
        
    Returns:
        Formatted string like "2m 30s" or "45s"
    """
    if seconds < 60:
        return f"{seconds:.1f}s"
    
    minutes = int(seconds // 60)
    remaining_seconds = seconds % 60
    
    if minutes < 60:
        return f"{minutes}m {remaining_seconds:.0f}s"
    
    hours = int(minutes // 60)
    remaining_minutes = minutes % 60
    return f"{hours}h {remaining_minutes}m"


def exact_time() -> str:
    """
    Get current timestamp in filename-safe format (always UTC)
    
    Returns:
        Timestamp string like "2025-12-19_143022" (in UTC)
    """
    return datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%M%S")


def format_timestamp_to_time(timestamp: str) -> str:
    """
    Convert timestamp string (YYYY-MM-DD_HHMMSS) to readable time format in GMT/UTC
    
    Args:
        timestamp: Timestamp string like "2025-12-19_143022" (assumed to be in UTC)
        
    Returns:
        Formatted time string like "2:30 PM GMT" or "10:15 AM GMT"
    """
    try:
        # Parse as naive datetime and assume it's UTC
        dt = datetime.strptime(timestamp, "%Y-%m-%d_%H%M%S")
        # Make it timezone-aware as UTC
        dt_utc = dt.replace(tzinfo=timezone.utc)
        # Format with GMT label
        return dt_utc.strftime("%H:%M GMT").lstrip('0')
    except (ValueError, AttributeError):
        return timestamp


def get_system_info(context: Optional[Any] = None) -> Dict[str, Any]:
    """
    Collect system information including hardware/software specs and execution environment
    
    Args:
        context: Lambda context object (if running on AWS Lambda), None if local
    
    Returns:
        Dictionary containing system information
    """
    system_info: Dict[str, Any] = {}
    
    # Detect execution environment
    is_lambda = os.environ.get('LAMBDA_TASK_ROOT') is not None or context is not None
    
    if is_lambda:
        system_info['environment'] = 'AWS Lambda'
        
        # Extract Lambda-specific information from context
        if context is not None:
            system_info['lambda_function_name'] = getattr(context, 'function_name', 'Unknown')
            system_info['lambda_memory_mb'] = getattr(context, 'memory_limit_in_mb', 'Unknown')
            system_info['lambda_request_id'] = getattr(context, 'aws_request_id', 'Unknown')
            
            # Extract region from ARN if available
            arn = getattr(context, 'invoked_function_arn', '')
            if arn and ':' in arn:
                # ARN format: arn:aws:lambda:region:account:function:name
                parts = arn.split(':')
                if len(parts) >= 4:
                    system_info['lambda_region'] = parts[3]
                else:
                    system_info['lambda_region'] = 'Unknown'
            else:
                system_info['lambda_region'] = 'Unknown'
        else:
            # Lambda environment but no context (shouldn't happen, but handle gracefully)
            system_info['lambda_function_name'] = 'Unknown'
            system_info['lambda_memory_mb'] = 'Unknown'
            system_info['lambda_region'] = os.environ.get('AWS_REGION', 'Unknown')
            system_info['lambda_request_id'] = 'Unknown'
    else:
        system_info['environment'] = 'Local'
    
    # Get hostname/computer name
    try:
        system_info['hostname'] = platform.node()
    except Exception:
        try:
            system_info['hostname'] = os.environ.get('COMPUTERNAME') or os.environ.get('HOSTNAME', 'Unknown')
        except Exception:
            system_info['hostname'] = 'Unknown'
    
    # Get operating system information
    try:
        system_info['os'] = f"{platform.system()} {platform.release()}"
        system_info['os_version'] = platform.version()
        system_info['os_arch'] = platform.machine()
    except Exception:
        system_info['os'] = 'Unknown'
        system_info['os_version'] = 'Unknown'
        system_info['os_arch'] = 'Unknown'
    
    # Get Python version
    system_info['python_version'] = sys.version.split()[0]
    system_info['python_implementation'] = platform.python_implementation()
    
    # Get CPU information (if available)
    try:
        system_info['cpu_count'] = os.cpu_count() or 'Unknown'
        system_info['processor'] = platform.processor()
    except Exception:
        system_info['cpu_count'] = 'Unknown'
        system_info['processor'] = 'Unknown'
    
    # Get memory information (if available and not Lambda)
    if not is_lambda:
        try:
            import psutil  # type: ignore  # Optional dependency for local development
            mem = psutil.virtual_memory()
            system_info['total_memory_gb'] = round(mem.total / (1024**3), 2)
            system_info['available_memory_gb'] = round(mem.available / (1024**3), 2)
        except ImportError:
            # psutil not available, skip memory info
            pass
        except Exception:
            pass
    
    return system_info


def send_auth_failure_alert(error_message: str,
                            recipients: Optional[List[str]] = None) -> bool:
    """
    Send a plain-text alert when the sync fails because QuickBooks OAuth
    re-authentication is required (invalid_grant / dead refresh token).

    Throttled to at most one email per UTC day via an S3 marker so a broken
    token does not email on every 15-minute scheduled run. The throttle is
    best-effort: if the marker cannot be read/written, the alert is still sent.

    Args:
        error_message: The exception text describing the failure.
        recipients: Email addresses (defaults to run-summary recipients).

    Returns:
        True if an alert was sent (or intentionally suppressed by the throttle).
    """
    try:
        if recipients is None:
            from config import get_email_recipients_run_summary
            recipients = get_email_recipients_run_summary()

        # Daily throttle marker in S3
        today = date.today().isoformat()
        marker_key = f"alerts/qb-auth-failure/{today}.marker"
        bucket_name = None
        s3 = None
        try:
            bucket_name = get_s3_bucket_name()
            s3 = boto3.client('s3')
            try:
                s3.head_object(Bucket=bucket_name, Key=marker_key)
                print("  ⏭️ Auth-failure alert already sent today; skipping duplicate")
                return True
            except ClientError as e:
                # 404/NoSuchKey => not sent yet; anything else, fall through and alert
                if e.response.get('Error', {}).get('Code') not in ('404', 'NoSuchKey', 'NotFound'):
                    print(f"  ⚠️ Throttle marker check inconclusive: {e}")
        except Exception as e:
            print(f"  ⚠️ Could not evaluate alert throttle: {e}")

        subject = "⚠️ QB-AvSight sync FAILED — QuickBooks re-authentication required"
        body = (
            "The QuickBooks → AvSight sync is failing because the QuickBooks OAuth "
            "refresh token is no longer valid (invalid_grant).\n"
            "Invoice Paid Date and other QuickBooks data will NOT update until this "
            "is re-authenticated.\n\n"
            f"Error:\n{error_message}\n\n"
            "Remediation runbook:\n"
            "  1. Re-authenticate QuickBooks with the local helper:\n"
            "       cd automations/lambda/qb-avsight-sync && python reauth_qb.py\n"
            "     Authorize in the browser when prompted; it writes fresh tokens to\n"
            "     the 'quickbooks/credentials' secret.\n"
            "  2. Trigger a catch-up full sync:\n"
            "       aws lambda invoke --function-name qb-avsight-sync \\\n"
            "         --payload '{\"sync_mode\":\"full\"}' \\\n"
            "         --cli-binary-format raw-in-base64-out /tmp/qb.json\n"
            "  3. Confirm the next scheduled runs succeed in CloudWatch\n"
            "     (log group /aws/lambda/qb-avsight-sync).\n\n"
            f"Alert time: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}\n"
        )

        msg = MIMEText(body, 'plain')
        msg['Subject'] = subject
        msg['From'] = 'automation@pioneer-aero.com'
        msg['To'] = ', '.join(recipients)

        ses = boto3.client('ses', region_name='us-east-1')
        ses.send_raw_email(
            Source='automation@pioneer-aero.com',
            Destinations=recipients,
            RawMessage={'Data': msg.as_string()},
        )
        print(f"  📧 Auth-failure alert sent to {', '.join(recipients)}")

        # Write throttle marker (best-effort)
        if bucket_name and s3:
            try:
                s3.put_object(
                    Bucket=bucket_name,
                    Key=marker_key,
                    Body=json.dumps({
                        'sent_at': datetime.now(timezone.utc).isoformat(),
                        'error': error_message,
                    }).encode('utf-8'),
                )
            except Exception as e:
                print(f"  ⚠️ Failed to write alert throttle marker: {e}")

        return True

    except Exception as e:
        print(f"  ⚠️ Failed to send auth-failure alert: {e}")
        return False


def send_email_summary(bills_update, bills_insert, invoices_updated,
                      recipients: Optional[List[str]] = None,
                      execution_time: str = "", invoice_dict: Optional[Dict] = None,
                      payment_dict: Optional[Dict] = None, context: Optional[Any] = None,
                      sync_type: str = 'full', last_run_timestamp: Optional[datetime] = None,
                      invoices_fetched: int = 0, bills_fetched: int = 0,
                      po_sync_results: Optional[Dict] = None) -> bool:
    """
    Send HTML email summary of sync results (run summary - sent after each sync)

    Args:
        bills_update: DataFrame of updated bills
        bills_insert: DataFrame of inserted bills
        invoices_updated: List of updated invoice records
        recipients: List of email addresses (if None, uses run summary recipients from config)
        execution_time: Formatted execution time string
        invoice_dict: Dictionary of invoice statistics
        payment_dict: Dictionary of payment statistics
        context: Lambda context object (optional, for system info collection)
        sync_type: Type of sync ('incremental' or 'full')
        last_run_timestamp: Last run timestamp if incremental sync (optional)
        invoices_fetched: Number of invoices fetched from QuickBooks
        bills_fetched: Number of bills fetched from QuickBooks
        
    Returns:
        True if email sent successfully, False otherwise
    """
    try:
        # Get recipients from config if not provided (run summary list)
        if recipients is None:
            from config import get_email_recipients_run_summary
            recipients = get_email_recipients_run_summary()
        
        # Set defaults for optional parameters
        if invoice_dict is None:
            invoice_dict = {}
        if payment_dict is None:
            payment_dict = {}
        if execution_time == "":
            execution_time = "Unknown"
        
        # Collect system information
        system_info = get_system_info(context)
        
        # Format sync type display (emojis optional/subtle)
        sync_type_display = 'Incremental Sync' if sync_type == 'incremental' else 'Full Sync'
        sync_type_color = '#1e40af' if sync_type == 'incremental' else '#ea580c'  # Orange for full sync to contrast with blue header
        
        # Format last run timestamp if available
        last_run_display = ""
        if last_run_timestamp:
            if isinstance(last_run_timestamp, datetime):
                last_run_display = last_run_timestamp.strftime("%Y-%m-%d %H:%M:%S UTC")
            else:
                last_run_display = str(last_run_timestamp)
        
        # Create message
        msg = MIMEMultipart('alternative')
        
        # Include date in subject for sorting and create new thread per date
        today = date.today().isoformat()  # YYYY-MM-DD
        msg['Subject'] = f'QBsync Run Summary - {today}'
        msg['From'] = 'automation@pioneer-aero.com'
        msg['To'] = ', '.join(recipients)
        
        # Generate Message-ID for this email
        message_id = make_msgid()
        msg['Message-ID'] = message_id
        
        # Get the thread Message-ID from S3 for today's date (for threading in Gmail)
        bucket_name = get_s3_bucket_name()
        thread_message_id = get_thread_message_id(bucket_name, today)
        
        if thread_message_id:
            # This is a follow-up email for today - add threading headers
            msg['In-Reply-To'] = thread_message_id
            msg['References'] = thread_message_id
        else:
            # This is the first email for today - save its Message-ID for future emails today
            save_thread_message_id(str(message_id), bucket_name, today)
        
        # Extract bill rows for template (preview first 10)
        # Layer's compose_sync_report expects dicts with Id, Amount, Vendor__c keys
        bills_update_rows_for_template = []
        for _, row in bills_update.head(10).iterrows():
            bill_id = row['Id'] if 'Id' in row.index and pd.notna(row['Id']) else ''
            bill_name = str(row['Name']) if 'Name' in row.index and pd.notna(row['Name']) else ''
            display_text = bill_name or (f"ID: {bill_id}" if bill_id else 'N/A')
            balance_due = row['Balance_Due__c'] if 'Balance_Due__c' in row.index and pd.notna(row['Balance_Due__c']) else 0
            total_amount = row['Total_Amount__c'] if 'Total_Amount__c' in row.index and pd.notna(row['Total_Amount__c']) else 0
            due_date = str(row['Due_Date__c']) if 'Due_Date__c' in row.index and pd.notna(row['Due_Date__c']) else '\u2014'
            bills_update_rows_for_template.append({
                'Id': bill_id, 'Vendor__c': display_text, 'Amount': total_amount,
                'Balance_Due__c': balance_due, 'Due_Date__c': due_date,
            })

        bills_insert_rows_for_template = []
        for _, row in bills_insert.head(10).iterrows():
            bill_id = row['Id'] if 'Id' in row.index and pd.notna(row['Id']) else ''
            bill_name = str(row['Name']) if 'Name' in row.index and pd.notna(row['Name']) else ''
            display_text = bill_name or (f"ID: {bill_id}" if bill_id else 'N/A')
            total_amount = row['Total_Amount__c'] if 'Total_Amount__c' in row.index and pd.notna(row['Total_Amount__c']) else 0
            balance_due = row['Balance_Due__c'] if 'Balance_Due__c' in row.index and pd.notna(row['Balance_Due__c']) else 0
            bill_date = str(row['Bill_Date__c']) if 'Bill_Date__c' in row.index and pd.notna(row['Bill_Date__c']) else '\u2014'
            bills_insert_rows_for_template.append({
                'Id': bill_id, 'Vendor__c': display_text, 'Amount': total_amount,
                'Balance_Due__c': balance_due, 'Bill_Date__c': bill_date,
            })

        # Build HTML body \u2014 AEROSPACE theme
        po_synced_count = po_sync_results.get('synced', 0) if po_sync_results else 0
        html_body = qb_sync_summary(
            sync_type=sync_type,
            execution_time=execution_time,
            invoices_fetched=invoices_fetched,
            bills_fetched=bills_fetched,
            invoices_updated_count=len(invoices_updated),
            bills_update_count=len(bills_update),
            bills_insert_count=len(bills_insert),
            invoice_total=invoice_dict.get('total', 0),
            payment_total=payment_dict.get('total', 0),
            bills_update_rows=bills_update_rows_for_template or None,
            bills_insert_rows=bills_insert_rows_for_template or None,
            system_info=system_info,
            last_run_display=last_run_display,
            po_synced_count=po_synced_count,
        )

        # Attach HTML body
        html_part = MIMEText(html_body, 'html')
        msg.attach(html_part)
        
        # Send email via SES
        ses = boto3.client('ses', region_name='us-east-1')
        ses.send_raw_email(
            Source='automation@pioneer-aero.com',
            Destinations=recipients,
            RawMessage={'Data': msg.as_string()},
        )
        
        return True
        
    except Exception as e:
        import traceback
        print(f"❌ Email sending failed: {e}")
        traceback.print_exc()
        return False

def find_order_number(text: str) -> Optional[str]:
    """
    Extract order number from text
    
    Args:
        text: Text string that may contain order numbers
        
    Returns:
        Order number string if found, None otherwise
    """
    if pd.isna(text):
        return None
    
    # Look for patterns like PO-XXXXX or RO-XXXXX.
    # Deliberately no bare-digit fallback: it matched stray invoice/account
    # numbers on overhead bills, writing junk Order__c values that then block
    # the fill-only healing on update (never resolves to an RO/PO anyway).
    patterns = [
        r'PO-\d+',
        r'RO-\d+',
        r'SO-\d+',
        r'INV-\d+'
    ]
    
    for pattern in patterns:
        match = re.search(pattern, str(text))
        if match:
            return match.group()
    
    return None

def get_description(text: str) -> str:
    """
    Extract clean description from text by removing order numbers
    
    Args:
        text: Text string that may contain order numbers
        
    Returns:
        Clean description string with order numbers removed
    """
    if pd.isna(text):
        return ""
    
    # Remove order numbers from description
    text = str(text)
    patterns = [
        r'PO-\d+',
        r'RO-\d+',
        r'SO-\d+',
        r'INV-\d+'
    ]
    
    for pattern in patterns:
        text = re.sub(pattern, '', text)
    
    return text.strip()


# ============================================================================
# S3 Functions for Daily Summary Accumulation
# ============================================================================

def get_s3_bucket_name() -> str:
    """
    Get the S3 bucket name from .config file
    
    Returns:
        S3 bucket name string
    """
    from config import get_s3_bucket_name as _get_s3_bucket_from_config
    return _get_s3_bucket_from_config()


def get_thread_message_id(bucket_name: Optional[str] = None, date_str: Optional[str] = None) -> Optional[str]:
    """
    Get the Message-ID of the first email in the thread from S3 for a specific date
    
    Args:
        bucket_name: S3 bucket name (optional, uses config if not provided)
        date_str: Date string in YYYY-MM-DD format (optional, uses today if not provided)
        
    Returns:
        Message-ID string if found, None otherwise
    """
    try:
        if bucket_name is None:
            bucket_name = get_s3_bucket_name()
        
        if date_str is None:
            date_str = date.today().isoformat()
        
        s3_client = boto3.client('s3')
        key = f'email-thread/message-id-{date_str}.txt'
        
        try:
            response = s3_client.get_object(Bucket=bucket_name, Key=key)
            message_id = response['Body'].read().decode('utf-8').strip()
            return message_id if message_id else None
        except ClientError as e:
            if e.response['Error']['Code'] == 'NoSuchKey':
                return None
            raise
    
    except Exception as e:
        print(f"⚠️ Failed to get thread Message-ID from S3: {e}")
        return None


def save_thread_message_id(message_id: str, bucket_name: Optional[str] = None, date_str: Optional[str] = None) -> bool:
    """
    Save the Message-ID of the first email in the thread to S3 for a specific date
    
    Args:
        message_id: Message-ID string to save
        bucket_name: S3 bucket name (optional, uses config if not provided)
        date_str: Date string in YYYY-MM-DD format (optional, uses today if not provided)
        
    Returns:
        True if saved successfully, False otherwise
    """
    try:
        if bucket_name is None:
            bucket_name = get_s3_bucket_name()
        
        if date_str is None:
            date_str = date.today().isoformat()
        
        s3_client = boto3.client('s3')
        key = f'email-thread/message-id-{date_str}.txt'
        
        s3_client.put_object(
            Bucket=bucket_name,
            Key=key,
            Body=message_id.encode('utf-8'),
            ContentType='text/plain'
        )
        
        print(f"✅ Saved thread Message-ID to s3://{bucket_name}/{key}")
        return True
        
    except Exception as e:
        print(f"❌ Failed to save thread Message-ID to S3: {e}")
        import traceback
        traceback.print_exc()
        return False


def parse_execution_time_to_seconds(time_str: str) -> float:
    """
    Parse execution time string (e.g., "2m 30s", "45s", "1h 15m") to seconds
    
    Args:
        time_str: Formatted time string
        
    Returns:
        Time in seconds as float
    """
    if not time_str or time_str == "Unknown":
        return 0.0
    
    total_seconds = 0.0
    
    # Parse hours
    if 'h' in time_str:
        hours_match = re.search(r'(\d+)h', time_str)
        if hours_match:
            total_seconds += int(hours_match.group(1)) * 3600
    
    # Parse minutes
    if 'm' in time_str:
        minutes_match = re.search(r'(\d+)m', time_str)
        if minutes_match:
            total_seconds += int(minutes_match.group(1)) * 60
    
    # Parse seconds
    if 's' in time_str:
        seconds_match = re.search(r'([\d.]+)s', time_str)
        if seconds_match:
            total_seconds += float(seconds_match.group(1))
    
    return total_seconds


def save_daily_summary_to_s3(bills_update_data: List[Dict], bills_insert_data: List[Dict], invoices_updated: List[Dict],
                              bills_insert_sf_ids: Dict[str, str],
                              execution_time: str, run_timestamp: str,
                              bucket_name: Optional[str] = None,
                              context: Optional[Any] = None,
                              sync_type: str = 'full') -> bool:
    """
    Save a single run's summary to S3, accumulating with previous runs for the day
    
    Args:
        bills_update_data: List of dictionaries containing updated bill data (exact format sent to Salesforce)
        bills_insert_data: List of dictionaries containing inserted bill data (exact format sent to Salesforce)
        invoices_updated: List of dictionaries containing updated invoice data (exact format sent to Salesforce)
        bills_insert_sf_ids: Dict mapping QBO_Bill_ID__c to Salesforce Id for inserted bills
        execution_time: Formatted execution time string
        run_timestamp: Timestamp of this run (format: YYYY-MM-DD_HHMMSS)
        bucket_name: S3 bucket name (optional, uses environment variable if not provided)
        context: Lambda context object (optional, for system info collection)
        sync_type: Type of sync ('incremental' or 'full')
        
    Returns:
        True if saved successfully, False otherwise
    """
    try:
        if bucket_name is None:
            bucket_name = get_s3_bucket_name()
        
        s3_client = boto3.client('s3')
        today = date.today().isoformat()  # YYYY-MM-DD
        key = f"daily-summaries/{today}/summary.json"
        
        # Get existing summary for today if it exists
        daily_summary = {
            'date': today,
            'runs': [],
            'total_bills_updated': 0,
            'total_bills_inserted': 0,
            'total_invoices_updated': 0,
            'total_runtime': '0s',  # Will be calculated
            'bills_update_ids': [],
            'bills_insert_ids': [],
            'invoices_update_ids': []
        }
        
        try:
            response = s3_client.get_object(Bucket=bucket_name, Key=key)
            existing_data = json.loads(response['Body'].read().decode('utf-8'))
            daily_summary = existing_data
            # Ensure total_runtime exists for backward compatibility
            if 'total_runtime' not in daily_summary:
                daily_summary['total_runtime'] = '0s'
            # Ensure ID lists exist (for backward compatibility with old format)
            if 'bills_update_ids' not in daily_summary:
                daily_summary['bills_update_ids'] = []
            if 'bills_insert_ids' not in daily_summary:
                daily_summary['bills_insert_ids'] = []
            if 'invoices_update_ids' not in daily_summary:
                daily_summary['invoices_update_ids'] = []
        except ClientError as e:
            if e.response['Error']['Code'] != 'NoSuchKey':
                raise e
            # No existing summary, use empty one
        
        # Extract IDs from the data
        # Bills Update: Extract Salesforce Id from each record
        bills_update_ids_new = [item.get('Id') for item in (bills_update_data if bills_update_data else []) if item.get('Id')]
        
        # Bills Insert: Use Salesforce IDs from bills_insert_sf_ids mapping
        bills_insert_ids_new = list(bills_insert_sf_ids.values()) if bills_insert_sf_ids else []
        
        # Invoices Update: Extract Salesforce Id from each record
        invoices_update_ids_new = [item.get('Id') for item in (invoices_updated if invoices_updated else []) if item.get('Id')]
        
        bills_update_len = len(bills_update_ids_new)
        bills_insert_len = len(bills_insert_ids_new)
        invoices_update_len = len(invoices_update_ids_new)
        
        # Collect system information for this run
        system_info = get_system_info(context)
        
        # Add this run's data
        run_data = {
            'timestamp': run_timestamp,
            'execution_time': execution_time,
            'bills_update_count': bills_update_len,
            'bills_insert_count': bills_insert_len,
            'invoices_updated_count': invoices_update_len,
            'system_info': system_info,
            'sync_type': sync_type  # 'incremental' or 'full'
        }
        
        daily_summary['runs'].append(run_data)
        daily_summary['total_bills_updated'] += bills_update_len
        daily_summary['total_bills_inserted'] += bills_insert_len
        daily_summary['total_invoices_updated'] += invoices_update_len
        
        # Calculate total runtime by summing all execution times
        total_runtime_seconds = 0.0
        for run in daily_summary['runs']:
            total_runtime_seconds += parse_execution_time_to_seconds(run.get('execution_time', '0s'))
        daily_summary['total_runtime'] = format_time(total_runtime_seconds)
        
        # Append new IDs (avoid duplicates)
        existing_bills_update_ids = set(daily_summary['bills_update_ids'])
        for bill_id in bills_update_ids_new:
            if bill_id and bill_id not in existing_bills_update_ids:
                daily_summary['bills_update_ids'].append(bill_id)
                existing_bills_update_ids.add(bill_id)
        
        existing_bills_insert_ids = set(daily_summary['bills_insert_ids'])
        for bill_id in bills_insert_ids_new:
            if bill_id and bill_id not in existing_bills_insert_ids:
                daily_summary['bills_insert_ids'].append(bill_id)
                existing_bills_insert_ids.add(bill_id)
        
        existing_invoice_ids = set(daily_summary['invoices_update_ids'])
        for invoice_id in invoices_update_ids_new:
            if invoice_id and invoice_id not in existing_invoice_ids:
                daily_summary['invoices_update_ids'].append(invoice_id)
                existing_invoice_ids.add(invoice_id)
        
        # Save back to S3
        json_data = json.dumps(daily_summary, default=str, indent=2)
        s3_client.put_object(
            Bucket=bucket_name,
            Key=key,
            Body=json_data.encode('utf-8'),
            ContentType='application/json'
        )
        
        print(f"✅ Saved daily summary to s3://{bucket_name}/{key}")
        return True
        
    except Exception as e:
        print(f"❌ Failed to save daily summary to S3: {e}")
        import traceback
        traceback.print_exc()
        return False


def get_daily_summary_from_s3(date_str: Optional[str] = None, 
                               bucket_name: Optional[str] = None) -> Optional[Dict]:
    """
    Retrieve the daily summary from S3
    
    Args:
        date_str: Date in YYYY-MM-DD format (defaults to today)
        bucket_name: S3 bucket name (optional)
        
    Returns:
        Dictionary containing the daily summary or None if not found
    """
    print(f"[DEBUG] get_daily_summary_from_s3 called with date_str={date_str}, bucket_name={bucket_name}")
    try:
        if bucket_name is None:
            bucket_name = get_s3_bucket_name()
            print(f"[DEBUG] bucket_name was None, got from config: {bucket_name}")
        
        if date_str is None:
            date_str = date.today().isoformat()
            print(f"[DEBUG] date_str was None, using today: {date_str}")
        
        s3_client = boto3.client('s3')
        key = f"daily-summaries/{date_str}/summary.json"
        print(f"[DEBUG] Attempting to get S3 object: bucket={bucket_name}, key={key}")
        
        response = s3_client.get_object(Bucket=bucket_name, Key=key)
        print(f"[DEBUG] S3 get_object successful. ContentLength: {response.get('ContentLength', 'Unknown')}")
        
        data = json.loads(response['Body'].read().decode('utf-8'))
        print(f"[DEBUG] Daily summary JSON parsed successfully. Keys: {list(data.keys()) if data else 'None'}")
        
        return data
        
    except ClientError as e:
        error_code = e.response['Error']['Code']
        print(f"[DEBUG] ClientError from S3: Code={error_code}, Message={e.response['Error'].get('Message', 'No message')}")
        if error_code == 'NoSuchKey':
            print(f"[DEBUG] Key not found in S3: {key}")
            return None
        print(f"[DEBUG] ClientError is not NoSuchKey, re-raising: {e}")
        raise e
    except Exception as e:
        print(f"[DEBUG] Exception in get_daily_summary_from_s3: {type(e).__name__}: {e}")
        print(f"❌ Failed to retrieve daily summary from S3: {e}")
        import traceback
        traceback.print_exc()
        return None


def send_end_of_day_email(date_str: Optional[str] = None,
                         recipients: Optional[List[str]] = None,
                         bucket_name: Optional[str] = None,
                         sf_credentials: Optional[Dict] = None) -> bool:
    """
    Send a richly formatted end-of-day email with all changes accumulated throughout the day
    
    Args:
        date_str: Date in YYYY-MM-DD format (defaults to today)
        recipients: List of email addresses (if None, uses default)
        bucket_name: S3 bucket name (optional)
        sf_credentials: Salesforce credentials dictionary (if None, fetches from Secrets Manager)
        
    Returns:
        True if email sent successfully, False otherwise
    """
    print(f"[DEBUG] send_end_of_day_email called with date_str={date_str}, recipients provided={recipients is not None}, bucket_name={bucket_name}")
    try:
        if date_str is None:
            date_str = date.today().isoformat()
            print(f"[DEBUG] date_str was None, set to today: {date_str}")

        print(f"[DEBUG] Getting daily summary from S3 for date: {date_str}, bucket: {bucket_name}")
        # Get daily summary from S3
        daily_summary = get_daily_summary_from_s3(date_str, bucket_name)

        if daily_summary is None:
            print(f"[DEBUG] ⚠️ No daily summary found for {date_str}")
            return False

        print(f"[DEBUG] Daily summary retrieved successfully. Keys: {list(daily_summary.keys())}")
        print(f"[DEBUG] Runs count: {len(daily_summary.get('runs', []))}")

        # Get recipients from .config file if not provided (daily summary list)
        if recipients is None:
            print("[DEBUG] Recipients not provided, fetching from config...")
            from config import get_email_recipients_daily_summary
            recipients = get_email_recipients_daily_summary()
            print(f"[DEBUG] Recipients retrieved: {recipients}")
        else:
            print(f"[DEBUG] Using provided recipients: {recipients}")
        
        # Get ID lists from S3
        print("[DEBUG] Extracting ID lists from daily summary...")
        bills_update_ids = daily_summary.get('bills_update_ids', [])
        bills_insert_ids = daily_summary.get('bills_insert_ids', [])
        invoices_update_ids = daily_summary.get('invoices_update_ids', [])
        print(f"[DEBUG] ID counts - Bills Updated: {len(bills_update_ids)}, Bills Inserted: {len(bills_insert_ids)}, Invoices Updated: {len(invoices_update_ids)}")
        
        # Get Salesforce credentials if not provided
        if sf_credentials is None:
            print("[DEBUG] Salesforce credentials not provided, fetching from Secrets Manager...")
            try:
                sf_credentials = get_secret('salesforce/credentials')
                print("[DEBUG] Salesforce credentials retrieved")
            except Exception as e:
                print(f"[DEBUG] Failed to get Salesforce credentials: {e}")
                sf_credentials = None
        
        # Initialize data structures for queried records
        bills_update_list = []
        bills_insert_list = []
        invoices_updated = []
        account_id_to_name = {}
        
        # Query Salesforce for records if we have IDs and credentials
        if sf_credentials and (bills_update_ids or bills_insert_ids or invoices_update_ids):
            try:
                from salesforce_connector import SalesforceConnector
                sf = SalesforceConnector(sf_credentials)
                sf.login()
                print("[DEBUG] Salesforce login successful")
                
                all_account_ids = set()
                
                # Query Payment__c records for bills_update_ids
                if bills_update_ids:
                    print("[DEBUG] Querying Salesforce for Bills Updated...")
                    try:
                        # Batch IDs if needed (Salesforce IN clause limit is 10,000)
                        batch_size = 10000
                        for i in range(0, len(bills_update_ids), batch_size):
                            batch_ids = bills_update_ids[i:i+batch_size]
                            id_list = "','".join(batch_ids)
                            bills_df = sf.soql_to_df(f"SELECT Id, Name, Account__c, Balance_Due__c, Bill_Date__c FROM Payment__c WHERE Id IN ('{id_list}')")
                            
                            # Convert to list of dicts
                            for _, row in bills_df.iterrows():
                                bill_dict = {
                                    'Id': row['Id'],
                                    'Name': row.get('Name', ''),
                                    'Account__c': row.get('Account__c', ''),
                                    'Balance_Due__c': row.get('Balance_Due__c', ''),
                                    'Bill_Date__c': row.get('Bill_Date__c', '')
                                }
                                bills_update_list.append(bill_dict)
                                
                                # Collect account IDs
                                account_id = row.get('Account__c', '')
                                if pd.notna(account_id) and account_id:
                                    all_account_ids.add(account_id)
                            
                            print(f"[DEBUG] Retrieved {len(bills_df)} Bills Updated records from batch {i//batch_size + 1}")
                    except Exception as e:
                        print(f"[DEBUG] Error querying Bills Updated from Salesforce: {e}")
                        import traceback
                        traceback.print_exc()
                
                # Query Payment__c records for bills_insert_ids
                if bills_insert_ids:
                    print("[DEBUG] Querying Salesforce for Bills Inserted...")
                    try:
                        batch_size = 10000
                        for i in range(0, len(bills_insert_ids), batch_size):
                            batch_ids = bills_insert_ids[i:i+batch_size]
                            id_list = "','".join(batch_ids)
                            bills_df = sf.soql_to_df(f"SELECT Id, Name, Account__c, Balance_Due__c, Bill_Date__c FROM Payment__c WHERE Id IN ('{id_list}')")
                            
                            # Convert to list of dicts
                            for _, row in bills_df.iterrows():
                                bill_dict = {
                                    'Id': row['Id'],
                                    'Name': row.get('Name', ''),
                                    'Account__c': row.get('Account__c', ''),
                                    'Balance_Due__c': row.get('Balance_Due__c', ''),
                                    'Bill_Date__c': row.get('Bill_Date__c', '')
                                }
                                bills_insert_list.append(bill_dict)
                                
                                # Collect account IDs
                                account_id = row.get('Account__c', '')
                                if pd.notna(account_id) and account_id:
                                    all_account_ids.add(account_id)
                            
                            print(f"[DEBUG] Retrieved {len(bills_df)} Bills Inserted records from batch {i//batch_size + 1}")
                    except Exception as e:
                        print(f"[DEBUG] Error querying Bills Inserted from Salesforce: {e}")
                        import traceback
                        traceback.print_exc()
                
                # Query inscor__Invoice__c records
                if invoices_update_ids:
                    print("[DEBUG] Querying Salesforce for Invoices Updated...")
                    try:
                        batch_size = 10000
                        for i in range(0, len(invoices_update_ids), batch_size):
                            batch_ids = invoices_update_ids[i:i+batch_size]
                            id_list = "','".join(batch_ids)
                            invoices_df = sf.soql_to_df(f"SELECT Id, Name, inscor__Account__c, inscor__Invoice_Date__c, Invoice_Balance__c FROM inscor__Invoice__c WHERE Id IN ('{id_list}')")
                            
                            # Convert to list of dicts
                            for _, row in invoices_df.iterrows():
                                invoice_dict = {
                                    'Id': row['Id'],
                                    'Name': row.get('Name', ''),
                                    'inscor__Account__c': row.get('inscor__Account__c', ''),
                                    'inscor__Invoice_Date__c': row.get('inscor__Invoice_Date__c', ''),
                                    'Invoice_Balance__c': row.get('Invoice_Balance__c', '')
                                }
                                invoices_updated.append(invoice_dict)
                                
                                # Collect account IDs
                                account_id = row.get('inscor__Account__c', '')
                                if pd.notna(account_id) and account_id:
                                    all_account_ids.add(account_id)
                            
                            print(f"[DEBUG] Retrieved {len(invoices_df)} Invoices Updated records from batch {i//batch_size + 1}")
                    except Exception as e:
                        print(f"[DEBUG] Error querying Invoices Updated from Salesforce: {e}")
                        import traceback
                        traceback.print_exc()
                
                # Query Account objects to get names
                if all_account_ids:
                    print(f"[DEBUG] Querying {len(all_account_ids)} Account objects for names...")
                    try:
                        account_ids_list = list(all_account_ids)
                        batch_size = 10000
                        for i in range(0, len(account_ids_list), batch_size):
                            batch_ids = account_ids_list[i:i+batch_size]
                            id_list = "','".join(batch_ids)
                            accounts_df = sf.soql_to_df(f"SELECT Id, Name FROM Account WHERE Id IN ('{id_list}')")
                            
                            # Create account ID to name mapping
                            for _, row in accounts_df.iterrows():
                                account_id = row['Id']
                                account_name = row.get('Name', '')
                                if pd.notna(account_name):
                                    account_id_to_name[account_id] = account_name
                            
                            print(f"[DEBUG] Retrieved {len(accounts_df)} Account records from batch {i//batch_size + 1}")
                    except Exception as e:
                        print(f"[DEBUG] Error querying Account objects from Salesforce: {e}")
                        import traceback
                        traceback.print_exc()
                
                # Replace account IDs with account names in the queried data
                print("[DEBUG] Replacing account IDs with account names...")
                for bill in bills_update_list:
                    account_id = bill.get('Account__c', '')
                    if account_id and account_id in account_id_to_name:
                        bill['Account__c_Name'] = account_id_to_name[account_id]
                
                for bill in bills_insert_list:
                    account_id = bill.get('Account__c', '')
                    if account_id and account_id in account_id_to_name:
                        bill['Account__c_Name'] = account_id_to_name[account_id]
                
                for invoice in invoices_updated:
                    account_id = invoice.get('inscor__Account__c', '')
                    if account_id and account_id in account_id_to_name:
                        invoice['inscor__Account__c_Name'] = account_id_to_name[account_id]
                
                print(f"[DEBUG] Query complete - Bills Updated: {len(bills_update_list)}, Bills Inserted: {len(bills_insert_list)}, Invoices Updated: {len(invoices_updated)}")
                
            except Exception as e:
                print(f"[DEBUG] Error initializing Salesforce connector: {e}")
                import traceback
                traceback.print_exc()
        else:
            if not sf_credentials:
                print("[DEBUG] ⚠️ No Salesforce credentials available, cannot query records")
            else:
                print("[DEBUG] No IDs to query from Salesforce")
        
        # Salesforce base URL
        salesforce_base_url = 'https://pioneer-aero.lightning.force.com/'
        
        # Create message
        print("[DEBUG] Creating email message...")
        msg = MIMEMultipart('alternative')
        msg['Subject'] = f'QBsync Daily Summary - {date_str}'
        msg['From'] = 'automation@pioneer-aero.com'
        msg['To'] = ', '.join(recipients)
        print(f"[DEBUG] Message created - Subject: {msg['Subject']}, From: {msg['From']}, To: {msg['To']}")
        
        # Format date for display
        display_date = datetime.strptime(date_str, '%Y-%m-%d').strftime('%B %d, %Y')
        
        # Extract rows for AEROSPACE template
        bills_update_rows_eod = [
            (
                bill.get('Name', '') or (f"ID: {bill.get('Id', 'N/A')}"),
                bill.get('Id', ''),
                bill.get('Account__c_Name', '') or '\u2014',
                bill.get('Balance_Due__c', 0) or 0,
                str(bill.get('Bill_Date__c', '')) or '\u2014',
            )
            for bill in bills_update_list
        ]

        bills_insert_rows_eod = [
            (
                bill.get('Name', '') or (f"ID: {bill.get('Id', 'N/A')}"),
                bill.get('Id', ''),
                bill.get('Account__c_Name', '') or '\u2014',
                bill.get('Balance_Due__c', 0) or 0,
                str(bill.get('Bill_Date__c', '')) or '\u2014',
            )
            for bill in bills_insert_list
        ]

        invoices_updated_rows_eod = [
            (
                inv.get('Name', '') or (f"ID: {inv.get('Id', 'N/A')}"),
                inv.get('Id', ''),
                inv.get('inscor__Account__c_Name', '') or '\u2014',
                inv.get('Invoice_Balance__c', 0) or 0,
                str(inv.get('inscor__Invoice_Date__c', '')) or '\u2014',
            )
            for inv in invoices_updated
        ]

        run_log_eod = [
            (
                run.get('timestamp', ''),
                run.get('sync_type', 'full'),
                run.get('bills_update_count', 0) + run.get('bills_insert_count', 0),
                run.get('invoices_updated_count', 0),
            )
            for run in daily_summary.get('runs', [])
        ]

        # Build HTML body \u2014 AEROSPACE theme
        print("[DEBUG] Building HTML email body...")
        html_body = qb_eod_summary(
            date_str=date_str,
            total_runs=len(daily_summary.get('runs', [])),
            bills_update_count=daily_summary.get('total_bills_updated', 0),
            bills_insert_count=daily_summary.get('total_bills_inserted', 0),
            invoices_updated_count=daily_summary.get('total_invoices_updated', 0),
            bills_update_rows=bills_update_rows_eod or None,
            bills_insert_rows=bills_insert_rows_eod or None,
            invoices_updated_rows=invoices_updated_rows_eod or None,
            run_log=run_log_eod or None,
        )
        print(f"[DEBUG] HTML body built. Length: {len(html_body)} characters")

        # Attach HTML body
        print("[DEBUG] Attaching HTML body to message...")
        html_part = MIMEText(html_body, 'html')
        msg.attach(html_part)
        print(f"[DEBUG] HTML body attached. HTML length: {len(html_body)} characters")
        
        # Create CSV files and ZIP attachment
        total_records = len(bills_update_list) + len(bills_insert_list) + len(invoices_updated)
        print(f"[DEBUG] Creating ZIP attachment. Total records: {total_records}")
        if total_records > 0:
            zip_buffer = io.BytesIO()
            
            with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
                # Create bills_updated.csv
                if len(bills_update_list) > 0:
                    bills_update_df = pd.DataFrame(bills_update_list)
                    csv_buffer = io.StringIO()
                    bills_update_df.to_csv(csv_buffer, index=False)
                    zip_file.writestr('bills_updated.csv', csv_buffer.getvalue())
                
                # Create bills_inserted.csv
                if len(bills_insert_list) > 0:
                    bills_insert_df = pd.DataFrame(bills_insert_list)
                    csv_buffer = io.StringIO()
                    bills_insert_df.to_csv(csv_buffer, index=False)
                    zip_file.writestr('bills_inserted.csv', csv_buffer.getvalue())
                
                # Create invoices_updated.csv
                if len(invoices_updated) > 0:
                    invoices_df = pd.DataFrame(invoices_updated)
                    csv_buffer = io.StringIO()
                    invoices_df.to_csv(csv_buffer, index=False)
                    zip_file.writestr('invoices_updated.csv', csv_buffer.getvalue())
            
            # Attach ZIP file
            zip_buffer.seek(0)
            zip_size = len(zip_buffer.getvalue())
            zip_attachment = MIMEApplication(zip_buffer.read(), _subtype='zip')
            zip_attachment.add_header('Content-Disposition', 'attachment', filename=f'qb-sync-data-{date_str}.zip')
            msg.attach(zip_attachment)
            print(f"[DEBUG] ZIP attachment added. Size: {zip_size} bytes")
        else:
            print("[DEBUG] No records to attach, skipping ZIP file")
        
        # Send email via SES
        print("[DEBUG] Sending email via SES...")
        ses = boto3.client('ses', region_name='us-east-1')
        ses.send_raw_email(
            Source='automation@pioneer-aero.com',
            Destinations=recipients,
            RawMessage={'Data': msg.as_string()},
        )
        print("[DEBUG] Message sent successfully via SES")
        
        print(f"✅ End-of-day email sent successfully for {date_str}")
        return True
        
    except Exception as e:
        print(f"[DEBUG] ❌ Exception caught in send_end_of_day_email: {type(e).__name__}: {e}")
        print(f"❌ End-of-day email sending failed: {e}")
        import traceback
        print("[DEBUG] Full traceback:")
        traceback.print_exc()
        return False


def get_last_run_timestamp(bucket_name: Optional[str] = None) -> Optional[datetime]:
    """
    Retrieve the last run timestamp from S3
    
    Args:
        bucket_name: S3 bucket name (optional, uses config if not provided)
        
    Returns:
        datetime object of last run timestamp, or None if not found or error
    """
    try:
        if bucket_name is None:
            bucket_name = get_s3_bucket_name()
        
        s3_client = boto3.client('s3')
        key = 'last-run-timestamp.json'
        
        try:
            response = s3_client.get_object(Bucket=bucket_name, Key=key)
            data = json.loads(response['Body'].read().decode('utf-8'))
            timestamp_str = data.get('last_run_timestamp')
            
            if timestamp_str:
                # Parse ISO 8601 format timestamp
                # Handle both with and without timezone
                if timestamp_str.endswith('Z'):
                    timestamp_str = timestamp_str[:-1] + '+00:00'
                dt = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                # Ensure timezone-aware (convert to UTC if naive)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                else:
                    dt = dt.astimezone(timezone.utc)
                return dt
            else:
                print("⚠️ Last run timestamp file exists but has no timestamp value")
                return None
                
        except ClientError as e:
            if e.response['Error']['Code'] == 'NoSuchKey':
                print("ℹ️ No previous run timestamp found (first run or incremental sync disabled)")
                return None
            else:
                print(f"⚠️ Error retrieving last run timestamp from S3: {e}")
                return None
                
    except Exception as e:
        print(f"⚠️ Failed to get last run timestamp: {e}")
        return None


def save_last_run_timestamp(timestamp: datetime, bucket_name: Optional[str] = None) -> bool:
    """
    Save the current run timestamp to S3
    
    Args:
        timestamp: datetime object to save (will be converted to UTC)
        bucket_name: S3 bucket name (optional, uses config if not provided)
        
    Returns:
        True if saved successfully, False otherwise
    """
    try:
        if bucket_name is None:
            bucket_name = get_s3_bucket_name()
        
        # Ensure timestamp is in UTC
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        else:
            timestamp = timestamp.astimezone(timezone.utc)
        
        s3_client = boto3.client('s3')
        key = 'last-run-timestamp.json'
        
        # Format as ISO 8601 with Z suffix for UTC
        timestamp_str = timestamp.strftime('%Y-%m-%dT%H:%M:%SZ')
        
        data = {
            'last_run_timestamp': timestamp_str,
            'updated_at': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
        }
        
        json_data = json.dumps(data, indent=2)
        s3_client.put_object(
            Bucket=bucket_name,
            Key=key,
            Body=json_data.encode('utf-8'),
            ContentType='application/json'
        )
        
        print(f"✅ Saved last run timestamp to S3: {timestamp_str}")
        return True
        
    except Exception as e:
        print(f"⚠️ Failed to save last run timestamp to S3: {e}")
        import traceback
        traceback.print_exc()
        return False