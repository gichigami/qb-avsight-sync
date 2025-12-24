"""
Utility functions for contact form Lambda function
Includes email sending and AWS Secrets Manager operations
"""

import boto3
import json
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Dict
from botocore.exceptions import ClientError


def get_secret(secret_name: str, region_name: str = 'us-east-1') -> Dict:
    """
    Retrieve a secret from AWS Secrets Manager
    
    Args:
        secret_name: Name of the secret (e.g., 'smtp/credentials')
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


def send_contact_form_email(form_data: Dict, smtp_config: Dict, recipient_email: str = 'gjohnson@pioneer-aero.com') -> bool:
    """
    Send contact form submission email via SMTP
    
    Args:
        form_data: Dictionary containing form fields (name, company, email, phone, message)
        smtp_config: SMTP configuration dictionary with server, port, username, password
        recipient_email: Email address to send to (default: gjohnson@pioneer-aero.com)
        
    Returns:
        True if email sent successfully, False otherwise
    """
    try:
        name = form_data.get('name', '')
        company = form_data.get('company', '')
        email = form_data.get('email', '')
        phone = form_data.get('phone', '')
        message = form_data.get('message', '')
        
        # Create message
        msg = MIMEMultipart('alternative')
        msg['Subject'] = f'AirBridgeQB Contact Form Submission from {name}'
        msg['From'] = smtp_config.get('from_email', smtp_config.get('username'))
        msg['To'] = recipient_email
        msg['Reply-To'] = email
        
        # Build HTML body
        html_body = f"""
        <html>
        <head>
            <style>
                body {{
                    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                    line-height: 1.6;
                    color: #333;
                    max-width: 600px;
                    margin: 0 auto;
                    padding: 20px;
                }}
                .header {{
                    background: linear-gradient(135deg, #2563eb 0%, #06b6d4 100%);
                    color: white;
                    padding: 30px;
                    border-radius: 10px;
                    margin-bottom: 30px;
                    text-align: center;
                }}
                .content {{
                    background: white;
                    padding: 25px;
                    border-radius: 8px;
                    box-shadow: 0 2px 4px rgba(0,0,0,0.1);
                }}
                .field {{
                    margin-bottom: 20px;
                    padding-bottom: 15px;
                    border-bottom: 1px solid #e9ecef;
                }}
                .field:last-child {{
                    border-bottom: none;
                }}
                .field-label {{
                    font-weight: 600;
                    color: #2563eb;
                    font-size: 14px;
                    text-transform: uppercase;
                    letter-spacing: 0.5px;
                    margin-bottom: 5px;
                }}
                .field-value {{
                    color: #333;
                    font-size: 16px;
                }}
                .message-box {{
                    background: #f8f9fa;
                    padding: 15px;
                    border-radius: 5px;
                    border-left: 4px solid #2563eb;
                    margin-top: 10px;
                    white-space: pre-wrap;
                }}
            </style>
        </head>
        <body>
            <div class="header">
                <h1>New Contact Form Submission</h1>
                <p>AirBridgeQB Website</p>
            </div>
            
            <div class="content">
                <div class="field">
                    <div class="field-label">Name</div>
                    <div class="field-value">{name}</div>
                </div>
                
                <div class="field">
                    <div class="field-label">Company</div>
                    <div class="field-value">{company}</div>
                </div>
                
                <div class="field">
                    <div class="field-label">Email</div>
                    <div class="field-value"><a href="mailto:{email}">{email}</a></div>
                </div>
        """
        
        # Add phone if provided
        if phone:
            html_body += f"""
                <div class="field">
                    <div class="field-label">Phone</div>
                    <div class="field-value">{phone}</div>
                </div>
            """
        
        # Add message
        html_body += f"""
                <div class="field">
                    <div class="field-label">Message</div>
                    <div class="message-box">{message}</div>
                </div>
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
        import traceback
        traceback.print_exc()
        return False

