"""
AWS Lambda function handler for AirBridgeQB website contact form submissions
"""

import json
import re
from typing import Dict, Any, Tuple
from utils import get_secret, send_contact_form_email


def validate_form_data(form_data: Dict) -> Tuple[bool, str]:
    """
    Validate contact form submission data
    
    Args:
        form_data: Dictionary containing form fields
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    name = form_data.get('name', '').strip()
    company = form_data.get('company', '').strip()
    email = form_data.get('email', '').strip()
    phone = form_data.get('phone', '').strip()
    message = form_data.get('message', '').strip()
    
    # Validate required fields
    if not name:
        return False, "Name is required"
    
    if not company:
        return False, "Company is required"
    
    if not email:
        return False, "Email is required"
    
    if not message:
        return False, "Message is required"
    
    # Validate email format
    email_pattern = r'^[^\s@]+@[^\s@]+\.[^\s@]+$'
    if not re.match(email_pattern, email):
        return False, "Invalid email format"
    
    # Validate message length
    if len(message) < 10:
        return False, "Message must be at least 10 characters long"
    
    # Validate phone format if provided (basic validation)
    if phone:
        phone_digits = re.sub(r'\D', '', phone)
        if len(phone_digits) < 10:
            return False, "Invalid phone number format"
    
    # Check for potential spam/injection attempts (basic checks)
    if len(name) > 200 or len(company) > 200 or len(message) > 5000:
        return False, "One or more fields exceed maximum length"
    
    return True, ""


def create_cors_headers() -> Dict[str, str]:
    """
    Create CORS headers for API Gateway response
    
    Returns:
        Dictionary of CORS headers
    """
    return {
        'Access-Control-Allow-Origin': 'https://gichigami.github.io',
        'Access-Control-Allow-Methods': 'POST, OPTIONS',
        'Access-Control-Allow-Headers': 'Content-Type',
        'Access-Control-Max-Age': '3600'
    }


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    AWS Lambda entry point - handles contact form submissions from API Gateway
    
    Args:
        event: API Gateway event data
        context: Lambda context object
        
    Returns:
        Response dictionary with status code, headers, and body
    """
    print("="*70)
    print(f"Contact form Lambda invoked: {event.get('requestContext', {}).get('requestId', 'unknown')}")
    print("="*70)
    
    cors_headers = create_cors_headers()
    
    # Handle OPTIONS request for CORS preflight
    if event.get('httpMethod') == 'OPTIONS':
        return {
            'statusCode': 200,
            'headers': cors_headers,
            'body': ''
        }
    
    try:
        # Parse request body
        if event.get('body'):
            if isinstance(event['body'], str):
                body = json.loads(event['body'])
            else:
                body = event['body']
        else:
            return {
                'statusCode': 400,
                'headers': cors_headers,
                'body': json.dumps({
                    'success': False,
                    'error': 'Request body is required'
                })
            }
        
        # Extract form data
        form_data = {
            'name': body.get('name', ''),
            'company': body.get('company', ''),
            'email': body.get('email', ''),
            'phone': body.get('phone', ''),
            'message': body.get('message', '')
        }
        
        print(f"📝 Received form submission from: {form_data.get('email', 'unknown')}")
        
        # Validate form data
        is_valid, error_message = validate_form_data(form_data)
        if not is_valid:
            print(f"❌ Validation failed: {error_message}")
            return {
                'statusCode': 400,
                'headers': cors_headers,
                'body': json.dumps({
                    'success': False,
                    'error': error_message
                })
            }
        
        # Retrieve SMTP credentials from Secrets Manager
        print("🔐 Retrieving SMTP credentials from Secrets Manager...")
        try:
            smtp_config = get_secret('smtp/credentials')
            # Ensure from_email is set
            if 'from_email' not in smtp_config:
                smtp_config['from_email'] = smtp_config.get('username')
        except Exception as e:
            print(f"❌ Failed to retrieve SMTP credentials: {e}")
            return {
                'statusCode': 500,
                'headers': cors_headers,
                'body': json.dumps({
                    'success': False,
                    'error': 'Failed to retrieve email configuration'
                })
            }
        
        # Send email
        print("📧 Sending contact form email...")
        success = send_contact_form_email(form_data, smtp_config)
        
        if success:
            print("✅ Contact form email sent successfully")
            return {
                'statusCode': 200,
                'headers': cors_headers,
                'body': json.dumps({
                    'success': True,
                    'message': 'Thank you for your interest! We will contact you soon.'
                })
            }
        else:
            print("❌ Failed to send contact form email")
            return {
                'statusCode': 500,
                'headers': cors_headers,
                'body': json.dumps({
                    'success': False,
                    'error': 'Failed to send email. Please try again later.'
                })
            }
        
    except json.JSONDecodeError as e:
        print(f"❌ Invalid JSON in request body: {e}")
        return {
            'statusCode': 400,
            'headers': cors_headers,
            'body': json.dumps({
                'success': False,
                'error': 'Invalid request format'
            })
        }
    
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        
        return {
            'statusCode': 500,
            'headers': cors_headers,
            'body': json.dumps({
                'success': False,
                'error': 'An unexpected error occurred. Please try again later.'
            })
        }

