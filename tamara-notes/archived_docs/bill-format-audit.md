# Bill Format Audit

Audits what file formats are available for bill text across all 56 `govbot-openstates-scrapers` repos.
Relevant for AI bill analysis — PDF-only bills require OCR or PDF parsing; HTML/XML/text formats are directly machine-readable.

Last updated: **2026-07-02**

---

## Summary

| Category | Count |
|----------|------:|
| Total repos | 56 |
| With bill data | 51 |
| Jurisdiction file only (scraper failed before writing bills) | 5 |
| No data directory | 0 |

**41% of active jurisdictions (21/51) provide at least one non-PDF format.**

---

## Format Breakdown

| Format | States |
|--------|--------|
| `text/html` (17) | AK, CA, DE, IL, KS, MI, MN, MS, NJ, NY, OH, PA, SC, SD, TX, WI, WV |
| `text/xml` (2) | USA (federal), UT |
| `application/msword` (2) | PA, PR |
| `application/vnd.openxmlformats-officedocument.wordprocessingml.document` (1) | SC |
| PDF only (28) | AL, CO, CT, DC, FL, GA, GU, IA, ID, IN, KY, LA, MA, MD, ME, MO, MP, NC, ND, NE, NV, OK, OR, RI, TN, VI, VT, WY |
| No version links (bills exist, links empty) (3) | MT, NH, WA |

---

## Full State Table

| State | Formats Found | Machine Readable? | Source Domain(s) |
|-------|--------------|:-----------------:|-----------------|
| AK | text/html, pdf | ✅ | www.akleg.gov |
| AL | pdf | ❌ | alison.legislature.state.al.us |
| AR | — (no bills yet) | ❌ | — |
| AZ | — (no bills yet) | ❌ | — |
| CA | text/html, pdf | ✅ | leginfo.legislature.ca.gov |
| CO | pdf | ❌ | leg.colorado.gov |
| CT | pdf | ❌ | ftp.cga.ct.gov, www.cga.ct.gov |
| DC | pdf | ❌ | lims.dccouncil.gov |
| DE | pdf, text/html | ✅ | legis.delaware.gov |
| FL | pdf | ❌ | flsenate.gov |
| GA | pdf | ❌ | webservices.legis.ga.gov, www.legis.ga.gov |
| GU | pdf | ❌ | guamlegislature.gov |
| HI | — (no bills yet) | ❌ | — |
| IA | pdf | ❌ | www.legis.iowa.gov |
| ID | pdf | ❌ | legislature.idaho.gov |
| IL | pdf, text/html | ✅ | ilga.gov |
| IN | pdf | ❌ | iga.in.gov, api.iga.in.gov |
| KS | pdf, text/html | ✅ | www.kslegislature.gov |
| KY | pdf | ❌ | apps.legislature.ky.gov |
| LA | pdf | ❌ | www.legis.la.gov |
| MA | pdf | ❌ | malegislature.gov |
| MD | pdf | ❌ | mgaleg.maryland.gov |
| ME | pdf | ❌ | legislature.maine.gov |
| MI | pdf, text/html | ✅ | legislature.mi.gov |
| MN | text/html | ✅ | www.revisor.mn.gov |
| MO | pdf | ❌ | www.senate.mo.gov |
| MP | pdf | ❌ | cnmileg.net |
| MS | text/html, pdf | ✅ | billstatus.ls.state.ms.us |
| MT | (no version links) | ❌ | bills.legmt.gov |
| NC | pdf | ❌ | www.ncleg.gov |
| ND | pdf | ❌ | ndlegis.gov |
| NE | pdf | ❌ | nebraskalegislature.gov |
| NH | (no version links) | ❌ | gc.nh.gov |
| NJ | text/html, pdf | ✅ | www.njleg.state.nj.us |
| NM | — (no bills yet) | ❌ | — |
| NV | pdf | ❌ | www.leg.state.nv.us |
| NY | text/html, pdf | ✅ | legislation.nysenate.gov, nyassembly.gov |
| OH | pdf, text/html | ✅ | www.legislature.ohio.gov |
| OK | pdf | ❌ | www.oklegislature.gov |
| OR | pdf | ❌ | olis.oregonlegislature.gov |
| PA | pdf, text/html, msword | ✅ | www.palegis.us |
| PR | msword | ✅ | sutra.oslpr.org |
| RI | pdf | ❌ | status.rilegislature.gov |
| SC | text/html, docx | ✅ | www.scstatehouse.gov |
| SD | text/html, pdf | ✅ | sdlegislature.gov |
| TN | pdf | ❌ | wapp.capitol.tn.gov |
| TX | text/html, pdf | ✅ | ftp.legis.state.tx.us, capitol.texas.gov |
| USA | text/xml, pdf | ✅ | www.govinfo.gov, congress.gov |
| UT | text/xml, pdf | ✅ | le.utah.gov |
| VA | — (no bills yet) | ❌ | — |
| VI | pdf | ❌ | billtracking.legvi.org |
| VT | pdf | ❌ | legislature.vermont.gov |
| WA | (no version links) | ❌ | app.leg.wa.gov |
| WI | pdf, text/html | ✅ | docs.legis.wisconsin.gov |
| WV | text/html | ✅ | www.wvlegislature.gov |
| WY | pdf | ❌ | wyoleg.gov |

---

## Notable Findings

- **MN and WV**: HTML only — no PDF at all. Already fully machine-readable.
- **PR**: Word doc only — no PDF or HTML. Unusual format.
- **SC**: HTML + docx, no PDF.
- **USA (federal) and UT**: XML format available — highest-fidelity structured text.
- **MT, NH, WA**: Bill records exist but `versions[].links` is empty — possible scraper gap, worth investigating.
- **AR, AZ, HI, NM, VA**: Scrapers have not produced bill files yet (jurisdiction metadata only).

---

## No-Data States (scraper not yet producing bills)

| State | Reason |
|-------|--------|
| AR | Scraper issue — active special session 2026S1 has 2 bills but produces 0 |
| AZ | WAF block — Sucuri blocks setsession.php POST; self-hosted runner pending |
| HI | WAF block — Cloudflare blocks bill pages |
| NM | FTP directory listing regex mismatch in `_init_mdb` |
| VA | Session kwarg fix in progress (PRs #58 + openstates #5723) |
