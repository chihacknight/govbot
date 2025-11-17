# 🏛️ Windy Civi: OpenCivicData Blockchain Transformer

[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

A GitHub Actions-powered pipeline that scrapes, formats, and extracts text from state and federal legislative data, organizing it into blockchain-style, versioned data structures. But more than that, it's part of a larger mission to make civic data transparent, permanent, and accessible to everyone.

## 💡 Why This Matters

Democracy relies on accessible information. Legislative data in the U.S. is often fragmented, inconsistently formatted, and easily lost when administrations change or sites go offline. **Windy Civi** is designed to solve that problem by creating a _decentralized, verifiable record_ of bills, votes, and actions—structured like a blockchain for traceability and accountability.

This project is inspired by open data movements and maintained by contributors who believe civic infrastructure should be public, durable, and transparent.

## ✨ Key Features

- **🔄 Incremental Processing** - Only processes new or updated bills (no duplicate work!)
- **💾 Auto-Save Failsafe** - Commits progress every 30 minutes (survives GitHub's 6-hour timeout)
- **🩺 Data Quality Monitoring** - Tracks orphaned bills (votes/events without bill data) to catch data issues
- **🔗 Bill-Event Linking** - Automatically connects committee hearings and events to their bills
- **⏱️ Timestamp Tracking** - Two-level timestamps for logs and text extraction
- **🎯 Multi-Format Text Extraction** - XML → HTML → PDF with fallbacks
- **🔀 Concurrent Job Support** - Multiple actions can run safely with git rebase
- **📦 Modular Actions** - Independent scrape, format, and extract actions

## 🧠 On AI and Collaboration

This project was developed with the help of AI tools like **ChatGPT** and **Cursor**, which I used as active collaborators rather than shortcuts. They were especially helpful when exploring architecture decisions, discussing different ways to structure functions, design data flows, and think through tradeoffs that are usually hard to reason about alone.

In many ways, AI became a kind of mentor. It helped me clarify my reasoning, consider alternative approaches, and better understand the 'why' behind every choice. But it also forced me to slow down. I learned to pause, ask questions, and make sure I truly understood what was being built rather than just moving fast.

Most unexpectedly, this process dramatically improved my debugging skills. By breaking problems into smaller conversations and exploring edge cases in real time, I became much more methodical and confident when tracking down issues. In short, coding with AI has been less about automation—and more about becoming a sharper, more reflective engineer.

## 🏗️ Repository Structure

```
├── actions/
│   ├── scrape/              # Scrape Action (job 1)
│   │   └── action.yml       # Docker-based scraping
│   ├── format/              # Format Action (job 2)
│   │   └── action.yml       # Data formatting + linking
│   └── extract/             # Text Extraction Action (independent)
│       └── action.yml       # Extract text from PDFs/XMLs/HTML
├── scrape_and_format/       # Core formatting logic
│   ├── handlers/            # Bill, vote, event processors
│   ├── postprocessors/      # Event linking, placeholder cleanup
│   └── utils/               # Path building, timestamps, I/O
├── text_extraction/         # Text extraction modules
│   └── utils/               # XML, HTML, PDF parsers
├── docs/                    # Documentation + example workflows
│   ├── orphan_tracking.md   # Orphan placeholder guide
│   └── example-caller-*.yml # Sample GitHub workflows
├── testing/                 # Test suites + sample data
├── Pipfile                  # Python dependencies
└── README.md
```

## 🚀 GitHub Actions Workflow

This pipeline uses **three modular actions** that work together but run independently:

### 📊 The Scrape & Format Workflow

These two actions run as **separate jobs in the same workflow**, passing data via artifacts:

#### **Action 1: Scrape** → Scrapes legislative data

- Docker-based scraping using OpenStates scrapers
- Creates artifact for next job
- Nightly releases (rolling + immutable archives)

#### **Action 2: Format** → Organizes into blockchain structure

- Downloads scrape artifact
- Incremental processing (only new/updated bills)
- Automatic session detection via API
- Links events to bills and sessions
- **Cleans up placeholder files** and tracks orphans
- Concurrent job support (git pull + rebase)

💡 **Why separate jobs?** Better debugging, preserved scrape data if formatting fails, and clearer logs.

### 🔤 The Text Extraction Action (Independent)

This runs as a **completely separate workflow**, usually a few hours after scrape+format:

#### **Action 3: Extract Text** → Extracts readable bill text

- Incremental processing (skips already-extracted bills)
- Auto-save every 30 minutes (prevents timeout data loss)
- Multi-format extraction (XML > HTML > PDF)
- Resumable after GitHub's 6-hour timeout
- Independent schedule (avoids timeouts)

💡 **Why separate?** Text extraction can take 4-6 hours for large datasets. Running independently allows it to restart and prevents blocking the scrape/format workflow.

## 📖 For Caller Repositories

Setting up a state pipeline? Everything you need is in the **[docs/for-caller-repos/](docs/for-caller-repos/)** folder:

- **[README_TEMPLATE.md](docs/for-caller-repos/README_TEMPLATE.md)** - Complete setup guide for state pipelines
- **[example-caller-scrape-format.yml](docs/for-caller-repos/example-caller-scrape-format.yml)** - Scrape + format workflow
- **[example-caller-text-extraction.yml](docs/for-caller-repos/example-caller-text-extraction.yml)** - Text extraction workflow

See the [docs/](docs/) folder for additional technical guides.

## 📊 Output Structure

```
country:us/
└── state:usa/                           # state:usa for federal, state:il for Illinois, etc.
    └── sessions/119/
        ├── bills/
        │   └── HR1234/
        │       ├── metadata.json           # Bill data + processing timestamps
        │       ├── logs/                   # Action logs + vote events
        │       │   ├── 20250101T120000Z_introduced.json
        │       │   └── 20250115T143000Z_vote_event_passed.json
        │       └── files/                  # Bill text
        │           ├── HR1234_text.xml     # Original XML
        │           ├── HR1234_text.txt     # Extracted text
        │           └── HR1234_text.pdf     # PDF fallback
        └── events/                         # Hearing/committee events
            └── 20250325T100000Z_hearing.json

.windycivi/                              # Pipeline metadata
├── errors/
│   ├── missing_session/
│   ├── text_extraction_errors/
│   ├── event_archive/
│   └── orphaned_placeholders_tracking.json  # Data quality monitoring
├── bill_session_mapping.json
├── sessions.json
└── latest_timestamp_seen.txt            # Last processed timestamp
```

### 🔍 Processing Metadata Example

Each bill's `metadata.json` includes `_processing` timestamps for incremental updates:

```json
{
  "identifier": "HR 1234",
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

## 🩺 Data Quality Monitoring

The pipeline automatically tracks **orphaned bills** - bills that have vote events or hearings but no actual bill data. This helps identify data quality issues like:

- Typos in bill identifiers (e.g., "HR 999" vs "HR999")
- Bills that weren't scraped but had related activity
- Timing issues (bill not scraped yet)

Check `.windycivi/errors/orphaned_placeholders_tracking.json` to see:

- Which bills are orphaned
- How long they've been orphaned (`first_seen`, `last_seen`)
- How many times they've appeared (`occurrence_count`)
- What data exists for them (vote counts, event counts)

**Chronic orphans** (seen 3+ times) are flagged for investigation. When a bill finally arrives, it's automatically resolved! 🎉

📖 See [docs/orphan_tracking.md](docs/orphan_tracking.md) for more details.

## ⚙️ Local Setup

**Requirements:**

- Python 3.12+
- pipenv
- Docker (for scraping)

**Installation:**

```bash
# Clone the repository
cd toolkit

# Install dependencies
pipenv install

# Run formatting (requires pre-scraped data)
pipenv run python scrape_and_format/main.py \
  --state usa \
  --openstates-data-folder /path/to/scraped/data \
  --git-repo-folder /path/to/output
```

**For scraping**, use the Docker-based action or OpenStates scrapers directly.

## 🧪 Testing

Run the test suite to verify everything works:

```bash
# Test incremental processing
bash testing/incremental/run_test.sh

# Test orphan placeholder cleanup
python testing/scripts/test_placeholder_cleanup.py
```

## 📚 Documentation

- **[Orphan Tracking Guide](docs/orphan_tracking.md)** - Understanding orphaned bills
- **[Incremental Processing](docs/incremental_processing/)** - How incremental updates work
- **[Example Workflows](docs/)** - Ready-to-use GitHub Actions examples

## 🌍 Project Vision

Windy Civi's long-term goal is to create a **permanent, blockchain-style public archive** for all legislative data—linking together OpenStates scrapers, GitHub repositories, and decentralized storage. Think of it as a civic data backbone for researchers, journalists, and citizens.

## 🤝 Contributing

This project is part of the broader **Windy Civi** ecosystem—a civic tech initiative based in Chicago focused on open data and transparency. We welcome collaborators, contributors, and curious minds.

- 🐙 [Open an Issue](https://github.com/windy-civi/toolkit/issues)
- 📬 Submit a PR
- 🌱 Help design future civic pipelines
- 💬 Join the conversation about civic tech

## 📜 License

MIT License - feel free to use, modify, and build upon this work.

**Built with care, code, and curiosity.** 🏛️✨

---

_Part of the [Windy Civi](https://github.com/windy-civi) ecosystem - Making civic data transparent and accessible._
