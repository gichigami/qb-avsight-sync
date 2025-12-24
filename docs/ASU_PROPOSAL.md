# QuickBooks-AvSight Sync Deployment Proposal
## AirSpares Unlimited

**Prepared by:** Garrett Johnson  
**Date:** January 2025  
**Hourly Rate:** $70/hour  
**Project Duration:** Estimated 6-9 weeks (8-10 hours/week)  
**Note:** Phase 0 (System Adaptation) has been completed, reducing overall project timeline

---

## Executive Summary

This proposal outlines the deployment of an automated synchronization system between QuickBooks Online and Salesforce AvSight ERP system for AirSpares Unlimited. The solution will automatically sync invoice and bill data on a scheduled basis, ensuring real-time financial data consistency between systems.

The project includes:
- ✅ System adaptation and generalization (completed - makes codebase deployable to any org)
- QuickBooks Online API configuration and OAuth setup
- Custom Salesforce object (Bill__c) creation in AvSight
- Complete AWS infrastructure deployment (Lambda, EventBridge, Secrets Manager, S3)
- Code customization for AirSpares Unlimited's environment
- Comprehensive testing and documentation
- Training and handoff

---

## Project Overview

### Current Solution
The sync system is a production-ready AWS Lambda-based solution that:
- Fetches invoices and bills from QuickBooks Online using the QuickBooks API
- Implements intelligent incremental sync that only processes records modified since the last run
- Performs full sync once daily to ensure complete data consistency
- Compares data with Salesforce AvSight Bill__c records
- Updates Salesforce with changed balances and new records
- Saves daily summaries to S3 for aggregation
- Sends comprehensive end-of-day email summaries
- Runs automatically on a schedule via AWS EventBridge:
  - Incremental sync: Every 15 minutes during business hours (8 AM - 5 PM Central)
  - Full sync: Once daily (7:50 AM Central)
  - End-of-day email: Daily at 5:20 PM Central

### Deliverables
1. Fully configured QuickBooks API integration with OAuth token management
2. New Bill__c custom object in Salesforce AvSight with required field mappings
3. Deployed AWS Lambda functions:
   - `qb-avsight-sync2` - Incremental sync (runs every 15 minutes during business hours)
   - `qb-avsight-sync` - Full sync (runs once daily)
   - `qb-avsight-end-of-day-email` - Daily summary email
4. AWS infrastructure (IAM roles, Secrets Manager, EventBridge, S3)
5. Configured email notification system with daily summaries
6. Complete documentation and user guide
7. Training session for AirSpares Unlimited staff

---

## Detailed Scope of Work

### Phase 0: System Adaptation and Generalization (20 hours)

**Tasks:**
- Refactor codebase from single-org implementation to multi-org adaptable system
- Extract hardcoded configurations to configurable files (config.json, config.py)
- Implement flexible Salesforce object mapping (Payment__c → Bill__c adaptable)
- Create modular architecture with separate connectors for QuickBooks and Salesforce
- Implement AWS Secrets Manager integration for secure credential storage
- Add incremental sync capability with timestamp tracking
- Implement S3-based daily summary aggregation system
- Create separate end-of-day email Lambda function
- Add comprehensive error handling and logging
- Create deployment-ready code structure with proper separation of concerns
- Implement configuration management system for easy customization
- Add support for configurable email recipients and schedules
- Create comprehensive documentation and implementation guides

**Why This Work Is Necessary:**
The original system was built specifically for a single Salesforce org with hardcoded configurations, object names, and business logic. This work will transform it into a production-ready, adaptable solution that can be deployed to any QuickBooks Online and Salesforce AvSight environment with minimal customization. This generalization work ensures the system is maintainable and scalable.

**Deliverables:**
- Adaptable, production-ready codebase
- Configuration management system
- Modular architecture
- Comprehensive documentation
- Implementation guide

**Estimated Time:** 20 hours  
**Cost:** $1,400

---

### Phase 1: QuickBooks API Configuration (5-7 hours)

**Tasks:**
- Register AirSpares Unlimited application in QuickBooks Developer Portal
- Configure OAuth 2.0 credentials (Client ID, Client Secret, Redirect URI)
- Set up QuickBooks Online sandbox/production environment
- Complete OAuth authorization flow to obtain initial tokens
- Store credentials securely in AWS Secrets Manager
- Test QuickBooks API connectivity and data retrieval
- Verify API rate limits and implement appropriate handling

**Deliverables:**
- Active QuickBooks API credentials
- Credentials stored in AWS Secrets Manager
- Test script confirming API connectivity

**Estimated Time:** 5-7 hours  
**Cost:** $350 - $490

---

### Phase 2: Salesforce Bill__c Object Creation (8-10 hours)

