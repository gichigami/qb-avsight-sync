# Contact Form Backend Deployment Guide

This guide walks you through deploying the contact form backend for the AirBridgeQB website. The backend consists of an AWS Lambda function that handles form submissions and sends emails via SMTP.

## Architecture

```
Website (GitHub Pages) → API Gateway → Lambda Function → SMTP Email
```

## Prerequisites

- AWS account with appropriate permissions
- AWS CLI configured (optional, but helpful)
- Existing SMTP credentials stored in AWS Secrets Manager at `smtp/credentials`
- Python 3.9+ (for local testing, if needed)

## Step 1: Prepare Lambda Deployment Package

### 1.1 Install Dependencies

Navigate to the contact form function directory:

```bash
cd deploy_packages/contact_form_function
```

Create a virtual environment and install dependencies:

```bash
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 1.2 Create Deployment Package

The deployment package should include:
- `lambda_function.py`
- `utils.py`
- `boto3` and its dependencies

**Option A: Create zip file manually (recommended for small packages)**

```bash
# Make sure you're in the contact_form_function directory
zip -r contact_form_function.zip lambda_function.py utils.py
cd venv/lib/python3.*/site-packages
zip -r ../../../../contact_form_function.zip boto3 botocore* s3transfer* urllib3* dateutil* jmespath* python_dateutil*
cd ../../../../..
```

**Option B: Use pip install --target**

```bash
# Create a clean package directory
mkdir -p package
pip install -r requirements.txt -t package/
cp lambda_function.py utils.py package/
cd package
zip -r ../contact_form_function.zip .
cd ..
```

### 1.3 Verify Package Size

Lambda deployment packages must be:
- Under 50 MB (unzipped) for direct upload
- Under 250 MB (unzipped) if using S3

If your package is too large, you may need to use Lambda Layers for dependencies.

## Step 2: Create Lambda Function

### 2.1 Create Function in AWS Console

1. Go to AWS Lambda Console: https://console.aws.amazon.com/lambda/
2. Click **Create function**
3. Choose **Author from scratch**
4. Configure:
   - **Function name**: `airbridge-contact-form` (or your preferred name)
   - **Runtime**: Python 3.9, 3.10, or 3.11 (choose based on your Python version)
   - **Architecture**: x86_64
   - **Execution role**: Create a new role with basic Lambda permissions (we'll update permissions next)

### 2.2 Upload Deployment Package

1. In the function code section, click **Upload from** → **.zip file**
2. Select your `contact_form_function.zip` file
3. Set the **Handler** to: `lambda_function.lambda_handler`
4. Click **Save**

### 2.3 Configure Function Settings

1. Go to **Configuration** → **General configuration**
2. Click **Edit**
3. Set:
   - **Timeout**: 30 seconds (email sending may take a few seconds)
   - **Memory**: 128 MB (should be sufficient)
4. Click **Save**

### 2.4 Set Up IAM Permissions

The Lambda function needs permission to read SMTP credentials from Secrets Manager.

1. Go to **Configuration** → **Permissions**
2. Click on the **Execution role** name (opens IAM console)
3. Click **Add permissions** → **Create inline policy**
4. Switch to **JSON** tab and paste:

```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "secretsmanager:GetSecretValue"
            ],
            "Resource": "arn:aws:secretsmanager:*:*:secret:smtp/credentials-*"
        }
    ]
}
```

5. Click **Review policy**
6. Name it: `SecretsManagerReadSMTP`
7. Click **Create policy**

## Step 3: Create API Gateway

### 3.1 Create REST API

1. Go to API Gateway Console: https://console.aws.amazon.com/apigateway/
2. Click **Create API**
3. Choose **REST API** → **Build**
4. Configure:
   - **Protocol**: REST
   - **Create new API**: New API
   - **API name**: `airbridge-contact-api` (or your preferred name)
   - **Endpoint Type**: Regional (recommended for cost)
5. Click **Create API**

### 3.2 Create POST Method

1. In the API, click **Actions** → **Create Resource**
2. Name: `contact`
3. Click **Create Resource**
4. With `/contact` selected, click **Actions** → **Create Method** → **POST**
5. Configure:
   - **Integration type**: Lambda Function
   - **Use Lambda Proxy integration**: ✅ Check this box
   - **Lambda Function**: Select your function name (e.g., `airbridge-contact-form`)
   - **Lambda Region**: Select your region
6. Click **Save**
7. Click **OK** when prompted to give API Gateway permission to invoke the Lambda

### 3.3 Configure CORS

1. With `/contact` selected, click **Actions** → **Enable CORS**
2. Configure CORS settings:
   - **Access-Control-Allow-Origin**: `https://gichigami.github.io`
   - **Access-Control-Allow-Headers**: `Content-Type`
   - **Access-Control-Allow-Methods**: `POST, OPTIONS`
   - Leave other fields as default
3. Click **Enable CORS and replace existing CORS headers**

### 3.4 Create OPTIONS Method (for CORS preflight)

1. With `/contact` selected, click **Actions** → **Create Method** → **OPTIONS**
2. Configure:
   - **Integration type**: Mock
3. Click **Save**
4. Under **Method Response**, configure:
   - **200** status code
   - **Headers**: `Access-Control-Allow-Origin`, `Access-Control-Allow-Headers`, `Access-Control-Allow-Methods`
