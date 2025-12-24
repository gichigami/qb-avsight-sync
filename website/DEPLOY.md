# Deploy AirBridgeQB Website to GitHub Pages

## Quick Setup Instructions

Your website files are ready and committed to git. Follow these steps to deploy:

### Step 1: Create GitHub Repository

1. Go to [github.com](https://github.com) and sign in
2. Click the "+" icon in the top right → "New repository"
3. Repository name: `airbridge-website` (or any name you prefer)
4. Description: "AirBridgeQB - QuickBooks & Salesforce Integration Website"
5. Set to **Public** (required for free GitHub Pages)
6. **DO NOT** initialize with README, .gitignore, or license (we already have files)
7. Click "Create repository"

### Step 2: Connect and Push

After creating the repository, GitHub will show you commands. Use these:

```bash
cd /Users/garrettjohnson/Desktop/Development/qb-avsight-sync2/website
git remote add origin https://github.com/YOUR_USERNAME/airbridge-website.git
git branch -M main
git push -u origin main
```

Replace `YOUR_USERNAME` with your actual GitHub username.

### Step 3: Enable GitHub Pages

1. Go to your repository on GitHub
2. Click **Settings** (top menu)
3. Scroll down to **Pages** (left sidebar)
4. Under "Source", select:
   - Branch: `main`
   - Folder: `/ (root)`
5. Click **Save**

### Step 4: Access Your Website

Your website will be live at:
- `https://YOUR_USERNAME.github.io/airbridge-website/`

It may take 1-2 minutes to become available after enabling Pages.

## Updating the Website

To update the website after making changes:

```bash
cd /Users/garrettjohnson/Desktop/Development/qb-avsight-sync2/website
git add .
git commit -m "Update website content"
git push
```

Changes will be live within 1-2 minutes.

## Custom Domain (Optional)

To use a custom domain (e.g., `airbridge.com`):

1. In GitHub Pages settings, add your custom domain
2. Configure DNS records with your domain provider:
   - Type: `CNAME`
   - Name: `www` (or `@` for root domain)
   - Value: `YOUR_USERNAME.github.io`
3. GitHub will provide SSL certificate automatically

## Troubleshooting

- **Site not loading?** Wait 2-3 minutes after enabling Pages
- **404 error?** Make sure `index.html` is in the root of the repository
- **Styling broken?** Check that `css/` and `js/` folders are included in the repo

