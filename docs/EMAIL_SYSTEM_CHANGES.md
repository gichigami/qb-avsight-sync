# Email System Changes Summary

## What Changed

The email notification system has been updated to accumulate all sync changes throughout the day and send a single, richly formatted email at the end of the day instead of sending an email after each sync run.

## New Behavior

### Before
- ✅ Email sent after every sync run
- ✅ Multiple emails per day
- ❌ No aggregation of daily changes

### After
- ✅ Each sync run saves summary to S3 (no immediate email)
- ✅ All changes accumulated throughout the day
- ✅ Single end-of-day email with complete daily summary
- ✅ Rich HTML formatting with all details

## Files Modified

1. **`utils.py`** - Added S3 functions:
   - `save_daily_summary_to_s3()` - Saves each run's summary to S3
   - `get_daily_summary_from_s3()` - Retrieves daily summary
   - `send_end_of_day_email()` - Sends aggregated daily email

2. **`qb-avsight-sync.py`** (renamed from `lambda_function.py`) - Updated to:
   - Save summaries to S3 instead of sending emails immediately
   - Removed immediate email sending code

3. **`end_of_day_email.py`** - NEW FILE:
   - Separate Lambda function to send end-of-day emails
   - Should be scheduled to run once per day (e.g., 6 PM)

## What You Need to Do

### 1. Set Up S3 Bucket

Follow the detailed instructions in `S3_SETUP_GUIDE.md`. Quick version:

```bash
# Create bucket
aws s3 mb s3://qb-avsight-sync-daily-summaries --region us-east-1

# Add environment variable to Lambda
aws lambda update-function-configuration \
    --function-name qb-avsight-sync2 \
    --environment Variables="{S3_BUCKET_NAME=qb-avsight-sync-daily-summaries}"
```

### 2. Update Lambda IAM Permissions

Add S3 read/write permissions to your Lambda execution role. See `S3_SETUP_GUIDE.md` for details.

### 3. Deploy Updated Code

Deploy the updated `qb-avsight-sync.py` (renamed from `lambda_function.py`) and `utils.py` to your Lambda function.

### 4. Create End-of-Day Email Lambda

1. Create a new Lambda function: `qb-avsight-end-of-day-email`
2. Upload `end_of_day_email.py` and `utils.py`
3. Set handler to `end_of_day_email.lambda_handler`
4. Set environment variable: `S3_BUCKET_NAME=qb-avsight-sync-daily-summaries`
5. Use same IAM role as main sync function (or create new one with same permissions)

### 5. Schedule End-of-Day Email

Set up EventBridge to trigger the end-of-day email function daily at your preferred time (e.g., 6 PM).

See `S3_SETUP_GUIDE.md` for detailed EventBridge setup commands.

## Testing

### Test S3 Storage

After deploying, run your sync function and check:

```bash
# List daily summaries
aws s3 ls s3://qb-avsight-sync-daily-summaries/daily-summaries/

# View today's summary
aws s3 cp s3://qb-avsight-sync-daily-summaries/daily-summaries/2025-01-20/summary.json - | jq .
```

### Test End-of-Day Email

Manually invoke the end-of-day email function:

```bash
aws lambda invoke \
    --function-name qb-avsight-end-of-day-email \
    --payload '{"date":"2025-01-20"}' \
    response.json

cat response.json
```

## Email Recipients

Currently set to send only to `gjohnson@pioneer-aero.com`. To change:

1. Edit `end_of_day_email.py` and modify the `recipients` list
2. Or store recipients in AWS Secrets Manager and retrieve them

## Data Retention

By default, summaries are kept indefinitely. To auto-delete old summaries:

1. Set up S3 lifecycle policy (see `S3_SETUP_GUIDE.md`)
2. Recommended: Keep summaries for 90 days

## Monitoring

Check CloudWatch logs for:
- Main sync function: Should show "✅ Daily summary saved to S3 successfully!"
- End-of-day email function: Should show "✅ End-of-day email sent successfully!"

## Rollback

If you need to revert to the old system:

1. Restore the old `send_email_summary()` call in `qb-avsight-sync.py` (renamed from `lambda_function.py`)
2. Remove S3 save code
3. Deploy the old version

The old email function is still in `utils.py` if needed.

## Questions?

- See `S3_SETUP_GUIDE.md` for detailed setup instructions
- Check CloudWatch logs for errors
- Verify S3 bucket permissions and environment variables