**Tasks:**
- Analyze existing object structures in Salesforce AvSight to understand field requirements
- Design Bill__c custom object schema based on sync requirements
- Create Bill__c custom object in Salesforce AvSight org
- Create required custom fields:
  - `Repair_Order__c` (Lookup to Repair Order)
  - `Purchase_Order__c` (Lookup to Purchase Order)
  - `Order__c` (Text, 255)
  - `Account__c` (Lookup to Account)
  - `QBO_Bill_ID__c` (Text, 255, Unique, External ID)
  - `Memo__c` (Long Text Area)
  - `Total_Amount__c` (Currency)
  - `Balance_Due__c` (Currency)
  - `Bill_Date__c` (Date)
  - `Due_Date__c` (Date)
- Set up field-level security and page layouts
- Configure object permissions for appropriate user profiles
- Create validation rules if needed
- Set up any required workflow rules or automation
- Test object creation and field population

**Deliverables:**
- Fully configured Bill__c custom object
- All required fields with proper data types and relationships
- Security settings configured
- Test records created and validated

**Estimated Time:** 8-10 hours  
**Cost:** $560 - $700

---

### Phase 3: AWS Infrastructure Setup (10-12 hours)

**Tasks:**
- Create AWS account structure (if needed) and configure access
- Set up IAM roles and policies:
  - Lambda execution role with Secrets Manager access
  - Lambda execution role with S3 access
  - EventBridge permissions to invoke Lambda
- Create AWS Secrets Manager secrets:
  - `quickbooks/credentials` (OAuth tokens and credentials)
  - `salesforce/credentials` (username, password, security token, instance URL)
  - `smtp/credentials` (SMTP server configuration)
- Create S3 bucket for daily summaries:
  - Configure bucket permissions
  - Set up lifecycle policies for data retention
  - Enable versioning (optional)
- Create CloudWatch Log Groups for Lambda functions
- Configure EventBridge rules for scheduled execution:
  - Incremental sync schedule (every 15 minutes, 8 AM - 5 PM Central)
  - Full sync schedule (daily at 7:50 AM Central)
  - End-of-day email schedule (daily at 5:20 PM Central)
- Set up CloudWatch alarms for monitoring
- Configure VPC settings if required (likely not needed)

**Deliverables:**
- Complete AWS infrastructure deployed
- All IAM roles and policies configured
- Secrets Manager populated with credentials
- S3 bucket created and configured
- EventBridge schedules set up

**Estimated Time:** 10-12 hours  
**Cost:** $700 - $840

---

### Phase 4: Code Customization and Deployment (8-12 hours)

**Tasks:**
- Customize code for AirSpares Unlimited:
  - Update object references from Payment__c to Bill__c (using adaptable codebase from Phase 0)
  - Configure email recipient lists in config.json
  - Update S3 bucket name configuration
  - Adjust any company-specific logic or mappings
- Package Lambda deployment artifacts:
  - Install Python dependencies
  - Create deployment packages for three Lambda functions
  - Optimize package size if needed
- Deploy Lambda functions:
  - Incremental sync function (`qb-avsight-sync2`) - 1,024 MB memory, 15 min timeout
  - Full sync function (`qb-avsight-sync`) - 1,024 MB memory, 15 min timeout
  - End-of-day email function (`qb-avsight-end-of-day-email`) - 256 MB memory, 30 sec timeout
- Configure Lambda function settings:
  - Memory allocation (1,024 MB for sync functions, 256 MB for email)
  - Timeout settings (15 minutes for sync functions, 30 seconds for email)
  - Environment variables (S3 bucket name, etc.)
  - Lambda layers if needed
- Update configuration to use Bill__c object (simplified due to Phase 0 work)
- Enable incremental sync feature in configuration
- Test data mappings and transformations
- Verify all API integrations

**Note:** This phase is significantly streamlined due to the system adaptation work completed in Phase 0, which made the codebase easily customizable for different Salesforce orgs.

**Deliverables:**
- Deployed Lambda functions (3 functions)
- Updated codebase customized for AirSpares Unlimited
- Configuration files properly set up
- Incremental sync enabled and tested

**Estimated Time:** 8-12 hours  
**Cost:** $560 - $840

---

### Phase 5: Integration Testing (10-12 hours)

**Tasks:**
- End-to-end testing of QuickBooks to Salesforce sync:
  - Test invoice sync (balance updates, status changes)
  - Test bill sync (inserts, updates, balance changes)
  - Verify data accuracy and completeness
- Test error handling:
  - Invalid credentials scenarios
  - API rate limiting
  - Network failures
  - Token expiration and refresh
- Test email notifications:
  - Run summary emails
  - End-of-day summary emails
  - Verify email formatting and content
