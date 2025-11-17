# Connecticut (CT) - FTP Server Timeout

**Status:** 🔴 Failing
**Date Reported:** October 23, 2025
**Category:** Infrastructure Issue
**Error Type:** `FTPError: error while retrieving ftp://ftp.cga.ct.gov/pub/data/committee.csv`
**Scraper Version:** `openstates/scrapers:latest` (as of Oct 2025)

---

## 🔴 Problem

The Connecticut scraper cannot access the state's FTP server to download committee data. The scraper crashes **before scraping any bills** because it requires this committee CSV file to start.

---

## 🔍 Error Details

**FTP URL:** `ftp://ftp.cga.ct.gov/pub/data/committee.csv`

**Error sequence:**

```
INFO scrapelib: GET - 'ftp://ftp.cga.ct.gov/pub/data/committee.csv'
(Waits 60 seconds)
WARNING scrapelib: got error while retrieving ftp://... sleeping for 10 seconds before retry
(Retry 1: waits 70 seconds)
WARNING scrapelib: got error while retrieving ftp://... sleeping for 20 seconds before retry
(Retry 2: waits 80 seconds)
WARNING scrapelib: got error while retrieving ftp://... sleeping for 40 seconds before retry
(Retry 3: fails)
socket.timeout: timed out
scrapelib.FTPError: error while retrieving ftp://ftp.cga.ct.gov/pub/data/committee.csv
```

**Total time spent:** ~4-5 minutes per attempt × 3 attempts = **~15 minutes** before giving up

---

## 💥 Impact

### On Scraping:

- ❌ Scraper crashes immediately (before scraping bills)
- ❌ All 3 Docker retry attempts fail the same way
- ❌ Saves only 4 JSON files (jurisdiction + organizations)
- ❌ **0 bills scraped**

### On Output:

```
Found 4 JSON files in _working/_data/ct
```

**What gets saved:**

- ✅ `jurisdiction_ocd-jurisdiction-country:us-state:ct-government.json`
- ✅ 3 organization files (Legislature, Senate, House)
- ❌ No bill files

### On Workflow:

- Continues with nightly artifact fallback
- If no nightly exists, formatter fails with "Not Found"

---

## 🔎 Root Cause

**Infrastructure/Network Issue:**

The Connecticut legislature uses an **FTP server** to host committee data. The scraper needs this file before it can scrape bills, but:

1. **FTP server not responding** to GitHub Actions runners
2. **Possible causes:**
   - FTP server is down/offline
   - Firewall blocking GitHub Actions IP addresses (`20.161.60.102`)
   - FTP port 21 blocked on GitHub infrastructure
   - Server overloaded or rate-limiting

**This is NOT a scraper code issue** - it's a network/infrastructure problem.

---

## 🧪 Comparison to Working Scrapers

### Working (New Mexico - similar FTP usage):

```
INFO scrapelib: GET - 'ftp://www.nmlegis.gov/other/LegInfo25S1.zip'
(Downloads successfully within seconds)
INFO openstates: save bill SB1 in 2025S1  ✅
```

### Broken (Connecticut):

```
INFO scrapelib: GET - 'ftp://ftp.cga.ct.gov/pub/data/committee.csv'
(Timeout after 60+ seconds per retry)
scrapelib.FTPError: error while retrieving  ❌
(Crashes before any bills)
```

**NM's FTP works, CT's doesn't** → Server-specific issue, not FTP protocol issue.

---

## 🛠️ Workaround

**Short-term:**

- ⚠️ Skip Connecticut - scraper cannot function without committee data
- Use nightly artifact if available: `use-scrape-cache: true`
- Monitor CT's FTP server: `ftp://ftp.cga.ct.gov/`

**Debugging:**
Try accessing the FTP server manually:

```bash
curl ftp://ftp.cga.ct.gov/pub/data/committee.csv
# or
ftp ftp.cga.ct.gov
```

**Long-term:**

- Report to OpenStates (they may have contacts at CT legislature)
- Check if CT provides alternative data sources (API, HTTPS downloads)
- Monitor for server recovery

---

## 📋 Upstream Information

- **Repository:** https://github.com/openstates/openstates-scrapers
- **Scraper File:** `scrapers/ct/bills.py`
- **Line:** 239 (`scrape_committee_names()`)
- **Data Source:** `ftp://ftp.cga.ct.gov/pub/data/committee.csv`
- **Issue Type:** Infrastructure/network (not code)

---

## 🎯 Detection

**How to identify this quickly:**

1. Watch for FTP GET message
2. If it hangs for 60+ seconds → FTP timeout
3. Don't wait for all 3 retries - cancel after first failure
4. Error is immediate (within first minute of scraping)

**Red flags:**

- `scrapelib.FTPError` in logs
- Long waits between retry warnings (60+ seconds)
- Only 4 JSON files created (jurisdiction/orgs)
- Crashes before any `save bill` messages

---

**Last Updated:** October 23, 2025
**Next Steps:** Monitor CT FTP server availability, consider reporting to OpenStates
