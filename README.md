# QuickBooks-AvSight Sync for AWS Lambda

Automated synchronization between QuickBooks Online and Salesforce AvSight ERP system, deployed as an AWS Lambda function.

## 📋 Overview

This Lambda function:
- Fetches invoices and bills from QuickBooks Online
- Compares with Salesforce AvSight records
- Updates Salesforce with changed balances and new records
- Sends email summaries of sync results
- Runs on a schedule via EventBridge

## 📁 Project Structure

```
QBsync/
├── qb-avsight-sync.py              # Main Lambda handler
├── end_of_day_email.py             # End-of-day email Lambda handler
├── quickbooks_connector.py         # QuickBooks API client
├── salesforce_connector.py         # Salesforce API client
├── utils.py                        # Helper functions (email, secrets)
├── config.py                       # Configuration management
├── config.json                     # Configuration file
├── requirements.txt                # Python dependencies
└── README.md                       # This file
```

## 🚀 Setup Instructions

### 1. QuickBooks Authentication (One-Time)

Run the authentication script **locally** to get your OAuth credentials:

```bash
python archive/authenticate_quickbooks.py
```

This will:
1. Generate an authorization URL
2. Guide you through QuickBooks OAuth flow
3. Save credentials to `qb_credentials.json` (which should be uploaded to AWS Secrets Manager, then deleted)

### 2. AWS Secrets Manager Setup

Create three secrets in AWS Secrets Manager:

#### QuickBooks Credentials
```bash
aws secretsmanager create-secret \
    --name quickbooks/credentials \
    --description 'QuickBooks OAuth credentials' \
    --secret-string file://archive/qb_credentials.json
```

#### Salesforce Credentials
```bash
aws secretsmanager create-secret \
    --name salesforce/credentials \
    --description 'Salesforce login credentials' \
    --secret-string '{
        "username": "your-username@pioneer-aero.com",
        "password": "your-password",
        "security_token": "your-security-token",
        "instance_url": "https://pioneer-aero.my.salesforce.com/"
    }'
```

#### SMTP Credentials
```bash
aws secretsmanager create-secret \
    --name smtp/credentials \
    --description 'SMTP email credentials' \
    --secret-string '{
        "server": "smtp.gmail.com",
        "port": 587,
        "username": "your-email@pioneer-aero.com",
        "password": "your-app-password",
        "from_email": "your-email@pioneer-aero.com"
    }'
```

### 3. Package Lambda Deployment

Create deployment package with dependencies:

```bash
# Create deployment directory
mkdir lambda-deployment
cd lambda-deployment

# Copy code files
cp ../qb-avsight-sync.py .
cp ../quickbooks_connector.py .
cp ../salesforce_connector.py .
cp ../utils.py .
cp ../config.py .
cp ../config.json .

# Install dependencies
pip install -r ../requirements.txt -t .

# Create ZIP
zip -r lambda-deployment.zip .
```

### 4. Create Lambda Function

```bash
aws lambda create-function \
    --function-name qb-avsight-sync \
    --runtime python3.11 \
    --role arn:aws:iam::YOUR-ACCOUNT:role/lambda-execution-role \
    --handler qb-avsight-sync.lambda_handler \
    --zip-file fileb://lambda-deployment.zip \
    --timeout 900 \
    --memory-size 512 \
    --environment Variables={PYTHONPATH=/var/task}
```

### 5. Grant Secrets Manager Access

Add this policy to your Lambda execution role:

```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "secretsmanager:GetSecretValue",
                "secretsmanager:UpdateSecret"
            ],
            "Resource": [
                "arn:aws:secretsmanager:us-east-1:*:secret:quickbooks/credentials-*",
                "arn:aws:secretsmanager:us-east-1:*:secret:salesforce/credentials-*",
                "arn:aws:secretsmanager:us-east-1:*:secret:smtp/credentials-*"
            ]
        }
    ]
}
```

### 6. Set Up EventBridge Schedule

Create a schedule to run the sync automatically:

