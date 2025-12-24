# AirBridgeQB Marketing Website

A professional single-page marketing website for AirBridgeQB - an automated synchronization solution between QuickBooks Online and Salesforce. Perfect for any Salesforce environment requiring AR/AP synchronization, including AvSight and custom implementations.

## Overview

This is a static website built with HTML, CSS, and JavaScript. It features:

- Responsive design (mobile-first approach)
- Modern, professional styling with gradient accents
- Smooth scrolling navigation
- Contact form with client-side validation
- Fully accessible markup
- SEO-friendly structure

## File Structure

```
website/
├── index.html          # Main HTML file with all sections
├── css/
│   └── styles.css      # All styling (responsive, modern design)
├── js/
│   └── script.js       # Smooth scrolling, form validation, interactions
└── README.md           # This file
```

## Deployment

### Option 1: Static Hosting (Recommended)

The website can be deployed to any static hosting service:

#### GitHub Pages
1. Create a new repository on GitHub
2. Upload all files from the `website/` directory
3. Go to repository Settings → Pages
4. Select the branch and folder (usually `main` and `/root`)
5. Your site will be available at `https://username.github.io/repository-name`

#### Netlify
1. Sign up at [netlify.com](https://www.netlify.com)
2. Drag and drop the `website` folder to Netlify's deploy area
3. Your site will be automatically deployed with a free `.netlify.app` domain
4. Optionally configure a custom domain

#### Vercel
1. Sign up at [vercel.com](https://www.vercel.com)
2. Import your project (if using Git) or upload the folder
3. Deploy with zero configuration
4. Your site will be available instantly

#### AWS S3 + CloudFront
1. Create an S3 bucket
2. Upload all files from the `website/` directory
3. Enable static website hosting in bucket properties
4. Configure CloudFront distribution for better performance (optional)
5. Set bucket policy for public read access

#### AWS Amplify
1. Connect your repository or upload files
2. Amplify will automatically detect the static site
3. Configure build settings (usually no build step needed)
4. Deploy and access via provided URL

### Option 2: Traditional Web Server

Upload all files to any web server via FTP/SFTP:

1. Upload `index.html` to the root directory (or subdirectory)
2. Ensure `css/` and `js/` directories maintain their structure
3. Set proper file permissions (644 for files, 755 for directories)
4. Access via your domain

## Contact Form Configuration

The contact form currently includes client-side validation only. To enable form submission, you'll need to configure one of the following:

### Option 1: Backend API Endpoint
1. Create a backend API endpoint to handle form submissions
2. Update the form submission handler in `js/script.js`
3. Add an AJAX request to send form data to your API

### Option 2: Third-Party Service
1. Use services like:
   - Formspree
   - EmailJS
   - Netlify Forms (if deploying on Netlify)
   - AWS SES (for serverless email)
2. Follow the service's integration instructions
3. Update the form action or JavaScript accordingly

### Option 3: Mailto Fallback (Temporary)
For a simple temporary solution, you can uncomment the mailto link in `js/script.js`:

```javascript
// Uncomment in the showSuccessMessage function:
const mailtoLink = `mailto:gjohnson@pioneer-aero.com?subject=AirBridgeQB Inquiry from ${encodeURIComponent(name)}&body=${encodeURIComponent(message)}`;
window.location.href = mailtoLink;
```

## Customization

### Colors
Edit CSS variables in `css/styles.css`:

```css
:root {
    --primary-color: #2563eb;
    --secondary-color: #06b6d4;
    /* ... other variables ... */
}
```

### Content
Edit `index.html` to update:
- Company information
- Feature descriptions
- Contact information
- Email addresses

### Contact Information
Update the footer section in `index.html` and the contact email address in `js/script.js`.

## Browser Support

- Chrome (latest)
- Firefox (latest)
- Safari (latest)
- Edge (latest)
- Mobile browsers (iOS Safari, Chrome Mobile)

## Performance

The website is optimized for performance:
- Minimal dependencies (no external libraries)
- System fonts for fast loading
- Optimized CSS and JavaScript
- Responsive images (if added)

## SEO

The website includes:
- Semantic HTML5 markup
- Meta description and keywords
- Proper heading hierarchy
- Alt text ready for images (add images as needed)

## Maintenance

To update content:
1. Edit the appropriate section in `index.html`
2. Update styles in `css/styles.css` if needed
3. Test changes locally before deploying
4. Deploy updated files to your hosting service

## Support

For questions or issues with the website, contact:
- Email: gjohnson@pioneer-aero.com

## License

© 2025 AirBridgeQB. All rights reserved.

