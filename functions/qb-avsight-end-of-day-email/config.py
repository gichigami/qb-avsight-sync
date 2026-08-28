"""
Configuration loader - reads non-secret parameters from config.json file
Secrets (credentials) remain in AWS Secrets Manager
"""

import json
import os
from typing import Dict, List, Optional


class Config:
    """Loads configuration from config.json file"""
    
    _config: Optional[Dict] = None
    _config_file = 'config.json'
    
    @classmethod
    def _load_config(cls) -> Dict:
        """Load configuration from .config file"""
        if cls._config is not None:
            return cls._config
        
        config_path = os.path.join(os.path.dirname(__file__), cls._config_file)
        
        if os.path.exists(config_path):
            try:
                with open(config_path, 'r') as f:
                    cls._config = json.load(f)
                return cls._config
            except Exception as e:
                print(f"⚠️ Error loading config file: {e}")
                return {}
        else:
            print(f"⚠️ Config file not found: {config_path}")
            print("Using default values")
            return {}
    
    @classmethod
    def get(cls, key: str, default):
        """Get a configuration value"""
        config = cls._load_config()
        return config.get(key, default)
    
    @classmethod
    def reload(cls):
        """Force reload of configuration file"""
        cls._config = None


# Convenience functions for common config values
def get_salesforce_batch_size() -> int:
    """Get Salesforce API batch size"""
    return Config.get('salesforce_batch_size', 100)


def get_results_directory() -> str:
    """Get directory for result CSV files"""
    return Config.get('results_directory', '/tmp')


def get_qb_redirect_uri() -> str:
    """Get QuickBooks OAuth redirect URI"""
    return Config.get('qb_redirect_uri', 
                     'https://developer.intuit.com/v2/OAuth2Playground/RedirectUrl')


def get_qb_max_results_per_page() -> int:
    """Get QuickBooks API max results per page"""
    return Config.get('qb_max_results_per_page', 100)


def get_email_recipients_run_summary() -> List[str]:
    """Get email recipients for run summary emails (sent after each sync)"""
    recipients = Config.get('email_recipients_run_summary', ['gjohnson@pioneer-aero.com'])
    if isinstance(recipients, list):
        return recipients
    elif isinstance(recipients, str):
        # Handle comma-separated string
        return [r.strip() for r in recipients.split(',') if r.strip()]
    return ['gjohnson@pioneer-aero.com']


def get_email_recipients_daily_summary() -> List[str]:
    """Get email recipients for daily summary emails (sent once per day)"""
    recipients = Config.get('email_recipients_daily_summary', ['gjohnson@pioneer-aero.com'])
    if isinstance(recipients, list):
        return recipients
    elif isinstance(recipients, str):
        # Handle comma-separated string
        return [r.strip() for r in recipients.split(',') if r.strip()]
    return ['gjohnson@pioneer-aero.com']


# Backward compatibility - defaults to run summary recipients
def get_email_recipients() -> List[str]:
    """Get email recipients list (backward compatibility - returns run summary recipients)"""
    return get_email_recipients_run_summary()


def get_s3_bucket_name() -> str:
    """Get S3 bucket name for daily summaries"""
    return Config.get('s3_bucket_name', 'qb-avsight-sync-daily-summaries')


def get_enable_incremental_sync() -> bool:
    """Get whether incremental sync is enabled"""
    return Config.get('enable_incremental_sync', False)

