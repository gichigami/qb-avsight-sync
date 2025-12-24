"""
Utility functions for QB-AvSight sync
Includes email notifications, time formatting, and AWS Secrets Manager operations
"""

import boto3
import json
import os
import smtplib
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

# DEBUG logging control - set DEBUG_LOGGING=true in Lambda environment to enable
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
        return dt_utc.strftime("%I:%M %p GMT").lstrip('0')
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


def send_email_summary(bills_update, bills_insert, invoices_updated, 
                      smtp_config: Dict, recipients: Optional[List[str]] = None, 
                      execution_time: str = "", invoice_dict: Optional[Dict] = None, 
                      payment_dict: Optional[Dict] = None, context: Optional[Any] = None,
                      sync_type: str = 'full', last_run_timestamp: Optional[datetime] = None,
                      invoices_fetched: int = 0, bills_fetched: int = 0) -> bool:
    """
    Send HTML email summary of sync results (run summary - sent after each sync)
    
    Args:
        bills_update: DataFrame of updated bills
        bills_insert: DataFrame of inserted bills
        invoices_updated: List of updated invoice records
        smtp_config: SMTP configuration dictionary
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
        
        # Format sync type display
        sync_type_display = '🔄 Incremental Sync' if sync_type == 'incremental' else '📥 Full Sync'
        sync_type_color = '#17a2b8' if sync_type == 'incremental' else '#667eea'
        
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
        msg['From'] = smtp_config['from_email']
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
        
        # Build HTML body
        html_body = f"""
        <html>
        <head>
            <style>
                body {{
                    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                    line-height: 1.6;
                    color: #333;
                    max-width: 800px;
                    margin: 0 auto;
                    padding: 20px;
                }}
                .header {{
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    color: white;
                    padding: 30px;
                    border-radius: 10px;
                    margin-bottom: 30px;
                    text-align: center;
                }}
                .sync-badge {{
                    display: inline-block;
                    background: {sync_type_color};
                    color: white;
                    padding: 8px 16px;
                    border-radius: 20px;
                    font-size: 14px;
                    font-weight: 600;
                    margin: 10px 0;
                }}
                .system-info-table td {{
                    padding: 8px 15px;
                    border-bottom: 1px solid #c8e6c9;
                }}
                .system-info-table tr:last-child td {{
                    border-bottom: none;
                }}
                .stat-grid {{
                    display: grid;
                    grid-template-columns: repeat(2, 1fr);
                    gap: 20px;
                    margin-bottom: 30px;
                }}
                .stat-card {{
                    background: #f8f9fa;
                    padding: 20px;
                    border-radius: 8px;
                    border-left: 4px solid #667eea;
                }}
                .stat-number {{
                    font-size: 32px;
                    font-weight: bold;
                    color: #667eea;
                    margin: 10px 0;
                }}
                .stat-label {{
                    color: #666;
                    font-size: 14px;
                    text-transform: uppercase;
                    letter-spacing: 1px;
                }}
                .section {{
                    background: white;
                    padding: 25px;
                    margin-bottom: 20px;
                    border-radius: 8px;
                    box-shadow: 0 2px 4px rgba(0,0,0,0.1);
                }}
                .section-title {{
                    color: #667eea;
                    font-size: 18px;
                    font-weight: bold;
                    margin-bottom: 15px;
                    padding-bottom: 10px;
                    border-bottom: 2px solid #e9ecef;
                }}
                table {{
                    width: 100%;
                    border-collapse: collapse;
                    margin-top: 15px;
                }}
                th {{
                    background: #667eea;
                    color: white;
                    padding: 12px;
                    text-align: left;
                    font-weight: 600;
                }}
                td {{
                    padding: 10px 12px;
                    border-bottom: 1px solid #e9ecef;
                }}
                tr:hover {{
                    background: #f8f9fa;
                }}
                .footer {{
                    text-align: center;
                    padding: 20px;
                    color: #666;
                    font-size: 12px;
                    border-top: 1px solid #e9ecef;
                    margin-top: 30px;
                }}
                .success {{ color: #28a745; font-weight: bold; }}
                .info {{ color: #17a2b8; }}
                .system-info {{
                    background: #e7f3ff;
                    border-left: 4px solid #17a2b8;
                    padding: 0;
                    margin: 20px 0;
                    border-radius: 5px;
                    overflow: hidden;
                }}
                .system-info-table {{
                    width: 100%;
                    border-collapse: collapse;
                }}
                .system-info-table td {{
                    padding: 8px 15px;
                    border-bottom: 1px solid #d0e7ff;
                }}
                .system-info-table tr:last-child td {{
                    border-bottom: none;
                }}
                .system-info-label {{
                    font-weight: 600;
                    color: #495057;
                    width: 40%;
                }}
                .system-info-value {{
                    color: #212529;
                    text-align: right;
                }}
            </style>
        </head>
        <body>
            <div class="header">
                <h1>🔄 QBsync Complete</h1>
                <div class="sync-badge">{sync_type_display}</div>
                <p style="margin: 10px 0 0 0; font-size: 14px; opacity: 0.9;">
                    {datetime.now().strftime("%B %d, %Y at %I:%M %p")}
                </p>
            </div>
            
            <div class="section">
                <div class="section-title">📊 Sync Details</div>
                <div class="system-info">
                    <table class="system-info-table">
                        <tr>
                            <td class="system-info-label">Sync Type:</td>
                            <td class="system-info-value"><strong>{sync_type_display}</strong></td>
                        </tr>
                        <tr>
                            <td class="system-info-label">Execution Time:</td>
                            <td class="system-info-value"><strong>{execution_time}</strong></td>
                        </tr>
                        {f'<tr><td class="system-info-label">Last Run Timestamp:</td><td class="system-info-value">{last_run_display}</td></tr>' if last_run_display else ''}
                        <tr>
                            <td class="system-info-label">Invoices Fetched from QuickBooks:</td>
                            <td class="system-info-value"><strong>{invoices_fetched:,}</strong></td>
                        </tr>
                        <tr>
                            <td class="system-info-label">Bills Fetched from QuickBooks:</td>
                            <td class="system-info-value"><strong>{bills_fetched:,}</strong></td>
                        </tr>
                        <tr>
                            <td class="system-info-label">Invoices Updated in Salesforce:</td>
                            <td class="system-info-value"><strong>{len(invoices_updated):,}</strong></td>
                        </tr>
                        <tr>
                            <td class="system-info-label">Bills Updated in Salesforce:</td>
                            <td class="system-info-value"><strong>{len(bills_update):,}</strong></td>
                        </tr>
                        <tr>
                            <td class="system-info-label">Bills Inserted in Salesforce:</td>
                            <td class="system-info-value"><strong>{len(bills_insert):,}</strong></td>
                        </tr>
                    </table>
                </div>
            </div>
            
            <div class="stat-grid">
                <div class="stat-card">
                    <div class="stat-label">Total QB Invoices</div>
                    <div class="stat-number">{invoice_dict.get('total', 0):,}</div>
                </div>
                <div class="stat-card">
                    <div class="stat-label">Total QB Bills</div>
                    <div class="stat-number">{payment_dict.get('total', 0):,}</div>
                </div>
                <div class="stat-card">
                    <div class="stat-label">Invoices Updated</div>
                    <div class="stat-number">{len(invoices_updated):,}</div>
                </div>
                <div class="stat-card">
                    <div class="stat-label">Bills Processed</div>
                    <div class="stat-number">{len(bills_update) + len(bills_insert):,}</div>
                </div>
            </div>
            
            <div class="section">
                <div class="section-title">💻 System Information</div>
                <div class="system-info">
                    <table class="system-info-table">
                        <tr>
                            <td class="system-info-label">Execution Environment:</td>
                            <td class="system-info-value"><strong>{system_info.get('environment', 'Unknown')}</strong></td>
                        </tr>
                        <tr>
                            <td class="system-info-label">Hostname/Computer:</td>
                            <td class="system-info-value">{system_info.get('hostname', 'Unknown')}</td>
                        </tr>
                        <tr>
                            <td class="system-info-label">Operating System:</td>
                            <td class="system-info-value">{system_info.get('os', 'Unknown')}</td>
                        </tr>
                        <tr>
                            <td class="system-info-label">OS Architecture:</td>
                            <td class="system-info-value">{system_info.get('os_arch', 'Unknown')}</td>
                        </tr>
                        <tr>
                            <td class="system-info-label">Python Version:</td>
                            <td class="system-info-value">{system_info.get('python_version', 'Unknown')} ({system_info.get('python_implementation', 'Unknown')})</td>
                        </tr>
        """
        
        # Add Lambda-specific info if running on AWS
        if system_info.get('environment') == 'AWS Lambda':
            html_body += f"""
                        <tr>
                            <td class="system-info-label">Lambda Function:</td>
                            <td class="system-info-value">{system_info.get('lambda_function_name', 'Unknown')}</td>
                        </tr>
                        <tr>
                            <td class="system-info-label">Lambda Region:</td>
                            <td class="system-info-value">{system_info.get('lambda_region', 'Unknown')}</td>
                        </tr>
                        <tr>
                            <td class="system-info-label">Memory Limit:</td>
                            <td class="system-info-value">{system_info.get('lambda_memory_mb', 'Unknown')} MB</td>
                        </tr>
            """
        else:
            # Add local system info
            if system_info.get('cpu_count') != 'Unknown':
                html_body += f"""
                        <tr>
                            <td class="system-info-label">CPU Count:</td>
                            <td class="system-info-value">{system_info.get('cpu_count', 'Unknown')}</td>
                        </tr>
                """
            if system_info.get('processor') != 'Unknown':
                html_body += f"""
                        <tr>
                            <td class="system-info-label">Processor:</td>
                            <td class="system-info-value">{system_info.get('processor', 'Unknown')}</td>
                        </tr>
                """
            if 'total_memory_gb' in system_info:
                html_body += f"""
                        <tr>
                            <td class="system-info-label">Total Memory:</td>
                            <td class="system-info-value">{system_info.get('total_memory_gb', 'Unknown')} GB</td>
                        </tr>
                        <tr>
                            <td class="system-info-label">Available Memory:</td>
                            <td class="system-info-value">{system_info.get('available_memory_gb', 'Unknown')} GB</td>
                        </tr>
                """
        
        html_body += """
                    </table>
                </div>
            </div>
        """
        
        # Bills updated section
        if len(bills_update) > 0:
            html_body += f"""
            <div class="section">
                <div class="section-title">📝 Bills Updated ({len(bills_update)})</div>
                <table>
                    <tr>
                        <th>QB Bill ID</th>
                        <th>Balance Due</th>
                        <th>Total Amount</th>
                        <th>Due Date</th>
                    </tr>
            """
            for _, row in bills_update.head(10).iterrows():
                html_body += f"""
                    <tr>
                        <td>{row.get('QBO_Bill_ID__c', 'N/A')}</td>
                        <td>${row.get('Balance_Due__c', 0):,.2f}</td>
                        <td>${row.get('Total_Amount__c', 0):,.2f}</td>
                        <td>{row.get('Due_Date__c', 'N/A')}</td>
                    </tr>
                """
            
            if len(bills_update) > 10:
                html_body += f"""
                    <tr>
                        <td colspan="4" style="text-align: center; font-style: italic; color: #666;">
                            ... and {len(bills_update) - 10} more
                        </td>
                    </tr>
                """
            html_body += "</table></div>"
        
        # Bills inserted section
        if len(bills_insert) > 0:
            html_body += f"""
            <div class="section">
                <div class="section-title">➕ New Bills Inserted ({len(bills_insert)})</div>
                <table>
                    <tr>
                        <th>QB Bill ID</th>
                        <th>Total Amount</th>
                        <th>Balance Due</th>
                        <th>Bill Date</th>
                    </tr>
            """
            for _, row in bills_insert.head(10).iterrows():
                html_body += f"""
                    <tr>
                        <td>{row.get('QBO_Bill_ID__c', 'N/A')}</td>
                        <td>${row.get('Total_Amount__c', 0):,.2f}</td>
                        <td>${row.get('Balance_Due__c', 0):,.2f}</td>
                        <td>{row.get('Bill_Date__c', 'N/A')}</td>
                    </tr>
                """
            
            if len(bills_insert) > 10:
                html_body += f"""
                    <tr>
                        <td colspan="4" style="text-align: center; font-style: italic; color: #666;">
                            ... and {len(bills_insert) - 10} more
                        </td>
                    </tr>
                """
            html_body += "</table></div>"
        
        # Footer
        html_body += f"""
            <div class="footer">
                <p class="success">✅ Sync completed in {execution_time}</p>
                <p>This is an automated message from the qb-avsight-sync system</p>
            </div>
        </body>
        </html>
        """
        
        # Attach HTML body
        html_part = MIMEText(html_body, 'html')
        msg.attach(html_part)
        
        # Send email
        with smtplib.SMTP(smtp_config['server'], smtp_config['port']) as server:
            server.starttls()
            server.login(smtp_config['username'], smtp_config['password'])
            server.send_message(msg)
        
        return True
        
    except Exception as e:
        print(f"❌ Email sending failed: {e}")
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
    
    # Look for patterns like PO-XXXXX or RO-XXXXX
    patterns = [
        r'PO-\d+',
        r'RO-\d+',
        r'SO-\d+',
        r'INV-\d+',
        r'\b\d{5,}\b'  # Any 5+ digit number
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


def format_execution_time_mmss(time_str: str) -> str:
    """
    Format execution time string to MM:SS format
    
    Args:
        time_str: Execution time string (e.g., "7m 10s", "3s", "1h 15m")
        
    Returns:
        Formatted string like "7:10" or "0:03"
    """
    if not time_str or time_str == "Unknown":
        return "0:00"
    
    total_seconds = parse_execution_time_to_seconds(time_str)
    minutes = int(total_seconds // 60)
    seconds = int(total_seconds % 60)
    
    return f"{minutes}:{seconds:02d}"


def save_daily_summary_to_s3(bills_update_data: List[Dict], bills_insert_data: List[Dict], invoices_updated: List[Dict],
                              bills_update_names: Dict[str, str], bills_update_account_names: Dict[str, str],
                              bills_insert_names: Dict[str, str], bills_insert_memos: Dict[str, str], bills_insert_account_names: Dict[str, str],
                              bills_insert_sf_ids: Dict[str, str], invoices_account_names: Dict[str, str],
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
        bills_update_names: Dict mapping bill ID to Name for updated bills
        bills_update_account_names: Dict mapping bill ID to Account Name for updated bills
        bills_insert_names: Dict mapping QBO_Bill_ID__c to Name for inserted bills
        bills_insert_memos: Dict mapping QBO_Bill_ID__c to Memo__c for inserted bills
        bills_insert_account_names: Dict mapping QBO_Bill_ID__c to Account Name for inserted bills
        bills_insert_sf_ids: Dict mapping QBO_Bill_ID__c to Salesforce Id for inserted bills
        invoices_account_names: Dict mapping invoice ID to Account Name
        execution_time: Formatted execution time string
        run_timestamp: Timestamp of this run (format: YYYY-MM-DD_HHMMSS)
        bucket_name: S3 bucket name (optional, uses environment variable if not provided)
        context: Lambda context object (optional, for system info collection)
        
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
            'all_bills_update': [],
            'all_bills_insert': [],
            'all_invoices_updated': [],
            'bills_update_metadata': {'names': {}, 'account_names': {}},
            'bills_insert_metadata': {'names': {}, 'memos': {}, 'account_names': {}, 'sf_ids': {}},
            'invoices_metadata': {'account_names': {}}
        }
        
        try:
            response = s3_client.get_object(Bucket=bucket_name, Key=key)
            existing_data = json.loads(response['Body'].read().decode('utf-8'))
            daily_summary = existing_data
            # Ensure total_runtime exists for backward compatibility
            if 'total_runtime' not in daily_summary:
                daily_summary['total_runtime'] = '0s'
            # Ensure metadata structures exist for backward compatibility
            if 'bills_update_metadata' not in daily_summary:
                daily_summary['bills_update_metadata'] = {'names': {}, 'account_names': {}}
            if 'bills_insert_metadata' not in daily_summary:
                daily_summary['bills_insert_metadata'] = {'names': {}, 'memos': {}, 'account_names': {}, 'sf_ids': {}}
            if 'invoices_metadata' not in daily_summary:
                daily_summary['invoices_metadata'] = {'account_names': {}}
        except ClientError as e:
            if e.response['Error']['Code'] != 'NoSuchKey':
                raise e
            # No existing summary, use empty one
        
        # Data is already in list of dicts format (exact format sent to Salesforce API)
        bills_update_list = bills_update_data if bills_update_data else []
        bills_insert_list = bills_insert_data if bills_insert_data else []
        bills_update_len = len(bills_update_list)
        bills_insert_len = len(bills_insert_list)
        
        # Collect system information for this run
        system_info = get_system_info(context)
        
        # Add this run's data
        run_data = {
            'timestamp': run_timestamp,
            'execution_time': execution_time,
            'bills_update_count': bills_update_len,
            'bills_insert_count': bills_insert_len,
            'invoices_updated_count': len(invoices_updated) if invoices_updated else 0,
            'system_info': system_info,
            'sync_type': sync_type  # 'incremental' or 'full'
        }
        
        daily_summary['runs'].append(run_data)
        daily_summary['total_bills_updated'] += bills_update_len
        daily_summary['total_bills_inserted'] += bills_insert_len
        daily_summary['total_invoices_updated'] += len(invoices_updated) if invoices_updated else 0
        
        # Calculate total runtime by summing all execution times
        total_runtime_seconds = 0.0
        for run in daily_summary['runs']:
            total_runtime_seconds += parse_execution_time_to_seconds(run.get('execution_time', '0s'))
        daily_summary['total_runtime'] = format_time(total_runtime_seconds)
        
        # Append all records (avoid duplicates by checking QBO_Bill_ID__c or Id)
        existing_bill_ids = {item.get('QBO_Bill_ID__c') for item in daily_summary['all_bills_update']}
        for item in bills_update_list:
            if item.get('QBO_Bill_ID__c') not in existing_bill_ids:
                daily_summary['all_bills_update'].append(item)
                existing_bill_ids.add(item.get('QBO_Bill_ID__c'))
        
        existing_bill_ids = {item.get('QBO_Bill_ID__c') for item in daily_summary['all_bills_insert']}
        for item in bills_insert_list:
            if item.get('QBO_Bill_ID__c') not in existing_bill_ids:
                daily_summary['all_bills_insert'].append(item)
                existing_bill_ids.add(item.get('QBO_Bill_ID__c'))
        
        existing_invoice_ids = {item.get('Id') for item in daily_summary['all_invoices_updated']}
        for item in invoices_updated:
            if item.get('Id') not in existing_invoice_ids:
                daily_summary['all_invoices_updated'].append(item)
                existing_invoice_ids.add(item.get('Id'))
        
        # Merge metadata (new metadata overwrites existing for same IDs)
        daily_summary['bills_update_metadata']['names'].update(bills_update_names)
        daily_summary['bills_update_metadata']['account_names'].update(bills_update_account_names)
        daily_summary['bills_insert_metadata']['names'].update(bills_insert_names)
        daily_summary['bills_insert_metadata']['memos'].update(bills_insert_memos)
        daily_summary['bills_insert_metadata']['account_names'].update(bills_insert_account_names)
        daily_summary['bills_insert_metadata']['sf_ids'].update(bills_insert_sf_ids)
        daily_summary['invoices_metadata']['account_names'].update(invoices_account_names)
        
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
    debug_print(f"get_daily_summary_from_s3 called with date_str={date_str}, bucket_name={bucket_name}")
    try:
        if bucket_name is None:
            bucket_name = get_s3_bucket_name()
            debug_print(f"bucket_name was None, got from config: {bucket_name}")
        
        if date_str is None:
            date_str = date.today().isoformat()
            debug_print(f"date_str was None, using today: {date_str}")
        
        s3_client = boto3.client('s3')
        key = f"daily-summaries/{date_str}/summary.json"
        debug_print(f"Attempting to get S3 object: bucket={bucket_name}, key={key}")
        
        response = s3_client.get_object(Bucket=bucket_name, Key=key)
        debug_print(f"S3 get_object successful. ContentLength: {response.get('ContentLength', 'Unknown')}")
        
        data = json.loads(response['Body'].read().decode('utf-8'))
        debug_print(f"Daily summary JSON parsed successfully. Keys: {list(data.keys()) if data else 'None'}")
        
        return data
        
    except ClientError as e:
        error_code = e.response['Error']['Code']
        debug_print(f"ClientError from S3: Code={error_code}, Message={e.response['Error'].get('Message', 'No message')}")
        if error_code == 'NoSuchKey':
            debug_print(f"Key not found in S3: {key}")
            return None
        debug_print(f"ClientError is not NoSuchKey, re-raising: {e}")
        raise e
    except Exception as e:
        debug_print(f"Exception in get_daily_summary_from_s3: {type(e).__name__}: {e}")
        print(f"❌ Failed to retrieve daily summary from S3: {e}")
        import traceback
        traceback.print_exc()
        return None


def send_end_of_day_email(date_str: Optional[str] = None,
                         smtp_config: Optional[Dict] = None,
                         recipients: Optional[List[str]] = None,
                         bucket_name: Optional[str] = None,
                         sf_credentials: Optional[Dict] = None) -> bool:
    """
    Send a richly formatted end-of-day email with all changes accumulated throughout the day
    
    Args:
        date_str: Date in YYYY-MM-DD format (defaults to today)
        smtp_config: SMTP configuration dictionary (if None, fetches from Secrets Manager)
        recipients: List of email addresses (if None, uses default)
        bucket_name: S3 bucket name (optional)
        sf_credentials: Salesforce credentials dictionary (if None, fetches from Secrets Manager)
        
    Returns:
        True if email sent successfully, False otherwise
    """
    # Helper function to format currency values
    def format_currency(value):
        if value is None or value == '':
            return '$0.00'
        try:
            float_val = float(value)
            if float_val == 0:
                return '$0.00'
            return f"${float_val:,.2f}"
        except (ValueError, TypeError):
            return '$0.00'
    
    # Helper function to clean NaN values
    def clean_nan(value):
        if value is None:
            return ''
        str_value = str(value)
        if str_value.lower() in ['nan', 'none', '']:
            return ''
        return str_value
    
    debug_print(f"send_end_of_day_email called with date_str={date_str}, smtp_config provided={smtp_config is not None}, recipients provided={recipients is not None}, bucket_name={bucket_name}, sf_credentials provided={sf_credentials is not None}")
    try:
        if date_str is None:
            date_str = date.today().isoformat()
            debug_print(f"date_str was None, set to today: {date_str}")
        
        debug_print(f"Getting daily summary from S3 for date: {date_str}, bucket: {bucket_name}")
        # Get daily summary from S3
        daily_summary = get_daily_summary_from_s3(date_str, bucket_name)
        
        if daily_summary is None:
            debug_print(f"⚠️ No daily summary found for {date_str}")
            return False
        
        debug_print(f"Daily summary retrieved successfully. Keys: {list(daily_summary.keys())}")
        debug_print(f"Runs count: {len(daily_summary.get('runs', []))}")
        
        # Get SMTP config if not provided
        if smtp_config is None:
            debug_print("SMTP config not provided, fetching from Secrets Manager...")
            smtp_config = get_secret('smtp/credentials')
            smtp_config['from_email'] = smtp_config.get('from_email', smtp_config.get('username'))
            debug_print(f"SMTP config retrieved. Server: {smtp_config.get('server', 'NOT SET')}, Port: {smtp_config.get('port', 'NOT SET')}, From: {smtp_config.get('from_email', 'NOT SET')}")
        else:
            debug_print(f"Using provided SMTP config. Server: {smtp_config.get('server', 'NOT SET')}, Port: {smtp_config.get('port', 'NOT SET')}")
        
        # Get recipients from .config file if not provided (daily summary list)
        if recipients is None:
            debug_print("Recipients not provided, fetching from config...")
            from config import get_email_recipients_daily_summary
            recipients = get_email_recipients_daily_summary()
            debug_print(f"Recipients retrieved: {recipients}")
        else:
            debug_print(f"Using provided recipients: {recipients}")
        
        # Get data lists (already in dict format - exact format sent to Salesforce API)
        debug_print("Extracting data lists from daily summary...")
        bills_update_list = daily_summary.get('all_bills_update', [])
        bills_insert_list = daily_summary.get('all_bills_insert', [])
        invoices_updated = daily_summary.get('all_invoices_updated', [])
        debug_print(f"Data counts - Bills Updated: {len(bills_update_list)}, Bills Inserted: {len(bills_insert_list)}, Invoices Updated: {len(invoices_updated)}")
        
        # Get metadata dictionaries
        debug_print("Extracting metadata dictionaries...")
        bills_update_metadata = daily_summary.get('bills_update_metadata', {'names': {}, 'account_names': {}})
        bills_insert_metadata = daily_summary.get('bills_insert_metadata', {'names': {}, 'memos': {}, 'account_names': {}})
        invoices_metadata = daily_summary.get('invoices_metadata', {'account_names': {}})
        
        bills_update_names = bills_update_metadata.get('names', {})
        bills_update_account_names = bills_update_metadata.get('account_names', {})
        bills_insert_names = bills_insert_metadata.get('names', {})
        bills_insert_memos = bills_insert_metadata.get('memos', {})
        bills_insert_account_names = bills_insert_metadata.get('account_names', {})
        bills_insert_sf_ids = bills_insert_metadata.get('sf_ids', {})
        invoices_account_names = invoices_metadata.get('account_names', {})
        debug_print(f"Metadata counts - Bills Update Names: {len(bills_update_names)}, Bills Insert Names: {len(bills_insert_names)}, Invoices Account Names: {len(invoices_account_names)}")
        
        # Query Salesforce for missing data if credentials provided
        sf = None
        acc_dict_reverse = {}
        
        if sf_credentials is None:
            debug_print("Salesforce credentials not provided, fetching from Secrets Manager...")
            try:
                sf_credentials = get_secret('salesforce/credentials')
                debug_print("Salesforce credentials retrieved")
            except Exception as e:
                debug_print(f"Failed to get Salesforce credentials: {e}")
                sf_credentials = None
        
        if sf_credentials:
            try:
                debug_print("Initializing Salesforce connector...")
                from salesforce_connector import SalesforceConnector
                sf = SalesforceConnector(sf_credentials)
                sf.login()
                debug_print("Salesforce login successful")
                
                # Query all necessary data from Salesforce
                all_account_ids = set()
                
                # Query Bills Updated
                if len(bills_update_list) > 0:
                    debug_print("Querying Salesforce for Bills Updated data...")
                    bill_ids = [bill['Id'] for bill in bills_update_list if bill.get('Id')]
                    if bill_ids:
                        try:
                            id_list = "','".join(bill_ids)
                            bills_update_df = sf.soql_to_df(f"SELECT Id, Name, Account__c, Memo__c FROM Payment__c WHERE Id IN ('{id_list}')")
                            
                            # Update bills_update_names from Salesforce
                            for _, row in bills_update_df.iterrows():
                                bill_id = row['Id']
                                name_val = row.get('Name', '')
                                if pd.notna(name_val):
                                    bills_update_names[bill_id] = clean_nan(name_val)
                                account_id = row.get('Account__c', '')
                                if pd.notna(account_id) and account_id:
                                    all_account_ids.add(account_id)
                                memo_val = row.get('Memo__c', '')
                                if pd.notna(memo_val) and memo_val:
                                    # Update the bill in bills_update_list
                                    for b in bills_update_list:
                                        if b.get('Id') == bill_id:
                                            b['Memo__c'] = clean_nan(memo_val)
                                            break
                            
                            debug_print(f"Retrieved {len(bills_update_df)} Bills Updated records from Salesforce")
                        except Exception as e:
                            debug_print(f"Error querying Bills Updated from Salesforce: {e}")
                            import traceback
                            traceback.print_exc()
                
                # Query Bills Inserted by QBO_Bill_ID__c
                bills_insert_account_ids_map = {}  # Map QBO_ID to Account__c from Salesforce
                if len(bills_insert_list) > 0:
                    debug_print("Querying Salesforce for Bills Inserted data...")
                    qbo_ids = [str(bill['QBO_Bill_ID__c']) for bill in bills_insert_list if bill.get('QBO_Bill_ID__c')]
                    if qbo_ids:
                        try:
                            # Escape single quotes in QBO IDs and remove any empty strings
                            escaped_qbo_ids = [qid.replace("'", "\\'") for qid in qbo_ids if qid]
                            if escaped_qbo_ids:
                                id_list = "','".join(escaped_qbo_ids)
                                bills_insert_df = sf.soql_to_df(f"SELECT Id, Name, Account__c, Memo__c, QBO_Bill_ID__c FROM Payment__c WHERE QBO_Bill_ID__c IN ('{id_list}')")
                                
                                # Update bills_insert mappings from Salesforce
                                for _, row in bills_insert_df.iterrows():
                                    qbo_id_val = row.get('QBO_Bill_ID__c', '')
                                    qbo_id = str(qbo_id_val) if pd.notna(qbo_id_val) else ''
                                    if qbo_id:
                                        sf_id = row['Id']
                                        bills_insert_sf_ids[qbo_id] = sf_id
                                        name_val = row.get('Name', '')
                                        if pd.notna(name_val) and name_val:
                                            bills_insert_names[qbo_id] = clean_nan(name_val)
                                        memo_val = row.get('Memo__c', '')
                                        if pd.notna(memo_val) and memo_val:
                                            bills_insert_memos[qbo_id] = clean_nan(memo_val)
                                        account_id = row.get('Account__c', '')
                                        if pd.notna(account_id) and account_id:
                                            bills_insert_account_ids_map[qbo_id] = account_id
                                            all_account_ids.add(account_id)
                                
                                debug_print(f"Retrieved {len(bills_insert_df)} Bills Inserted records from Salesforce")
                        except Exception as e:
                            debug_print(f"Error querying Bills Inserted from Salesforce: {e}")
                            import traceback
                            traceback.print_exc()
                
                # Query Invoices Updated
                invoices_df = None
                if len(invoices_updated) > 0:
                    debug_print("Querying Salesforce for Invoices Updated data...")
                    invoice_ids = [inv['Id'] for inv in invoices_updated if inv.get('Id')]
                    if invoice_ids:
                        try:
                            id_list = "','".join(invoice_ids)
                            invoices_df = sf.soql_to_df(f"SELECT Id, Name, inscor__Account__c FROM inscor__Invoice__c WHERE Id IN ('{id_list}')")
                            
                            # Update invoice account mappings
                            for _, row in invoices_df.iterrows():
                                invoice_id = row['Id']
                                account_id = row.get('inscor__Account__c', '')
                                if pd.notna(account_id) and account_id:
                                    all_account_ids.add(account_id)
                            
                            debug_print(f"Retrieved {len(invoices_df)} Invoices Updated records from Salesforce")
                        except Exception as e:
                            debug_print(f"Error querying Invoices Updated from Salesforce: {e}")
                            import traceback
                            traceback.print_exc()
                
                # Query Account names for all account IDs
                if all_account_ids:
                    debug_print(f"Querying {len(all_account_ids)} Account records for names...")
                    try:
                        id_list = "','".join(all_account_ids)
                        accounts_df = sf.soql_to_df(f"SELECT Id, Name FROM Account WHERE Id IN ('{id_list}')")
                        # Ensure account IDs are strings for consistent lookups
                        acc_dict_reverse = dict(zip(accounts_df.Id.astype(str), accounts_df.Name.fillna('').astype(str)))
                        debug_print(f"Retrieved {len(acc_dict_reverse)} Account names from Salesforce")
                        
                        # Update account names for Bills Updated
                        for bill in bills_update_list:
                            bill_id = bill.get('Id', '')
                            account_id = clean_nan(bill.get('Account__c', ''))
                            if account_id and bill_id:
                                account_id_str = str(account_id)
                                if account_id_str in acc_dict_reverse:
                                    account_name = acc_dict_reverse.get(account_id_str, '')
                                    if account_name:
                                        bills_update_account_names[bill_id] = clean_nan(account_name)
                        
                        # Update account names for Bills Inserted (use Account__c from Salesforce query)
                        for qbo_id, account_id in bills_insert_account_ids_map.items():
                            # Ensure account_id is a string for comparison
                            account_id_str = str(account_id) if account_id else ''
                            if account_id_str and account_id_str in acc_dict_reverse:
                                account_name = acc_dict_reverse.get(account_id_str, '')
                                if account_name:
                                    bills_insert_account_names[qbo_id] = clean_nan(account_name)
                        
                        # Update account names for Invoices Updated (use invoices_df from Salesforce query)
                        if invoices_df is not None:
                            for _, row in invoices_df.iterrows():
                                invoice_id = row['Id']
                                account_id = row.get('inscor__Account__c', '')
                                if pd.notna(account_id) and account_id:
                                    account_id_str = str(account_id)
                                    if account_id_str in acc_dict_reverse:
                                        account_name = acc_dict_reverse.get(account_id_str, '')
                                        if account_name:
                                            invoices_account_names[invoice_id] = clean_nan(account_name)
                    except Exception as e:
                        debug_print(f"Error querying Accounts from Salesforce: {e}")
                        import traceback
                        traceback.print_exc()
            except Exception as e:
                debug_print(f"Error initializing Salesforce connector: {e}")
                import traceback
                traceback.print_exc()
        
        # Salesforce base URL
        salesforce_base_url = 'https://pioneer-aero.lightning.force.com/'
        
        # Create message
        debug_print("Creating email message...")
        msg = MIMEMultipart('alternative')
        msg['Subject'] = f'QBsync Daily Summary - {date_str}'
        msg['From'] = smtp_config['from_email']
        msg['To'] = ', '.join(recipients)
        debug_print(f"Message created - Subject: {msg['Subject']}, From: {msg['From']}, To: {msg['To']}")
        
        # Format date for display
        display_date = datetime.strptime(date_str, '%Y-%m-%d').strftime('%B %d, %Y')
        
        # Build rich HTML body
        debug_print("Building HTML email body...")
        html_body = f"""
        <html>
        <head>
            <style>
                body {{
                    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                    line-height: 1.6;
                    color: #333;
                    max-width: 900px;
                    margin: 0 auto;
                    padding: 20px;
                    background: #f5f5f5;
                }}
                .header {{
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    color: white;
                    padding: 40px;
                    border-radius: 10px;
                    margin-bottom: 30px;
                    text-align: center;
                    box-shadow: 0 4px 6px rgba(0,0,0,0.1);
                }}
                .header h1 {{
                    margin: 0;
                    font-size: 32px;
                }}
                .header p {{
                    margin: 10px 0 0 0;
                    font-size: 16px;
                    opacity: 0.95;
                }}
                .summary-stats {{
                    display: grid;
                    grid-template-columns: repeat(5, 1fr);
                    gap: 15px;
                    margin-bottom: 30px;
                }}
                .stat-card {{
                    background: white;
                    padding: 25px;
                    border-radius: 8px;
                    text-align: center;
                    box-shadow: 0 2px 4px rgba(0,0,0,0.1);
                    border-top: 4px solid #667eea;
                }}
                .stat-number {{
                    font-size: 36px;
                    font-weight: bold;
                    color: #667eea;
                    margin: 10px 0;
                }}
                .stat-label {{
                    color: #666;
                    font-size: 13px;
                    text-transform: uppercase;
                    letter-spacing: 1px;
                    font-weight: 600;
                }}
                .runs-summary {{
                    background: white;
                    padding: 20px;
                    border-radius: 8px;
                    margin-bottom: 20px;
                    box-shadow: 0 2px 4px rgba(0,0,0,0.1);
                }}
                .runs-summary h3 {{
                    color: #667eea;
                    margin-top: 0;
                    border-bottom: 2px solid #e9ecef;
                    padding-bottom: 10px;
                }}
                .runs-container {{
                    width: 100%;
                }}
                .run-group {{
                    margin-bottom: 20px;
                    background: #f8f9fa;
                    border-radius: 5px;
                    border-left: 3px solid #667eea;
                    overflow: hidden;
                }}
                .run-group-header {{
                    padding: 12px 15px;
                    background: #e9ecef;
                    font-size: 13px;
                    color: #495057;
                    border-bottom: 2px solid #667eea;
                }}
                .run-group-table {{
                    width: 100%;
                    border-collapse: collapse;
                    font-size: 13px;
                }}
                .run-group-table thead {{
                    background: #667eea;
                    color: white;
                }}
                .run-group-table th {{
                    padding: 8px 12px;
                    text-align: left;
                    font-weight: 600;
                    font-size: 12px;
                }}
                .run-group-table td {{
                    padding: 6px 12px;
                    border-bottom: 1px solid #dee2e6;
                    color: #495057;
                }}
                .run-group-table tbody tr:hover {{
                    background: #ffffff;
                }}
                .run-group-table tbody tr:last-child td {{
                    border-bottom: none;
                }}
                .system-breakdown {{
                    background: white;
                    padding: 20px;
                    border-radius: 8px;
                    margin-bottom: 20px;
                    box-shadow: 0 2px 4px rgba(0,0,0,0.1);
                }}
                .system-breakdown h3 {{
                    color: #667eea;
                    margin-top: 0;
                    border-bottom: 2px solid #e9ecef;
                    padding-bottom: 10px;
                }}
                .breakdown-row {{
                    display: flex;
                    justify-content: space-between;
                    padding: 8px 0;
                    border-bottom: 1px solid #e9ecef;
                    gap: 15px;
                }}
                .breakdown-row:last-child {{
                    border-bottom: none;
                }}
                .breakdown-label {{
                    font-weight: 600;
                    color: #495057;
                    flex-shrink: 0;
                }}
                .breakdown-value {{
                    color: #212529;
                    text-align: right;
                }}
                .section {{
                    background: white;
                    padding: 30px;
                    margin-bottom: 20px;
                    border-radius: 8px;
                    box-shadow: 0 2px 4px rgba(0,0,0,0.1);
                }}
                .section-title {{
                    color: #667eea;
                    font-size: 20px;
                    font-weight: bold;
                    margin-bottom: 20px;
                    padding-bottom: 15px;
                    border-bottom: 3px solid #667eea;
                }}
                table {{
                    width: 100%;
                    border-collapse: collapse;
                    margin-top: 15px;
                }}
                th {{
                    background: #667eea;
                    color: white;
                    padding: 14px;
                    text-align: left;
                    font-weight: 600;
                    font-size: 14px;
                }}
                td {{
                    padding: 12px 14px;
                    border-bottom: 1px solid #e9ecef;
                    font-size: 14px;
                }}
                tr:hover {{
                    background: #f8f9fa;
                }}
                .footer {{
                    text-align: center;
                    padding: 25px;
                    color: #666;
                    font-size: 13px;
                    border-top: 2px solid #e9ecef;
                    margin-top: 30px;
                    background: white;
                    border-radius: 8px;
                }}
                .success {{ color: #28a745; font-weight: bold; }}
                .info {{ color: #17a2b8; }}
                .highlight {{ background: #fff3cd; padding: 2px 6px; border-radius: 3px; }}
            </style>
        </head>
        <body>
            <div class="header">
                <h1>📊 QBsync Daily Summary</h1>
                <p>{display_date}</p>
            </div>
            
            <div class="summary-stats">
                <div class="stat-card">
                    <div class="stat-label">Total Runs</div>
                    <div class="stat-number">{len(daily_summary.get('runs', []))}</div>
                </div>
                <div class="stat-card">
                    <div class="stat-label">Total Runtime</div>
                    <div class="stat-number">{daily_summary.get('total_runtime', '0s')}</div>
                </div>
                <div class="stat-card">
                    <div class="stat-label">Bills Updated</div>
                    <div class="stat-number">{daily_summary.get('total_bills_updated', 0):,}</div>
                </div>
                <div class="stat-card">
                    <div class="stat-label">Bills Inserted</div>
                    <div class="stat-number">{daily_summary.get('total_bills_inserted', 0):,}</div>
                </div>
                <div class="stat-card">
                    <div class="stat-label">Invoices Updated</div>
                    <div class="stat-number">{daily_summary.get('total_invoices_updated', 0):,}</div>
                </div>
            </div>
        """
        
        # Calculate system info breakdown and average runtime
        runs = daily_summary.get('runs', [])
        total_runs = len(runs)
        aws_runs = sum(1 for run in runs if run.get('system_info', {}).get('environment') == 'AWS Lambda')
        local_runs = total_runs - aws_runs
        
        # Calculate average runtime
        if total_runs > 0:
            total_runtime_seconds = parse_execution_time_to_seconds(daily_summary.get('total_runtime', '0s'))
            avg_runtime_seconds = total_runtime_seconds / total_runs
            avg_runtime = format_time(avg_runtime_seconds)
        else:
            avg_runtime = '0s'
        
        # System breakdown section
        html_body += f"""
            <div class="system-breakdown">
                <h3>📊 Execution Summary</h3>
                <div class="breakdown-row">
                    <span class="breakdown-label">Total Runtime: </span>
                    <span class="breakdown-value"><strong>{daily_summary.get('total_runtime', '0s')}</strong></span>
                </div>
                <div class="breakdown-row">
                    <span class="breakdown-label">Average Runtime per Run: </span>
                    <span class="breakdown-value"><strong>{avg_runtime}</strong></span>
                </div>
                <div class="breakdown-row">
                    <span class="breakdown-label">Runs on AWS Lambda: </span>
                    <span class="breakdown-value"><strong>{aws_runs}</strong></span>
                </div>
                <div class="breakdown-row">
                    <span class="breakdown-label">Runs on Local Machine: </span>
                    <span class="breakdown-value"><strong>{local_runs}</strong></span>
                </div>
            </div>
        """
        
        # Runs summary section - grouped by common system fields
        if len(daily_summary.get('runs', [])) > 0:
            # Group runs by common system fields
            from collections import defaultdict
            run_groups = defaultdict(list)
            
            for run in daily_summary['runs']:
                system_info = run.get('system_info', {})
                env = system_info.get('environment', 'Unknown')
                os_info = system_info.get('os', 'Unknown')
                python_version = system_info.get('python_version', 'Unknown')
                
                # Create group key from common fields
                if env == 'AWS Lambda':
                    lambda_func = system_info.get('lambda_function_name', 'Unknown')
                    lambda_region = system_info.get('lambda_region', 'Unknown')
                    lambda_memory = system_info.get('lambda_memory_mb', 'Unknown')
                    group_key = (env, os_info, python_version, lambda_region, lambda_memory, lambda_func)
                else:
                    group_key = (env, os_info, python_version, 'N/A', 'N/A', 'N/A')
                
                run_groups[group_key].append(run)
            
            html_body += """
            <div class="runs-summary">
                <h3>🔄 Sync Runs Today</h3>
            """
            
            # Sort groups by first run timestamp (most recent first)
            sorted_groups = sorted(run_groups.items(), 
                                  key=lambda x: x[1][0].get('timestamp', ''), 
                                  reverse=True)
            
            for group_key, runs in sorted_groups:
                env, os_info, python_version, region, memory, lambda_func = group_key
                
                # Group header with common fields
                html_body += f"""
                <div class="run-group">
                    <div class="run-group-header">
                        <strong>Execution Environment:</strong> {env} | 
                        <strong>OS:</strong> {os_info} | 
                        <strong>Python:</strong> {python_version}
                """
                
                if env == 'AWS Lambda':
                    html_body += f"""
                        <strong>Lambda Function:</strong> {lambda_func} | 
                        <strong>Region:</strong> {region} | 
                        <strong>Memory:</strong> {memory} MB"""
                
                html_body += f"""
                    </div>
                    <table class="run-group-table">
                        <thead>
                            <tr>
                                <th>Time</th>
                                <th>Hostname</th>
                                <th>Duration</th>
                                <th>Type</th>
                                <th>Records Updated</th>
                            </tr>
                        </thead>
                        <tbody>
                """
                
                # Sort runs within group by timestamp (most recent first)
                runs.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
                
                for run in runs:
                    timestamp = run.get('timestamp', 'Unknown')
                    exec_time_raw = run.get('execution_time', 'Unknown')
                    exec_time = format_execution_time_mmss(exec_time_raw)
                    execution_time_formatted = format_timestamp_to_time(timestamp)
                    system_info = run.get('system_info', {})
                    hostname = system_info.get('hostname', 'Unknown')
                    
                    sync_type = run.get('sync_type', 'full')
                    sync_type_display = '🔄 Incr' if sync_type == 'incremental' else '📥 Full'
                    
                    bills_updated_count = run.get('bills_update_count', 0)
                    bills_inserted_count = run.get('bills_insert_count', 0)
                    invoices_updated_count = run.get('invoices_updated_count', 0)
                    total_records = bills_updated_count + bills_inserted_count + invoices_updated_count
                    records_display = f"B:{bills_updated_count} I:{bills_inserted_count} Inv:{invoices_updated_count}" if total_records > 0 else "None"
                    
                html_body += f"""
                            <tr>
                                <td>{execution_time_formatted}</td>
                                <td>{hostname}</td>
                                <td>{exec_time}</td>
                                <td>{sync_type_display}</td>
                                <td>{records_display}</td>
                            </tr>
                    """
                
                html_body += """
                        </tbody>
                        </table>
                </div>
                """
            
            html_body += """
            </div>
            """
        
        # Bills Updated table
        if len(bills_update_list) > 0:
            html_body += f"""
            <div class="section">
                <div class="section-title">📝 Bills Updated ({len(bills_update_list)})</div>
                <table>
                    <thead>
                    <tr>
                            <th>Bill</th>
                            <th>Account</th>
                            <th>Memo</th>
                        <th>Balance Due</th>
                        <th>Total Amount</th>
                        <th>Due Date</th>
                        <th>Bill Date</th>
                    </tr>
                    </thead>
                    <tbody>
            """
            for bill in bills_update_list:
                bill_id = bill.get('Id', '')
                bill_name = clean_nan(bills_update_names.get(bill_id, ''))
                if not bill_name:
                    bill_name = 'N/A' if not bill_id else 'N/A'  # Don't show "ID: {id}", use N/A
                account_name = clean_nan(bills_update_account_names.get(bill_id, ''))
                if not account_name:
                    account_name = ''  # Leave blank instead of showing ID or N/A
                memo = clean_nan(bill.get('Memo__c', ''))
                balance_due = bill.get('Balance_Due__c', '')
                total_amount = bill.get('Total_Amount__c', '')
                due_date = bill.get('Due_Date__c', '')
                bill_date = bill.get('Bill_Date__c', '')
                
                # Format currency values using helper function
                balance_due_formatted = format_currency(balance_due)
                total_amount_formatted = format_currency(total_amount)
                
                # Create Salesforce link - always use bill_name from Salesforce query
                if bill_id and bill_name and bill_name != 'N/A':
                    bill_link = f'<a href="{salesforce_base_url}{bill_id}" style="color: #667eea; text-decoration: none; font-weight: 600;">{bill_name}</a>'
                elif bill_id:
                    # Fallback: if we have ID but no name, still create link with ID
                    bill_link = f'<a href="{salesforce_base_url}{bill_id}" style="color: #667eea; text-decoration: none; font-weight: 600;">{bill_id}</a>'
                else:
                    bill_link = bill_name if bill_name else 'N/A'
                
                html_body += f"""
                    <tr>
                            <td>{bill_link}</td>
                            <td>{account_name}</td>
                            <td>{memo}</td>
                            <td>{balance_due_formatted}</td>
                            <td>{total_amount_formatted}</td>
                            <td>{due_date if due_date else 'N/A'}</td>
                            <td>{bill_date if bill_date else 'N/A'}</td>
                    </tr>
                """
            html_body += """
                    </tbody>
                </table>
            </div>
            """
        
        # Bills Inserted table
        if len(bills_insert_list) > 0:
            html_body += f"""
            <div class="section">
                <div class="section-title">➕ Bills Inserted ({len(bills_insert_list)})</div>
                <table>
                    <thead>
                    <tr>
                            <th>Bill</th>
                            <th>Account</th>
                            <th>Memo</th>
                        <th>Total Amount</th>
                        <th>Balance Due</th>
                        <th>Bill Date</th>
                        <th>Due Date</th>
                    </tr>
                    </thead>
                    <tbody>
            """
            for bill in bills_insert_list:
                # For inserted bills, match by QBO_Bill_ID__c to get the Salesforce ID and metadata
                qbo_id = str(bill.get('QBO_Bill_ID__c', '')) if bill.get('QBO_Bill_ID__c') else ''
                bill_id = bills_insert_sf_ids.get(qbo_id, '') if qbo_id else ''
                bill_name = clean_nan(bills_insert_names.get(qbo_id, '')) if qbo_id else ''
                memo = clean_nan(bills_insert_memos.get(qbo_id, '')) if qbo_id else ''
                if not memo:
                    # Fallback to Memo__c from bill data if metadata missing
                    memo = clean_nan(bill.get('Memo__c', ''))
                account_name = clean_nan(bills_insert_account_names.get(qbo_id, '')) if qbo_id else ''
                if not account_name:
                    account_name = ''  # Leave blank instead of showing ID or N/A
                
                total_amount = bill.get('Total_Amount__c', '')
                balance_due = bill.get('Balance_Due__c', '')
                bill_date = bill.get('Bill_Date__c', '')
                due_date = bill.get('Due_Date__c', '')
                
                # Format currency values using helper function
                balance_due_formatted = format_currency(balance_due)
                total_amount_formatted = format_currency(total_amount)
                
                # Create Salesforce link - always create if we have bill_id
                if bill_id and bill_name:
                    bill_link = f'<a href="{salesforce_base_url}{bill_id}" style="color: #667eea; text-decoration: none; font-weight: 600;">{bill_name}</a>'
                elif bill_id:
                    # Fallback: if we have ID but no name, use ID as link text
                    bill_link = f'<a href="{salesforce_base_url}{bill_id}" style="color: #667eea; text-decoration: none; font-weight: 600;">{bill_id}</a>'
                else:
                    # No Salesforce ID yet, show QBO ID as text
                    bill_link = f"QBO ID: {qbo_id}" if qbo_id else 'N/A'
                
                html_body += f"""
                    <tr>
                            <td>{bill_link}</td>
                            <td>{account_name}</td>
                            <td>{memo}</td>
                            <td>{total_amount_formatted}</td>
                            <td>{balance_due_formatted}</td>
                            <td>{bill_date if bill_date else 'N/A'}</td>
                            <td>{due_date if due_date else 'N/A'}</td>
                    </tr>
                """
            html_body += """
                    </tbody>
                </table>
            </div>
            """
        
        # Invoices Updated table
        if len(invoices_updated) > 0:
            html_body += f"""
            <div class="section">
                <div class="section-title">📄 Invoices Updated ({len(invoices_updated)})</div>
                <table>
                    <thead>
                    <tr>
                            <th>Invoice</th>
                            <th>Account</th>
                        <th>Balance</th>
                        <th>Status</th>
                    </tr>
                    </thead>
                    <tbody>
            """
            for invoice in invoices_updated:
                invoice_id = invoice.get('Id', '')
                invoice_name = clean_nan(invoice.get('Name', ''))
                if not invoice_name:
                    invoice_name = 'N/A'  # Don't show "ID: {id}", use N/A
                account_name = clean_nan(invoices_account_names.get(invoice_id, ''))
                if not account_name:
                    account_name = ''  # Leave blank instead of showing ID or N/A
                balance = invoice.get('Invoice_Balance__c', '')
                status = invoice.get('inscor__Status__c', '')
                
                # Format currency values using helper function
                balance_formatted = format_currency(balance)
                
                # Create Salesforce link - always use invoice_name
                if invoice_id and invoice_name and invoice_name != 'N/A':
                    invoice_link = f'<a href="{salesforce_base_url}{invoice_id}" style="color: #667eea; text-decoration: none; font-weight: 600;">{invoice_name}</a>'
                elif invoice_id:
                    # Fallback: if we have ID but no name, still create link with ID
                    invoice_link = f'<a href="{salesforce_base_url}{invoice_id}" style="color: #667eea; text-decoration: none; font-weight: 600;">{invoice_id}</a>'
                else:
                    invoice_link = invoice_name if invoice_name else 'N/A'
                
                html_body += f"""
                    <tr>
                            <td>{invoice_link}</td>
                            <td>{account_name}</td>
                            <td>{balance_formatted}</td>
                            <td>{clean_nan(status) if status else 'N/A'}</td>
                    </tr>
                """
            html_body += """
                    </tbody>
                </table>
            </div>
            """
        
        # Add note about ZIP attachment
        total_records = len(bills_update_list) + len(bills_insert_list) + len(invoices_updated)
        if total_records > 0:
            html_body += f"""
            <div class="section">
                <div class="section-title">📎 Data Export</div>
                <p style="margin: 15px 0; line-height: 1.8;">
                    Detailed data has been exported to CSV files and attached as a ZIP archive.<br>
                    The ZIP file contains:
                </p>
                <ul style="margin: 10px 0; padding-left: 30px; line-height: 2;">
                    <li><strong>bills_updated.csv</strong> - {len(bills_update_list)} bill update record(s)</li>
                    <li><strong>bills_inserted.csv</strong> - {len(bills_insert_list)} bill insert record(s)</li>
                    <li><strong>invoices_updated.csv</strong> - {len(invoices_updated)} invoice update record(s)</li>
                </ul>
                <p style="margin: 15px 0; line-height: 1.8;">
                    These CSV files contain the exact data that was sent to the Salesforce API.
                </p>
            </div>
            """
        
        # Footer
        html_body += f"""
            <div class="footer">
                <p class="success">✅ Daily sync summary for {display_date}</p>
                <p>This email contains all changes accumulated throughout the day</p>
                <p style="margin-top: 15px; font-size: 11px; color: #999;">
                    Generated automatically by qb-avsight-sync system
                </p>
            </div>
        </body>
        </html>
        """
        
        # Attach HTML body
        debug_print("Attaching HTML body to message...")
        html_part = MIMEText(html_body, 'html')
        msg.attach(html_part)
        debug_print(f"HTML body attached. HTML length: {len(html_body)} characters")
        
        # Create CSV files and ZIP attachment
        total_records = len(bills_update_list) + len(bills_insert_list) + len(invoices_updated)
        debug_print(f"Creating ZIP attachment. Total records: {total_records}")
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
            debug_print(f"ZIP attachment added. Size: {zip_size} bytes")
        else:
            debug_print("No records to attach, skipping ZIP file")
        
        # Send email
        debug_print(f"Attempting to send email via SMTP...")
        debug_print(f"SMTP Server: {smtp_config['server']}, Port: {smtp_config['port']}")
        debug_print(f"Username: {smtp_config['username']}")
        
        try:
            with smtplib.SMTP(smtp_config['server'], smtp_config['port']) as server:
                debug_print("SMTP connection established")
                debug_print("Starting TLS...")
                server.starttls()
                debug_print("TLS started successfully")
                debug_print("Attempting login...")
                server.login(smtp_config['username'], smtp_config['password'])
                debug_print("Login successful")
                debug_print("Sending message...")
                server.send_message(msg)
                debug_print("Message sent successfully via SMTP")
        except smtplib.SMTPException as smtp_error:
            debug_print(f"SMTP error occurred: {smtp_error}")
            raise
        except Exception as smtp_err:
            debug_print(f"Error during SMTP operations: {smtp_err}")
            raise
        
        print(f"✅ End-of-day email sent successfully for {date_str}")
        return True
        
    except Exception as e:
        debug_print(f"❌ Exception caught in send_end_of_day_email: {type(e).__name__}: {e}")
        print(f"❌ End-of-day email sending failed: {e}")
        import traceback
        debug_print("Full traceback:")
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