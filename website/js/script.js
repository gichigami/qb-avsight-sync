// Mobile Navigation Toggle
const navToggle = document.getElementById('nav-toggle');
const navMenu = document.getElementById('nav-menu');
const navLinks = document.querySelectorAll('.nav-link');

if (navToggle) {
    navToggle.addEventListener('click', () => {
        navMenu.classList.toggle('active');
        navToggle.classList.toggle('active');
    });
}

// Close mobile menu when clicking on a link
navLinks.forEach(link => {
    link.addEventListener('click', () => {
        navMenu.classList.remove('active');
        navToggle.classList.remove('active');
    });
});

// Smooth scrolling for navigation links
document.querySelectorAll('a[href^="#"]').forEach(anchor => {
    anchor.addEventListener('click', function (e) {
        e.preventDefault();
        const target = document.querySelector(this.getAttribute('href'));
        if (target) {
            const offsetTop = target.offsetTop - 60; // Account for fixed navbar
            window.scrollTo({
                top: offsetTop,
                behavior: 'smooth'
            });
        }
    });
});

// Navbar scroll effect
const navbar = document.getElementById('navbar');
let lastScroll = 0;

window.addEventListener('scroll', () => {
    const currentScroll = window.pageYOffset;
    
    if (currentScroll > 50) {
        navbar.classList.add('scrolled');
    } else {
        navbar.classList.remove('scrolled');
    }
    
    lastScroll = currentScroll;
});

// API Gateway endpoint for contact form submissions
const CONTACT_FORM_API_URL = 'https://ov9ok9i1h8.execute-api.us-east-1.amazonaws.com/prod/contact';

// Form Validation and Submission
const contactForm = document.getElementById('contact-form');

if (contactForm) {
    contactForm.addEventListener('submit', async function(e) {
        e.preventDefault();
        
        // Clear previous error messages
        clearErrors();
        
        // Get form values
        const name = document.getElementById('name').value.trim();
        const company = document.getElementById('company').value.trim();
        const email = document.getElementById('email').value.trim();
        const phone = document.getElementById('phone').value.trim();
        const message = document.getElementById('message').value.trim();
        
        let isValid = true;
        
        // Validate name
        if (name === '') {
            showError('name-error', 'Name is required');
            isValid = false;
        }
        
        // Validate company
        if (company === '') {
            showError('company-error', 'Company is required');
            isValid = false;
        }
        
        // Validate email
        if (email === '') {
            showError('email-error', 'Email is required');
            isValid = false;
        } else if (!isValidEmail(email)) {
            showError('email-error', 'Please enter a valid email address');
            isValid = false;
        }
        
        // Validate phone (optional, but if provided, check format)
        if (phone !== '' && !isValidPhone(phone)) {
            showError('phone-error', 'Please enter a valid phone number');
            isValid = false;
        }
        
        // Validate message
        if (message === '') {
            showError('message-error', 'Message is required');
            isValid = false;
        } else if (message.length < 10) {
            showError('message-error', 'Message must be at least 10 characters long');
            isValid = false;
        }
        
        if (isValid) {
            // Submit form to API Gateway
            await submitContactForm({
                name: name,
                company: company,
                email: email,
                phone: phone,
                message: message
            });
        }
    });
}

// Submit contact form to API Gateway
async function submitContactForm(formData) {
    const submitButton = contactForm.querySelector('.btn-submit');
    const originalButtonText = submitButton ? submitButton.textContent : 'Send Message';
    
    // Disable submit button and show loading state
    if (submitButton) {
        submitButton.disabled = true;
        submitButton.textContent = 'Sending...';
    }
    
    // Hide any previous messages
    const formMessage = document.getElementById('form-message');
    if (formMessage) {
        formMessage.style.display = 'none';
    }
    
    try {
        // Check if API URL is configured
        if (CONTACT_FORM_API_URL.includes('YOUR_API_GATEWAY_URL_HERE')) {
            throw new Error('API Gateway URL not configured. Please update CONTACT_FORM_API_URL in script.js');
        }
        
        const response = await fetch(CONTACT_FORM_API_URL, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(formData)
        });
        
        const data = await response.json();
        
        if (response.ok && data.success) {
            // Success - show success message and reset form
            showSuccessMessage(data.message || 'Thank you for your interest! We will contact you soon.');
            contactForm.reset();
        } else {
            // Error response from API
            const errorMessage = data.error || 'Failed to send message. Please try again later.';
            showErrorMessage(errorMessage);
        }
    } catch (error) {
        console.error('Error submitting contact form:', error);
        
        // Handle network errors or other exceptions
        let errorMessage = 'Failed to send message. Please check your connection and try again.';
        
        if (error.message.includes('API Gateway URL not configured')) {
            errorMessage = 'Contact form is not yet configured. Please contact the site administrator.';
        } else if (error.message.includes('Failed to fetch')) {
            errorMessage = 'Network error. Please check your connection and try again.';
        }
        
        showErrorMessage(errorMessage);
    } finally {
        // Re-enable submit button
        if (submitButton) {
            submitButton.disabled = false;
            submitButton.textContent = originalButtonText;
        }
    }
}

// Email validation helper
function isValidEmail(email) {
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    return emailRegex.test(email);
}

// Phone validation helper (basic validation)
function isValidPhone(phone) {
    const phoneRegex = /^[\d\s\-\+\(\)]+$/;
    return phoneRegex.test(phone) && phone.replace(/\D/g, '').length >= 10;
}