- Test scheduled execution:
  - Verify EventBridge triggers Lambda correctly
  - Test at different times of day
- Load testing with realistic data volumes
- Verify S3 daily summary storage
- Test edge cases:
  - Missing relationships (Orders, Accounts)
  - Duplicate records
  - Large data volumes
- Performance testing and optimization

**Deliverables:**
- Comprehensive test results document
- All identified issues resolved
- System ready for production use

**Estimated Time:** 10-12 hours  
**Cost:** $700 - $840

---

### Phase 6: Documentation and Training (6-8 hours)

**Tasks:**
- Create deployment documentation:
  - Architecture overview
  - Infrastructure setup guide
  - Configuration management
- Create user documentation:
  - How the sync works
  - What gets synced and when
  - How to interpret email summaries
  - Troubleshooting guide
- Create operational runbook:
  - How to monitor the system
  - How to check logs
  - Common issues and solutions
  - How to update credentials
- Conduct training session (2-3 hours):
  - System overview for management
  - Operational training for IT staff
  - Q&A session
- Create quick reference guides

**Deliverables:**
- Complete documentation package
- Training materials and presentations
- Conducted training session
- Recorded training session (if requested)

**Estimated Time:** 6-8 hours  
**Cost:** $420 - $560

---

### Phase 7: Production Deployment and Go-Live Support (4-6 hours)

**Tasks:**
- Final production configuration review
- Deploy to production AWS account
- Final end-to-end testing in production environment
- Monitor first few sync cycles
- Address any immediate issues
- Verify all stakeholders receive emails correctly
- Confirm data accuracy with AirSpares Unlimited team
- Post-deployment optimization

**Deliverables:**
- System running in production
- Successful first sync cycles
- Sign-off from AirSpares Unlimited

**Estimated Time:** 4-6 hours  
**Cost:** $280 - $420

---

### Phase 8: Buffer for Unexpected Issues (8-10 hours)

**Tasks:**
- Additional troubleshooting time
- Unforeseen integration challenges
- Scope adjustments
- Additional testing requirements
- Additional training sessions if needed

**Estimated Time:** 8-10 hours  
**Cost:** $560 - $700

---

## Total Project Estimate

| Phase | Description | Hours | Cost Range |
|-------|-------------|-------|------------|
| 0 | System Adaptation and Generalization | 20 | $1,400 |
| 1 | QuickBooks API Configuration | 5-7 | $350 - $490 |
| 2 | Salesforce Bill__c Object Creation | 8-10 | $560 - $700 |
| 3 | AWS Infrastructure Setup | 10-12 | $700 - $840 |
| 4 | Code Customization and Deployment | 8-12 | $560 - $840 |
| 5 | Integration Testing | 10-12 | $700 - $840 |
| 6 | Documentation and Training | 6-8 | $420 - $560 |
| 7 | Production Deployment | 4-6 | $280 - $420 |
| 8 | Buffer/Contingency | 8-10 | $560 - $700 |
| **TOTAL** | | **79-97 hours** | **$5,530 - $6,990** |

---

## Timeline

**Estimated Duration:** 6-9 weeks from project start  
**Availability:** 8-10 hours per week

**Proposed Schedule:**
- **Before Project Start:** Phase 0 (System Adaptation and Generalization - 20 hours) - Completed
- **Weeks 1-2:** Phase 1 (QuickBooks API Configuration - 5-7 hours) and Phase 2 (Salesforce Bill__c Object Creation - 8-10 hours)
- **Weeks 3-4:** Phase 3 (AWS Infrastructure Setup - 10-12 hours)
- **Weeks 5-6:** Phase 4 (Code Customization and Deployment - 8-12 hours)
- **Weeks 7-8:** Phase 5 (Integration Testing - 10-12 hours)
- **Week 9:** Phase 6 (Documentation and Training - 6-8 hours) and Phase 7 (Production Deployment - 4-6 hours)
- **Week 10 (if needed):** Buffer time, go-live support, final adjustments, and Phase 8 (Contingency - 8-10 hours)

*Note: Timeline is based on 8-10 hours of work per week and assumes timely access to required systems and stakeholders for approvals and testing. Phase 0 will be completed before project start, which streamlines subsequent phases and does not extend the project timeline. Some phases may overlap or be adjusted based on client availability and feedback cycles.*

---

## Assumptions and Prerequisites

### Client Responsibilities:
1. Provide access to QuickBooks Online account
2. Provide access to Salesforce AvSight org (System Administrator)
3. Provide AWS account or create new account
4. Provide list of email recipients for notifications
5. Provide SMTP credentials for email service
6. Designate project stakeholders and decision-makers
7. Allocate time for testing and feedback
8. Review and approve Salesforce object design before implementation
9. Provide QuickBooks Developer account access or coordinate account creation

