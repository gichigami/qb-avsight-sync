#!/bin/bash
# Setup EventBridge schedules for QB-AvSight sync

ACCOUNT_ID="904198142431"
REGION="us-east-1"

echo "=========================================="
echo "Setting up EventBridge Schedules"
echo "=========================================="

# Update existing sync schedule to run every hour 8 AM - 5 PM Central
# Central Time: CST (UTC-6) or CDT (UTC-5)
# 8 AM CST = 14:00 UTC, 8 AM CDT = 13:00 UTC
# 5 PM CST = 23:00 UTC, 5 PM CDT = 22:00 UTC
# Using 14:00-23:00 UTC gives: CST 8 AM-5 PM, CDT 9 AM-6 PM
# This alternates between 8 AM and 9 AM start as requested
echo ""
echo "1. Updating main sync schedule..."
aws events put-rule \
    --name "qb-avsight-sync-schedule" \
    --schedule-expression "cron(0 14-23 * * ? *)" \
    --description "Run QB-AvSight sync every hour from 8 AM to 5 PM Central (14:00-23:00 UTC = 8 AM-5 PM CST / 9 AM-6 PM CDT)" \
    --state ENABLED

echo "✅ Updated sync schedule"

# Create end-of-day email schedule (20 minutes after last sync run)
# Last sync run: 23:00 UTC (5 PM CST / 6 PM CDT)
# 20 minutes after: 23:20 UTC (5:20 PM CST / 6:20 PM CDT)
echo ""
echo "2. Creating end-of-day email schedule..."
aws events put-rule \
    --name "qb-avsight-end-of-day-email" \
    --schedule-expression "cron(20 23 * * ? *)" \
    --description "Send daily summary email 20 minutes after last sync (23:20 UTC = 5:20 PM CST / 6:20 PM CDT)" \
    --state ENABLED

echo "✅ Created end-of-day email schedule"

# Get Lambda function ARNs
SYNC_FUNCTION_ARN="arn:aws:lambda:${REGION}:${ACCOUNT_ID}:function:qb-avsight-sync2"
EMAIL_FUNCTION_ARN="arn:aws:lambda:${REGION}:${ACCOUNT_ID}:function:qb-avsight-end-of-day-email"

# Add sync function as target (update existing)
echo ""
echo "3. Updating sync schedule target..."
aws events put-targets \
    --rule "qb-avsight-sync-schedule" \
    --targets "Id=1,Arn=${SYNC_FUNCTION_ARN}"

echo "✅ Updated sync schedule target"

# Add email function as target
echo ""
echo "4. Adding email function as target..."
aws events put-targets \
    --rule "qb-avsight-end-of-day-email" \
    --targets "Id=1,Arn=${EMAIL_FUNCTION_ARN}"

echo "✅ Added email function target"

# Grant EventBridge permission to invoke Lambda functions
echo ""
echo "5. Granting EventBridge permissions..."

# For sync function
aws lambda add-permission \
    --function-name qb-avsight-sync2 \
    --statement-id "eventbridge-sync-schedule" \
    --action "lambda:InvokeFunction" \
    --principal events.amazonaws.com \
    --source-arn "arn:aws:events:${REGION}:${ACCOUNT_ID}:rule/qb-avsight-sync-schedule" 2>/dev/null || echo "Permission already exists for sync function"

# For email function
aws lambda add-permission \
    --function-name qb-avsight-end-of-day-email \
    --statement-id "eventbridge-end-of-day-email" \
    --action "lambda:InvokeFunction" \
    --principal events.amazonaws.com \
    --source-arn "arn:aws:events:${REGION}:${ACCOUNT_ID}:rule/qb-avsight-end-of-day-email" 2>/dev/null || echo "Permission already exists for email function"

echo "✅ Permissions configured"

echo ""
echo "=========================================="
echo "✅ EventBridge Setup Complete!"
echo "=========================================="
echo ""
echo "Schedule Summary:"
echo "  • Main Sync: Every hour 14:00-23:00 UTC"
echo "    - CST: 8:00 AM - 5:00 PM Central"
echo "    - CDT: 9:00 AM - 6:00 PM Central (starts at 9 AM as requested)"
echo "  • Daily Email: 23:20 UTC (20 minutes after last sync)"
echo "    - CST: 5:20 PM Central (20 min after 5 PM sync)"
echo "    - CDT: 6:20 PM Central (20 min after 6 PM sync)"
echo ""
echo "Note: Times shift by 1 hour during daylight saving time."
echo "Email is sent 20 minutes after the last sync run of the day."

