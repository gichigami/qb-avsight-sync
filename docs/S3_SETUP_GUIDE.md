# S3 Setup Guide for Daily Email Summaries

This guide will walk you through setting up an S3 bucket to store daily QuickBooks sync summaries.

## Prerequisites

- AWS CLI installed and configured on your computer
- AWS account with appropriate permissions
- Your AWS credentials configured (run `aws configure` if you haven't already)

## Step 1: Create the S3 Bucket

Run this command to create a new S3 bucket. Replace `qb-avsight-sync-daily-summaries` with your preferred bucket name (must be globally unique):

```bash
aws s3 mb s3://qb-avsight-sync-daily-summaries --region us-east-1
```

**Note:** S3 bucket names must be globally unique across all AWS accounts. If the name is taken, try:
- `qb-avsight-sync-daily-summaries-<your-initials>`
- `qb-avsight-sync-summaries-<your-company>`
- Or any other unique name

## Step 2: Configure Bucket Versioning (Optional but Recommended)

This helps protect against accidental deletions:

```bash
aws s3api put-bucket-versioning \
    --bucket qb-avsight-sync-daily-summaries \
    --versioning-configuration Status=Enabled
```

## Step 3: Set Up Lifecycle Policy (Optional)

To automatically clean up old summaries after a certain period (e.g., 90 days), create a lifecycle policy:

```bash
cat > lifecycle-policy.json << 'EOF'
{
    "Rules": [
        {
            "Id": "DeleteOldSummaries",
            "Status": "Enabled",
            "Prefix": "daily-summaries/",
            "Expiration": {
                "Days": 90
            }
        }
    ]
}
EOF

aws s3api put-bucket-lifecycle-configuration \
    --bucket qb-avsight-sync-daily-summaries \
    --lifecycle-configuration file://lifecycle-policy.json
```

This will automatically delete summaries older than 90 days. Adjust the `Days` value as needed.

## Step 4: Configure Lambda IAM Permissions

Your Lambda function needs permission to read and write to S3. You'll need to update your Lambda execution role with S3 permissions.

### Option A: Using AWS Console

1. Go to AWS Lambda → Your function → Configuration → Permissions
2. Click on the Execution role
3. Click "Add permissions" → "Create inline policy"
4. Use the JSON policy editor and paste this:

```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "s3:PutObject",
                "s3:GetObject",
                "s3:ListBucket"
            ],
            "Resource": [
                "arn:aws:s3:::qb-avsight-sync-daily-summaries",
                "arn:aws:s3:::qb-avsight-sync-daily-summaries/*"
            ]
        }
    ]
}
```

Replace `qb-avsight-sync-daily-summaries` with your actual bucket name.

### Option B: Using AWS CLI

First, find your Lambda function's role ARN:

```bash
aws lambda get-function-configuration \
    --function-name qb-avsight-sync2 \
    --query 'Role' \
    --output text
```

Then create a policy file:

```bash
cat > s3-policy.json << 'EOF'
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "s3:PutObject",
                "s3:GetObject",
                "s3:ListBucket"
            ],
            "Resource": [
                "arn:aws:s3:::qb-avsight-sync-daily-summaries",
                "arn:aws:s3:::qb-avsight-sync-daily-summaries/*"
            ]
        }
    ]
}
EOF
```

Attach the policy to your Lambda role (replace `YOUR_ROLE_NAME` with the role name from the ARN above):

```bash
aws iam put-role-policy \
    --role-name YOUR_ROLE_NAME \
    --policy-name S3DailySummariesAccess \
    --policy-document file://s3-policy.json
```

## Step 5: Set Environment Variable in Lambda

You need to tell your Lambda function which S3 bucket to use:

1. Go to AWS Lambda → Your function → Configuration → Environment variables
2. Click "Edit"
3. Add a new environment variable:
   - **Key:** `S3_BUCKET_NAME`
   - **Value:** `qb-avsight-sync-daily-summaries` (or your bucket name)

Or using AWS CLI:

```bash
aws lambda update-function-configuration \
    --function-name qb-avsight-sync2 \
    --environment Variables="{S3_BUCKET_NAME=qb-avsight-sync-daily-summaries}"
```

## Step 6: Set Up End-of-Day Email Lambda Function

You'll need to create a separate Lambda function that sends the end-of-day email. This should be triggered once per day (e.g., at 6:00 PM).

### Create the Lambda Function

1. Create a new Lambda function called `qb-avsight-end-of-day-email`
2. Upload the `end_of_day_email.py` file (or package it with `utils.py`)
3. Set the same environment variable `S3_BUCKET_NAME`
4. Set the handler to `end_of_day_email.lambda_handler`
5. Set timeout to 30 seconds
6. Use the same IAM role as your main sync function (or create a new one with the same permissions)

### Set Up EventBridge Schedule

Create a scheduled rule to trigger the end-of-day email function daily:

```bash
aws events put-rule \
    --name qb-avsight-end-of-day-email \
    --schedule-expression "cron(0 18 * * ? *)" \
    --description "Trigger end-of-day email at 6 PM EST daily"
```

**Note:** The cron expression `cron(0 18 * * ? *)` means 6:00 PM UTC. Adjust for your timezone:
- EST (UTC-5): `cron(0 23 * * ? *)` for 6 PM EST
- PST (UTC-8): `cron(0 2 * * ? *)` for 6 PM PST (next day)

Then add the Lambda function as a target:

```bash
aws events put-targets \
    --rule qb-avsight-end-of-day-email \
    --targets "Id"="1","Arn"="arn:aws:lambda:us-east-1:YOUR_ACCOUNT_ID:function:qb-avsight-end-of-day-email"
```

Replace `YOUR_ACCOUNT_ID` with your AWS account ID. You can find it with:

```bash
aws sts get-caller-identity --query Account --output text
```

## Step 7: Verify Setup

Test that everything works:

1. **Test S3 access from Lambda:**
   - Run your main sync function
   - Check CloudWatch logs to see if it successfully saves to S3
   - Verify the file exists: `aws s3 ls s3://qb-avsight-sync-daily-summaries/daily-summaries/`

2. **Test end-of-day email:**
   - Manually invoke the end-of-day email function:
     ```bash
     aws lambda invoke \
         --function-name qb-avsight-end-of-day-email \
         --payload '{"date":"2025-01-20"}' \
         response.json
     ```
   - Check your email to see if the summary was received

## Troubleshooting

### Lambda can't access S3

- Check IAM permissions on the Lambda execution role
- Verify the bucket name in the environment variable matches the actual bucket
- Check CloudWatch logs for specific error messages

### End-of-day email not sending

- Verify the EventBridge schedule is active
- Check that the Lambda function has SMTP credentials in Secrets Manager
- Review CloudWatch logs for the end-of-day email function
- Test manually by invoking the function

### No data in daily summary

- Make sure your main sync function is running and saving to S3
- Check the date format matches (YYYY-MM-DD)
- Verify the S3 bucket path: `daily-summaries/YYYY-MM-DD/summary.json`

## File Structure in S3

Your S3 bucket will have this structure:

```
qb-avsight-sync-daily-summaries/
└── daily-summaries/
    ├── 2025-01-20/
    │   └── summary.json
    ├── 2025-01-21/
    │   └── summary.json
    └── 2025-01-22/
        └── summary.json
```

Each `summary.json` contains all the sync runs for that day, including:
- List of all runs with timestamps
- All bills updated
- All bills inserted
- All invoices updated
- Summary statistics

## Cost Considerations

S3 storage is very inexpensive:
- First 50 TB: $0.023 per GB/month
- PUT requests: $0.005 per 1,000 requests
- GET requests: $0.0004 per 1,000 requests

For daily summaries, you're looking at:
- Storage: ~$0.01-0.10/month (depending on data volume)
- Requests: ~$0.01/month

Total estimated cost: **Less than $1/month**

## Next Steps

1. Complete the S3 bucket setup
2. Update your Lambda function with the environment variable
3. Deploy the updated code
4. Set up the end-of-day email Lambda function
5. Configure the EventBridge schedule
6. Test the complete flow

If you need help with any step, check the AWS documentation or reach out for assistance!

