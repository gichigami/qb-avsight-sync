# Cleanup & Migration Guide

## 🗑️ What to Delete

### Files to Remove Completely

1. **qb_secrets.json** - Duplicates qb_tokens.json, replaced by AWS Secrets Manager
2. **qb_tokens.json** - Local token storage, replaced by AWS Secrets Manager  
3. **Old lambda_handler.py** - Replaced by new modular structure
4. **galesforce.py** - Replaced by salesforce_connector.py

### Why These Were Problematic

#### qb_secrets.json vs qb_tokens.json
**Problem:** Two files stored overlapping credential data
- Both had `access_token`, `refresh_token`, `realm_id`
- `qb_secrets.json` also had `client_id` and `client_secret`
- `qb_tokens.json` had `saved_at` timestamp
- No clear "source of truth"

**Solution:** Single secret in AWS Secrets Manager that contains ALL credentials

#### galesforce.py
**Problem:** Hardcoded credentials in plain text
```python
username='gjohnson@pioneer-aero.com'
password='Rotterdam13*'  # 🚨 EXPOSED IN CODE
security_token='ZNm89XfS0uA3XNQdyFBsx1bP'  # 🚨 EXPOSED IN CODE
```

**Solution:** Credentials stored securely in AWS Secrets Manager, never in code

#### Old lambda_handler.py
**Problem:** 1400+ lines, everything mixed together
- QuickBooks API logic mixed with sync logic
- Email functions embedded in main file
- Hard to test individual components
- Difficult to maintain

**Solution:** Modular structure with clear separation of concerns

## ✨ New Structure Benefits

### Before (Old Structure)
```
QBsync/
├── lambda_handler.py          # 1400 lines, everything mixed
├── qb_secrets.json            # Partial credentials
├── qb_tokens.json             # Overlapping credentials  
├── galesforce.py              # Hardcoded passwords
└── authenticate_quickbooks.py # Setup script mixed with code
```

### After (New Structure)
```
QBsync/
├── qb-avsight-sync.py              # 250 lines, clean orchestration (renamed from lambda_function.py)
├── quickbooks_connector.py         # 150 lines, QB logic only
├── salesforce_connector.py         # 120 lines, SF logic only
├── utils.py                        # 200 lines, helpers only
├── requirements.txt                # Dependencies
├── authenticate_quickbooks.py      # Standalone setup tool
└── README.md                       # Comprehensive docs
```

## 📊 Key Improvements

### 1. Single Source of Truth for Credentials

**Before:**
```
qb_secrets.json    → client_id, client_secret, tokens
qb_tokens.json     → tokens only (duplicate!)
galesforce.py      → hardcoded SF credentials
(email password)   → hardcoded SMTP password
```

**After:**
```
AWS Secrets Manager:
  - quickbooks/credentials  → All QB credentials
  - salesforce/credentials  → All SF credentials
  - smtp/credentials        → All email credentials
```

### 2. Automatic Token Rotation

**Before:**
- Tokens saved to local JSON files
- Manual refresh required
- No persistence in Lambda

**After:**
- Lambda automatically refreshes tokens
- Updated tokens saved back to Secrets Manager
- No manual intervention needed

### 3. Testable Components

**Before:**
- 1400-line file, can't test pieces individually
- QuickBooks logic embedded in main function

**After:**
```python
# Each module can be tested independently
from quickbooks_connector import QuickBooksConnector
from salesforce_connector import SalesforceConnector

# Easy to mock for testing
qb = QuickBooksConnector(mock_credentials)
invoices = qb.get_invoices()
```

### 4. Clear Separation of Concerns

| File | Purpose | Lines |
|------|---------|-------|
| qb-avsight-sync.py | Orchestration & Lambda handler | ~250 |
| quickbooks_connector.py | QuickBooks API client | ~150 |
| salesforce_connector.py | Salesforce API client | ~120 |
| utils.py | Helpers (email, secrets, time) | ~200 |
| authenticate_quickbooks.py | One-time setup (not deployed) | ~150 |

## 🔄 Migration Steps

### 1. Save Your Current Credentials

First, extract credentials from your existing files:

```bash
# From qb_secrets.json (or qb_tokens.json)
CLIENT_ID="..."
CLIENT_SECRET="..."
REFRESH_TOKEN="..."
ACCESS_TOKEN="..."
REALM_ID="..."

# From galesforce.py
SF_USERNAME="gjohnson@pioneer-aero.com"
SF_PASSWORD="..."
SF_TOKEN="..."

# Your email password
SMTP_PASSWORD="..."
```

