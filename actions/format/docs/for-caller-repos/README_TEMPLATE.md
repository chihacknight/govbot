# 🏛️ Windy Civi Data Pipeline Template

A **GitHub Actions-powered pipeline** that scrapes, cleans, versions, and extracts text from state legislative data from **Open States**. This repository acts as a standardized template for all state-level pipelines within the Windy Civi ecosystem.

---

## ⚙️ What This Pipeline Does

Each state pipeline provides a self-contained automation workflow to:

1. 🧹 **Scrape** data for a single U.S. state from the [OpenStates](https://github.com/openstates/openstates-scrapers) project
2. 🧼 **Sanitize** the data by removing ephemeral fields (`_id`, `scraped_at`) for deterministic output
3. 🧠 **Format** it into a blockchain-style, versioned structure with incremental processing
4. 🔗 **Link** events to bills and sessions automatically
5. 🩺 **Monitor** data quality by tracking orphaned bills
6. 📄 **Extract** full text from bills, amendments, and supporting documents (PDFs, XMLs, HTMLs)
7. 📂 **Commit** the formatted output and extracted text nightly (or manually) with auto-save

This approach keeps every state repository consistent, auditable, and easy to maintain.

---

## ✨ Key Features

- **🔄 Incremental Processing** - Only processes new or updated bills (no duplicate work!)
- **💾 Auto-Save Failsafe** - Commits progress every 30 minutes during text extraction
- **🩺 Data Quality Monitoring** - Tracks orphaned bills (votes/events without bill data)
- **🔗 Bill-Event Linking** - Automatically connects committee hearings and events to bills
- **⏱️ Timestamp Tracking** - Two-level timestamps for logs and text extraction
- **🎯 Multi-Format Text Extraction** - XML → HTML → PDF with fallbacks
- **🔀 Concurrent Job Support** - Multiple runs can safely update the same repository
- **📊 Detailed Error Logging** - Categorized errors for easy debugging

---

## 🔧 Setup Instructions

1. **Click the green "Use this template" button** on this repository page to create a new repository from this template.

2. **Name your new repository** using the convention: `STATE-data-pipeline` (e.g., `il-data-pipeline`, `tx-data-pipeline`).

3. **Update the state abbreviation** in both workflow files:

   **In `.github/workflows/scrape-and-format-data.yml`:**

   ```yaml
   env:
     STATE_CODE: il # CHANGE THIS to your state abbreviation

   jobs:
     scrape:
       - name: Scrape data
         uses: windy-civi/toolkit/actions/scrape@main
         with:
           state: ${{ env.STATE_CODE }}

     format:
       - name: Format data
         uses: windy-civi/toolkit/actions/format@main
         with:
           state: ${{ env.STATE_CODE }}
   ```

   **In `.github/workflows/extract-text.yml`:**

   ```yaml
   - name: Extract text
     uses: windy-civi/toolkit/actions/extract@main
     with:
       state: il # CHANGE THIS to your state abbreviation
   ```

   Make sure the state abbreviation matches the folder name used in [Open States scrapers](https://github.com/openstates/openstates-scrapers/tree/main/scrapers).

4. **Enable GitHub Actions** in your repo (if not already enabled).

5. (Optional) Enable nightly runs by ensuring the schedule blocks are uncommented in both workflow files:

   ```yaml
   on:
     workflow_dispatch:
     schedule:
       - cron: "0 1 * * *" # For scrape-and-format-data.yml
       # or
       - cron: "0 3 * * *" # For extract-text.yml (runs later to avoid overlap)
   ```

---

## 📅 Workflow Schedule

The pipeline runs in two stages:

### **Stage 1: Scrape & Format** (1am UTC)

Two separate jobs that run sequentially:

1. **Scrape Job** - Downloads legislative data using OpenStates scrapers
2. **Format Job** - Processes scraped data, links events, and monitors quality

### **Stage 2: Text Extraction** (3am UTC)

Independent workflow that extracts full bill text from documents.

This separation allows:

- ✅ Faster metadata updates
- ✅ Independent monitoring and debugging
- ✅ Text extraction can timeout and restart without affecting scraping
- ✅ Better resource management (text extraction can take hours)

---

## 📁 Folder Structure

```
STATE-data-pipeline/
├── .github/workflows/
│   ├── scrape-and-format-data.yml  # Metadata scraping + formatting
│   └── extract-text.yml             # Text extraction (independent)
├── country:us/
│   └── state:xx/                    # state:usa for federal, state:il for Illinois, etc.
│       └── sessions/
│           └── {session_id}/
│               ├── bills/
│               │   └── {bill_id}/
│               │       ├── metadata.json      # Bill data + _processing timestamps
│               │       ├── files/             # Extracted text & documents
│               │       │   ├── *.pdf          # Original PDFs
│               │       │   ├── *.xml          # Original XMLs
│               │       │   └── *_extracted.txt # Extracted text
│               │       ├── action_logs.jsonl  # Every action, one per line, append-only
│               │       └── vote_event_logs.jsonl # Every roll call, one per line, append-only
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
│   ├── bill_session_mapping.json    # Bill-to-session mappings (flattened)
│   ├── sessions.json                # Session metadata (flattened)
│   └── latest_timestamp_seen.txt    # Last processed timestamp
├── Pipfile, Pipfile.lock
└── README.md
```

---

## 📦 Output Format

### Metadata Output (`country:us/state:*/`)

Formatted metadata is saved to `country:us/state:xx/sessions/`, organized by session and bill.

Each bill directory contains:

- `metadata.json` – structured information about the bill **with `_processing` timestamps**
- `action_logs.jsonl` – every action on the bill, one JSON object per line, appended the night it was first seen (`first_seen`); the last lines are the newest
- `vote_event_logs.jsonl` – every roll call, one per line; a correction repeats the vote's `id` on a later line
- (a repo not yet converted to this layout has a `logs/` folder with one file per action or vote instead)
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

When text extraction is enabled, each bill directory also includes:

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

The pipeline automatically tracks **orphaned bills** - bills that have vote events or hearings but no actual bill data. Check this file periodically to identify data quality issues:

```json
{
  "HB999": {
    "first_seen": "2025-01-21T12:00:00Z",
    "last_seen": "2025-01-23T14:30:00Z",
    "occurrence_count": 3,
    "session": "103",
    "vote_count": 2,
    "event_count": 0,
    "path": "country:us/state:il/sessions/103/bills/HB999"
  }
}
```

**What to look for:**

- Bills with high `occurrence_count` (3+) are **chronic orphans** - likely data quality issues
- Check for typos in bill identifiers or scraper configuration
- Orphans automatically resolve when the bill data arrives! 🎉

📖 See [orphan tracking documentation](https://github.com/windy-civi/toolkit/blob/main/docs/orphan_tracking.md) for more details.

---

## 🪵 Logging & Error Handling

Each run includes detailed logs to track progress and capture failures:

### Scraping & Formatting Logs

- New actions and votes are appended to each bill's `action_logs.jsonl` / `vote_event_logs.jsonl`
- Processing summary shows total bills, events, and votes processed
- Session mapping tracks bill-to-session relationships
- **Orphan tracking** shows new, existing, and resolved orphans

### Text Extraction Logs

- Download attempts with success/failure status
- Extraction method used (XML, HTML, PDF)
- Error details saved to `text_extraction_errors/`
- **Auto-save commits** every 30 minutes prevent data loss
- Summary reports include:
  - Total documents processed
  - Successful extractions by type
  - Skipped (already extracted) documents
  - Failed downloads/extractions with reasons

Pipelines are fault-tolerant — if a bill fails, the workflow continues for all others.

---

## 📄 Supported Document Types

The text extraction workflow supports:

| Type           | Format   | Extraction Method   | Notes                          |
| -------------- | -------- | ------------------- | ------------------------------ |
| **Bills**      | XML      | Direct XML parsing  | Primary bill text              |
| **Bills**      | PDF      | pdfplumber + PyPDF2 | With strikethrough detection   |
| **Bills**      | HTML     | BeautifulSoup       | Fallback for HTML-only sources |
| **Amendments** | PDF      | pdfplumber + PyPDF2 | State amendments only          |
| **Documents**  | PDF/HTML | Auto-detect         | CBO reports, committee reports |

**Note**: Federal `congress.gov` HTML amendments are currently skipped due to blocking issues. XML bill versions from `govinfo.gov` work perfectly.

---

## 🔧 Workflow Configuration Options

### Scrape Action Inputs

```yaml
uses: windy-civi/toolkit/actions/scrape@main
with:
  state: il # State abbreviation (required)
  github-token: ${{ secrets.GITHUB_TOKEN }}
  use-scrape-cache: "false" # Skip scraping, use cached data
```

### Format Action Inputs

```yaml
uses: windy-civi/toolkit/actions/format@main
with:
  state: il # State abbreviation (required)
  github-token: ${{ secrets.GITHUB_TOKEN }}
```

### Text Extraction Action Inputs

```yaml
uses: windy-civi/toolkit/actions/extract@main
with:
  state: il # State abbreviation (required)
  github-token: ${{ secrets.GITHUB_TOKEN }}
```

---

## 🧩 Optional: Enabling Raw Scraped Data Storage

By default, raw scraped data (`_data/`) is not stored to keep the repository lightweight.

### ✅ To Enable `_data` Saving:

Uncomment the copy and commit steps in your workflow file:

```yaml
- name: Copy Scraped Data to Repo
  run: |
    mkdir -p "$GITHUB_WORKSPACE/_data/$STATE"
    cp -r "${RUNNER_TEMP}/_working/_data/$STATE"/* "$GITHUB_WORKSPACE/_data/$STATE/"
```

And include `_data` in the commit:

```bash
git add _data country:us/ .windycivi/
```

### 🚫 To Disable `_data` Saving (Default):

Comment out the copy step and exclude `_data` from the commit command:

```bash
git add country:us/ .windycivi/
```

---

## 🚀 Running the Pipeline

### Automatic (Scheduled)

Once enabled, workflows run automatically:

- **Scrape & Format**: 1am UTC daily
- **Text Extraction**: 3am UTC daily (runs independently)

### Manual Trigger

1. Go to **Actions** tab in GitHub
2. Select the workflow (Scrape & Format or Extract Text)
3. Click **Run workflow**
4. Choose the branch and click **Run**

### Testing Locally

```bash
# Clone the repository
git clone https://github.com/YOUR-ORG/STATE-data-pipeline
cd STATE-data-pipeline

# Install dependencies
pipenv install

# Run scraping and formatting
pipenv run python scrape_and_format/main.py \
  --state il \
  --openstates-data-folder /path/to/scraped/data \
  --git-repo-folder /path/to/output

# Run text extraction (with incremental flag)
pipenv run python text_extraction/main.py \
  --state il \
  --data-folder /path/to/output \
  --output-folder /path/to/output \
  --incremental
```

---

## 🔍 Known Issues

See the [known_problems/](https://github.com/windy-civi/toolkit/tree/main/known_problems) directory in the main repository for:

- State-specific scraper issues
- Formatter validation issues
- Text extraction limitations
- Status of all 56 jurisdictions

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
4. Monitor auto-save commits during text extraction runs

### Common Issues

**Scraping fails**:

- Check if OpenStates scraper for your state is working
- Verify state abbreviation matches OpenStates format
- Check for new legislative sessions not yet configured

**Text extraction fails or times out**:

- Check `.windycivi/errors/text_extraction_errors/` for details
- Look for auto-save commits (pipeline saves progress every 30 minutes)
- Re-run the workflow - it will resume from where it left off (incremental)
- Review error logs for specific bills

**Orphaned bills appear**:

- Check `orphaned_placeholders_tracking.json` for details
- Verify bill identifiers match between scraper and vote/event data
- Bills may auto-resolve on next scrape if it's a timing issue

**Push conflicts**:

- The pipeline auto-handles conflicts with `git pull --rebase`
- If manual resolution needed, check logs for specific conflicts

---

## 🤝 Contributions & Support

This template is part of the [Windy Civi](https://github.com/windy-civi) project. If you're onboarding a new state or improving the automation, feel free to open an issue or PR.

**Main Repository**: https://github.com/windy-civi/toolkit

For discussions, join our community on Slack or GitHub Discussions.

---

## 🎯 Next Steps After Setup

1. ✅ Verify both workflows are enabled
2. ✅ Test with manual trigger first (start with Scrape & Format)
3. ✅ Check output in `country:us/state:xx/sessions/`
4. ✅ Review `.windycivi/errors/orphaned_placeholders_tracking.json` for data quality
5. ✅ Check any errors in `.windycivi/errors/`
6. ✅ Test text extraction workflow independently
7. ✅ Enable scheduled runs once testing is successful
8. ✅ Monitor first few automated runs for issues

---

## 📚 Additional Documentation

- **[Incremental Processing Guide](https://github.com/windy-civi/toolkit/blob/main/docs/incremental_processing/)** - How incremental updates work
- **[Orphan Tracking Guide](https://github.com/windy-civi/toolkit/blob/main/docs/orphan_tracking.md)** - Understanding data quality monitoring
- **[Main Repository README](https://github.com/windy-civi/toolkit)** - Full technical documentation

---

**Part of the [Windy Civi](https://windycivi.com) ecosystem — building a transparent, verifiable civic data archive for all 50 states.**
