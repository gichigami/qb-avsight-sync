# QuickBooks-AvSight Sync Implementation Guide
## AirSpares Unlimited

**Prepared by:** Garrett Johnson  
**Date:** January 2025  
**Version:** 1.0

---

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Phase 1: QuickBooks API Configuration](#phase-1-quickbooks-api-configuration)
3. [Phase 2: Salesforce Setup](#phase-2-salesforce-setup)
4. [Phase 3: Email/SMTP Configuration](#phase-3-emailsmtp-configuration)
5. [Phase 4: AWS Account Setup](#phase-4-aws-account-setup)
6. [Phase 5: AWS Infrastructure Deployment](#phase-5-aws-infrastructure-deployment)
7. [Phase 6: Code Deployment](#phase-6-code-deployment)
8. [Phase 7: Testing and Validation](#phase-7-testing-and-validation)
9. [Phase 8: Go-Live and Monitoring](#phase-8-go-live-and-monitoring)
10. [Troubleshooting](#troubleshooting)
11. [Support and Maintenance](#support-and-maintenance)

---

## Prerequisites

Before beginning implementation, ensure you have:

- [ ] QuickBooks Online account with admin access
- [ ] Salesforce AvSight org with System Administrator access
- [ ] AWS account (or ability to create one)
- [ ] Gmail account or access to SMTP email server
- [ ] AWS CLI installed and configured (for command-line deployment)
- [ ] Python 3.11+ installed (for local testing)
- [ ] Basic familiarity with AWS services (Lambda, Secrets Manager, S3, EventBridge)

**Estimated Time for Prerequisites:** 1-2 hours

---

## Phase 1: QuickBooks API Configuration

**Estimated Time:** 5-7 hours  
**Cost:** $500 - $700

### Step 1.1: Create QuickBooks Developer Account

1. Navigate to the [Intuit Developer Portal](https://developer.intuit.com/)
2. Click **"Sign In"** or **"Create Account"**
3. Sign in with your Intuit account or create a new one
4. Complete the developer registration process

**Resources:**
- [Intuit Developer Portal](https://developer.intuit.com/)
- [Getting Started Guide](https://developer.intuit.com/app/developer/qbo/docs/develop/authentication-and-authorization)

**Time Estimate:** 30 minutes

---

### Step 1.2: Create a New App

1. In the Intuit Developer Portal, click **"Create an app"**
2. Select **"QuickBooks Online"** as the product
3. Fill in the app details:
   - **App Name:** `AirSpares Unlimited - AvSight Sync` (or your preferred name)
   - **App Type:** Select **"OAuth 2.0"**
   - **Environment:** Select **"Production"** (or "Sandbox" for testing)
4. Click **"Create"**

**Resources:**
- [Creating Your First App](https://developer.intuit.com/app/developer/qbo/docs/develop/authentication-and-authorization/oauth-2.0)

**Time Estimate:** 15 minutes

---

### Step 1.3: Configure OAuth 2.0 Settings

1. In your app's settings, navigate to **"Keys & Credentials"**
2. Note your **Client ID** and **Client Secret** (you'll need these later)
3. Configure **Redirect URIs:**
   - Add: `https://developer.intuit.com/v2/OAuth2Playground/RedirectUrl`
   - This is the standard OAuth playground URL for testing
4. For production, you may want to add your own redirect URI (optional)
5. Save your changes

**Important:** Keep your Client ID and Client Secret secure. Do not share them publicly.

**Resources:**
- [OAuth 2.0 Configuration](https://developer.intuit.com/app/developer/qbo/docs/develop/authentication-and-authorization/oauth-2.0#configure-your-app)

**Time Estimate:** 20 minutes

---

### Step 1.4: Complete OAuth Authorization Flow

1. You'll need to complete the OAuth flow to get initial access and refresh tokens
2. Use the OAuth 2.0 Playground or a local script to complete authorization:
   - Navigate to: [OAuth 2.0 Playground](https://developer.intuit.com/app/developer/playground)
   - Enter your Client ID and Client Secret
   - Select **"QuickBooks Online"** as the product
   - Select scopes: `com.intuit.quickbooks.accounting`
   - Click **"Connect to QuickBooks"**
   - Sign in and authorize the app
   - Copy the **Authorization Code**
   - Exchange it for **Access Token** and **Refresh Token**
   - Note your **Realm ID** (Company ID)

**Alternative:** Use a local authentication script if provided by your developer.

**Resources:**
- [OAuth 2.0 Playground](https://developer.intuit.com/app/developer/playground)
- [OAuth 2.0 Flow Documentation](https://developer.intuit.com/app/developer/qbo/docs/develop/authentication-and-authorization/oauth-2.0#oauth-2.0-flow)

**Time Estimate:** 1-2 hours (including testing)

---

### Step 1.5: Test QuickBooks API Connection

1. Use the OAuth Playground or a test script to verify you can:
   - Query invoices: `GET /v3/company/{realmId}/query?query=SELECT * FROM Invoice MAXRESULTS 5`
   - Query bills: `GET /v3/company/{realmId}/query?query=SELECT * FROM Bill MAXRESULTS 5`
2. Verify you receive data back from QuickBooks
3. Note any API rate limits or restrictions

**Resources:**
- [QuickBooks API Explorer](https://developer.intuit.com/app/developer/qbo/docs/develop/explore-the-quickbooks-online-api)
- [API Rate Limits](https://developer.intuit.com/app/developer/qbo/docs/develop/authentication-and-authorization/oauth-2.0#rate-limits)

**Time Estimate:** 30 minutes

---

### Step 1.6: Document Credentials

Create a secure document (password-protected) with the following information:

```
Client ID: [your-client-id]
Client Secret: [your-client-secret]
Realm ID: [your-realm-id]
Access Token: [initial-access-token]
Refresh Token: [refresh-token]
Environment: production (or sandbox)
Redirect URI: https://developer.intuit.com/v2/OAuth2Playground/RedirectUrl
```

**Important:** These credentials will be stored in AWS Secrets Manager in Phase 5. Keep them secure until then.

**Time Estimate:** 15 minutes

---

## Phase 2: Salesforce Setup

**Estimated Time:** 8-10 hours  
**Cost:** $800 - $1,000

### Step 2.1: Create API-Enabled User

1. Log in to Salesforce AvSight as a System Administrator
2. Navigate to **Setup** → **Users** → **Users**
3. Click **"New User"** or select an existing user to modify
4. Create a dedicated user for API access (recommended) or use an existing admin user
5. Ensure the user has:
   - **Profile:** System Administrator (or custom profile with API access)
   - **API Enabled:** Check this checkbox (required)
   - **Active:** User must be active
6. Save the user

**Resources:**
- [Create Users in Salesforce](https://help.salesforce.com/s/articleView?id=sf.users.htm)
- [Enable API Access for Users](https://help.salesforce.com/s/articleView?id=sf.user_management_enable_api_access.htm)

**Time Estimate:** 30 minutes

---

### Step 2.2: Generate Security Token

1. Log in as the API user you just created
2. Navigate to **Setup** → **My Personal Information** → **Reset My Security Token**
3. Click **"Reset Security Token"**
4. Check the email associated with the user account
5. Copy the security token from the email (it will look like: `ABCD1234EFGH5678`)

**Important:** 
- The security token is required for API authentication
- If the user's password changes, the security token must be reset
- Security tokens expire after password changes

**Resources:**
- [Reset Security Token](https://help.salesforce.com/s/articleView?id=sf.user_security_token.htm)

**Time Estimate:** 15 minutes

---

### Step 2.3: Document Salesforce Credentials

Create a secure document with:

```
Username: [api-user@yourcompany.com]
Password: [user-password]
Security Token: [security-token-from-email]
Instance URL: [https://yourinstance.salesforce.com]
```

**Note:** The Instance URL can be found in your browser's address bar when logged into Salesforce, or in **Setup** → **Company Information**.

**Time Estimate:** 15 minutes

---

### Step 2.4: Create Bill__c Custom Object

1. In Salesforce, navigate to **Setup** → **Object Manager**
2. Click **"Create"** → **"Custom Object"**
3. Fill in the object details:
   - **Label:** `Bill`
   - **Plural Label:** `Bills`
   - **Object Name:** `Bill__c` (auto-generated)
   - **Record Name:** Select **"Text"** or **"Auto Number"**
   - **Data Type:** Text (255 characters)
   - **Field Name:** `Bill Name`
4. Check **"Allow Reports"** and **"Allow Activities"**
5. Click **"Save"**

**Resources:**
- [Create Custom Objects](https://help.salesforce.com/s/articleView?id=sf.customize_createobjects.htm)

**Time Estimate:** 30 minutes

---

### Step 2.5: Create Required Custom Fields

Create the following fields on the Bill__c object:

#### Field 1: Repair_Order__c (Lookup)
1. In Object Manager, select **Bill__c**
2. Click **"Fields & Relationships"** → **"New"**
3. Select **"Lookup Relationship"**
4. Related To: **inscor__Repair_Order__c**
5. Field Name: `Repair_Order__c`
6. Field Label: `Repair Order`
7. Click **"Next"** → **"Next"** → **"Save"**

#### Field 2: Purchase_Order__c (Lookup)
- Same process as above
- Related To: **inscor__Purchase_Order__c**
- Field Name: `Purchase_Order__c`
- Field Label: `Purchase Order`

#### Field 3: Order__c (Text)
1. Select **"Text"**
2. Field Name: `Order__c`
3. Field Label: `Order`
4. Length: **255**
5. Click **"Next"** → **"Save"**

#### Field 4: Account__c (Lookup)
- Related To: **Account**
- Field Name: `Account__c`
- Field Label: `Account`

#### Field 5: QBO_Bill_ID__c (Text - External ID)
1. Select **"Text"**
2. Field Name: `QBO_Bill_ID__c`
3. Field Label: `QuickBooks Bill ID`
4. Length: **255**
5. Check **"Unique"** and **"External ID"**
6. Click **"Next"** → **"Save"**

#### Field 6: Memo__c (Long Text Area)
1. Select **"Long Text Area"**
2. Field Name: `Memo__c`
3. Field Label: `Memo`
4. Length: **32,000**
5. Click **"Next"** → **"Save"**

#### Field 7: Total_Amount__c (Currency)
1. Select **"Currency"**
2. Field Name: `Total_Amount__c`
3. Field Label: `Total Amount`
4. Decimal Places: **2**
5. Click **"Next"** → **"Save"**

#### Field 8: Balance_Due__c (Currency)
- Same as Total_Amount__c
- Field Name: `Balance_Due__c`
- Field Label: `Balance Due`

#### Field 9: Bill_Date__c (Date)
1. Select **"Date"**
2. Field Name: `Bill_Date__c`
3. Field Label: `Bill Date`
4. Click **"Next"** → **"Save"**

#### Field 10: Due_Date__c (Date)
- Same as Bill_Date__c
- Field Name: `Due_Date__c`
- Field Label: `Due Date`

**Resources:**
- [Create Custom Fields](https://help.salesforce.com/s/articleView?id=sf.customize_createfields.htm)
- [External ID Fields](https://help.salesforce.com/s/articleView?id=sf.customize_crossobject_field_types.htm)

**Time Estimate:** 2-3 hours

---

### Step 2.6: Configure Field-Level Security

1. Navigate to **Setup** → **Object Manager** → **Bill__c**
2. Click **"Field-Level Security"**
3. For each field, ensure appropriate profiles have **"Read"** and **"Edit"** access
4. At minimum, System Administrators should have full access

**Time Estimate:** 30 minutes

---

### Step 2.7: Configure Object Permissions

1. Navigate to **Setup** → **Object Manager** → **Bill__c**
2. Click **"Object Permissions"** or configure via **Profiles**
3. Ensure appropriate profiles have:
   - **Read**
   - **Create**
   - **Edit**
   - **Delete** (if needed)
   - **View All** (optional)
   - **Modify All** (optional)

**Time Estimate:** 30 minutes

---

### Step 2.8: Create Page Layout

1. Navigate to **Setup** → **Object Manager** → **Bill__c**
2. Click **"Page Layouts"** → **"New"** or edit existing
3. Add all created fields to the layout
4. Organize fields into logical sections
5. Save the layout

**Time Estimate:** 30 minutes

---

### Step 2.9: Test Object Creation

1. Navigate to the **Bills** tab (or use App Launcher)
2. Click **"New"**
3. Fill in test data:
   - Bill Name: `Test Bill 001`
   - QBO_Bill_ID__c: `TEST-001`
   - Total_Amount__c: `1000.00`
   - Balance_Due__c: `1000.00`
   - Bill_Date__c: Today's date
4. Save the record
5. Verify all fields are visible and editable
6. Delete the test record (optional)

**Time Estimate:** 30 minutes

---

## Phase 3: Email/SMTP Configuration

**Estimated Time:** 1-2 hours  
**Cost:** $100 - $200

### Step 3.1: Gmail App Password Setup (Recommended)

If using Gmail for SMTP:

1. Log in to your Gmail account
2. Navigate to [Google Account Settings](https://myaccount.google.com/)
3. Click **"Security"** in the left sidebar
4. Under **"Signing in to Google"**, find **"2-Step Verification"**
   - If not enabled, enable it first (required for app passwords)
5. After 2-Step Verification is enabled, click **"App passwords"**
6. Select **"Mail"** and **"Other (Custom name)"**
7. Enter a name: `AvSight Sync System`
8. Click **"Generate"**
9. Copy the 16-character app password (you won't see it again)

**Important:** 
- Use the app password, NOT your regular Gmail password
- App passwords are required when 2-Step Verification is enabled
- Each app password is unique and can be revoked independently

**Resources:**
- [Gmail App Passwords](https://support.google.com/accounts/answer/185833)
- [Enable 2-Step Verification](https://support.google.com/accounts/answer/185839)

**Time Estimate:** 30 minutes

---

### Step 3.2: Alternative SMTP Configuration

If using a different email provider:

#### Microsoft 365 / Outlook
- Server: `smtp.office365.com`
- Port: `587`
- Security: TLS
- Requires app password (similar to Gmail)

#### Other SMTP Servers
- Contact your IT department for SMTP server details
- Common settings:
  - Server: `smtp.yourdomain.com`
  - Port: `587` (TLS) or `465` (SSL)
  - Authentication: Required

**Resources:**
- [Microsoft 365 SMTP Settings](https://support.microsoft.com/en-us/office/pop-imap-and-smtp-settings-for-outlook-com-d088b986-291d-42b8-9564-9c414e2aa040)

**Time Estimate:** 30 minutes - 1 hour

---

### Step 3.3: Document SMTP Credentials

Create a secure document with:

```
SMTP Server: smtp.gmail.com (or your SMTP server)
Port: 587
Security: TLS
Username: [your-email@yourcompany.com]
Password: [app-password or SMTP-password]
From Email: [your-email@yourcompany.com]
```

**Time Estimate:** 15 minutes

---

### Step 3.4: Test SMTP Connection

You can test the SMTP connection using a simple Python script or email client:

```python
import smtplib
from email.mime.text import MIMEText

smtp_server = "smtp.gmail.com"
smtp_port = 587
username = "your-email@yourcompany.com"
password = "your-app-password"

try:
    server = smtplib.SMTP(smtp_server, smtp_port)
    server.starttls()
    server.login(username, password)
    print("✅ SMTP connection successful!")
    server.quit()
except Exception as e:
    print(f"❌ SMTP connection failed: {e}")
```

**Time Estimate:** 30 minutes

---

## Phase 4: AWS Account Setup

**Estimated Time:** 1-2 hours  
**Cost:** $100 - $200

### Step 4.1: Create AWS Account (If Needed)

1. Navigate to [AWS Sign Up](https://aws.amazon.com/)
2. Click **"Create an AWS Account"**
3. Follow the registration process:
   - Enter email and account name
   - Provide payment information (required, but free tier available)
   - Verify identity via phone call
4. Select a support plan (Basic is free)

**Resources:**
- [AWS Account Creation](https://aws.amazon.com/premiumsupport/knowledge-center/create-and-activate-aws-account/)
- [AWS Free Tier](https://aws.amazon.com/free/)

**Time Estimate:** 30 minutes

---

### Step 4.2: Install and Configure AWS CLI

1. Install AWS CLI:
   - **macOS:** `brew install awscli`
   - **Windows:** Download from [AWS CLI Installer](https://aws.amazon.com/cli/)
   - **Linux:** `sudo apt-get install awscli` or `sudo yum install awscli`

2. Configure AWS CLI:
   ```bash
   aws configure
   ```
   - Enter your AWS Access Key ID
   - Enter your AWS Secret Access Key
   - Enter default region: `us-east-1` (or your preferred region)
   - Enter default output format: `json`

**Resources:**
- [AWS CLI Installation](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html)
- [AWS CLI Configuration](https://docs.aws.amazon.com/cli/latest/userguide/cli-configure-quickstart.html)

**Time Estimate:** 30 minutes

---

### Step 4.3: Create IAM User for Deployment (Recommended)

1. Navigate to AWS Console → **IAM** → **Users**
2. Click **"Add users"**
3. Enter username: `avsight-sync-deployer`
4. Select **"Provide user access to the AWS Management Console"** (optional)
5. Select **"Attach policies directly"**
6. Attach policies:
   - `AWSLambda_FullAccess`
   - `AmazonS3FullAccess`
   - `SecretsManagerReadWrite`
   - `CloudWatchLogsFullAccess`
   - `AmazonEventBridgeFullAccess`
   - `IAMFullAccess` (for creating execution roles)
7. Create user and save **Access Key ID** and **Secret Access Key**

**Important:** Store these credentials securely. You'll use them for AWS CLI configuration.

**Resources:**
- [Creating IAM Users](https://docs.aws.amazon.com/IAM/latest/UserGuide/id_users_create.html)
- [IAM Best Practices](https://docs.aws.amazon.com/IAM/latest/UserGuide/best-practices.html)

**Time Estimate:** 30 minutes

---

## Phase 5: AWS Infrastructure Deployment

**Estimated Time:** 10-12 hours  
**Cost:** $1,000 - $1,200

### Step 5.1: Create IAM Execution Role for Lambda

1. Navigate to AWS Console → **IAM** → **Roles**
2. Click **"Create role"**
3. Select **"AWS service"** → **"Lambda"**
4. Click **"Next"**
5. Attach the following policies:
   - `SecretsManagerReadWrite` (or create custom policy with Secrets Manager access)
   - `AmazonS3FullAccess` (or create custom policy for specific bucket)
   - `CloudWatchLogsFullAccess` (for logging)
6. Click **"Next"**
7. Role name: `qb-avsight-sync-lambda-role`
8. Click **"Create role"**

**Custom Policy for Secrets Manager (if needed):**
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
                "arn:aws:secretsmanager:*:*:secret:quickbooks/credentials-*",
                "arn:aws:secretsmanager:*:*:secret:salesforce/credentials-*",
                "arn:aws:secretsmanager:*:*:secret:smtp/credentials-*"
            ]
        }
    ]
}
```

**Resources:**
- [Creating IAM Roles](https://docs.aws.amazon.com/IAM/latest/UserGuide/id_roles_create.html)
- [Lambda Execution Role](https://docs.aws.amazon.com/lambda/latest/dg/lambda-intro-execution-role.html)

**Time Estimate:** 1 hour

---

### Step 5.2: Create S3 Bucket for Daily Summaries

1. Navigate to AWS Console → **S3**
2. Click **"Create bucket"**
3. Bucket name: `qb-avsight-sync-daily-summaries-asu` (must be globally unique)
4. AWS Region: `us-east-1` (or your preferred region)
5. **Block Public Access:** Keep all settings enabled (recommended)
6. Click **"Create bucket"**

**Configure Versioning (Optional but Recommended):**
1. Select the bucket → **"Properties"** tab
2. Scroll to **"Bucket Versioning"**
3. Click **"Edit"** → Enable versioning → **"Save changes"**

**Configure Lifecycle Policy (Optional):**
1. Select the bucket → **"Management"** tab
2. Click **"Create lifecycle rule"**
3. Rule name: `DeleteOldSummaries`
4. Scope: Apply to all objects
5. Lifecycle rule actions: **"Expire current versions of objects"**
6. Days after object creation: `90` (or your preferred retention period)
7. Click **"Create rule"**

**Resources:**
- [Creating S3 Buckets](https://docs.aws.amazon.com/AmazonS3/latest/userguide/create-bucket-overview.html)
- [S3 Lifecycle Policies](https://docs.aws.amazon.com/AmazonS3/latest/userguide/object-lifecycle-mgmt.html)

**Time Estimate:** 30 minutes

---

### Step 5.3: Create Secrets in AWS Secrets Manager

#### Secret 1: QuickBooks Credentials

```bash
aws secretsmanager create-secret \
    --name quickbooks/credentials \
    --description "QuickBooks OAuth credentials for AvSight sync" \
    --secret-string '{
        "client_id": "YOUR_CLIENT_ID",
        "client_secret": "YOUR_CLIENT_SECRET",
        "access_token": "YOUR_ACCESS_TOKEN",
        "refresh_token": "YOUR_REFRESH_TOKEN",
        "realm_id": "YOUR_REALM_ID",
        "environment": "production",
        "redirect_uri": "https://developer.intuit.com/v2/OAuth2Playground/RedirectUrl"
    }'
```

**Or via AWS Console:**
1. Navigate to **Secrets Manager** → **"Store a new secret"**
2. Select **"Other type of secret"**
3. Select **"Plaintext"** tab
4. Paste the JSON above (with your actual credentials)
5. Secret name: `quickbooks/credentials`
6. Click **"Next"** → **"Next"** → **"Store"**

#### Secret 2: Salesforce Credentials

```bash
aws secretsmanager create-secret \
    --name salesforce/credentials \
    --description "Salesforce API credentials for AvSight sync" \
    --secret-string '{
        "username": "api-user@yourcompany.com",
        "password": "user-password",
        "security_token": "security-token",
        "instance_url": "https://yourinstance.salesforce.com"
    }'
```

#### Secret 3: SMTP Credentials

```bash
aws secretsmanager create-secret \
    --name smtp/credentials \
    --description "SMTP email credentials for AvSight sync notifications" \
    --secret-string '{
        "server": "smtp.gmail.com",
        "port": 587,
        "username": "your-email@yourcompany.com",
        "password": "your-app-password",
        "from_email": "your-email@yourcompany.com"
    }'
```

**Resources:**
- [AWS Secrets Manager](https://docs.aws.amazon.com/secretsmanager/latest/userguide/intro.html)
- [Creating Secrets](https://docs.aws.amazon.com/secretsmanager/latest/userguide/manage_create-basic-secret.html)

**Time Estimate:** 1 hour

---

### Step 5.4: Create CloudWatch Log Groups

CloudWatch Log Groups are created automatically when Lambda functions run, but you can create them manually:

```bash
aws logs create-log-group --log-group-name /aws/lambda/qb-avsight-sync2
aws logs create-log-group --log-group-name /aws/lambda/qb-avsight-sync
aws logs create-log-group --log-group-name /aws/lambda/qb-avsight-end-of-day-email
```

**Time Estimate:** 15 minutes

---

### Step 5.5: Configure EventBridge Schedules

#### Schedule 1: Incremental Sync (Every 15 minutes, 8 AM - 5 PM Central)

```bash
# Create the rule
aws events put-rule \
    --name qb-avsight-sync-schedule \
    --schedule-expression "cron(0,15,30,45 14-23 * * ? *)" \
    --description "Run QB-AvSight incremental sync every 15 minutes during business hours (8 AM - 5 PM Central)"

# Note: 14-23 UTC = 8 AM - 5 PM Central (adjust for your timezone)
```

#### Schedule 2: Full Sync (Daily at 7:50 AM Central)

```bash
aws events put-rule \
    --name qb-avsight-sync-full-schedule \
    --schedule-expression "cron(50 13 * * ? *)" \
    --description "Run QB-AvSight full sync daily at 7:50 AM Central"

# Note: 13:50 UTC = 7:50 AM Central (adjust for your timezone)
```

#### Schedule 3: End-of-Day Email (Daily at 5:20 PM Central)

```bash
aws events put-rule \
    --name qb-avsight-end-of-day-email \
    --schedule-expression "cron(20 23 * * ? *)" \
    --description "Send daily summary email at 5:20 PM Central"

# Note: 23:20 UTC = 5:20 PM Central (adjust for your timezone)
```

**Note:** You'll add Lambda functions as targets after deploying the functions in Phase 6.

**Resources:**
- [Amazon EventBridge Scheduler](https://docs.aws.amazon.com/scheduler/latest/UserGuide/what-is-scheduler.html)
- [Cron Expressions](https://docs.aws.amazon.com/eventbridge/latest/userguide/eb-create-rule-schedule.html)

**Time Estimate:** 1 hour

---

### Step 5.6: Set Up CloudWatch Alarms (Optional but Recommended)

Create alarms to monitor Lambda function health:

```bash
# Alarm for sync function errors
aws cloudwatch put-metric-alarm \
    --alarm-name qb-avsight-sync-errors \
    --alarm-description "Alert when sync function has errors" \
    --metric-name Errors \
    --namespace AWS/Lambda \
    --statistic Sum \
    --period 300 \
    --threshold 1 \
    --comparison-operator GreaterThanThreshold \
    --evaluation-periods 1 \
    --dimensions Name=FunctionName,Value=qb-avsight-sync2
```

**Resources:**
- [CloudWatch Alarms](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/AlarmThatSendsEmail.html)

**Time Estimate:** 1 hour

---

## Phase 6: Code Deployment

**Estimated Time:** 12-18 hours  
**Cost:** $1,200 - $1,800

### Step 6.1: Obtain Code Package

1. Receive the code package from your developer
2. Extract the files to a local directory
3. Review the code structure:
   - `lambda_function.py` - Main sync function
   - `quickbooks_connector.py` - QuickBooks API client
   - `salesforce_connector.py` - Salesforce API client
   - `utils.py` - Helper functions
   - `config.py` - Configuration management
   - `requirements.txt` - Python dependencies
   - `end_of_day_email.py` - End-of-day email function

**Time Estimate:** 30 minutes

---

### Step 6.2: Customize Configuration

1. Edit `config.json` (if provided) or update `config.py`:
   ```json
   {
     "salesforce_batch_size": 100,
     "results_directory": "/tmp",
     "qb_redirect_uri": "https://developer.intuit.com/v2/OAuth2Playground/RedirectUrl",
     "qb_max_results_per_page": 100,
     "enable_incremental_sync": true,
     "email_recipients_run_summary": [
       "recipient1@yourcompany.com"
     ],
     "email_recipients_daily_summary": [
       "recipient1@yourcompany.com",
       "recipient2@yourcompany.com"
     ],
     "s3_bucket_name": "qb-avsight-sync-daily-summaries-asu"
   }
   ```

2. Update email recipient lists
3. Update S3 bucket name to match your bucket
4. Verify all configuration values

**Time Estimate:** 30 minutes

---

### Step 6.3: Update Code for Bill__c Object

If the code uses `Payment__c`, update all references to `Bill__c`:

1. Search for `Payment__c` in all Python files
2. Replace with `Bill__c`
3. Files to check:
   - `lambda_function.py`
   - `salesforce_connector.py` (if object-specific)
   - Any other files referencing the object

**Time Estimate:** 1-2 hours

---

### Step 6.4: Create Deployment Package for Main Sync Function

```bash
# Create deployment directory
mkdir lambda-deployment
cd lambda-deployment

# Copy code files
cp ../qb-avsight-sync.py .
cp ../quickbooks_connector.py .
cp ../salesforce_connector.py .
cp ../utils.py .
cp ../config.py .
cp ../config.json .

# Install dependencies
pip install -r ../requirements.txt -t .

# Create ZIP file
zip -r qb-avsight-sync2.zip .
```

**Time Estimate:** 30 minutes

---

### Step 6.5: Deploy Incremental Sync Lambda Function

```bash
aws lambda create-function \
    --function-name qb-avsight-sync2 \
    --runtime python3.11 \
    --role arn:aws:iam::YOUR-ACCOUNT-ID:role/qb-avsight-sync-lambda-role \
    --handler qb-avsight-sync.lambda_handler \
    --zip-file fileb://qb-avsight-sync2.zip \
    --timeout 900 \
    --memory-size 1024 \
    --environment Variables='{
        "S3_BUCKET_NAME": "qb-avsight-sync-daily-summaries-asu"
    }'
```

**Or via AWS Console:**
1. Navigate to **Lambda** → **"Create function"**
2. Select **"Author from scratch"**
3. Function name: `qb-avsight-sync2`
4. Runtime: **Python 3.11**
5. Architecture: **x86_64**
6. Execution role: Select `qb-avsight-sync-lambda-role`
7. Click **"Create function"**
8. Upload the ZIP file
9. Handler: `qb-avsight-sync.lambda_handler`
10. Timeout: **15 minutes** (900 seconds)
11. Memory: **1024 MB**
12. Environment variables: Add `S3_BUCKET_NAME` = `qb-avsight-sync-daily-summaries-asu`
13. Click **"Save"**

**Time Estimate:** 1 hour

---

### Step 6.6: Deploy Full Sync Lambda Function

Repeat Step 6.5 for the full sync function:

```bash
# Create separate deployment package (or reuse if code is identical)
aws lambda create-function \
    --function-name qb-avsight-sync \
    --runtime python3.11 \
    --role arn:aws:iam::YOUR-ACCOUNT-ID:role/qb-avsight-sync-lambda-role \
    --handler qb-avsight-sync.lambda_handler \
    --zip-file fileb://qb-avsight-sync2.zip \
    --timeout 900 \
    --memory-size 1024 \
    --environment Variables='{
        "S3_BUCKET_NAME": "qb-avsight-sync-daily-summaries-asu"
    }'
```

**Time Estimate:** 30 minutes

---

### Step 6.7: Deploy End-of-Day Email Lambda Function

1. Create deployment package for email function:
   ```bash
   mkdir email-deployment
   cd email-deployment
   cp ../end_of_day_email.py .
   cp ../utils.py .
   cp ../config.py .
   pip install -r ../requirements.txt -t .
   zip -r qb-avsight-end-of-day-email.zip .
   ```

2. Deploy the function:
   ```bash
   aws lambda create-function \
       --function-name qb-avsight-end-of-day-email \
       --runtime python3.11 \
       --role arn:aws:iam::YOUR-ACCOUNT-ID:role/qb-avsight-sync-lambda-role \
       --handler end_of_day_email.lambda_handler \
       --zip-file fileb://qb-avsight-end-of-day-email.zip \
       --timeout 30 \
       --memory-size 256 \
       --environment Variables='{
           "S3_BUCKET_NAME": "qb-avsight-sync-daily-summaries-asu"
       }'
   ```

**Time Estimate:** 1 hour

---

### Step 6.8: Grant EventBridge Permission to Invoke Lambda

For each Lambda function, grant EventBridge permission:

```bash
# Incremental sync
aws lambda add-permission \
    --function-name qb-avsight-sync2 \
    --statement-id eventbridge-invoke-sync \
    --action lambda:InvokeFunction \
    --principal events.amazonaws.com \
    --source-arn arn:aws:events:us-east-1:YOUR-ACCOUNT-ID:rule/qb-avsight-sync-schedule

# Full sync
aws lambda add-permission \
    --function-name qb-avsight-sync \
    --statement-id eventbridge-invoke-full \
    --action lambda:InvokeFunction \
    --principal events.amazonaws.com \
    --source-arn arn:aws:events:us-east-1:YOUR-ACCOUNT-ID:rule/qb-avsight-sync-full-schedule

# End-of-day email
aws lambda add-permission \
    --function-name qb-avsight-end-of-day-email \
    --statement-id eventbridge-invoke-email \
    --action lambda:InvokeFunction \
    --principal events.amazonaws.com \
    --source-arn arn:aws:events:us-east-1:YOUR-ACCOUNT-ID:rule/qb-avsight-end-of-day-email
```

**Time Estimate:** 30 minutes

---

### Step 6.9: Add Lambda Functions as EventBridge Targets

```bash
# Incremental sync target
aws events put-targets \
    --rule qb-avsight-sync-schedule \
    --targets "Id=1,Arn=arn:aws:lambda:us-east-1:YOUR-ACCOUNT-ID:function:qb-avsight-sync2"

# Full sync target
aws events put-targets \
    --rule qb-avsight-sync-full-schedule \
    --targets "Id=1,Arn=arn:aws:lambda:us-east-1:YOUR-ACCOUNT-ID:function:qb-avsight-sync"

# End-of-day email target
aws events put-targets \
    --rule qb-avsight-end-of-day-email \
    --targets "Id=1,Arn=arn:aws:lambda:us-east-1:YOUR-ACCOUNT-ID:function:qb-avsight-end-of-day-email"
```

**Time Estimate:** 30 minutes

---

## Phase 7: Testing and Validation

**Estimated Time:** 10-12 hours  
**Cost:** $1,000 - $1,200

### Step 7.1: Manual Lambda Invocation Test

Test each Lambda function manually:

```bash
# Test incremental sync
aws lambda invoke \
    --function-name qb-avsight-sync2 \
    --payload '{}' \
    response.json

# Check response
cat response.json

# Test full sync
aws lambda invoke \
    --function-name qb-avsight-sync \
    --payload '{}' \
    response.json

# Test end-of-day email
aws lambda invoke \
    --function-name qb-avsight-end-of-day-email \
    --payload '{}' \
    response.json
```

**Time Estimate:** 1 hour

---

### Step 7.2: Check CloudWatch Logs

```bash
# View logs for incremental sync
aws logs tail /aws/lambda/qb-avsight-sync2 --follow

# View logs for full sync
aws logs tail /aws/lambda/qb-avsight-sync --follow

# View logs for email function
aws logs tail /aws/lambda/qb-avsight-end-of-day-email --follow
```

**Or via AWS Console:**
1. Navigate to **CloudWatch** → **Log groups**
2. Select the log group for your function
3. Review recent log streams

**Time Estimate:** 1 hour

---

### Step 7.3: Verify QuickBooks Data Retrieval

1. Check CloudWatch logs for successful QuickBooks API calls
2. Verify invoices and bills are being fetched
3. Check for any API rate limit errors
4. Verify token refresh is working (if applicable)

**Time Estimate:** 1 hour

---

### Step 7.4: Verify Salesforce Updates

1. Log in to Salesforce
2. Navigate to **Bills** tab
3. Check for new Bill__c records created
4. Verify existing records are being updated
5. Check field values match QuickBooks data
6. Verify relationships (Repair Orders, Purchase Orders, Accounts) are populated

**Time Estimate:** 2 hours

---

### Step 7.5: Verify Email Notifications

1. Check that run summary emails are being sent (if enabled)
2. Wait for end-of-day email (or trigger manually)
3. Verify email recipients are correct
4. Check email content and formatting
5. Verify S3 summaries are being created

**Time Estimate:** 1 hour

---

### Step 7.6: Test Scheduled Execution

1. Wait for scheduled execution times
2. Verify functions are triggered automatically
3. Check CloudWatch logs for scheduled runs
4. Verify no errors occur during scheduled execution

**Time Estimate:** 2 hours (waiting for schedules)

---

### Step 7.7: Load Testing

1. Test with realistic data volumes
2. Verify performance is acceptable
3. Check for timeout issues
4. Monitor AWS costs during testing

**Time Estimate:** 2 hours

---

### Step 7.8: Error Handling Tests

Test error scenarios:
- Invalid QuickBooks credentials
- Invalid Salesforce credentials
- Network failures
- API rate limits
- Missing relationships in Salesforce

**Time Estimate:** 2 hours

---

## Phase 8: Go-Live and Monitoring

**Estimated Time:** 4-6 hours  
**Cost:** $400 - $600

### Step 8.1: Final Production Configuration Review

1. Verify all credentials are correct
2. Verify all configuration values
3. Verify email recipients
4. Verify schedules are correct
5. Review IAM permissions

**Time Estimate:** 1 hour

---

### Step 8.2: Enable EventBridge Schedules

Ensure all schedules are enabled:

```bash
aws events enable-rule --name qb-avsight-sync-schedule
aws events enable-rule --name qb-avsight-sync-full-schedule
aws events enable-rule --name qb-avsight-end-of-day-email
```

**Time Estimate:** 15 minutes

---

### Step 8.3: Monitor First Sync Cycles

1. Monitor CloudWatch logs for first few sync cycles
2. Verify no errors occur
3. Check Salesforce for data updates
4. Verify emails are being sent
5. Address any immediate issues

**Time Estimate:** 2 hours

---

### Step 8.4: Set Up Monitoring Dashboard (Optional)

1. Create CloudWatch dashboard
2. Add key metrics:
   - Lambda invocations
   - Lambda errors
   - Lambda duration
   - S3 object counts
3. Set up email alerts for critical errors

**Time Estimate:** 1 hour

---

### Step 8.5: Document Production Configuration

Document:
- Lambda function names and ARNs
- S3 bucket name
- Secrets Manager secret names
- EventBridge schedule names
- Email recipients
- Contact information for support

**Time Estimate:** 1 hour

---

## Troubleshooting

### Common Issues and Solutions

#### Issue: Lambda Function Timeout
**Solution:** Increase timeout setting or optimize code performance

#### Issue: QuickBooks Token Expired
**Solution:** Tokens should auto-refresh. Check Secrets Manager permissions.

#### Issue: Salesforce Authentication Failed
**Solution:** Verify security token is correct and user is active.

#### Issue: Email Not Sending
**Solution:** Verify SMTP credentials and check Gmail app password.

#### Issue: S3 Access Denied
**Solution:** Verify Lambda execution role has S3 permissions.

#### Issue: EventBridge Not Triggering
**Solution:** Verify schedules are enabled and Lambda permissions are correct.

**Resources:**
- [AWS Lambda Troubleshooting](https://docs.aws.amazon.com/lambda/latest/dg/troubleshooting.html)
- [QuickBooks API Troubleshooting](https://developer.intuit.com/app/developer/qbo/docs/develop/troubleshooting)

---

## Support and Maintenance

### Regular Maintenance Tasks

1. **Monthly:** Review CloudWatch logs for errors
2. **Quarterly:** Review AWS costs
3. **As Needed:** Update credentials if passwords change
4. **As Needed:** Update code for API changes

### Getting Help

- **Developer Contact:** Garrett Johnson (gjohnson@pioneer-aero.com)
- **AWS Support:** [AWS Support Center](https://console.aws.amazon.com/support/)
- **QuickBooks API Support:** [Intuit Developer Support](https://help.developer.intuit.com/)

---

## Appendix: Time and Cost Summary

| Phase | Description | Estimated Time | Estimated Cost |
|-------|-------------|----------------|----------------|
| 1 | QuickBooks API Configuration | 5-7 hours | $500 - $700 |
| 2 | Salesforce Setup | 8-10 hours | $800 - $1,000 |
| 3 | Email/SMTP Configuration | 1-2 hours | $100 - $200 |
| 4 | AWS Account Setup | 1-2 hours | $100 - $200 |
| 5 | AWS Infrastructure Deployment | 10-12 hours | $1,000 - $1,200 |
| 6 | Code Deployment | 12-18 hours | $1,200 - $1,800 |
| 7 | Testing and Validation | 10-12 hours | $1,000 - $1,200 |
| 8 | Go-Live and Monitoring | 4-6 hours | $400 - $600 |
| **TOTAL** | | **51-69 hours** | **$5,100 - $6,900** |

**Note:** These estimates assume you have basic familiarity with AWS, Salesforce, and API integrations. Times may vary based on experience level and system complexity.

---

**Document Version:** 1.0  
**Last Updated:** January 2025  
**Prepared by:** Garrett Johnson