// Show error message
function showError(errorId, message) {
    const errorElement = document.getElementById(errorId);
    if (errorElement) {
        errorElement.textContent = message;
    }
}

// Clear all error messages
function clearErrors() {
    const errorElements = document.querySelectorAll('.error-message');
    errorElements.forEach(element => {
        element.textContent = '';
    });
    
    const formMessage = document.getElementById('form-message');
    if (formMessage) {
        formMessage.classList.remove('success', 'error');
        formMessage.style.display = 'none';
    }
}

// Show success message
function showSuccessMessage(message) {
    const formMessage = document.getElementById('form-message');
    if (formMessage) {
        formMessage.textContent = message || 'Thank you for your interest! We will contact you soon.';
        formMessage.classList.remove('error');
        formMessage.classList.add('success');
        formMessage.style.display = 'block';
        
        // Scroll to success message
        formMessage.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        
        // Hide success message after 5 seconds
        setTimeout(() => {
            formMessage.style.display = 'none';
        }, 5000);
    }
}

// Show error message
function showErrorMessage(message) {
    const formMessage = document.getElementById('form-message');
    if (formMessage) {
        formMessage.textContent = message;
        formMessage.classList.remove('success');
        formMessage.classList.add('error');
        formMessage.style.display = 'block';
        
        // Scroll to error message
        formMessage.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }
}

// Pricing Calculator - Card-based selection
let selectedOptions = {
    deployment: null,
    infrastructure: null
};

function formatPrice(min, max) {
    if (min === max) {
        return `$${min.toLocaleString()}`;
    }
    return `$${min.toLocaleString()} - $${max.toLocaleString()}`;
}

function formatMonthlyPrice(min, max) {
    if (min === max) {
        return `$${min.toLocaleString()}/month`;
    }
    return `$${min.toLocaleString()}-${max.toLocaleString()}/month`;
}

function updatePricingSummary() {
    // Update deployment cost
    if (selectedOptions.deployment) {
        const card = selectedOptions.deployment;
        const min = parseInt(card.dataset.priceMin);
        const max = parseInt(card.dataset.priceMax);
        document.getElementById('deployment-cost').textContent = formatPrice(min, max);
    }

    // Update infrastructure cost
    if (selectedOptions.infrastructure) {
        const card = selectedOptions.infrastructure;
        const min = parseInt(card.dataset.priceMin);
        const max = parseInt(card.dataset.priceMax);
        document.getElementById('infrastructure-cost').textContent = `~${formatMonthlyPrice(min, max)}`;
    }

    // Calculate and update total monthly cost (infrastructure only)
    if (selectedOptions.infrastructure) {
        const infraMin = parseInt(selectedOptions.infrastructure.dataset.priceMin);
        const infraMax = parseInt(selectedOptions.infrastructure.dataset.priceMax);
        
        document.getElementById('monthly-total').textContent = `~${formatMonthlyPrice(infraMin, infraMax)}`;
    }
}

function handleCardSelection(card, category) {
    // Remove selected class from all cards in the same group
    const group = card.closest('.pricing-cards-compact');
    group.querySelectorAll('.selectable-card').forEach(c => {
        c.classList.remove('selected');
        const indicator = c.querySelector('.card-select-indicator');
        if (indicator) {
            indicator.textContent = 'Click to select';
        }
    });
    
    // Add selected class to clicked card
    card.classList.add('selected');
    
    // Update indicator text
    const indicator = card.querySelector('.card-select-indicator');
    if (indicator) {
        indicator.textContent = '✓ Selected';
    }
    
    // Update selected option
    selectedOptions[category] = card;
    
    // Update summary
    updatePricingSummary();
}

// Initialize pricing calculator on page load
document.addEventListener('DOMContentLoaded', () => {
    // Set up card click listeners
    const deploymentCards = document.querySelectorAll('.selectable-card[data-deployment]');
    const infrastructureCards = document.querySelectorAll('.selectable-card[data-infrastructure]');

    deploymentCards.forEach(card => {
        card.addEventListener('click', () => handleCardSelection(card, 'deployment'));
        card.style.cursor = 'pointer';
    });

    infrastructureCards.forEach(card => {
        card.addEventListener('click', () => handleCardSelection(card, 'infrastructure'));
        card.style.cursor = 'pointer';
    });

    // Set default selections (first card in each group)
    if (deploymentCards.length > 0) {
        handleCardSelection(deploymentCards[0], 'deployment');
    }
    if (infrastructureCards.length > 0) {
        handleCardSelection(infrastructureCards[0], 'infrastructure');
    }

    // Add animation on scroll (optional enhancement)
    const observerOptions = {
        threshold: 0.1,
        rootMargin: '0px 0px -50px 0px'
    };

    const observer = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                entry.target.style.opacity = '1';
                entry.target.style.transform = 'translateY(0)';
            }
        });
    }, observerOptions);

    // Observe elements for fade-in animation
    const animatedElements = document.querySelectorAll('.problem-card, .feature-card, .benefit-item, .customization-item');
    animatedElements.forEach(el => {
        el.style.opacity = '0';
        el.style.transform = 'translateY(20px)';
        el.style.transition = 'opacity 0.6s ease, transform 0.6s ease';
        observer.observe(el);
    });
});

