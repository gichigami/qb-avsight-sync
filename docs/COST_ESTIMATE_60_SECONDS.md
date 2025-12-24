# Monthly Cost Estimate - QB-AvSight Sync System
## Incremental Sync Every 60 Seconds During Working Hours

## Assumptions
- **Working Hours:** 8 AM - 5 PM Central (9 hours = 540 minutes)
- **Sync Frequency:** Every 60 seconds (1 minute)
- **Invocations per day:** 540 minutes / 1 minute = **540 invocations/day**
- **Invocations per month:** 540 × 30 days = **16,200/month**

## Lambda Function Costs

### qb-avsight-sync2 (Incremental Sync - Every 60 Seconds)
- **Invocations:** 540/day × 30 days = **16,200/month**
- **Memory:** 1,024 MB (1 GB)
- **Estimated Duration:** 3 minutes average (180,000 ms)
- **GB-seconds per month:** 16,200 × 1 GB × 180 seconds = **2,916,000 GB-seconds**
- **Cost:** 2,916,000 × $0.0000166667 = **$48.60/month**

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
- **Total requests:** 16,200 + 30 + 30 = **16,260/month**
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
- **Summaries per day:** 540 (one per sync run)
- **Monthly storage:** 540 × 30 × 50 KB = ~810 MB
- **Storage cost:** 0.81 GB × $0.023 = **$0.019/month** (negligible)

### S3 PUT Requests
- **PUTs per day:** 540 (one per sync run)
- **Monthly PUTs:** 540 × 30 = **16,200**
- **Cost:** 16,200 / 1,000 × $0.005 = **$0.08/month**

### S3 GET Requests
- **GETs per day:** ~1 (daily email reads summary)
- **Monthly GETs:** 30
- **Cost:** 30 / 1,000 × $0.0004 = **$0.000012/month** (negligible)

## CloudWatch Logs Costs

- **Estimated log data:** ~10 MB per sync run
- **Monthly log data:** (16,200 + 30) × 10 MB = ~162.3 GB
- **Cost:** First 5 GB free, remaining 157.3 GB × $0.50 = **$78.65/month**

## Total Monthly Cost Estimate

| Service | Monthly Cost |
|---------|--------------|
| Lambda Compute (sync2 - 60 sec) | $48.60 |
| Lambda Compute (full sync) | $0.18 |
| Lambda Compute (email) | $0.00 |
| Lambda Requests | $0.00 |
| EventBridge | $0.00 |
| Secrets Manager | $1.20 |
| S3 Storage | $0.02 |
| S3 Requests | $0.08 |
| CloudWatch Logs | $78.65 |
| **TOTAL** | **~$128.73/month** |

## Comparison to Current Setup (Every 15 Minutes)

| Metric | Current (15 min) | New (60 sec) | Increase |
|--------|------------------|--------------|----------|
| Invocations/day | 40 | 540 | 13.5x |
| Invocations/month | 1,200 | 16,200 | 13.5x |
| Lambda Compute Cost | $3.60 | $48.60 | $45.00 |
| CloudWatch Logs Cost | $3.65 | $78.65 | $75.00 |
| S3 Requests Cost | $0.01 | $0.08 | $0.07 |
| **Total Monthly Cost** | **$8.64** | **$128.73** | **$120.09** |

## Cost Breakdown by Service

The significant cost increase comes from:
1. **CloudWatch Logs:** $75.00 increase (largest component)
   - 13.5x more log data generated
   - 162.3 GB/month vs 12.3 GB/month
2. **Lambda Compute:** $45.00 increase
   - 13.5x more invocations
   - Same duration per invocation
3. **S3 Requests:** $0.07 increase (minimal)

## Cost Optimization Recommendations

1. **CloudWatch Logs (Highest Impact):**
   - Reduce log retention period (e.g., 7 days instead of default)
   - Implement log filtering to reduce log volume
   - Consider using log sampling for high-frequency syncs
   - Estimated savings: Could reduce CloudWatch costs by 50-80%

2. **Lambda Duration:**
   - Optimize sync code to reduce execution time
   - If duration can be reduced to 1 minute average: ~$16.20/month (saves $32.40)

3. **S3 Lifecycle:**
   - Set up lifecycle policies to delete old summaries after 30 days
   - Minimal impact on cost but good practice

## Alternative: Hybrid Approach

Consider a hybrid approach:
- **Peak hours (9 AM - 4 PM):** Sync every 60 seconds
- **Off-peak hours (8-9 AM, 4-5 PM):** Sync every 5 minutes

This would reduce invocations to approximately:
- Peak: 7 hours × 60 = 420 invocations/day
- Off-peak: 2 hours × 12 = 24 invocations/day
- **Total: 444 invocations/day = 13,320/month**

Estimated cost: ~$105-110/month (savings of ~$18-23/month)

## Notes

- Costs are estimates based on typical usage patterns
- Actual costs may vary based on:
  - Actual execution duration (may be faster if incremental syncs process less data)
  - Amount of data processed per sync
  - CloudWatch log retention settings (biggest variable)
  - S3 storage growth over time
- The free tier still covers:
  - First 1M Lambda requests/month (16,260 << 1,000,000)
  - First 5 GB CloudWatch Logs/month (only covers ~3% of logs)
  - EventBridge scheduled rules are free

