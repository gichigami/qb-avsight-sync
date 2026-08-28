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

Shared modules live in one place; each function directory holds its handler and
anything specific to it. A deployment package is `_shared/` + the function dir:

```
QBsync/
├── functions/
│   ├── _shared/                         # one canonical copy, used by both
│   │   ├── utils.py                     #   email, secrets, S3, alerting
│   │   ├── config.py                    #   configuration accessors
│   │   └── salesforce_connector.py      #   Salesforce API client
│   ├── qb-avsight-sync/                 # -> Lambda: qb-avsight-sync
│   │   ├── lambda_function.py           #   main sync handler
│   │   ├── quickbooks_connector.py      #   QuickBooks client (this fn only)
│   │   ├── config.json                  #   runtime config (no secrets)
│   │   └── requirements.txt             #   pinned dependencies
│   └── qb-avsight-end-of-day-email/     # -> Lambda: qb-avsight-end-of-day-email
│       ├── lambda_function.py           #   EOD email handler
│       ├── config.json
│       └── requirements.txt
├── scripts/
│   ├── build_and_deploy.sh              # assemble _shared + fn dir, deploy
│   └── verify_against_prod.sh           # assert repo == deployed code
├── docs/PRODUCTION_STATE.md             # deployed AWS resources
└── README.md
```

A function's own file wins over `_shared/` on a name collision, so a function
can override a shared module if it ever genuinely needs to. Neither does today.

> **`config.json` stays per-function** — the two deployments legitimately carry
> different keys (the sync's includes the PO-sync settings). So do the pinned
> `requirements.txt` files.

> **This repo is the source of truth**, reconciled against the live packages and
> verified byte-for-byte. Deploy only via `scripts/build_and_deploy.sh`; see
> `docs/PRODUCTION_STATE.md` for the full deployed configuration.

### Checking the repo still matches production

```bash
scripts/verify_against_prod.sh                    # all functions
scripts/verify_against_prod.sh qb-avsight-sync    # just one
```

Downloads each live package and diffs every first-party file, exiting non-zero
on drift. Dependency-version differences are reported as warnings, not
failures — they shift on any rebuild and are not source drift.

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

Use the build script — it assembles `functions/_shared/` plus the function's own
directory, installs that function's pinned dependencies, and excludes the
packages supplied by Lambda layers:

```bash
scripts/build_and_deploy.sh qb-avsight-sync
scripts/build_and_deploy.sh qb-avsight-end-of-day-email
scripts/build_and_deploy.sh qb-avsight-sync --dry-run   # build the zip only
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

Each function has its own `config.json`. Edit the relevant one, then redeploy
that function:

```jsonc
// functions/qb-avsight-sync/config.json          -> run-summary emails
// functions/qb-avsight-end-of-day-email/config.json -> daily-summary emails
"email_recipients_run_summary":   ["user1@pioneer-aero.com"],
"email_recipients_daily_summary": ["user1@pioneer-aero.com"]
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
scripts/build_and_deploy.sh qb-avsight-sync   # or qb-avsight-end-of-day-email
scripts/verify_against_prod.sh                # confirm they now match
```

A change to `functions/_shared/` affects **both** Lambdas, but only the one you
deploy actually picks it up. After editing a shared module, deploy every
function you intend to change — `verify_against_prod.sh` will keep reporting
drift for any you skip, which is the intended signal, not a failure.

## 📝 File Explanations

### Core Files (Deployed to Lambda)

**functions/qb-avsight-sync/lambda_function.py**
- Main entry point for the sync function
- Contains sync orchestration logic
- Reads `sync_mode` (`incremental` / `full`) from the EventBridge payload

**functions/qb-avsight-end-of-day-email/lambda_function.py**
- End-of-day email Lambda handler
- Sends daily summary emails
- Aggregates the day's sync results from S3

**quickbooks_connector.py** *(main sync only)*
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

> `utils.py`, `config.py` and `salesforce_connector.py` live once in
> `functions/_shared/` and are used by both Lambdas — edit them in one place.
> `config.json` and `requirements.txt` stay per-function, because the two
> deployments legitimately differ there.

### Directory Structure

- `functions/` - One directory per deployed Lambda; the source of truth
- `scripts/` - Build, deploy, and prod-verification tooling
- `docs/` - Documentation; `PRODUCTION_STATE.md` records the deployed AWS resources
- `archive/` - Test scripts, helper utilities, and backup files
- `deploy_packages/contact_form_function/` - Source for the **separate**
  `airbridge-contact-form` Lambda, unrelated to the QB sync. Kept because this
  is its only copy; it has not been verified against its deployed package.
- `website/` - Static site paired with `airbridge-contact-form`

The stale `deploy_packages/{main,full_sync,email}_function/` trees, which held
outdated vendored copies of the sync code, were removed once `functions/` became
authoritative. They remain in git history at commit `c7243ed`.

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
