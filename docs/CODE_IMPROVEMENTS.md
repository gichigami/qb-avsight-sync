# Code Improvements Analysis

This document identifies code quality improvements that do not change the overall functionality of the program.

## Critical Fixes

### 1. **File Path Bug (qb-avsight-sync.py, previously lambda_function.py lines 196, 201)**
**Issue:** Missing `/` separator in file paths
```python
# Current (BROKEN):
unpaid_invoices.to_csv('/tmpunpaid_invoices.csv', index=False)
unpaid_bills.to_csv('/tmpunpaid_bills.csv', index=False)

# Should be:
unpaid_invoices.to_csv('/tmp/unpaid_invoices.csv', index=False)
unpaid_bills.to_csv('/tmp/unpaid_bills.csv', index=False)
```
**Reason:** Files will be created in root directory instead of `/tmp`, causing permission errors in Lambda.

---

### 2. **Incorrect Return Type Annotations**
**Issue:** Type hints don't match actual return types

**qb-avsight-sync.py (previously lambda_function.py) line 64:**
```python
# Current:
def process_bills(bills) -> tuple:

# Should be:
def process_bills(bills) -> pd.DataFrame:
```
**Reason:** Function returns `pd.DataFrame`, not `tuple`. Incorrect type hints mislead developers and break static analysis.

**quickbooks_connector.py lines 115, 154:**
```python
# Current:
def get_all_invoices(self) -> pd.DataFrame:
def get_all_bills(self) -> pd.DataFrame:

# Should be:
def get_all_invoices(self) -> List[Dict]:
def get_all_bills(self) -> List[Dict]:
```
**Reason:** Functions return `List[Dict]`, not `pd.DataFrame`. Type hints should reflect actual return types.

---

## Code Quality Improvements

### 3. **Remove Large Commented-Out Code Blocks (qb-avsight-sync.py, previously lambda_function.py lines 159-179)**
**Issue:** 20+ lines of commented code clutter the file
**Reason:** Dead code reduces readability. Either delete it or move to documentation if it's needed for reference.

---

### 4. **Remove Unused Imports**
**Issue:** `io` imported but never used (utils.py line 16)
**Reason:** Unused imports add noise and can cause confusion. Remove to keep imports clean.

---

### 5. **Extract Magic Numbers to Constants**
**Issue:** Hardcoded values scattered throughout code
**Examples:**
- `batch_size = 100` (appears multiple times)
- `max_results = 100` (quickbooks_connector.py)
- `retry_count` limits
- CSV export paths

**Reason:** Magic numbers make code harder to maintain. Extract to named constants at module level:
```python
# At top of file:
SALESFORCE_BATCH_SIZE = 100
QUICKBOOKS_MAX_RESULTS = 100
RESULTS_DIRECTORY = '/tmp'
MAX_TOKEN_RETRY_ATTEMPTS = 1
```

---

### 6. **Fix Inconsistent Variable Naming (PEP 8)**
**Issue:** Mix of camelCase and snake_case for variables
**Examples:**
- `vendorDict`, `poDict`, `roDict`, `accDict`, `invcDict`, `payDict` (should be snake_case)
- `bills_update`, `bills_insert` (correct snake_case)

**Reason:** PEP 8 requires snake_case for variables. Consistent naming improves readability.

**Fix:**
```python
# Current:
vendorDict = dict(...)
poDict = dict(...)

# Should be:
vendor_dict = dict(...)
po_dict = dict(...)
```

---

### 7. **Remove Redundant Code/Comments**
**Issue:** Multiple empty lines and redundant comments
**Examples:**
- Lines 207-209: Three empty lines with comment "Extract Order number"
- Line 212-213: Commented-out code
- Line 258: Commented-out code

**Reason:** Clean code is easier to read and maintain.

---

### 8. **Improve Error Handling for CSV Exports**
**Issue:** No error handling when writing CSV files
**Current:**
```python
invoices_df.to_csv('/tmp/quickbooks_invoices.csv', index=False)
```

**Should be:**
```python
try:
    invoices_df.to_csv('/tmp/quickbooks_invoices.csv', index=False)
except Exception as e:
    print(f"⚠️ Failed to export invoices CSV: {e}")
    # Continue execution - CSV export is not critical
```

**Reason:** If disk is full or permissions are wrong, the entire sync will fail. Graceful degradation is better.

---

### 9. **Refactor Code Duplication**
**Issue:** `process_invoices()` and `process_bills()` have nearly identical logic
**Reason:** DRY principle - duplicated code is harder to maintain and more error-prone.

**Suggestion:** Extract common logic:
```python
def _extract_line_items(lines, detail_type):
    """Extract descriptions from line items"""
    items_desc = []
    if lines:
        for line in lines:
            if line.get('DetailType') == detail_type:
                if 'Description' in line:
                    items_desc.append(line['Description'])
    return items_desc

def _determine_payment_status(balance, total):
    """Determine payment status from balance"""
    return 'Paid' if balance == 0 else 'Unpaid'
```

---

### 10. **Move Import to Top Level**
**Issue:** `os` imported inside function (utils.py `get_s3_bucket_name()`)
**Current:**
```python
def get_s3_bucket_name() -> str:
    import os
    return os.environ.get('S3_BUCKET_NAME', 'qb-avsight-sync-daily-summaries')
```

**Should be:**
```python
import os  # At top of file

def get_s3_bucket_name() -> str:
    return os.environ.get('S3_BUCKET_NAME', 'qb-avsight-sync-daily-summaries')
```

