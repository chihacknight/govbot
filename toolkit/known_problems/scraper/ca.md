# California (CA) - Missing sqlalchemy Dependency

**Status:** 🔴 Failing
**Date Reported:** October 23, 2025
**Category:** Docker Image Issue (Upstream)
**Error Type:** `ModuleNotFoundError: No module named 'sqlalchemy'`
**Scraper Version:** `openstates/scrapers:latest` (as of Oct 2025)

---

## 🔴 Problem

The California scraper fails to even **import** because the Docker image is missing the `sqlalchemy` Python dependency. The scraper crashes immediately on startup before scraping any data.

---

## 🔍 Error Details

**Import error:**

```python
File "/opt/openstates/openstates/scrapers/ca/__init__.py", line 4, in <module>
    from .bills import CABillScraper
File "/opt/openstates/openstates/scrapers/ca/bills.py", line 9, in <module>
    from sqlalchemy.orm import sessionmaker
ModuleNotFoundError: No module named 'sqlalchemy'
```

**Traceback shows:**

- Scraper tries to import `CABillScraper`
- `bills.py` requires `sqlalchemy.orm`
- **sqlalchemy is not installed in Docker image**
- Scraper crashes before doing anything

---

## 💥 Impact

### On Scraping:

- ❌ Scraper **cannot even start** (import error)
- ❌ All 3 Docker retry attempts fail identically
- ❌ Crashes in first second of execution
- ❌ **0 files saved** (not even jurisdiction/organization metadata)

### On Output:

```
Found 0 JSON files in _working/_data/ca
```

**Complete failure** - no usable data at all.

### On Workflow:

- Tries to use nightly artifact fallback
- If no nightly exists, job fails completely
- Cannot build California data pipeline

---

## 🔬 Why This is Different

### Compared to Other Failures:

| Issue Type      | Florida                | Connecticut     | California                |
| --------------- | ---------------------- | --------------- | ------------------------- |
| **Error Stage** | During bill extraction | FTP download    | **Import/startup**        |
| **Error Type**  | Selector broken        | Network timeout | **Missing dependency**    |
| **Files Saved** | 4 (jurisdiction/orgs)  | 4 (same)        | **0 (crashes too early)** |
| **Category**    | Scraper code           | Infrastructure  | **Docker image**          |

**CA is the worst** - it doesn't even get past imports!

---

## 🔎 Root Cause

**Docker Image Packaging Issue:**

The California scraper code requires `sqlalchemy`, but the `openstates/scrapers:latest` Docker image **doesn't include it** in the installed dependencies.

**Why only California?**

- Most scrapers don't use sqlalchemy
- CA scraper has unique requirements
- Dependencies not properly declared or Docker build incomplete
- This is an **upstream packaging bug**

**Code location:**

```python
# scrapers/ca/bills.py, line 9
from sqlalchemy.orm import sessionmaker  # ← Dependency missing from Docker!
```

---

## 🛠️ Workaround

**Short-term:**

- ⚠️ Skip California - scraper is completely broken
- No fallback possible (can't even start)
- Wait for OpenStates to fix Docker image

**For OpenStates maintainers:**
Fix by adding to Docker image dependencies:

```dockerfile
# In Dockerfile or requirements
sqlalchemy>=1.4.0  # Or whatever version CA scraper needs
```

---

## 📋 Upstream Information

- **Repository:** https://github.com/openstates/openstates-scrapers
- **Issue:** Docker image missing `sqlalchemy` dependency
- **Scraper File:** `scrapers/ca/bills.py` (requires sqlalchemy)
- **Fix Location:** Dockerfile or pyproject.toml dependencies
- **Report To:** https://github.com/openstates/openstates-scrapers/issues

**This should be reported as a bug!** It's a clear packaging issue.

---

## 🎯 Detection

**How to identify immediately:**

1. Scraper crashes in first second
2. Error: `ModuleNotFoundError: No module named 'sqlalchemy'`
3. **0 JSON files created** (not even metadata)
4. All 3 retry attempts fail identically

**Instant failure** - no need to wait or monitor logs.

---

**Last Updated:** October 23, 2025
**Next Steps:** Report to OpenStates as Docker image packaging bug