### 2. Upload to AWS Secrets Manager

```bash
# QuickBooks
aws secretsmanager create-secret \
    --name quickbooks/credentials \
    --secret-string '{
        "client_id": "'$CLIENT_ID'",
        "client_secret": "'$CLIENT_SECRET'",
        "refresh_token": "'$REFRESH_TOKEN'",
        "access_token": "'$ACCESS_TOKEN'",
        "realm_id": "'$REALM_ID'",
        "environment": "production",
        "redirect_uri": "https://developer.intuit.com/v2/OAuth2Playground/RedirectUrl"
    }'

# Salesforce  
aws secretsmanager create-secret \
    --name salesforce/credentials \
    --secret-string '{
        "username": "'$SF_USERNAME'",
        "password": "'$SF_PASSWORD'",
        "security_token": "'$SF_TOKEN'",
        "instance_url": "https://pioneer-aero.my.salesforce.com/"
    }'

# SMTP
aws secretsmanager create-secret \
    --name smtp/credentials \
    --secret-string '{
        "server": "smtp.gmail.com",
        "port": 587,
        "username": "gjohnson@pioneer-aero.com",
        "password": "'$SMTP_PASSWORD'",
        "from_email": "gjohnson@pioneer-aero.com"
    }'
```

### 3. Deploy New Code

Follow deployment steps in README.md

### 4. Test the New Setup

```bash
# Test Lambda manually
aws lambda invoke \
    --function-name qb-avsight-sync \
    --payload '{}' \
    response.json

# Check the response
cat response.json

# Check logs
aws logs tail /aws/lambda/qb-avsight-sync --follow
```

### 5. Delete Old Files

**Only after confirming the new setup works:**

```bash
# Delete local credential files
rm qb_secrets.json
rm qb_tokens.json
rm authenticate_quickbooks.py  # Keep in setup/ directory instead

# Delete old code
rm galesforce.py
# Keep old lambda_handler.py temporarily as backup
mv lambda_handler.py lambda_handler.py.backup
```

## 🔒 Security Improvements

### Before
- ❌ Credentials in plain text files
- ❌ Passwords in source code
- ❌ Tokens stored locally
- ❌ No encryption at rest
- ❌ Can't rotate without code changes

### After
- ✅ All credentials in AWS Secrets Manager
- ✅ Encrypted at rest with KMS
- ✅ Encrypted in transit
- ✅ IAM controls access
- ✅ Automatic rotation support
- ✅ Audit trail in CloudWatch
- ✅ Can rotate through console/API

## 📈 Maintenance Improvements

### Code Changes
**Before:** Edit 1400-line file, hope nothing breaks
**After:** Edit specific module, test in isolation

### Debugging
**Before:** Add print statements, redeploy entire function
**After:** Check CloudWatch Logs, clear component boundaries

### Adding Features
**Before:** Find where to add code in massive file
**After:** Clear place to add (new method in appropriate connector)

### Testing
**Before:** Can't test without full QB/SF setup
**After:** Can mock individual connectors, test logic separately

## 🎯 Summary

### Files Removed
1. ❌ qb_secrets.json (merged into AWS Secrets Manager)
2. ❌ qb_tokens.json (merged into AWS Secrets Manager)
3. ❌ galesforce.py (replaced by salesforce_connector.py)
4. ❌ Old lambda_handler.py (replaced by modular structure)

### Files Added
1. ✅ qb-avsight-sync.py (clean orchestration, renamed from lambda_function.py)
2. ✅ quickbooks_connector.py (QB API logic)
3. ✅ salesforce_connector.py (SF API logic, no hardcoded creds)
4. ✅ utils.py (helpers & AWS integration)
5. ✅ requirements.txt (explicit dependencies)
6. ✅ README.md (comprehensive documentation)

### Key Benefits
- 🔒 **Security**: No credentials in code
- 🧩 **Modularity**: Clear separation of concerns
- 🧪 **Testability**: Each component can be tested independently
- 📝 **Maintainability**: Easy to understand and modify
- 🔄 **Automation**: Token rotation handled automatically
- 📊 **Observability**: Better logging and monitoring

---

**Next Steps:**
1. Test new structure thoroughly
2. Delete old files only after confirmation
3. Update any documentation that references old structure
4. Train team on new deployment process
