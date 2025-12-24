#!/usr/bin/env python3
"""
Test script for AirBridgeQB contact form API endpoint
Tests the deployed Lambda function via API Gateway
"""

import requests
import json
import sys
from datetime import datetime

# API Gateway endpoint
API_ENDPOINT = "https://ov9ok9i1h8.execute-api.us-east-1.amazonaws.com/prod/contact"

def test_contact_form():
    """Test the contact form API endpoint"""
    
    print("=" * 70)
    print("Testing AirBridgeQB Contact Form API")
    print("=" * 70)
    print(f"Endpoint: {API_ENDPOINT}")
    print(f"Timestamp: {datetime.now().isoformat()}")
    print()
    
    # Test data
    test_data = {
        "name": f"Test User - {datetime.now().strftime('%H:%M:%S')}",
        "company": "Test Company Inc.",
        "email": "test@example.com",
        "phone": "555-123-4567",
        "message": "This is a test submission from the automated test script. Please ignore this message."
    }
    
    print("Test Data:")
    print(json.dumps(test_data, indent=2))
    print()
    
    # Headers
    headers = {
        "Content-Type": "application/json",
        "Origin": "https://gichigami.github.io"
    }
    
    try:
        print("Sending POST request...")
        response = requests.post(
            API_ENDPOINT,
            json=test_data,
            headers=headers,
            timeout=30
        )
        
        print(f"Status Code: {response.status_code}")
        print(f"Response Headers: {dict(response.headers)}")
        print()
        
        # Try to parse JSON response
        try:
            response_data = response.json()
            print("Response Body (JSON):")
            print(json.dumps(response_data, indent=2))
            print()
            
            # Check if successful
            if response.status_code == 200 and response_data.get('success'):
                print("✅ SUCCESS: Contact form submission processed successfully!")
                print(f"   Message: {response_data.get('message', 'N/A')}")
                return True
            else:
                print("❌ ERROR: Request returned non-success status or response")
                print(f"   Error: {response_data.get('error', 'Unknown error')}")
                return False
                
        except json.JSONDecodeError:
            print("Response Body (Text):")
            print(response.text)
            print()
            print("❌ ERROR: Response is not valid JSON")
            return False
            
    except requests.exceptions.Timeout:
        print("❌ ERROR: Request timed out")
        return False
    except requests.exceptions.ConnectionError as e:
        print(f"❌ ERROR: Connection error - {e}")
        return False
    except requests.exceptions.RequestException as e:
        print(f"❌ ERROR: Request failed - {e}")
        return False
    except Exception as e:
        print(f"❌ ERROR: Unexpected error - {e}")
        import traceback
        traceback.print_exc()
        return False

def test_cors_preflight():
    """Test CORS OPTIONS request"""
    
    print("=" * 70)
    print("Testing CORS Preflight (OPTIONS request)")
    print("=" * 70)
    print()
    
    headers = {
        "Origin": "https://gichigami.github.io",
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "Content-Type"
    }
    
    try:
        print("Sending OPTIONS request...")
        response = requests.options(API_ENDPOINT, headers=headers, timeout=10)
        
        print(f"Status Code: {response.status_code}")
        print(f"Response Headers:")
        for key, value in response.headers.items():
            if 'access-control' in key.lower():
                print(f"  {key}: {value}")
        print()
        
        if response.status_code == 200:
            print("✅ SUCCESS: CORS preflight request successful")
            return True
        else:
            print(f"❌ ERROR: CORS preflight returned status {response.status_code}")
            return False
            
    except Exception as e:
        print(f"❌ ERROR: CORS preflight test failed - {e}")
        return False

def test_validation():
    """Test API validation with invalid data"""
    
    print("=" * 70)
    print("Testing Input Validation")
    print("=" * 70)
    print()
    
    # Test missing required fields
    invalid_data = {
        "name": "",  # Missing name
        "email": "invalid-email",  # Invalid email format
        "message": "short"  # Message too short
    }
    
    headers = {
        "Content-Type": "application/json",
        "Origin": "https://gichigami.github.io"
    }
    
    try:
        print("Sending request with invalid data...")
        response = requests.post(
            API_ENDPOINT,
            json=invalid_data,
            headers=headers,
            timeout=30
        )
        
        print(f"Status Code: {response.status_code}")
        
        try:
            response_data = response.json()
            print("Response Body:")
            print(json.dumps(response_data, indent=2))
            print()
            
            # Should return 400 with error message
            if response.status_code == 400 and not response_data.get('success'):
                print("✅ SUCCESS: Validation working correctly (rejected invalid data)")
                return True
            else:
                print("⚠️  WARNING: Validation may not be working as expected")
                return False
                
        except json.JSONDecodeError:
            print("Response Body (Text):")
            print(response.text)
            return False
            
    except Exception as e:
        print(f"❌ ERROR: Validation test failed - {e}")
        return False

if __name__ == "__main__":
    print()
    
    # Run tests
    results = []
    
    # Test CORS
    results.append(("CORS Preflight", test_cors_preflight()))
    print()
    
    # Test validation
    results.append(("Input Validation", test_validation()))
    print()
    
    # Test actual submission
    results.append(("Contact Form Submission", test_contact_form()))
    print()
    
    # Summary
    print("=" * 70)
    print("Test Summary")
    print("=" * 70)
    for test_name, passed in results:
        status = "✅ PASSED" if passed else "❌ FAILED"
        print(f"{test_name}: {status}")
    
    print()
    
    # Exit code
    all_passed = all(result[1] for result in results)
    if all_passed:
        print("🎉 All tests passed!")
        sys.exit(0)
    else:
        print("⚠️  Some tests failed. Check the output above for details.")
        sys.exit(1)

