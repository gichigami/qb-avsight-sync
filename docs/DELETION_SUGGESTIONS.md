# Files Suggested for Deletion

This document lists files and directories that could be safely deleted if you want to further clean up the codebase.

## Already Moved to Archive

The following files have been moved to `archive/`:
- Test scripts: `test_local.py`, `test_email_with_dummy_data.py`
- Helper scripts: `authenticate_quickbooks.py`, `set_test_timestamp.py`, `set_log_retention.sh`, `setup_eventbridge.sh`
- Backup files: `utils.py.bak`
- Credential files: `qb_credentials.json` (contains sensitive data, should be deleted after uploading to AWS Secrets Manager)
- Old zip files: All deployment zip files

## Suggested for Deletion

### 1. deploy_packages/ Directory
**Status**: Keep for now, but consider archiving when not actively deploying

The `deploy_packages/` directory contains deployment packages that are regenerated during deployment. These could be archived if you're not actively deploying, or deleted if you prefer to regenerate them from source when needed.

**Current contents**:
- `contact_form_function/` - Separate Lambda function (website contact form)
- `email_function/` - Deployment package for end-of-day email
- `full_sync_function/` - Deployment package for full sync
- `main_function/` - Deployment package for main sync

**Note**: The deployment packages contain old copies of `lambda_function.py` that should be updated to `qb-avsight-sync.py` when you next deploy. The deployment documentation in `docs/AWS_DEPLOYMENT_GUIDE.md` and `docs/IMPLEMENTATION_GUIDE.md` has been updated to reference the new filename.

### 2. venv/ Directory
**Status**: Keep for local development

The `venv/` directory is the Python virtual environment. Keep it for local development, but it should be in `.gitignore` (not committed to version control).

### 3. website/ Directory
**Status**: Keep if it's part of the project, otherwise consider archiving

The `website/` directory appears to be a separate project (contact form Lambda function). If it's not directly related to the QB-AvSight sync, consider moving it to `archive/` or a separate repository.

### 4. Duplicate Directories (Already Cleaned)
The following duplicate directories have been removed:
- `venv/bin 2/`
- `venv/lib 2/`
- `venv/pyvenv 2.cfg`
- `deploy_packages/email_function 2/`
- `deploy_packages/main_function 2/`
- `deploy_packages/main_function 3/`

## Core Files to Keep

These files are essential for running `qb-avsight-sync.py` and `end_of_day_email.py`:

- `qb-avsight-sync.py` (renamed from `lambda_function.py`)
- `end_of_day_email.py`
- `quickbooks_connector.py`
- `salesforce_connector.py`
- `utils.py`
- `config.py`
- `config.json`
- `requirements.txt`
- `README.md`

## Summary

Most unnecessary files have been moved to `archive/`. The main remaining items that could be deleted are:
1. **deploy_packages/** - If you're not actively deploying and prefer to regenerate packages when needed
2. **website/** - If it's not part of this project

The virtual environment (`venv/`) should be kept for local development but should be in `.gitignore`.

