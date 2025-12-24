"""
authenticate_quickbooks.py

ONE-TIME SETUP SCRIPT - Run this LOCALLY to get QuickBooks credentials
DO NOT deploy this to Lambda

This script helps you:
1. Authenticate with QuickBooks
2. Get your OAuth tokens
3. Generate JSON for AWS Secrets Manager
"""

import requests
import json
from urllib.parse import urlencode


class QuickBooksAuthenticator:
    """Helper class for one-time QuickBooks OAuth setup"""
    
    def __init__(self, client_id, client_secret, redirect_uri, environment='production'):
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri
        self.environment = environment
        
        if environment == 'sandbox':
            self.base_url = 'https://sandbox-quickbooks.api.intuit.com'
        else:
            self.base_url = 'https://quickbooks.api.intuit.com'
            
        self.auth_base_url = 'https://appcenter.intuit.com/connect/oauth2'
        self.token_url = 'https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer'
        
        self.access_token = None
        self.refresh_token = None
        self.realm_id = None
    
    def get_authorization_url(self):
        """Generate OAuth2 authorization URL"""
        params = {
            'client_id': self.client_id,
            'scope': 'com.intuit.quickbooks.accounting',
            'redirect_uri': self.redirect_uri,
            'response_type': 'code',
            'state': 'security_token'
        }
        return f"{self.auth_base_url}?{urlencode(params)}"
    
    def complete_authorization(self, auth_code, realm_id):
        """Exchange authorization code for tokens"""
        headers = {
            'Accept': 'application/json',
            'Content-Type': 'application/x-www-form-urlencoded'
        }
        
        data = {
            'grant_type': 'authorization_code',
            'code': auth_code.strip(),
            'redirect_uri': self.redirect_uri
        }
        
        response = requests.post(
            self.token_url,
            headers=headers,
            data=data,
            auth=(self.client_id, self.client_secret)
        )
        
        if response.status_code == 200:
            tokens = response.json()
            self.access_token = tokens['access_token']
            self.refresh_token = tokens['refresh_token']
            self.realm_id = realm_id.strip()
            return True
        else:
            print(f"❌ Error: {response.text}")
            return False


def main():
    """Interactive setup wizard"""
    print("\n" + "="*70)
    print("QUICKBOOKS AUTHENTICATION SETUP FOR AWS LAMBDA")
    print("="*70)
    
    print("\n📋 Prerequisites:")
    print("1. QuickBooks Developer account (developer.intuit.com)")
    print("2. QuickBooks app created with OAuth credentials")
    print("3. AWS CLI configured with appropriate permissions")
    
    print("\n" + "="*70)
    print("STEP 1: ENTER YOUR QUICKBOOKS APP CREDENTIALS")
    print("="*70)
    print("Find these at: https://developer.intuit.com/app/developer/myapps")
    
    CLIENT_ID = input("\nClient ID: ").strip()
    CLIENT_SECRET = input("Client Secret: ").strip()
    REDIRECT_URI = 'https://developer.intuit.com/v2/OAuth2Playground/RedirectUrl'
    
    env_choice = input("\nEnvironment?\n  [1] Production (default)\n  [2] Sandbox\nChoice: ").strip()
    ENVIRONMENT = 'sandbox' if env_choice == '2' else 'production'
    
    # Initialize authenticator
    qb = QuickBooksAuthenticator(
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
        redirect_uri=REDIRECT_URI,
        environment=ENVIRONMENT
    )
    
    # Get authorization URL
    auth_url = qb.get_authorization_url()
    
    print("\n" + "="*70)
    print("STEP 2: AUTHORIZE IN YOUR BROWSER")
    print("="*70)
    print("\n📋 Copy this URL and paste it in your browser:")
    print("-"*70)
    print(auth_url)
    print("-"*70)
    
    print("\nWhat happens next:")
    print("1. You'll be redirected to QuickBooks sign-in")
    print("2. Sign in to your QuickBooks company")
    print("3. Authorize the app to access your data")
    print("4. You'll see a page with 'Authorization Code' and 'Realm ID'")
    
    input("\nPress ENTER when you've completed authorization...")
    
    # Get codes from user
    print("\n" + "="*70)
    print("STEP 3: ENTER THE CODES FROM QUICKBOOKS")
    print("="*70)
    auth_code = input("\nAuthorization Code: ").strip()
    realm_id = input("Realm ID (Company ID): ").strip()
    
    # Complete authentication
    print("\n🔄 Exchanging authorization code for tokens...")
    success = qb.complete_authorization(auth_code, realm_id)
    
    if success:
        print("\n" + "="*70)
        print("✅ AUTHENTICATION SUCCESSFUL!")
        print("="*70)
        
        # Create credentials JSON
        qb_credentials = {
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "refresh_token": qb.refresh_token,
            "access_token": qb.access_token,
            "realm_id": qb.realm_id,
            "redirect_uri": REDIRECT_URI,
            "environment": ENVIRONMENT
        }
        
        # Save to file
        filename = 'qb_credentials.json'
        with open(filename, 'w') as f:
            json.dump(qb_credentials, f, indent=2)
        
        print(f"\n✅ Credentials saved to: {filename}")
        print("\n📋 Credentials preview:")
        print("-"*70)
        print(json.dumps(qb_credentials, indent=2))
        print("-"*70)
        
        print("\n" + "="*70)
        print("STEP 4: UPLOAD TO AWS SECRETS MANAGER")
        print("="*70)
        
        print("\n📝 Run this AWS CLI command:")
        print("-"*70)
        print(f"aws secretsmanager create-secret \\")
        print(f"    --name quickbooks/credentials \\")
        print(f"    --description 'QuickBooks OAuth credentials for Lambda sync' \\")
        print(f"    --secret-string file://{filename}")
        print("-"*70)
        
        print("\n💡 Tips:")
        print(f"• Keep {filename} secure - it contains sensitive credentials")
        print("• Delete the file after uploading to Secrets Manager")
        print("• The refresh token will be automatically rotated by Lambda")
        print("• Verify the secret was created with: aws secretsmanager list-secrets")
        
        print("\n✅ Setup complete! You can now deploy your Lambda function.")
        
    else:
        print("\n❌ Authentication failed.")
        print("Please check your codes and try again.")


if __name__ == "__main__":
    main()
