"""
Script to set a test timestamp in S3 for incremental sync testing
This will make the next sync run fetch only records modified since this timestamp
"""

import json
import boto3
from datetime import datetime, timezone, timedelta
from config import get_s3_bucket_name

def set_test_timestamp(hours_ago: int = 24):
    """
    Set a test timestamp in S3 that is hours_ago hours in the past
    
    Args:
        hours_ago: Number of hours ago to set the timestamp (default: 24)
    """
    bucket_name = get_s3_bucket_name()
    key = 'last-run-timestamp.json'
    
    # Create timestamp that is hours_ago hours in the past
    test_timestamp = datetime.now(timezone.utc) - timedelta(hours=hours_ago)
    timestamp_str = test_timestamp.strftime('%Y-%m-%dT%H:%M:%SZ')
    
    data = {
        'last_run_timestamp': timestamp_str,
        'updated_at': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
        'test_note': f'Test timestamp set {hours_ago} hours ago for incremental sync testing'
    }
    
    s3_client = boto3.client('s3')
    
    try:
        json_data = json.dumps(data, indent=2)
        s3_client.put_object(
            Bucket=bucket_name,
            Key=key,
            Body=json_data.encode('utf-8'),
            ContentType='application/json'
        )
        
        print("="*70)
        print("✅ Test timestamp uploaded to S3")
        print("="*70)
        print(f"Bucket: {bucket_name}")
        print(f"Key: {key}")
        print(f"Timestamp: {timestamp_str}")
        print(f"Time: {test_timestamp.isoformat()}")
        print(f"Hours ago: {hours_ago}")
        print("\nNext sync run will only fetch records modified since this timestamp.")
        print("="*70)
        
    except Exception as e:
        print(f"❌ Failed to upload test timestamp: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    import sys
    
    # Allow specifying hours ago as command line argument
    hours_ago = 24
    if len(sys.argv) > 1:
        try:
            hours_ago = int(sys.argv[1])
        except ValueError:
            print(f"⚠️ Invalid hours argument: {sys.argv[1]}, using default: 24")
    
    set_test_timestamp(hours_ago)

