# Monthly Cost Estimate - QB-AvSight Sync System

## Lambda Function Costs

### qb-avsight-sync2 (Incremental Sync)
- **Invocations:** 40/day × 30 days = **1,200/month**
- **Memory:** 1,024 MB (1 GB)
- **Estimated Duration:** 3 minutes average (180,000 ms)
- **GB-seconds per month:** 1,200 × 1 GB × 180 seconds = **216,000 GB-seconds**
- **Cost:** 216,000 × $0.0000166667 = **$3.60/month**

### qb-avsight-sync (Full Sync)
- **Invocations:** 1/day × 30 days = **30/month**
- **Memory:** 1,024 MB (1 GB)
- **Estimated Duration:** 6 minutes average (360,000 ms)
- **GB-seconds per month:** 30 × 1 GB × 360 seconds = **10,800 GB-seconds**
- **Cost:** 10,800 × $0.0000166667 = **$0.18/month**

### qb-avsight-end-of-day-email
- **Invocations:** 1/day × 30 days = **30/month**
- **Memory:** 256 MB (0.25 GB)
- **Estimated Duration:** 20 seconds average (20,000 ms)
- **GB-seconds per month:** 30 × 0.25 GB × 20 seconds = **150 GB-seconds**
- **Cost:** 150 × $0.0000166667 = **$0.0025/month** (essentially free)

### Lambda Request Costs
- **Total requests:** 1,200 + 30 + 30 = **1,260/month**
- **Cost:** First 1M requests are free, so **$0.00/month**

## EventBridge Costs

- **Rules:** 3 rules (qb-avsight-sync-schedule, qb-avsight-sync-full-schedule, qb-avsight-end-of-day-email)
- **Custom events:** 0 (using scheduled rules only)
- **Cost:** **$0.00/month** (scheduled rules are free)

## Secrets Manager Costs

- **Secrets:** 3 secrets (quickbooks/credentials, salesforce/credentials, smtp/credentials)
- **Cost:** 3 × $0.40 = **$1.20/month**

## S3 Storage Costs

### Daily Summaries Storage
- **Estimated size per summary:** ~50 KB
- **Summaries per day:** 1
- **Monthly storage:** 30 × 50 KB = 1.5 MB
- **Storage cost:** 0.0015 GB × $0.023 = **$0.0000345/month** (negligible)

### S3 PUT Requests
- **PUTs per day:** ~40 (one per sync run)
- **Monthly PUTs:** 40 × 30 = 1,200
- **Cost:** 1,200 / 1,000 × $0.005 = **$0.006/month**

### S3 GET Requests
- **GETs per day:** ~1 (daily email reads summary)
- **Monthly GETs:** 30
- **Cost:** 30 / 1,000 × $0.0004 = **$0.000012/month** (negligible)

## CloudWatch Logs Costs

- **Estimated log data:** ~10 MB per sync run
- **Monthly log data:** (1,200 + 30) × 10 MB = ~12.3 GB
- **Cost:** First 5 GB free, remaining 7.3 GB × $0.50 = **$3.65/month**

## Total Monthly Cost Estimate

| Service | Monthly Cost |
|---------|--------------|
| Lambda Compute (sync2) | $3.60 |
| Lambda Compute (full sync) | $0.18 |
| Lambda Compute (email) | $0.00 |
| Lambda Requests | $0.00 |
| EventBridge | $0.00 |
| Secrets Manager | $1.20 |
| S3 Storage | $0.00 |
| S3 Requests | $0.01 |
| CloudWatch Logs | $3.65 |
| **TOTAL** | **~$8.64/month** |

## Notes

- Costs are estimates based on typical usage patterns
- Actual costs may vary based on:
  - Actual execution duration (incremental syncs may be faster/slower)
  - Amount of data processed
  - CloudWatch log retention settings
  - S3 storage growth over time
- The free tier covers:
  - First 1M Lambda requests/month
  - First 5 GB CloudWatch Logs/month
  - EventBridge scheduled rules are free

## Cost Optimization Opportunities

1. **CloudWatch Logs:** Consider reducing log retention period if not needed long-term
2. **Lambda Memory:** Could potentially reduce memory allocation if execution times are consistently low
3. **S3 Lifecycle:** Set up lifecycle policies to archive old summaries to cheaper storage tiers

