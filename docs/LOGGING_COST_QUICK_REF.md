# Quick Reference: Reduce Logging Costs

## 🚀 Immediate Actions (5 minutes)

### 1. Set Log Retention (Run this now!)
```bash
# Quick script (sets all to 7 days)
./set_log_retention.sh

# Or manually for each function:
aws logs put-retention-policy \
    --log-group-name /aws/lambda/qb-avsight-sync2 \
    --retention-in-days 7

aws logs put-retention-policy \
    --log-group-name /aws/lambda/qb-avsight-end-of-day-email \
    --retention-in-days 7
```

### 2. Check Current Log Volume
```bash
# See all log groups and their sizes
aws logs describe-log-groups \
    --log-group-name-prefix /aws/lambda/qb-avsight \
    --query 'logGroups[*].[logGroupName,storedBytes,retentionInDays]' \
    --output table
```

## 📊 Cost Impact

| Action | Cost Savings | Time to Implement |
|--------|--------------|-------------------|
| Set 7-day retention | ~77% storage cost | 2 minutes |
| Remove DEBUG logs | 60-80% ingestion | 1-2 hours |
| Use logging levels | 50-70% total | 2-4 hours |

## 🔍 Key Commands

### View Recent Logs (Last Hour)
```bash
aws logs tail /aws/lambda/qb-avsight-sync2 --since 1h
```

### Check Log Retention
```bash
aws logs describe-log-groups \
    --log-group-name-prefix /aws/lambda/qb-avsight \
    --query 'logGroups[*].[logGroupName,retentionInDays]' \
    --output table
```

### Estimate Monthly Cost
```bash
# Get stored bytes (in GB)
aws logs describe-log-groups \
    --log-group-name /aws/lambda/qb-avsight-sync2 \
    --query 'logGroups[0].storedBytes' \
    --output text | awk '{print $1/1024/1024/1024 " GB"}'

# Calculate: (GB × $0.03) = monthly storage cost
```

## ⚙️ Environment Variables to Set

Add to Lambda function configuration:
```bash
# Set log level to INFO (removes DEBUG logs)
aws lambda update-function-configuration \
    --function-name qb-avsight-sync2 \
    --environment Variables="{LOG_LEVEL=INFO}"

# Disable DEBUG logging entirely
aws lambda update-function-configuration \
    --function-name qb-avsight-sync2 \
    --environment Variables="{DEBUG_LOGGING=false}"
```

## 📝 Code Changes Needed

### Replace DEBUG prints with conditional logging:
```python
# Add to top of files
import os
DEBUG = os.environ.get('DEBUG_LOGGING', 'false').lower() == 'true'

# Replace this:
print("[DEBUG] Processing bill...")

# With this:
if DEBUG:
    print("[DEBUG] Processing bill...")
```

### Use proper logging module:
```python
import logging
logger = logging.getLogger(__name__)

# Instead of print()
logger.info("Sync started")
logger.warning("Rate limit approaching")
logger.error("Sync failed")
# No logger.debug() in production
```

## 🎯 Recommended Retention Periods

- **1 day**: Maximum savings, minimal debugging
- **3 days**: Good balance
- **7 days**: **Recommended for production** ✅
- **14 days**: Longer debugging window
- **30 days**: Compliance only

## 💰 Expected Savings

**Before:** ~$0.53/GB/month (logs kept forever)  
**After:** ~$0.11-0.21/GB/month (7-day retention, no DEBUG)  
**Savings: 60-75% reduction**

## 📚 Full Guide

See `REDUCE_LOGGING_COSTS.md` for complete details.