**Reason:** PEP 8 requires imports at module level. Function-level imports are only for circular dependency workarounds.

---

### 11. **Remove Hardcoded Instance URL**
**Issue:** salesforce_connector.py line 30 has hardcoded URL that's already in credentials
**Current:**
```python
sf_instance = 'https://pioneer-aero.my.salesforce.com/' #Your Salesforce Instance URL
```

**Should use:**
```python
sf_instance = self.instance_url
```

**Reason:** Avoids duplication and makes code more maintainable. Instance URL is already stored in `self.instance_url`.

---

### 12. **Add Type Hints to Function Parameters**
**Issue:** Missing type hints on many functions
**Examples:**
- `process_invoices(invoices)` - should be `process_invoices(invoices: List[Dict])`
- `process_bills(bills)` - should be `process_bills(bills: List[Dict])`
- `find_order_number(text)` - should be `find_order_number(text: str) -> Optional[str]`

**Reason:** Type hints improve IDE support, catch errors early, and serve as documentation.

---

### 13. **Extract Repeated DataFrame Filtering Patterns**
**Issue:** Repeated filtering logic for paid/unpaid items
**Current pattern appears multiple times:**
```python
invoices_df[invoices_df['Payment Status'] == 'Paid']
bills_df[bills_df['Payment Status'] == 'Unpaid']
```

**Reason:** Extract to helper functions for reusability and consistency.

---

### 14. **Improve Dictionary Creation Pattern**
**Issue:** Repeated pattern for creating dictionaries from DataFrames
**Current (lines 232-240):**
```python
vendorDict = pd.concat([po[['Id','inscor__Vendor__c']], ro[['Id','inscor__Vendor__c']]])
vendorDict = dict(zip(vendorDict.Id,vendorDict.inscor__Vendor__c))
poDict = dict(zip(po.Name,po.Id))
roDict = dict(zip(ro.Name, ro.Id))
accDict = dict(zip(acc.Name, acc.Id))
```

**Reason:** Could be extracted to a helper function:
```python
def create_lookup_dict(df: pd.DataFrame, key_col: str, value_col: str) -> Dict:
    """Create a lookup dictionary from DataFrame columns"""
    return dict(zip(df[key_col], df[value_col]))
```

---

### 15. **Add Constants for Field Names**
**Issue:** String literals for field names scattered throughout
**Examples:**
- `'Payment Status'`, `'Balance Due'`, `'QBO_Bill_ID__c'`, etc.

**Reason:** Typo in field name would cause runtime error. Constants catch errors at import time.

**Suggestion:**
```python
# At top of file or in constants module:
class QBFields:
    PAYMENT_STATUS = 'Payment Status'
    BALANCE_DUE = 'Balance Due'
    QUICKBOOKS_ID = 'QuickBooks ID'
    # etc.
```

---

### 16. **Improve Function Documentation**
**Issue:** Some functions lack comprehensive docstrings
**Examples:**
- `process_invoices()` and `process_bills()` don't document parameter types
- `find_order_number()` doesn't document return type clearly

**Reason:** Better documentation improves maintainability and IDE support.

---

### 17. **Consolidate Salesforce Data Fetching**
**Issue:** Repeated pattern for fetching Salesforce data (lines 218-230)
**Current:**
```python
pay = sf.soql_to_df("SELECT FIELDS(ALL) FROM Payment__c LIMIT 1").drop(columns=["attributes"]).columns.tolist()
pay = sf.soql_to_df(f"SELECT {','.join(x for x in pay)} FROM Payment__c")
```

**Reason:** This pattern is repeated 4 times. Extract to helper method in `SalesforceConnector`:
```python
def get_all_fields(self, object_name: str) -> pd.DataFrame:
    """Get all fields for a Salesforce object"""
    fields = self.soql_to_df(f"SELECT FIELDS(ALL) FROM {object_name} LIMIT 1")
    fields = fields.drop(columns=["attributes"]).columns.tolist()
    return self.soql_to_df(f"SELECT {','.join(fields)} FROM {object_name}")
```

---

### 18. **Add Input Validation**
**Issue:** No validation that DataFrames are not empty before operations
**Examples:**
- Line 139: `invoices_df[invoices_df['Payment Status'] == 'Paid']` - no check if `invoices_df` is empty
- Line 262: `bills.merge(pay, ...)` - no check if `pay` is empty

**Reason:** Empty DataFrames can cause confusing errors. Early validation provides clearer error messages.

---

### 19. **Use f-strings Consistently**
**Issue:** Some string formatting uses older `.format()` or `%` syntax
**Reason:** f-strings are more readable and performant (Python 3.6+).

---

### 20. **Extract Long Function**
**Issue:** `main()` function is 234 lines long (lines 105-338)
**Reason:** Functions should ideally be < 50 lines. Break into smaller, focused functions:
- `fetch_and_process_qb_data()`
- `fetch_salesforce_data()`
- `prepare_bills_for_salesforce()`
- `update_salesforce_records()`
- `export_results_to_csv()`

---

## Summary

**Priority 1 (Critical Bugs):**
1. Fix file path bug (lines 196, 201)
2. Fix return type annotations

**Priority 2 (Code Quality):**
3. Remove commented code
4. Fix variable naming (PEP 8)
5. Extract magic numbers to constants
6. Add error handling for CSV exports
7. Move imports to top level

**Priority 3 (Maintainability):**
8. Refactor code duplication
9. Add type hints
10. Extract helper functions
11. Improve documentation

These improvements will make the codebase more maintainable, readable, and less error-prone without changing functionality.

