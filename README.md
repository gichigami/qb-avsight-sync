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
├── qb-avsight-sync.py              # Main Lambda handler   -> qb-avsight-sync
├── end_of_day_email.py             # EOD email handler     -> qb-avsight-end-of-day-email
├── quickbooks_connector.py         # QuickBooks API client (main sync only)
├── salesforce_connector.py         # Salesforce API client
├── utils.py                        # Helper functions (email, secrets, S3)
├── config.py                       # Configuration accessors
├── config.json                     # Runtime configuration (deployed; no secrets)
├── requirements.txt                # Pinned to production versions
├── scripts/build_and_deploy.sh     # Build + deploy either function
├── docs/PRODUCTION_STATE.md        # Deployed AWS resources (source of truth)
└── README.md                       # This file
```

> **Handler naming:** both Lambdas are configured with the handler
> `lambda_function.lambda_handler`. The build script renames the descriptive
> source file to `lambda_function.py` inside the deployment package, so
> `qb-avsight-sync.py` and `end_of_day_email.py` are never both in one zip.

> **This repo is the source of truth.** It was reconciled against the live
> Lambda packages on 2026-08-28. Deploy only via `scripts/build_and_deploy.sh`
> so the two never drift again; see `docs/PRODUCTION_STATE.md` for the full
> deployed configuration.

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

### 3. Package and Deploy

Use the build script — it assembles the correct module set per function, pins
dependencies to the versions running in production, renames the handler, and
excludes the packages provided by Lambda layers:

```bash
scripts/build_and_deploy.sh sync            # deploy qb-avsight-sync
scripts/build_and_deploy.sh eod             # deploy qb-avsight-end-of-day-email
scripts/build_and_deploy.sh sync --dry-run  # build the zip only
```

**Lambda layers supply `pandas`/`boto3` (`AWSSDKPandas-Python311`) and
`pioneer_email` (`pioneer-email`).** These are deliberately not vendored here;
`utils.py` imports `pioneer_email.templates` and will not run outside Lambda
without that layer.

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

Three EventBridge rules drive the automation (all times UTC):

| Rule | Expression | Target | Payload |
|---|---|---|---|
| `qb-avsight-sync-schedule` | `cron(*/15 14-23 * * ? *)` | `qb-avsight-sync` | `{"sync_mode": "incremental"}` |
| `qb-avsight-sync-full-schedule` | `cron(50 13 * * ? *)` | `qb-avsight-sync` | `{"sync_mode": "full"}` |
| `qb-avsight-end-of-day-email` | `cron(2 23 * * ? *)` | `qb-avsight-end-of-day-email` | *(none)* |

The sync mode is chosen by the EventBridge payload, not by separate functions.
Incremental runs use the last-run timestamp; a nightly full sync backfills
anything the incremental pass missed.

## 📊 What Gets Synced

### Invoices
- Updates invoice balances in Salesforce when they change in QuickBooks
- Updates invoice status (Paid/Sent) based on balance
- Syncs QuickBooks IDs

### Bills (Payments)
- Updates existing bill balances and amounts
- Inserts new bills from QuickBooks
- Maintains bill dates and due dates

### Invoice Paid Dates
- Reads QuickBooks `Payment` records and computes, per fully-paid invoice, the
  date of the payment that drove the balance to zero
- Applied per payment *line* (`Line.Amount`), not per payment total — QuickBooks
  writes valid `TotalAmt = 0` payments when applying existing customer credit

### PO Numbers (Salesforce → QuickBooks)
- Writes the AvSight PO number back onto the QuickBooks invoice's
  `P.O. Number` custom field via sparse update
- The only flow that writes *into* QuickBooks; everything else is read-only
- Gated by `po_sync_enabled` and capped by `po_sync_batch_size` in `config.json`
- Handles stale `SyncToken` conflicts (QuickBooks error 5010)

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
- Lambda refreshes tokens automatically. QuickBooks rotates the refresh token on
  every refresh, so `QuickBooksConnector` persists the new one to Secrets Manager
  *immediately* via the `on_token_refresh` callback — the execution role needs
  `secretsmanager:UpdateSecret`.
- If the refresh token dies (`invalid_grant`), the sync emails an alert via
  `send_auth_failure_alert()`, throttled to once per UTC day by an S3 marker
  under `alerts/qb-auth-failure/`. Re-authenticate to recover, then run a
  catch-up full sync:
  ```bash
  aws lambda invoke --function-name qb-avsight-sync \
      --payload '{"sync_mode":"full"}' \
      --cli-binary-format raw-in-base64-out /tmp/qb.json
  ```

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

Commit the change, then deploy from the repo:

```bash
scripts/build_and_deploy.sh sync   # or: eod
```

To confirm the deployed code matches this repo, compare the handler in the live
package against the source:

```bash
aws lambda get-function --function-name qb-avsight-sync \
    --query 'Code.Location' --output text \
  | xargs curl -s -o /tmp/live.zip
unzip -p /tmp/live.zip lambda_function.py | diff - qb-avsight-sync.py && echo "in sync"
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
- Email notification system (SES + the `pioneer-email` layer templates)
- OAuth failure alerting with daily S3-marker throttling
- S3 persistence for daily summaries and bulk write results
- Time formatting helpers

**config.py** & **config.json**
- Configuration management
- Settings for batch sizes, directories, email recipients, PO sync toggles
- `config.json` is deployed with the code and contains no secrets

### Directory Structure

- `scripts/` - Build and deploy tooling
- `docs/` - Documentation; `PRODUCTION_STATE.md` records the deployed AWS resources
- `archive/` - Test scripts, helper utilities, and backup files
- `deploy_packages/` - **Stale.** Vendored copies of an older build, kept from
  before this repo was reconciled with production. They are *not* the source of
  truth and contain outdated copies of `lambda_function.py` / `utils.py`. Build
  from the repo root via `scripts/build_and_deploy.sh` instead.
- `website/` - Static site for the separate `airbridge-contact-form` automation

## 🤝 Support

For issues or questions:
- Check CloudWatch Logs first
- Review Salesforce API usage limits
- Verify QuickBooks OAuth is still valid
- Contact Garrett Johnson (gjohnson@pioneer-aero.com)

## 📜 License

Internal use only - Pioneer Aero Supply

---

**Last Updated:** August 2026
**Version:** 2.1 (reconciled with production — see `docs/PRODUCTION_STATE.md`)
