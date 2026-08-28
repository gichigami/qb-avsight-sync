# AWS Lambda Functions Deployment Guide

Complete guide for deploying and managing all QB-AvSight AWS Lambda functions.

## Table of Contents

1. [Overview](#overview)
2. [Prerequisites](#prerequisites)
3. [Function Inventory](#function-inventory)
4. [Deployment Procedures](#deployment-procedures)
5. [Configuration Management](#configuration-management)
6. [EventBridge Schedules](#eventbridge-schedules)
7. [API Gateway Setup](#api-gateway-setup)
8. [IAM Roles & Permissions](#iam-roles--permissions)
9. [Monitoring & Troubleshooting](#monitoring--troubleshooting)
10. [Common Commands Reference](#common-commands-reference)

---

## Overview

This project consists of 4 AWS Lambda functions that sync data between QuickBooks Online and Salesforce AvSight, send email notifications, and handle website contact form submissions.

### Architecture

```
EventBridge Schedules → Lambda Functions → QuickBooks/Salesforce APIs
                                    ↓
                            Secrets Manager (credentials)
                                    ↓
                            S3 (daily summaries)
                                    ↓
                            SMTP (email notifications)

API Gateway → Contact Form Lambda → SMTP
```

---

## Prerequisites

### 1. AWS CLI Setup

```bash
# Install AWS CLI (if not already installed)
# macOS:
brew install awscli

# Verify installation
aws --version

# Configure credentials
aws configure
# Enter:
# - AWS Access Key ID
# - AWS Secret Access Key
# - Default region: us-east-1
# - Default output format: json
```

### 2. Required AWS Resources

Before deploying, ensure these resources exist:

- **S3 Bucket**: `qb-avsight-sync-daily-summaries` (for daily summary storage)
- **Secrets Manager Secrets**:
  - `quickbooks/credentials` - QuickBooks OAuth credentials
  - `salesforce/credentials` - Salesforce API credentials
  - `smtp/credentials` - SMTP email credentials
- **IAM Roles** (will be created during deployment if needed)

### 3. Local Development Setup

```bash
# Navigate to project directory
cd /Users/garrettjohnson/Desktop/Development/qb-avsight-sync2

# Create virtual environment (optional, for local testing)
python3 -m venv venv
source venv/bin/activate

# Install dependencies (for local testing)
pip install -r requirements.txt
```

---

## Function Inventory

### Current Deployed Functions

Verified against AWS on 2026-08-28.

| Function Name | Runtime | Handler | Memory | Timeout | Purpose |
|--------------|---------|---------|--------|---------|---------|
| `qb-avsight-sync` | python3.11 | `lambda_function.lambda_handler` | 1024 MB | 900s | Both incremental and full sync; mode comes from the event payload |
| `qb-avsight-end-of-day-email` | python3.11 | `lambda_function.lambda_handler` | 256 MB | 70s | Daily summary email |
| `airbridge-contact-form` | python3.11 | `lambda_function.lambda_handler` | 128 MB | 30s | Website contact form handler |
| `qb-avsight-sync2` | python3.11 | `lambda_function.lambda_handler` | 1024 MB | 900s | **Obsolete.** Described in AWS as "formerly handled full sync"; no schedule targets it |

### EventBridge Schedules

Both sync rules target the **same** function and select behaviour via the event
payload — there is no longer a separate full-sync function.

| Rule Name | Schedule | Target Function | Input | Description |
|-----------|----------|----------------|-------|-------------|
| `qb-avsight-sync-schedule` | `cron(*/15 14-23 * * ? *)` | `qb-avsight-sync` | `{"sync_mode": "incremental"}` | Every 15 minutes, 14:00-23:00 UTC (8 AM-5 PM CST / 9 AM-6 PM CDT) |
| `qb-avsight-sync-full-schedule` | `cron(50 13 * * ? *)` | `qb-avsight-sync` | `{"sync_mode": "full"}` | Daily at 13:50 UTC (7:50 AM CST / 8:50 AM CDT) |
| `qb-avsight-end-of-day-email` | `cron(2 23 * * ? *)` | `qb-avsight-end-of-day-email` | *(none)* | Daily at 23:02 UTC (5:02 PM CST / 6:02 PM CDT) |

---

## Deployment Procedures

> **Superseded for the QuickBooks sync functions.** The manual packaging steps
> that used to live here described `deploy_packages/{main,full_sync,email}_function/`,
> which no longer exist, and treated full sync as a separate Lambda, which it
> is not. Deploy from `functions/<function-name>/` with the build script:
>
> ```bash
> scripts/build_and_deploy.sh qb-avsight-sync
> scripts/build_and_deploy.sh qb-avsight-end-of-day-email
> scripts/build_and_deploy.sh qb-avsight-sync --dry-run   # build only
>
> scripts/verify_against_prod.sh   # confirm repo matches deployed code
> ```
>
> The script installs each function's pinned dependencies, excludes the
> packages supplied by the `AWSSDKPandas-Python311` and `pioneer-email` layers,
> and uploads via `aws lambda update-function-code`. See the repository README
> and `docs/PRODUCTION_STATE.md`. The original manual steps remain in git
> history at commit `c7243ed`.

The contact-form function below is a separate automation and is still deployed
by hand.


### airbridge-contact-form (deployed manually)

**Purpose**: Handles contact form submissions from the website.

**Deployment Steps**:

#### 1. Prepare Deployment Package

```bash
cd /Users/garrettjohnson/Desktop/Development/qb-avsight-sync2

# Navigate to contact form function directory
cd deploy_packages/contact_form_function

# Create deployment package
mkdir -p package
cd package

# Copy source files
cp ../qb-avsight-sync.py .
cp ../utils.py .

# Install dependencies (boto3 is provided by Lambda runtime)
# For minimal package, we can skip boto3 installation
# But if you want to include it:
pip install boto3 -t . --platform manylinux2014_x86_64 --only-binary=:all:

# Create ZIP file
zip -r airbridge-contact-form.zip . -x "*.pyc" "__pycache__/*" "*.dist-info/*"

# Move ZIP
mv airbridge-contact-form.zip ../../../
cd ../../..
```

#### 2. Deploy Function

```bash
# Update function code
aws lambda update-function-code \
    --function-name airbridge-contact-form \
    --zip-file fileb://deploy_packages/airbridge-contact-form.zip

# Verify
aws lambda get-function-configuration --function-name airbridge-contact-form
```

---

## Configuration Management

### config.json

`config.json` contains non-sensitive configuration packaged with each Lambda.
**Each function has its own copy** at `functions/<function-name>/config.json`,
matching what is actually deployed — they are not identical.

`functions/qb-avsight-sync/config.json`:

```json
{
  "salesforce_batch_size": 100,
  "results_directory": "/tmp",
  "qb_redirect_uri": "https://developer.intuit.com/v2/OAuth2Playground/RedirectUrl",
  "qb_max_results_per_page": 100,
  "enable_incremental_sync": true,
  "email_recipients_run_summary": [
    "gjohnson@pioneer-aero.com"
  ],
  "email_recipients_daily_summary": [
    "gjohnson@pioneer-aero.com"
  ],
  "s3_bucket_name": "qb-avsight-sync-daily-summaries",
  "po_sync_enabled": true,
  "po_sync_batch_size": 200
}
```

`functions/qb-avsight-end-of-day-email/config.json` carries a subset:
`salesforce_batch_size`, `results_directory`, `email_recipients_daily_summary`,
`s3_bucket_name`.

**To update configuration**:
1. Edit `config.json` in the relevant function directory
2. Redeploy that function with `scripts/build_and_deploy.sh <function-name>`
3. Run `scripts/verify_against_prod.sh` to confirm the change landed

### Environment Variables

Some configuration is set via Lambda environment variables:

- `S3_BUCKET_NAME`: S3 bucket for daily summaries. Set only on
  `qb-avsight-end-of-day-email`; `qb-avsight-sync` has **no** environment
  variables and reads the bucket from its `config.json`.

**To update environment variables**:

```bash
aws lambda update-function-configuration \
    --function-name FUNCTION_NAME \
    --environment Variables='{"KEY":"VALUE"}'
```

### Secrets Manager

Sensitive credentials are stored in AWS Secrets Manager:

- `quickbooks/credentials` - QuickBooks OAuth tokens
- `salesforce/credentials` - Salesforce API credentials
- `smtp/credentials` - SMTP email credentials

**To update secrets**:

```bash
# Update QuickBooks credentials
aws secretsmanager update-secret \
    --secret-id quickbooks/credentials \
    --secret-string '{"key":"value"}'

# Update Salesforce credentials
aws secretsmanager update-secret \
    --secret-id salesforce/credentials \
    --secret-string '{"key":"value"}'

# Update SMTP credentials
aws secretsmanager update-secret \
    --secret-id smtp/credentials \
    --secret-string '{"key":"value"}'
```

---

## EventBridge Schedules

### Current Schedules

The sync functions are triggered by EventBridge (CloudWatch Events) schedules.

### Setup/Update Schedules

Use the provided script:

```bash
cd /Users/garrettjohnson/Desktop/Development/qb-avsight-sync2
chmod +x setup_eventbridge.sh
./setup_eventbridge.sh
```

### Manual Schedule Management

#### Create/Update Sync Schedule

```bash
# Main incremental sync (every 15 minutes, 14:00-23:00 UTC)
aws events put-rule \
    --name "qb-avsight-sync-schedule" \
    --schedule-expression "cron(*/15 14-23 * * ? *)" \
    --description "Run QB-AvSight sync every 15 minutes from 8 AM to 5 PM Central" \
    --state ENABLED

# Add Lambda as target
aws events put-targets \
    --rule "qb-avsight-sync-schedule" \
    --targets "Id=1,Arn=arn:aws:lambda:us-east-1:904198142431:function:qb-avsight-sync2"

# Grant permission
aws lambda add-permission \
    --function-name qb-avsight-sync2 \
    --statement-id "eventbridge-sync-schedule" \
    --action "lambda:InvokeFunction" \
    --principal events.amazonaws.com \
    --source-arn "arn:aws:events:us-east-1:904198142431:rule/qb-avsight-sync-schedule"
```

#### Create/Update End-of-Day Email Schedule

```bash
# End-of-day email (23:02 UTC = 5:02 PM CST / 6:02 PM CDT)
aws events put-rule \
    --name "qb-avsight-end-of-day-email" \
    --schedule-expression "cron(2 23 * * ? *)" \
    --description "Send daily summary email at end of day" \
    --state ENABLED

# Add Lambda as target
aws events put-targets \
    --rule "qb-avsight-end-of-day-email" \
    --targets "Id=1,Arn=arn:aws:lambda:us-east-1:904198142431:function:qb-avsight-end-of-day-email"

# Grant permission
aws lambda add-permission \
    --function-name qb-avsight-end-of-day-email \
    --statement-id "eventbridge-end-of-day-email" \
    --action "lambda:InvokeFunction" \
    --principal events.amazonaws.com \
    --source-arn "arn:aws:events:us-east-1:904198142431:rule/qb-avsight-end-of-day-email"
```

#### List All Schedules

```bash
aws events list-rules --query 'Rules[?contains(Name, `qb-avsight`)].{Name:Name,Schedule:ScheduleExpression,State:State}' --output table
```

#### Disable/Enable Schedule

```bash
# Disable
aws events disable-rule --name "qb-avsight-sync-schedule"

# Enable
aws events enable-rule --name "qb-avsight-sync-schedule"
```

---

## API Gateway Setup

The `airbridge-contact-form` function is exposed via API Gateway.

### Current API

- **API Name**: `airbridge-contact-api`
- **API ID**: `ov9ok9i1h8`

### View API Details

```bash
# Get API details
aws apigateway get-rest-api --rest-api-id ov9ok9i1h8

# List resources
aws apigateway get-resources --rest-api-id ov9ok9i1h8

# Get deployment stages
aws apigateway get-stages --rest-api-id ov9ok9i1h8
```

### Update API Integration

If you need to update the Lambda integration:

```bash
# Get resource ID for the POST method
RESOURCE_ID=$(aws apigateway get-resources --rest-api-id ov9ok9i1h8 --query 'items[?path==`/contact`].id' --output text)

# Update integration
aws apigateway put-integration \
    --rest-api-id ov9ok9i1h8 \
    --resource-id $RESOURCE_ID \
    --http-method POST \
    --type AWS_PROXY \
    --integration-http-method POST \
    --uri arn:aws:apigateway:us-east-1:lambda:path/2015-03-31/functions/arn:aws:lambda:us-east-1:904198142431:function:airbridge-contact-form/invocations
```

### Deploy API

```bash
# Create deployment
aws apigateway create-deployment \
    --rest-api-id ov9ok9i1h8 \
    --stage-name prod \
    --description "Deploy updated API"
```

---

## IAM Roles & Permissions

### Required IAM Roles

1. **qb-avsight-sync2-role** (`arn:aws:iam::904198142431:role/service-role/qb-avsight-sync2-role-cmwssj0z`)
   - Used by: `qb-avsight-sync2`, `qb-avsight-end-of-day-email`
   - Permissions needed:
     - Secrets Manager: Read `quickbooks/credentials`, `salesforce/credentials`, `smtp/credentials`
     - S3: Read/Write to `qb-avsight-sync-daily-summaries` bucket
     - CloudWatch Logs: Write logs

2. **lambda-execution-role** (`arn:aws:iam::904198142431:role/lambda-execution-role`)
   - Used by: `qb-avsight-sync`
   - Permissions needed: Same as above

3. **airbridge-contact-form-role** (`arn:aws:iam::904198142431:role/airbridge-contact-form-role`)
   - Used by: `airbridge-contact-form`
   - Permissions needed:
     - Secrets Manager: Read `smtp/credentials`
     - CloudWatch Logs: Write logs

### View Role Policies

```bash
# List policies for a role
aws iam list-role-policies --role-name service-role/qb-avsight-sync2-role-cmwssj0z

# Get inline policy
aws iam get-role-policy \
    --role-name service-role/qb-avsight-sync2-role-cmwssj0z \
    --policy-name POLICY_NAME
```

### Required Permissions Policy

Example policy for sync functions:

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
        "arn:aws:secretsmanager:us-east-1:904198142431:secret:quickbooks/credentials-*",
        "arn:aws:secretsmanager:us-east-1:904198142431:secret:salesforce/credentials-*",
        "arn:aws:secretsmanager:us-east-1:904198142431:secret:smtp/credentials-*"
      ]
    },
    {
      "Effect": "Allow",
      "Action": [
        "s3:GetObject",
        "s3:PutObject",
        "s3:ListBucket"
      ],
      "Resource": [
        "arn:aws:s3:::qb-avsight-sync-daily-summaries",
        "arn:aws:s3:::qb-avsight-sync-daily-summaries/*"
      ]
    },
    {
      "Effect": "Allow",
      "Action": [
        "logs:CreateLogGroup",
        "logs:CreateLogStream",
        "logs:PutLogEvents"
      ],
      "Resource": "arn:aws:logs:*:*:*"
    }
  ]
}
```

---

## Monitoring & Troubleshooting

### View Function Logs

```bash
# Tail logs in real-time (recommended)
aws logs tail /aws/lambda/qb-avsight-sync2 --follow

# View recent logs
aws logs tail /aws/lambda/qb-avsight-sync2 --since 1h

# Get specific log stream
aws logs get-log-events \
    --log-group-name /aws/lambda/qb-avsight-sync2 \
    --log-stream-name STREAM_NAME \
    --limit 50
```

### Check Function Metrics

```bash
# List CloudWatch metrics for a function
aws cloudwatch list-metrics \
    --namespace AWS/Lambda \
    --dimensions Name=FunctionName,Value=qb-avsight-sync2
```

### Test Function Invocation

```bash
# Invoke function with empty payload
aws lambda invoke \
    --function-name qb-avsight-sync2 \
    --payload '{}' \
    response.json

# View response
cat response.json | jq .

# Invoke with custom payload
aws lambda invoke \
    --function-name qb-avsight-sync2 \
    --payload '{"test": "data"}' \
    response.json
```

### Common Issues

#### Issue: Function timeout

**Solution**: Increase timeout
```bash
aws lambda update-function-configuration \
    --function-name FUNCTION_NAME \
    --timeout 900
```

#### Issue: Out of memory

**Solution**: Increase memory
```bash
aws lambda update-function-configuration \
    --function-name FUNCTION_NAME \
    --memory-size 2048
```

#### Issue: Permission denied (Secrets Manager)

**Solution**: Check IAM role has Secrets Manager permissions
```bash
# Verify role
aws lambda get-function-configuration --function-name FUNCTION_NAME --query Role

# Check role policies
aws iam list-role-policies --role-name ROLE_NAME
```

#### Issue: Package too large

**Solution**: Use Lambda Layers for dependencies
- pandas and boto3 are already in the `AWSSDKPandas-Python311` layer
- Only package application-specific dependencies

#### Issue: Function not triggered by EventBridge

**Solution**: Check permissions and target configuration
```bash
# Verify rule exists
aws events describe-rule --name RULE_NAME

# Check targets
aws events list-targets-by-rule --rule RULE_NAME

# Verify Lambda permission
aws lambda get-policy --function-name FUNCTION_NAME
```

---

## Common Commands Reference

### List All Functions

```bash
# List all qb-avsight functions
aws lambda list-functions \
    --query 'Functions[?contains(FunctionName, `qb-avsight`) || contains(FunctionName, `airbridge`)].{Name:FunctionName,Runtime:Runtime,Memory:MemorySize,Timeout:Timeout,LastModified:LastModified}' \
    --output table
```

### Get Function Details

```bash
# Get full configuration
aws lambda get-function-configuration --function-name FUNCTION_NAME

# Get function code location
aws lambda get-function --function-name FUNCTION_NAME --query Code.Location
```

### Update Function Code

```bash
# From local ZIP file
aws lambda update-function-code \
    --function-name FUNCTION_NAME \
    --zip-file fileb://path/to/package.zip

# From S3
aws lambda update-function-code \
    --function-name FUNCTION_NAME \
    --s3-bucket BUCKET_NAME \
    --s3-key package.zip
```

### Update Function Configuration

```bash
# Update timeout
aws lambda update-function-configuration \
    --function-name FUNCTION_NAME \
    --timeout 900

# Update memory
aws lambda update-function-configuration \
    --function-name FUNCTION_NAME \
    --memory-size 1024

# Update environment variables
aws lambda update-function-configuration \
    --function-name FUNCTION_NAME \
    --environment Variables='{"KEY":"VALUE"}'

# Update handler
aws lambda update-function-configuration \
    --function-name FUNCTION_NAME \
    --handler new_handler.function
```

### View Logs

```bash
# Tail logs (follow mode)
aws logs tail /aws/lambda/FUNCTION_NAME --follow

# View logs since specific time
aws logs tail /aws/lambda/FUNCTION_NAME --since 1h
aws logs tail /aws/lambda/FUNCTION_NAME --since 2024-01-01T00:00:00

# Filter logs
aws logs tail /aws/lambda/FUNCTION_NAME --filter-pattern "ERROR"
```

### Invoke Functions

```bash
# Basic invocation
aws lambda invoke \
    --function-name FUNCTION_NAME \
    --payload '{}' \
    response.json

# With custom payload
aws lambda invoke \
    --function-name FUNCTION_NAME \
    --payload '{"key":"value"}' \
    response.json

# View response
cat response.json | jq .
```

### EventBridge Commands

```bash
# List all rules
aws events list-rules

# Describe a rule
aws events describe-rule --name RULE_NAME

# List targets for a rule
aws events list-targets-by-rule --rule RULE_NAME

# Enable/Disable rule
aws events enable-rule --name RULE_NAME
aws events disable-rule --name RULE_NAME
```

### Secrets Manager Commands

```bash
# List secrets
aws secretsmanager list-secrets

# Get secret value
aws secretsmanager get-secret-value --secret-id SECRET_NAME

# Update secret
aws secretsmanager update-secret \
    --secret-id SECRET_NAME \
    --secret-string '{"key":"value"}'
```

### S3 Commands

```bash
# List objects in bucket
aws s3 ls s3://qb-avsight-sync-daily-summaries/

# Download a file
aws s3 cp s3://qb-avsight-sync-daily-summaries/FILE_NAME ./

# Upload a file
aws s3 cp ./FILE_NAME s3://qb-avsight-sync-daily-summaries/
```

---

## Quick Deployment Checklist

When deploying updates:

- [ ] Update `config.json` if needed
- [ ] Recreate deployment packages with updated code
- [ ] Test deployment package locally (if possible)
- [ ] Update Lambda function code
- [ ] Verify function configuration (timeout, memory, environment variables)
- [ ] Test function invocation
- [ ] Check CloudWatch logs for errors
- [ ] Verify EventBridge schedules are still configured correctly
- [ ] Monitor first few scheduled runs

---

## Support & Resources

- **AWS Lambda Documentation**: https://docs.aws.amazon.com/lambda/
- **EventBridge Documentation**: https://docs.aws.amazon.com/eventbridge/
- **Secrets Manager Documentation**: https://docs.aws.amazon.com/secretsmanager/
- **Project README**: See `README.md` in project root

---

## Notes

- **Account ID**: `904198142431`
- **Region**: `us-east-1`
- **Lambda Layer**: `arn:aws:lambda:us-east-1:336392948345:layer:AWSSDKPandas-Python311:7` (provides pandas and boto3)
- All functions use Python 3.11 runtime
- Timezone considerations: EventBridge schedules use UTC; adjust for local timezone (CST/CDT)

---

*Last Updated: 2025-12-23*

