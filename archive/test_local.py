# from lambda_function import lambda_handler

# class MockContext:
#     function_name = "qb-avsight-sync-local"
#     memory_limit_in_mb = 1024

# if __name__ == "__main__":
#     print("Running local test...")
#     response = lambda_handler({}, MockContext())
#     print(response)

"""
Local test script for QuickBooks-AvSight sync
Run this instead of deploying to Lambda for testing
Tests the end-of-day email function with full debug output

Usage:
    python test_local.py                    # Test with today's date
    python test_local.py 2025-12-22        # Test with specific date
"""

import json
import sys
from end_of_day_email import lambda_handler as email_lambda_handler
from datetime import date, datetime

# Simulate Lambda event and context
class MockContext:
    def __init__(self, function_name="qb-avsight-end-of-day-email-local"):
        self.function_name = function_name
        self.memory_limit_in_mb = 1024
        self.invoked_function_arn = "arn:aws:lambda:local"
        self.aws_request_id = "local-test-123"

if __name__ == "__main__":
    print("="*70)
    print("LOCAL TEST - End-of-Day Email Function")
    print("="*70)
    print(f"Test started at: {datetime.now().isoformat()}")
    print()
    
    # Get date from command line or use today
    if len(sys.argv) > 1:
        test_date = sys.argv[1]
        print(f"Testing with date from command line: {test_date}")
    else:
        # Use yesterday (2025-12-22) by default since we know it has data
        test_date = "2025-12-23"
        print(f"No date provided, using default test date: {test_date}")
        print("(You can provide a date as an argument: python test_local.py 2025-12-23)")
    
    print("\n" + "="*70)
    print("TEST: End-of-Day Email Function (end_of_day_email)")
    print("="*70)
    print(f"Date: {test_date}")
    print()
    
    email_event = {'date': test_date}
    email_context = MockContext("qb-avsight-end-of-day-email-local")
    
    try:
        print("Calling email_lambda_handler...")
        print("-" * 70)
        email_response = email_lambda_handler(email_event, email_context)
        print("-" * 70)
        print("\n" + "="*70)
        print("END-OF-DAY EMAIL FUNCTION RESPONSE:")
        print("="*70)
        print(json.dumps(email_response, indent=2))
        
        if email_response.get('statusCode') == 200:
            print("\n✅ End-of-day email function test completed successfully!")
        else:
            print(f"\n⚠️  End-of-day email function returned status code: {email_response.get('statusCode')}")
            print("Check the debug output above for details.")
            
    except Exception as e:
        print(f"\n❌ End-of-day email function error: {type(e).__name__}: {e}")
        import traceback
        print("\n" + "="*70)
        print("FULL TRACEBACK:")
        print("="*70)
        traceback.print_exc()
    
    print("\n" + "="*70)
    print("TEST COMPLETE")
    print("="*70)
    print(f"Test ended at: {datetime.now().isoformat()}")