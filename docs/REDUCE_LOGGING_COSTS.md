# Guide: Reducing AWS CloudWatch Logs Costs

## Current Situation
Your Lambda functions are generating extensive logs with:
- **326+ DEBUG print statements** across the codebase
- Verbose logging for every operation
- No log retention policies configured
- All logs stored indefinitely

## CloudWatch Logs Pricing
- **Ingestion**: $0.50 per GB ingested
- **Storage**: $0.03 per GB/month
- **Data scanned by Logs Insights**: $0.005 per GB

**Example Cost Impact:**
- If your functions generate 1 GB of logs per month:
  - Ingestion: $0.50
  - Storage (if kept 1 year): $0.36
  - **Total: ~$0.86/month per GB**

## Cost Reduction Strategies

### 1. Set Log Retention Policies (IMMEDIATE ACTION)

Set automatic log expiration to delete old logs:

```bash
# Set retention to 7 days (recommended for production)
aws logs put-retention-policy \
    --log-group-name /aws/lambda/qb-avsight-sync2 \
    --retention-in-days 7

aws logs put-retention-policy \
    --log-group-name /aws/lambda/qb-avsight-end-of-day-email \
    --retention-in-days 7

# If you have other Lambda functions:
aws logs put-retention-policy \
    --log-group-name /aws/lambda/qb-avsight-sync-full \
    --retention-in-days 7

aws logs put-retention-policy \
    --log-group-name /aws/lambda/qb-avsight-contact-form \
    --retention-in-days 7
```

**Retention Options:**
- **1 day**: Maximum cost savings, minimal debugging window
- **3 days**: Good balance for most issues
- **7 days**: Recommended for production (catches weekly issues)
- **14 days**: If you need longer debugging window
- **30 days**: Only if required for compliance

**Cost Savings Example:**
- Before: Logs kept forever → $0.03/GB/month indefinitely
- After (7 days): Logs auto-deleted → $0.03/GB/month × (7/30) = **~$0.007/GB/month**
- **Savings: ~77% reduction in storage costs**

### 2. Remove or Conditionally Disable DEBUG Logging

Your codebase has 326+ `[DEBUG]` print statements. These should be:
- Removed entirely, OR
- Wrapped in environment variable checks

**Option A: Remove DEBUG statements (Recommended)**
- Keep only ERROR, WARNING, and key INFO messages
- Remove all `[DEBUG]` print statements

**Option B: Conditional DEBUG logging**
Add to your Lambda functions:
```python
import os

# At the top of your files
DEBUG_MODE = os.environ.get('DEBUG_LOGGING', 'false').lower() == 'true'

def debug_print(message):
    if DEBUG_MODE:
        print(f"[DEBUG] {message}")
```

Then replace all `print("[DEBUG] ...")` with `debug_print("...")`

**Cost Impact:**
- Removing DEBUG logs can reduce log volume by **60-80%**
- If you generate 1 GB/month, this saves **$0.30-0.40/month in ingestion costs**

### 3. Use Structured Logging with Levels

Replace `print()` with proper logging that respects log levels:

```python
import logging
import os

# Configure logging
log_level = os.environ.get('LOG_LEVEL', 'INFO').upper()
logging.basicConfig(
    level=getattr(logging, log_level),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Use appropriate levels
logger.info("Sync started")  # Normal operation
logger.warning("Rate limit approaching")  # Important but not error
logger.error("Sync failed")  # Errors only
# Remove all logger.debug() calls in production
```

**Set LOG_LEVEL in Lambda:**
```bash
aws lambda update-function-configuration \
    --function-name qb-avsight-sync2 \
    --environment Variables="{LOG_LEVEL=INFO}"

aws lambda update-function-configuration \
    --function-name qb-avsight-end-of-day-email \
    --environment Variables="{LOG_LEVEL=INFO}"
```

### 4. Reduce Verbose Output

**Current Issues:**
- Printing full DataFrames
- Printing entire dictionaries
- Printing all records being processed

**Solutions:**
```python
# Instead of:
print(f"Processing {len(bills)} bills...")
for bill in bills:
    print(f"Bill: {bill}")  # Too verbose!

# Use:
logger.info(f"Processing {len(bills)} bills...")
if DEBUG_MODE:
    for bill in bills:
        logger.debug(f"Bill: {bill}")
```

### 5. Filter Logs at Source

Use log filtering to prevent unnecessary logs from being ingested:

