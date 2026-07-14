# 🏛️ Idaho legislation file tree

Formatted, versioned legislative data for Idaho. Part of the [govbot](https://github.com/chihacknight/govbot) civic data project.

This [Chi Hack Night](https://chihacknight.com) project transforms **Open States** scraper output into a git-native, filesystem-friendly structure.

This enables a few things:

- **Free Unlimited Git Powered Legislative Data Analysis**: The raw data is as simple as a `git pull`.
- **Event Source Data Analysis**: Replay a session from our immutable event logs, making for a paper-trail.
- **Easier AI Analysis**: Plain text legislation with files/folders works with a number of different tools.
- **Decentralize Government Data**: Because We the People

## How to use

Just `git clone` this repo — everything under `country:us/` is the dataset.

---

## ⚙️ Where This Repo Fits

This is the **formatted data repo** for Idaho — one of two repos per jurisdiction:

1. **Scraper repo** (`govbot-openstates-scrapers/id-legislation`) — runs [OpenStates](https://github.com/openstates/openstates-scrapers) scrapers, produces raw scraped JSON
2. **This repo** (`id-legislation`) — reads the scraper repo's output and:
   1. 🧼 **Sanitizes** the data by removing ephemeral fields (`_id`, `scraped_at`) for deterministic output
   2. 🧠 **Formats** it into a blockchain-style, versioned structure with incremental processing
   3. 🔗 **Links** events to bills and sessions automatically
   4. 🩺 **Monitors** data quality by tracking orphaned bills
   5. 📄 **Extracts** full text from bills, amendments, and supporting documents (PDFs, XMLs, HTMLs)
   6. 📂 **Commits** the formatted output and extracted text nightly (or manually), with auto-save

This split keeps scraping (which can be blocked/rate-limited per state) independent from formatting/extraction, and keeps every jurisdiction's repo consistent, auditable, and easy to maintain.

---

## ✨ Key Features

- **🔄 Incremental Processing** - Only processes new or updated bills (no duplicate work!)
- **💾 Auto-Save Failsafe** - Commits progress during long text-extraction runs, and auto-restarts if a run times out
- **🩺 Data Quality Monitoring** - Tracks orphaned bills (votes/events without bill data)
- **🔗 Bill-Event Linking** - Automatically connects committee hearings and events to bills
- **⏱️ Timestamp Tracking** - Two-level timestamps for logs and text extraction
- **🎯 Multi-Format Text Extraction** - XML → HTML → PDF with fallbacks
- **📊 Detailed Error Logging** - Categorized errors for easy debugging

---

## 🔧 Setup & Configuration

This repo is generated and kept up to date by [`actions/pipeline-manager`](https://github.com/chihacknight/govbot/tree/main/actions/pipeline-manager) in the main `chihacknight/govbot` repo — it is not set up by hand.

To change Idaho's configuration (branch pinning, runner, enabled jobs, labels), edit its entry in [`chn-openstates-files.yml`](https://github.com/chihacknight/govbot/blob/main/actions/pipeline-manager/chn-openstates-files.yml) and re-run `apply.py` — don't hand-edit the workflow files in this repo directly, since the next `apply.py` run will overwrite them.

Current settings for Idaho:

- **State code**: `id`
- **Toolkit branch**: `main`
- **Scraper repo**: `govbot-openstates-scrapers/id-legislation`

---

## 📅 Workflow Schedule

Two independent workflows:

### `format.yml` — Format Data (12:00 PM UTC daily)

Pulls the latest scraped data from the scraper repo, sanitizes it, formats it into `country:us/state:id/sessions/...`, links events, and updates orphan tracking.

### `extract-text.yml` — Text Extraction (8:00 AM UTC daily)

Downloads and extracts full bill text into each bill's `files/` folder. Runs independently of formatting since it can take hours on large states. If a run times out or fails, a follow-up job automatically re-triggers it — incremental processing means it resumes rather than starting over.

Both can also be run manually via **Actions → [workflow] → Run workflow**.

---

## 📁 Folder Structure

```
id-legislation/
├── .github/workflows/
│   ├── format.yml            # Format scraped data + link events/orphans
│   └── extract-text.yml      # Text extraction (independent, longer-running)
├── country:us/
│   └── state:id/            # state:usa for federal, state:il for Illinois, etc.
│       └── sessions/
│           └── {session_id}/
│               ├── bills/
│               │   └── {bill_id}/
│               │       ├── metadata.json      # Bill data + _processing timestamps
│               │       ├── files/             # Extracted text & documents
│               │       │   ├── *.pdf          # Original PDFs
│               │       │   ├── *.xml          # Original XMLs
│               │       │   ├── *.html         # Original HTML
│               │       │   └── *_extracted.txt # Extracted text
│               │       └── logs/              # Action/event/vote logs
│               └── events/                    # Committee hearings
│                   └── {timestamp}_hearing.json
├── .windycivi/                      # Pipeline metadata (committed)
│   ├── errors/                      # Processing errors
│   │   ├── text_extraction_errors/  # Text extraction failures
│   │   │   ├── download_failures/   # Failed downloads
│   │   │   ├── parsing_errors/      # Failed text parsing
│   │   │   └── missing_files/       # Missing source files
│   │   ├── missing_session/         # Bills without session info
│   │   ├── event_archive/           # Archived event data
│   │   └── orphaned_placeholders_tracking.json  # Data quality monitoring
│   ├── bill_session_mapping.json    # Bill-to-session mappings
│   ├── sessions.json                # Session metadata
│   ├── latest_timestamp_seen.txt    # Last processed timestamp
│   └── last-processed-sha           # Last scraper-repo commit this repo formatted
└── data.json                        # DCAT dataset descriptor
```

---

## 📦 Output Format

### Metadata Output (`country:us/state:*/`)

Formatted metadata is saved to `country:us/state:id/sessions/`, organized by session and bill.

Each bill directory contains:

- `metadata.json` – structured information about the bill **with `_processing` timestamps**
- `logs/` – action, event, and vote logs
- `files/` – original documents and extracted text

**Example `metadata.json` structure:**

```json
{
  "identifier": "HB 1234",
  "title": "Example Bill",
  "_processing": {
    "logs_latest_update": "2025-01-15T14:30:00Z",
    "text_extraction_latest_update": "2025-01-16T08:00:00Z"
  },
  "actions": [
    {
      "description": "Introduced in House",
      "date": "2025-01-01",
      "_processing": {
        "log_file_created": "2025-01-01T12:00:00Z"
      }
    }
  ]
}
```

### Text Extraction Output (`files/`)

When text extraction runs, each bill directory also includes:

- `files/` – original documents and extracted text
  - `*.pdf` – Original PDF documents
  - `*.xml` – Original XML bill text
  - `*.html` – Original HTML documents
  - `*_extracted.txt` – Plain text extracted from documents

### Error Output (`.windycivi/errors/`)

Failed items are logged separately:

- `.windycivi/errors/text_extraction_errors/download_failures/` – Documents that couldn't be downloaded
- `.windycivi/errors/text_extraction_errors/parsing_errors/` – Documents that couldn't be parsed
- `.windycivi/errors/text_extraction_errors/missing_files/` – Bills missing source files
- `.windycivi/errors/missing_session/` – Bills without session information

### Data Quality Monitoring (`orphaned_placeholders_tracking.json`)

Tracks **orphaned bills** - bills that have vote events or hearings but no actual bill data. Check this file periodically to identify data quality issues:

```json
{
  "HB999": {
    "first_seen": "2025-01-21T12:00:00Z",
    "last_seen": "2025-01-23T14:30:00Z",
    "occurrence_count": 3,
    "session": "103",
    "vote_count": 2,
    "event_count": 0,
    "path": "country:us/state:id/sessions/103/bills/HB999"
  }
}
```

**What to look for:**

- Bills with high `occurrence_count` (3+) are **chronic orphans** - likely data quality issues
- Check for typos in bill identifiers or scraper configuration
- Orphans automatically resolve when the bill data arrives! 🎉

📖 See [orphan tracking documentation](https://github.com/chihacknight/govbot/blob/main/actions/format/docs/orphan_tracking.md) for more details.

---

## 🪵 Logging & Error Handling

### Formatting Logs

- Logs are saved per bill under `logs/`
- Processing summary shows total bills, events, and votes processed
- Session mapping tracks bill-to-session relationships
- **Orphan tracking** shows new, existing, and resolved orphans

### Text Extraction Logs

- Download attempts with success/failure status
- Extraction method used (XML, HTML, PDF)
- Error details saved to `.windycivi/errors/text_extraction_errors/`
- Summary reports include total documents processed, successful extractions by type, skipped (already extracted) documents, and failed downloads/extractions with reasons

Both workflows are fault-tolerant — if a single bill fails, the run continues for all others.

---

## 📄 Supported Document Types

| Type           | Format   | Extraction Method   | Notes                          |
| -------------- | -------- | ------------------- | ------------------------------ |
| **Bills**      | XML      | Direct XML parsing  | Primary bill text              |
| **Bills**      | PDF      | pdfplumber + PyPDF2 | With strikethrough detection   |
| **Bills**      | HTML     | BeautifulSoup       | Fallback for HTML-only sources |
| **Amendments** | PDF      | pdfplumber + PyPDF2 | State amendments only          |
| **Documents**  | PDF/HTML | Auto-detect         | CBO reports, committee reports |

**Note**: Federal `congress.gov` HTML amendments are currently skipped due to blocking issues. XML bill versions from `govinfo.gov` work perfectly.

---

## 📊 Monitoring & Debugging

### Check Workflow Status

- GitHub Actions tab shows all runs
- Green checkmark = success
- Red X = failure (click for logs)

### Check Data Quality

1. Review `.windycivi/errors/orphaned_placeholders_tracking.json` for data issues
2. Look for chronic orphans (occurrence_count >= 3)
3. Check `.windycivi/errors/` for formatting/extraction errors

### Common Issues

**No new data showing up**:

- Check the scraper repo (`govbot-openstates-scrapers/id-legislation`) actually got fresh data first — this repo only formats what that repo has already scraped
- Check `.windycivi/last-processed-sha` against the scraper repo's latest commit

**Text extraction fails or times out**:

- Check `.windycivi/errors/text_extraction_errors/` for details
- A timed-out/failed run auto-restarts and resumes (incremental) — no manual re-run needed
- Review error logs for specific bills

**Orphaned bills appear**:

- Check `orphaned_placeholders_tracking.json` for details
- Verify bill identifiers match between scraper and vote/event data
- Bills may auto-resolve on the next format run if it's a timing issue

---

## 🤝 Contributions & Support

This repo is generated from a template in the [`chihacknight/govbot`](https://github.com/chihacknight/govbot) monorepo (`actions/pipeline-manager/templates/openstates-to-ocd-files/`). If you're fixing a bug in the pipeline itself (not this jurisdiction's data), open an issue or PR there — changes to this repo's workflow files will be overwritten on the next `apply.py` run.

For discussions, join the Chi Hack Night community on Slack or GitHub Discussions.

---

## 📚 Additional Documentation

- **[Data Structures Reference](https://github.com/chihacknight/govbot/blob/main/actions/format/docs/DATA_STRUCTURES.md)** - Full schema for bills, logs, events, errors
- **[Orphan Tracking Guide](https://github.com/chihacknight/govbot/blob/main/actions/format/docs/orphan_tracking.md)** - Understanding data quality monitoring
- **[Main Repository](https://github.com/chihacknight/govbot)** - Full technical documentation

---

**Part of the [Windy Civi](https://windycivi.com) ecosystem — building a transparent, verifiable civic data archive for all 56 US jurisdictions.**
