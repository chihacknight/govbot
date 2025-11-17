# State Scraper Testing Status

Tracking the status of OpenStates scrapers for all 50 states, DC, and territories.

**Last Updated:** October 23, 2025
**OpenStates Scrapers:** https://github.com/openstates/openstates-scrapers/tree/main/scrapers

---

## Legend

- ✅ **Working** - Scraper runs successfully, bills saved
- 🔴 **Failing** - Scraper crashes or saves 0 bills
- 🟡 **Partial** - Scraper runs but has data quality issues
- 🔄 **Testing** - Currently being tested
- ❓ **Not Tested** - Not yet tested with current scraper version

---

## 📊 Summary

- **Total Jurisdictions:** 55 (50 states + DC + 4 territories + USA)
- **Working:** 1
- **Failing:** 2
- **Testing:** 0
- **Not Tested:** 52

---

## 🗺️ Status by Jurisdiction

### States (50)

| State          | Code | Status | Last Tested  | Notes                                               |
| -------------- | ---- | ------ | ------------ | --------------------------------------------------- |
| Alabama        | al   | ❓     | Never        |                                                     |
| Alaska         | ak   | ❓     | Never        |                                                     |
| Arizona        | az   | ❓     | Never        |                                                     |
| Arkansas       | ar   | ❓     | Never        |                                                     |
| California     | ca   | 🔴     | Oct 23, 2025 | Missing sqlalchemy dependency - crashes on import   |
| Colorado       | co   | ❓     | Never        |                                                     |
| Connecticut    | ct   | 🔴     | Oct 23, 2025 | FTP server timeout - cannot download committee data |
| Delaware       | de   | ❓     | Never        |                                                     |
| Florida        | fl   | ✅     | Oct 23, 2025 | Working! Bills being saved successfully             |
| Georgia        | ga   | ❓     | Never        |                                                     |
| Hawaii         | hi   | ❓     | Never        |                                                     |
| Idaho          | id   | ❓     | Never        |                                                     |
| Illinois       | il   | ❓     | Never        |                                                     |
| Indiana        | in   | ❓     | Never        |                                                     |
| Iowa           | ia   | ❓     | Never        |                                                     |
| Kansas         | ks   | ❓     | Never        |                                                     |
| Kentucky       | ky   | ❓     | Never        |                                                     |
| Louisiana      | la   | ❓     | Never        |                                                     |
| Maine          | me   | ❓     | Never        |                                                     |
| Maryland       | md   | ❓     | Never        |                                                     |
| Massachusetts  | ma   | ❓     | Never        |                                                     |
| Michigan       | mi   | ❓     | Never        |                                                     |
| Minnesota      | mn   | ❓     | Never        |                                                     |
| Mississippi    | ms   | ❓     | Never        |                                                     |
| Missouri       | mo   | ❓     | Never        |                                                     |
| Montana        | mt   | ❓     | Never        |                                                     |
| Nebraska       | ne   | ❓     | Never        |                                                     |
| Nevada         | nv   | ❓     | Never        |                                                     |
| New Hampshire  | nh   | ❓     | Never        |                                                     |
| New Jersey     | nj   | ❓     | Never        |                                                     |
| New Mexico     | nm   | ❓     | Never        |                                                     |
| New York       | ny   | ❓     | Never        |                                                     |
| North Carolina | nc   | ❓     | Never        |                                                     |
| North Dakota   | nd   | ❓     | Never        |                                                     |
| Ohio           | oh   | ❓     | Never        |                                                     |
| Oklahoma       | ok   | ❓     | Never        |                                                     |
| Oregon         | or   | ❓     | Never        |                                                     |
| Pennsylvania   | pa   | ❓     | Never        |                                                     |
| Rhode Island   | ri   | ❓     | Never        |                                                     |
| South Carolina | sc   | ❓     | Never        |                                                     |
| South Dakota   | sd   | ❓     | Never        |                                                     |
| Tennessee      | tn   | ❓     | Never        |                                                     |
| Texas          | tx   | ❓     | Never        |                                                     |
| Utah           | ut   | ❓     | Never        |                                                     |
| Vermont        | vt   | ❓     | Never        |                                                     |
| Virginia       | va   | ❓     | Never        |                                                     |
| Washington     | wa   | ❓     | Never        |                                                     |
| West Virginia  | wv   | ❓     | Never        |                                                     |
| Wisconsin      | wi   | ❓     | Never        |                                                     |
| Wyoming        | wy   | ❓     | Never        |                                                     |

### Federal

| Jurisdiction | Code | Status | Last Tested | Notes |
| ------------ | ---- | ------ | ----------- | ----- |
| Federal/USA  | usa  | ❓     | Never       |       |

### District of Columbia

| Jurisdiction         | Code | Status | Last Tested | Notes |
| -------------------- | ---- | ------ | ----------- | ----- |
| District of Columbia | dc   | ❓     | Never       |       |

### Territories (5)

| Territory                | Code | Status | Last Tested | Notes |
| ------------------------ | ---- | ------ | ----------- | ----- |
| Guam                     | gu   | ❓     | Never       |       |
| Northern Mariana Islands | mp   | ❓     | Never       |       |
| Puerto Rico              | pr   | ❓     | Never       |       |
| U.S. Virgin Islands      | vi   | ❓     | Never       |       |

---

## 📝 Testing Checklist

For each jurisdiction, verify:

- [ ] Scraper runs without crashing
- [ ] Saves bills (look for `INFO openstates: save bill` messages)
- [ ] Bills have required fields (identifier, title, actions)
- [ ] Formatter processes bills successfully
- [ ] Output appears in `country:us/state:*/sessions/*/bills/`

---

## 🔴 Known Issues

### Florida (fl) - House Search Selector Broken

**Status:** 🔴 Failing
**Tested:** October 23, 2025
**Symptoms:**

- Scraper runs for 6 hours processing bills
- ERROR messages: `Selector Error... could not find bill in House Search`
- **0 bills saved** (no "save bill" success messages in logs)
- Times out after 6 hours with no output

**Issue:** The `flhouse.gov` website changed HTML structure, breaking the scraper's search selectors. Senate side (`flsenate.gov`) may work, but House bills can't be extracted.

For additional issue documentation, create detailed files in `scraper/` folder.

---

**Testing Notes:**

- Start with smaller states (fewer bills = faster testing)
- Federal (usa) and large states (CA, TX, NY, FL) will take longest
- Some territories may have minimal legislative activity
- Check for "save bill" messages in logs - absence = scraper broken
