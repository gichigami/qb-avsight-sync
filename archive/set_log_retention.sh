#!/bin/bash

# Script to set CloudWatch Logs retention policies for Lambda functions
# This reduces logging costs by automatically deleting old logs

# Configuration
RETENTION_DAYS=${1:-7}  # Default to 7 days, can override: ./set_log_retention.sh 3

echo "=========================================="
echo "Setting CloudWatch Logs Retention Policies"
echo "=========================================="
echo "Retention period: $RETENTION_DAYS days"
echo ""

# List of Lambda function log groups
LOG_GROUPS=(
    "/aws/lambda/qb-avsight-sync2"
    "/aws/lambda/qb-avsight-end-of-day-email"
    "/aws/lambda/qb-avsight-sync-full"
    "/aws/lambda/qb-avsight-contact-form"
)

# Function to set retention policy
set_retention() {
    local log_group=$1
    local days=$2
    
    echo "Setting retention for: $log_group"
    
    # Check if log group exists
    if aws logs describe-log-groups --log-group-name-prefix "$log_group" --query "logGroups[?logGroupName=='$log_group']" --output text | grep -q "$log_group"; then
        aws logs put-retention-policy \
            --log-group-name "$log_group" \
            --retention-in-days "$days"
        
        if [ $? -eq 0 ]; then
            echo "  ✅ Successfully set retention to $days days"
        else
            echo "  ❌ Failed to set retention"
        fi
    else
        echo "  ⚠️  Log group not found (function may not exist yet)"
    fi
    echo ""
}

# Set retention for each log group
for log_group in "${LOG_GROUPS[@]}"; do
    set_retention "$log_group" "$RETENTION_DAYS"
done

echo "=========================================="
echo "Checking current retention settings..."
echo "=========================================="

# Display current retention settings
aws logs describe-log-groups \
    --log-group-name-prefix "/aws/lambda/qb-avsight" \
    --query 'logGroups[*].[logGroupName,retentionInDays]' \
    --output table

echo ""
echo "Done! Logs older than $RETENTION_DAYS days will be automatically deleted."
echo ""
echo "To change retention period, run:"
echo "  ./set_log_retention.sh <days>"
echo ""
echo "Common retention periods:"
echo "  1 day  - Maximum cost savings"
echo "  3 days - Good for most use cases"
echo "  7 days - Recommended for production"
echo "  14 days - Longer debugging window"
echo "  30 days - Compliance requirements"