```bash
# Create EventBridge rule (runs daily at 8 AM)
aws events put-rule \
    --name qb-avsight-sync-schedule \
    --schedule-expression "cron(0 8 * * ? *)"

# Add Lambda as target
aws events put-targets \
    --rule qb-avsight-sync-schedule \
    --targets "Id"="1","Arn"="arn:aws:lambda:us-east-1:YOUR-ACCOUNT:function:qb-avsight-sync"

# Grant EventBridge permission to invoke Lambda
aws lambda add-permission \
    --function-name qb-avsight-sync \
    --statement-id eventbridge-invoke \
    --action lambda:InvokeFunction \
    --principal events.amazonaws.com \
    --source-arn arn:aws:events:us-east-1:YOUR-ACCOUNT:rule/qb-avsight-sync-schedule
```

## 🔧 Configuration

### Email Recipients

Edit the recipients list in `config.json`:

```python
recipients = [
    'user1@pioneer-aero.com',
    'user2@pioneer-aero.com',
]
```

### Sync Schedule

Modify the EventBridge cron expression to change sync frequency:

- Daily at 8 AM: `cron(0 8 * * ? *)`
- Every 6 hours: `cron(0 */6 * * ? *)`
- Weekdays at 9 AM: `cron(0 9 ? * MON-FRI *)`

## 📊 What Gets Synced

### Invoices
- Updates invoice balances in Salesforce when they change in QuickBooks
- Updates invoice status (Paid/Sent) based on balance
- Syncs QuickBooks IDs

### Bills (Payments)
- Updates existing bill balances and amounts
- Inserts new bills from QuickBooks
- Maintains bill dates and due dates

## 🔐 Security Best Practices

1. **Never commit credentials** - Use AWS Secrets Manager only
2. **Delete local credential files** after uploading to Secrets Manager
3. **Use IAM roles** with least privilege principle
4. **Enable CloudWatch Logs** for audit trail
5. **Rotate secrets regularly** through Secrets Manager

## 🐛 Troubleshooting

### Check Lambda Logs
```bash
aws logs tail /aws/lambda/qb-avsight-sync --follow
```

### Test Manually
```bash
aws lambda invoke \
    --function-name qb-avsight-sync \
    --payload '{}' \
    response.json
```

### Common Issues

**Token expired errors:**
- Lambda automatically refreshes tokens
- Check that Lambda has permission to update secrets

**Salesforce authentication fails:**
- Verify security token is current
- Check that password hasn't changed
- Ensure IP restrictions allow Lambda's IPs

**No data syncing:**
- Verify QuickBooks and Salesforce contain matching records
- Check that QuickBooks IDs are populated in Salesforce

## 📈 Monitoring

Key metrics to monitor in CloudWatch:

- Lambda duration (should be < 5 minutes)
- Error count (should be 0)
- Invocation count
- Secrets Manager API calls

## 🔄 Updating the Lambda

When you make code changes:

```bash
# Repackage
cd lambda-deployment
zip -r lambda-deployment.zip .

# Update function
aws lambda update-function-code \
    --function-name qb-avsight-sync \
    --zip-file fileb://lambda-deployment.zip
```

## 📝 File Explanations

### Core Files (Deployed to Lambda)

**qb-avsight-sync.py**
- Main entry point for Lambda sync function
- Contains sync orchestration logic
- Handles EventBridge triggers

**end_of_day_email.py**
- End-of-day email Lambda handler
- Sends daily summary emails
- Aggregates daily sync results

**quickbooks_connector.py**
- QuickBooks API client
- OAuth token management
- Query execution

**salesforce_connector.py**
- Salesforce API client
- SOQL query execution
- Bulk update/insert operations

**utils.py**
- AWS Secrets Manager integration
- Email notification system
- Time formatting helpers

**config.py** & **config.json**
- Configuration management
- Settings for batch sizes, directories, email recipients

### Directory Structure

- `archive/` - Contains test scripts, helper utilities, old deployment packages, and backup files
- `docs/` - Contains all markdown documentation files
- `deploy_packages/` - Contains deployment packages for Lambda functions (can be regenerated from source)
- `venv/` - Python virtual environment for local development (should be in `.gitignore`)

## 🤝 Support

For issues or questions:
- Check CloudWatch Logs first
- Review Salesforce API usage limits
- Verify QuickBooks OAuth is still valid
- Contact Garrett Johnson (gjohnson@pioneer-aero.com)

## 📜 License

Internal use only - Pioneer Aero Supply

---

**Last Updated:** December 2025
**Version:** 2.0 (AWS Lambda Migration)
