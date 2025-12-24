# Configuration File Guide

All non-secret parameters are now stored in a `config.json` file.

## File Location

The configuration file is located at:
```
config.json
```

## Configuration Parameters

Edit `.config` to change these settings:

```json
{
  "salesforce_batch_size": 100,
  "results_directory": "/tmp",
  "qb_redirect_uri": "https://developer.intuit.com/v2/OAuth2Playground/RedirectUrl",
  "qb_max_results_per_page": 100,
  "email_recipients": [
    "gjohnson@pioneer-aero.com"
  ],
  "s3_bucket_name": "qb-avsight-sync-daily-summaries"
}
```

## Parameters Explained

| Parameter | Description | Default |
|-----------|-------------|---------|
| `salesforce_batch_size` | Number of records to process per Salesforce API batch | 100 |
| `results_directory` | Directory where CSV result files are saved | `/tmp` |
| `qb_redirect_uri` | QuickBooks OAuth redirect URI | `https://developer.intuit.com/v2/OAuth2Playground/RedirectUrl` |
| `qb_max_results_per_page` | Maximum records per QuickBooks API page | 100 |
| `email_recipients_run_summary` | List of email addresses for run summaries (after each sync) | `["gjohnson@pioneer-aero.com"]` |
| `email_recipients_daily_summary` | List of email addresses for daily summaries (end of day) | `["gjohnson@pioneer-aero.com"]` |
| `s3_bucket_name` | S3 bucket name for storing daily summaries | `qb-avsight-sync-daily-summaries` |

## Email Recipients Configuration

### Run Summary Recipients (After Each Sync)
These recipients receive an email after each sync run:

```json
{
  "email_recipients_run_summary": [
    "gjohnson@pioneer-aero.com"
  ]
}
```

### Daily Summary Recipients (End of Day)
These recipients receive the comprehensive daily summary email:

```json
{
  "email_recipients_daily_summary": [
    "gjohnson@pioneer-aero.com",
    "cstotts@pioneer-aero.com",
    "mramineni@pioneer-aero.com",
    "lli@pioneer-aero.com",
    "ejimenez@pioneer-aero.com",
    "ofaruqi@pioneer-aero.com",
    "jsilva@pioneer-aero.com"
  ]
}
```

## Important Notes

1. **Secrets remain in AWS Secrets Manager** - Credentials (passwords, tokens, etc.) are NOT in this file
2. **File is gitignored** - The `config.json` file is excluded from git to prevent committing configuration
3. **No code changes needed** - Just edit `config.json` and restart the application
4. **JSON format required** - Make sure the file is valid JSON

## Example: Changing Email Recipients

### Change Run Summary Recipients (After Each Sync)

1. Edit `config.json`:
```json
{
  "email_recipients_run_summary": [
    "newemail@example.com"
  ]
}
```

### Change Daily Summary Recipients (End of Day)

1. Edit `config.json`:
```json
{
  "email_recipients_daily_summary": [
    "newemail@example.com",
    "anotheremail@example.com",
    "yetanother@example.com"
  ]
}
```

2. Restart your Lambda function or local test - no code changes needed!

## Example: Changing Batch Size

1. Edit `config.json`:
```json
{
  "salesforce_batch_size": 200
}
```

2. The next sync will use the new batch size automatically.

## Security

- ✅ The `.config` file is in `.gitignore` - won't be committed to git
- ✅ Only non-sensitive parameters are in `.config`
- ✅ All credentials remain in AWS Secrets Manager
- ⚠️ Don't commit `.config` to version control

## Troubleshooting

If the config file is missing or invalid, the application will:
- Print a warning message
- Use default values
- Continue running normally

Check the logs for messages like:
```
⚠️ Config file not found: config.json
Using default values
```