### Technical Prerequisites:
1. QuickBooks Online subscription (active)
2. Salesforce AvSight instance with customization permissions
3. AWS account with appropriate permissions
4. Email server (SMTP) access for notifications
5. Internet connectivity for API access

---

## Monthly Operating Costs

After deployment, the system will incur ongoing AWS infrastructure costs. Based on the current implementation with incremental sync running every 15 minutes during business hours (8 AM - 5 PM Central), full sync once daily, and end-of-day email, the estimated monthly costs are:

### AWS Service Costs Breakdown

| Service | Usage | Monthly Cost |
|---------|-------|--------------|
| **Lambda Compute (Incremental Sync)** | 40 invocations/day × 30 days = 1,200/month<br>1,024 MB memory × 3 min avg duration | $3.60 |
| **Lambda Compute (Full Sync)** | 1 invocation/day × 30 days = 30/month<br>1,024 MB memory × 6 min avg duration | $0.18 |
| **Lambda Compute (End-of-Day Email)** | 1 invocation/day × 30 days = 30/month<br>256 MB memory × 20 sec avg duration | $0.00 |
| **Lambda Requests** | 1,260 total requests/month | $0.00 (free tier) |
| **EventBridge** | 3 scheduled rules | $0.00 (scheduled rules are free) |
| **Secrets Manager** | 3 secrets stored | $1.20 |
| **S3 Storage** | ~1.5 MB/month for daily summaries | $0.00 (negligible) |
| **S3 Requests** | ~1,200 PUTs + 30 GETs/month | $0.01 |
| **CloudWatch Logs** | ~12.3 GB/month (first 5 GB free) | $3.65 |
| **TOTAL MONTHLY COST** | | **~$8.64/month** |

### Cost Notes

- **Free Tier Benefits:** The first 1 million Lambda requests per month are free, and the first 5 GB of CloudWatch Logs per month are free, which significantly reduces costs.
- **Cost Optimization:** Costs may vary slightly based on:
  - Actual execution duration (incremental syncs may be faster/slower depending on data volume)
  - Amount of data processed
  - CloudWatch log retention settings (default retention can be adjusted to reduce costs)
  - S3 storage growth over time (minimal impact expected)
- **Scalability:** As data volume grows, costs will scale proportionally but remain very reasonable due to AWS's pay-per-use pricing model.

### Cost Comparison

This automated sync solution provides enterprise-grade reliability and automation at a minimal monthly cost of approximately **$8-9 per month**, which is significantly less than the cost of manual data entry or maintaining a dedicated server for this purpose.

---

## Payment Terms

- **Phase 0 Payment:** $1,400 (due upon project approval - covers completed system adaptation work)
- **Initial Payment:** 40% of remaining balance upon project start ($1,652 - $2,236)
- **Milestone Payment:** 30% upon successful completion of testing phase ($1,239 - $1,677)
- **Final Payment:** 30% upon production deployment and acceptance ($1,239 - $1,677)

**Payment Schedule Summary:**
- Phase 0 (System Adaptation): $1,400 (due upon approval)
- Remaining Project Work: $4,130 - $5,590 (phased payments as above)
- **Total Project Cost:** $5,530 - $6,990

All invoices are due within 15 days of receipt.

---

## Terms and Conditions

1. **Scope Changes:** Any changes to the scope of work will be documented and may result in additional time and cost estimates.

2. **Third-Party Services:** Costs for third-party services (AWS, QuickBooks, Salesforce) are the responsibility of AirSpares Unlimited and not included in this proposal. See "Monthly Operating Costs" section below for AWS cost estimates.

3. **Data Security:** All credentials and sensitive data will be stored in AWS Secrets Manager following security best practices.

4. **Warranty:** The delivered solution will be free from defects for 30 days post-deployment. Any defects identified during this period will be addressed at no additional cost.

5. **Intellectual Property:** The custom code and configurations will be owned by AirSpares Unlimited upon final payment.

6. **Cancellation:** If the project is cancelled, payment is due for all completed work up to the cancellation date.

---

## Next Steps

To proceed with this project:

1. Review and approve this proposal
2. Sign and return the proposal
3. Provide initial payment (50%)
4. Schedule kickoff meeting to discuss:
   - Access credentials
   - Timeline preferences
   - Communication preferences
   - Initial configuration requirements

---

## Contact Information

**Garrett Johnson**  
Email: gjohnson@pioneer-aero.com

---

**Proposal Valid Until:** February 28, 2025

Thank you for considering this proposal. I look forward to working with AirSpares Unlimited to deploy this automated sync solution.