```python
# Only log errors and warnings in production
import sys

class LogFilter:
    def __init__(self, min_level=logging.WARNING):
        self.min_level = min_level
    
    def filter(self, record):
        return record.levelno >= self.min_level

# In production, only log WARNING and above
if os.environ.get('ENVIRONMENT') == 'production':
    logging.getLogger().addFilter(LogFilter(logging.WARNING))
```

### 6. Use CloudWatch Logs Insights Efficiently

When querying logs, use time ranges and filters:

```bash
# Instead of scanning all logs:
aws logs tail /aws/lambda/qb-avsight-sync2 --since 1h

# Use specific time ranges:
aws logs filter-log-events \
    --log-group-name /aws/lambda/qb-avsight-sync2 \
    --start-time $(date -d '1 hour ago' +%s)000 \
    --filter-pattern "ERROR"
```

### 7. Monitor Log Volume

Set up CloudWatch alarms to track log ingestion:

```bash
# Create metric filter for log ingestion
aws logs put-metric-filter \
    --log-group-name /aws/lambda/qb-avsight-sync2 \
    --filter-name LogIngestion \
    --filter-pattern "" \
    --metric-transformations \
        metricName=LogIngestionBytes \
        metricNamespace=LambdaLogs \
        metricValue=1 \
        defaultValue=0

# Create alarm if logs exceed threshold
aws cloudwatch put-metric-alarm \
    --alarm-name HighLogIngestion \
    --alarm-description "Alert when log ingestion is high" \
    --metric-name LogIngestionBytes \
    --namespace LambdaLogs \
    --statistic Sum \
    --period 3600 \
    --threshold 1000000000 \
    --comparison-operator GreaterThanThreshold \
    --evaluation-periods 1
```

## Implementation Priority

### Immediate (Do Today - 5 minutes)
1. ✅ Set log retention policies to 7 days for all Lambda functions
2. ✅ Review current log volume in CloudWatch

### Short-term (This Week - 1-2 hours)
1. Remove or disable all `[DEBUG]` print statements
2. Replace `print()` with proper `logging` module
3. Set `LOG_LEVEL=INFO` environment variable

### Long-term (This Month - 4-8 hours)
1. Refactor verbose logging to be more concise
2. Implement conditional DEBUG logging
3. Set up CloudWatch alarms for log volume

## Quick Commands Reference

### Check Current Log Retention
```bash
aws logs describe-log-groups \
    --log-group-name-prefix /aws/lambda/qb-avsight \
    --query 'logGroups[*].[logGroupName,retentionInDays]' \
    --output table
```

### Check Log Volume (Last 24 Hours)
```bash
aws logs filter-log-events \
    --log-group-name /aws/lambda/qb-avsight-sync2 \
    --start-time $(date -d '24 hours ago' +%s)000 \
    --query 'events[*].message' \
    --output text | wc -c
```

### Estimate Monthly Cost
```bash
# Get log group size
aws logs describe-log-groups \
    --log-group-name /aws/lambda/qb-avsight-sync2 \
    --query 'logGroups[0].storedBytes'

# Calculate: (storedBytes / 1024^3) * $0.03 = monthly storage cost
# Plus: (ingestedBytes / 1024^3) * $0.50 = ingestion cost
```

### Set Retention for All Lambda Log Groups
```bash
# List all Lambda log groups
aws logs describe-log-groups \
    --log-group-name-prefix /aws/lambda/qb-avsight \
    --query 'logGroups[*].logGroupName' \
    --output text | \
    xargs -I {} aws logs put-retention-policy \
        --log-group-name {} \
        --retention-in-days 7
```

## Expected Cost Savings

**Before Optimization:**
- Log ingestion: ~$0.50/GB/month
- Log storage (kept forever): ~$0.36/GB/year = $0.03/GB/month
- **Total: ~$0.53/GB/month**

**After Optimization (7-day retention, no DEBUG logs):**
- Log ingestion: ~$0.10-0.20/GB/month (60-80% reduction)
- Log storage: ~$0.007/GB/month (77% reduction)
- **Total: ~$0.11-0.21/GB/month**

**Savings: 60-75% reduction in logging costs**

## Additional Tips

1. **Use X-Ray for tracing instead of verbose logs** (if needed)
2. **Log to S3 for long-term storage** (cheaper than CloudWatch for archival)
3. **Use log sampling** for high-volume operations
4. **Monitor costs** in AWS Cost Explorer → CloudWatch Logs

## Next Steps

1. Run the retention policy commands above
2. Review and remove unnecessary DEBUG statements
3. Monitor log volume reduction over the next week
4. Adjust retention period based on your debugging needs