5. Under **Integration Response**, configure:
   - **200** status code
   - **Header Mappings**:
     - `Access-Control-Allow-Origin`: `'https://gichigami.github.io'`
     - `Access-Control-Allow-Headers`: `'Content-Type'`
     - `Access-Control-Allow-Methods`: `'POST, OPTIONS'`
6. Click **Save**

### 3.5 Deploy API

1. Click **Actions** → **Deploy API**
2. Configure:
   - **Deployment stage**: `prod` (or create new stage)
   - **Stage description**: `Production deployment`
3. Click **Deploy**
4. **Copy the Invoke URL** - you'll need this for the frontend configuration
   - Format: `https://xxxxxxxxxx.execute-api.us-east-1.amazonaws.com/prod`
   - Your endpoint will be: `https://xxxxxxxxxx.execute-api.us-east-1.amazonaws.com/prod/contact`

## Step 4: Configure Frontend

### 4.1 Update API Gateway URL

1. Open `website/js/script.js`
2. Find the line:
   ```javascript
   const CONTACT_FORM_API_URL = 'YOUR_API_GATEWAY_URL_HERE/contact';
   ```
3. Replace `YOUR_API_GATEWAY_URL_HERE` with your actual API Gateway invoke URL
   - Example: `const CONTACT_FORM_API_URL = 'https://xxxxxxxxxx.execute-api.us-east-1.amazonaws.com/prod/contact';`

### 4.2 Test Locally (Optional)

1. Open `website/index.html` in a browser
2. Fill out the contact form
3. Submit and check browser console for any errors
4. Verify the request is sent to the correct endpoint

### 4.3 Commit and Push

```bash
cd website
git add js/script.js
git commit -m "Configure contact form API endpoint"
git push origin main
```

## Step 5: Testing

### 5.1 Test from Website

1. Go to your deployed website: https://gichigami.github.io/airbridge-website/
2. Navigate to the Contact section
3. Fill out and submit the form
4. Verify success message appears
5. Check email inbox at `gjohnson@pioneer-aero.com` for the submission

### 5.2 Test API Directly (Optional)

You can test the API directly using curl:

```bash
curl -X POST https://YOUR_API_GATEWAY_URL/prod/contact \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Test User",
    "company": "Test Company",
    "email": "test@example.com",
    "phone": "555-1234",
    "message": "This is a test message from the contact form."
  }'
```

### 5.3 Check CloudWatch Logs

If something goes wrong:

1. Go to AWS CloudWatch Console: https://console.aws.amazon.com/cloudwatch/
2. Go to **Log groups**
3. Find `/aws/lambda/airbridge-contact-form` (or your function name)
4. Check recent log streams for errors

## Troubleshooting

### Issue: "Secret smtp/credentials not found"

**Solution**: Ensure the SMTP credentials secret exists in Secrets Manager:
1. Go to Secrets Manager: https://console.aws.amazon.com/secretsmanager/
2. Verify `smtp/credentials` exists
3. Check the Lambda execution role has permission to read it

### Issue: CORS errors in browser

**Solution**: 
1. Verify CORS is enabled on the API Gateway resource
2. Check that the `Access-Control-Allow-Origin` header includes your website domain
3. Ensure OPTIONS method is configured correctly

### Issue: "Internal server error" or timeout

**Solution**:
1. Check CloudWatch logs for detailed error messages
2. Verify SMTP credentials are correct in Secrets Manager
3. Test SMTP connection independently
4. Increase Lambda timeout if needed

### Issue: Email not received

**Solution**:
1. Check CloudWatch logs to see if email was sent
2. Verify SMTP credentials in Secrets Manager
3. Check spam/junk folder
4. Verify recipient email address is correct in `lambda_function.py`

## Cost Estimation

- **Lambda**: Free tier covers 1M requests/month, then $0.20 per 1M requests
- **API Gateway**: Free tier covers 1M requests/month for first year, then $3.50 per 1M requests
- **Secrets Manager**: ~$0.40/month per secret (reuses existing SMTP secret)
- **CloudWatch Logs**: Free tier covers 5GB ingestion/month, then $0.50 per GB

**Estimated monthly cost**: $0-1 (within free tiers) or ~$0.40/month for Secrets Manager access

## Security Considerations

1. **Rate Limiting**: Consider adding rate limiting to prevent abuse (can be done via API Gateway throttling)
2. **Input Validation**: The Lambda function validates all inputs, but you may want to add additional checks
3. **Secret Rotation**: Consider implementing secret rotation for SMTP credentials
4. **Monitoring**: Set up CloudWatch alarms for Lambda errors

## Maintenance

- Monitor CloudWatch logs regularly
- Check Lambda function metrics for errors or performance issues
- Update dependencies periodically (`pip list --outdated`)
- Review and update IAM permissions as needed

## Alternative: Third-Party Services

If you prefer a simpler setup without AWS infrastructure, consider:

1. **Formspree** (easiest):
   - Sign up at https://formspree.io
   - Get form endpoint URL
   - Update form `action` attribute in `index.html`
   - No backend code needed

2. **EmailJS**:
   - Sign up at https://www.emailjs.com
   - Configure SMTP service
   - Add EmailJS SDK to website
   - Update JavaScript to use EmailJS API
   - Sends emails directly from frontend

## Support

For issues or questions:
- Check CloudWatch logs first
- Review AWS Lambda and API Gateway documentation
- Contact: gjohnson@pioneer-aero.com

