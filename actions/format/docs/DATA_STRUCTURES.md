# 📊 Windy Civi Data Structures

Complete specification of all data formats produced by the Windy Civi legislative data pipeline.

> **📋 Version 2.0 (Planned)** - This document reflects the **new simplified structure** that will be implemented soon:
>
> - Removed `data_output/` wrapper folder
> - Removed `data_processed/` folder (start at `country:us/`)
> - Renamed `data_not_processed/` → `errors/`
> - Unified federal/state paths (both use `state:{code}`)
>
> See "Migration Guide" at the bottom for upgrade instructions.

---

## 🗂️ Directory Structure

**Note:** Each state/federal jurisdiction has its own repository. The structure below is what exists in each repo.

```
{state}-data-pipeline/                       # e.g., usa-data-pipeline, il-data-pipeline
├── .github/
│   └── workflows/                           # GitHub Actions
├── country:us/
│   └── state:{state_code}/                  # state:usa (federal), state:il, state:tx, etc.
│       └── sessions/{session_id}/
│           ├── bills/{bill_id}/
│           │   ├── metadata.json            # Bill metadata
│           │   ├── action_logs.jsonl        # Every action, one per line, append-only
│           │   ├── vote_event_logs.jsonl    # Every roll call, one per line, append-only
│           │   └── files/                   # Bill text
│           └── events/                      # Committee hearings
│               └── {timestamp}_{event}.json
├── .windycivi/                              # Pipeline metadata (committed & reused)
│   ├── errors/                              # Processing errors & quality monitoring
│   │   ├── missing_session/                 # Bills without session info
│   │   ├── text_extraction_errors/          # Text extraction failures
│   │   ├── event_archive/                   # Events pending bill linkage
│   │   └── orphaned_placeholders_tracking.json
│   ├── bill_session_mapping.json            # Bill-to-session mappings
│   ├── sessions.json                        # Session metadata
│   └── latest_timestamp_seen.txt            # Last processed timestamp
├── Pipfile                                  # Python dependencies
├── Pipfile.lock
└── README.md
```

### Key Changes from Previous Version:

1. **No `data_output/` wrapper** - Each repo is a data pipeline, so the root IS the output
2. **No `data_processed/` folder** - Start directly with `country:us/`
3. **Uniform jurisdiction naming** - Federal uses `state:usa` (not `congress`)
4. **Everything in `.windycivi/`** - All pipeline metadata grouped in one hidden folder
5. **Flattened metadata files** - Each repo is state-specific, so `sessions.json` instead of `sessions/{state}.json`

### Why This Structure?

- **One repo per jurisdiction** - usa-data-pipeline, il-data-pipeline, tx-data-pipeline, etc.
- **Only 3 root folders** - `.github/`, `country:us/`, `.windycivi/` - clean and minimal
- **Consistent paths** - Same structure for federal and state (simplifies bot code)
- **OpenStates compatible** - Follows OpenCivicData jurisdiction model
- **Hidden pipeline folder** - `.windycivi/` follows Unix convention for configuration/metadata
- **Clear separation** - Legislative data vs. pipeline metadata

### Important: `.windycivi/` is Committed!

The `.windycivi/` folder contains **persistent metadata** that must be:

- ✅ Committed to git after each run
- ✅ Pulled before each run (ensures incremental processing works)
- ✅ Never in `.gitignore`

**Why?** These files enable incremental processing:

- `latest_timestamp_seen.txt` - Prevents reprocessing old data
- `sessions.json` - Maps session IDs to names/dates
- `bill_session_mapping.json` - Links bills without session metadata

Without these files, the pipeline would reprocess everything from scratch each night!

### Example: Federal vs State

**Federal (usa-data-pipeline):**

```
country:us/state:usa/sessions/119/bills/HR1234/metadata.json
```

**State (il-data-pipeline):**

```
country:us/state:il/sessions/103/bills/HB1234/metadata.json
```

**Bot code can now use one pattern:**

```python
def get_bill_path(repo_root, state, session, bill_id):
    return f"{repo_root}/country:us/state:{state}/sessions/{session}/bills/{bill_id}"

# Works for both:
get_bill_path(usa_repo, "usa", "119", "HR1234")  # Federal
get_bill_path(il_repo, "il", "103", "HB1234")    # State
```

---

## 📄 Bill Metadata (`metadata.json`)

The primary data structure for all bills. Includes all bill information plus processing metadata for incremental updates.

### Schema

```json
{
  "legislative_session": "string (required)",
  "identifier": "string (required)",
  "title": "string (required)",
  "from_organization": "string",
  "classification": ["array of strings"],
  "subject": ["array of strings"],
  "abstracts": [
    {
      "abstract": "string",
      "note": "string"
    }
  ],
  "other_titles": [
    {
      "title": "string",
      "note": "string"
    }
  ],
  "other_identifiers": [
    {
      "identifier": "string",
      "scheme": "string"
    }
  ],
  "actions": [
    {
      "description": "string (required)",
      "date": "ISO 8601 datetime (required)",
      "organization_id": "string",
      "classification": ["array of strings"],
      "related_entities": [
        {
          "name": "string",
          "entity_type": "string"
        }
      ],
      "_processing": {
        "log_file_created": "ISO 8601 datetime"
      }
    }
  ],
  "sponsorships": [
    {
      "name": "string (required)",
      "classification": "string",
      "entity_type": "string",
      "primary": "boolean",
      "person_id": "string",
      "organization_id": "string or null"
    }
  ],
  "related_bills": [
    {
      "legislative_session": "string",
      "identifier": "string",
      "relation_type": "string"
    }
  ],
  "versions": [
    {
      "note": "string",
      "date": "ISO 8601 datetime",
      "links": [
        {
          "url": "string (required)",
          "media_type": "string"
        }
      ]
    }
  ],
  "documents": [
    {
      "note": "string",
      "date": "ISO 8601 datetime",
      "links": [
        {
          "url": "string (required)",
          "media_type": "string"
        }
      ]
    }
  ],
  "sources": [
    {
      "url": "string (required)",
      "note": "string"
    }
  ],
  "_processing": {
    "logs_latest_update": "ISO 8601 datetime",
    "text_extraction_latest_update": "ISO 8601 datetime (optional)"
  }
}
```

### Example

```json
{
  "legislative_session": "119",
  "identifier": "S 1379",
  "title": "REPAIR Act",
  "from_organization": "~{\"classification\": \"upper\"}",
  "classification": ["bill"],
  "subject": ["Transportation", "Consumer Protection"],
  "abstracts": [
    {
      "abstract": "A bill to ensure consumers have access to data relating to their motor vehicles...",
      "note": ""
    }
  ],
  "other_titles": [
    {
      "title": "Right to Equitable and Professional Auto Industry Repair Act",
      "note": "Short title"
    }
  ],
  "actions": [
    {
      "description": "Introduced in Senate",
      "date": "2025-04-09T04:00:00+00:00",
      "organization_id": "~{\"classification\": \"upper\"}",
      "classification": ["introduction"],
      "related_entities": [],
      "_processing": {
        "log_file_created": "2025-10-21T03:26:28Z"
      }
    }
  ],
  "sponsorships": [
    {
      "name": "Josh Hawley",
      "classification": "primary",
      "entity_type": "person",
      "primary": true,
      "person_id": "~{\"name\": \"Josh Hawley\"}",
      "organization_id": null
    }
  ],
  "versions": [
    {
      "note": "Introduced in Senate",
      "date": "2025-04-09",
      "links": [
        {
          "url": "https://www.govinfo.gov/content/pkg/BILLS-119s1379is/xml/BILLS-119s1379is.xml",
          "media_type": "application/xml"
        }
      ]
    }
  ],
  "sources": [
    {
      "url": "https://api.congress.gov/v3/bill/119/s/1379",
      "note": "Congress.gov API"
    }
  ],
  "_processing": {
    "logs_latest_update": "2025-10-21T03:26:28Z",
    "text_extraction_latest_update": "2025-10-21T08:15:42Z"
  }
}
```

---

## 📝 Action and vote logs (`action_logs.jsonl`, `vote_event_logs.jsonl`)

Every night's scrape is the whole dataset. These two files, one pair per bill, mark
what is **new**: each action or roll call is appended once, the first night the
pipeline sees it. They are **append-only**: lines are never edited, reordered or
removed. So:

- `git diff` of a night's commit lists exactly the bills with new activity, and the
  added lines are exactly the new entries.
- The last lines of a file are the newest activity on that bill.
- "What's new since yesterday" = lines whose `first_seen` is after yesterday.

Written by `actions/format/utils/log_jsonl.py`; line schemas in
`actions/format/schemas/action_log.schema.json` and `vote_event_log.schema.json`.

### Fields on every line

| Field | Meaning |
|---|---|
| `id` | Stable id within the file. It is the old per-entry filename minus `.json` (e.g. `20250114T210515Z.classification.introduction.upper`), with a `~<hash>` suffix when two different entries would otherwise share it. |
| `first_seen` | When the raw scrape that first contained the entry was committed to the scraper repo (ISO 8601). Not the formatter's run time, so a backfill from the raw history gets the right night. `null` for entries converted from the old layout with no record of when they were first seen. |
| `chamber` | Plain chamber (`upper`, `lower`, `legislature`, `executive`, …) decoded from the `~{"classification": …}` string beside it. `null` when there is none. |
| `bill_id` | The bill identifier. |

### `action_logs.jsonl`

```json
{"id": "20250131T030931Z.classification.introduction.lower", "first_seen": "2025-11-25T00:00:00+00:00", "chamber": "lower",
 "action": {"description": "H Introduced and Referred to H05", "occurred_at": "2025-01-31T03:09:31+00:00",
            "jurisdiction_id": "~{\"classification\": \"lower\"}", "session_id": "2025", "entity_type": "bill",
            "classifications": ["introduction", "referral-committee"], "related_entities": [],
            "sources": [{"url": "https://wyoleg.gov/Legislation/2025/HB0001", "note": ""}]},
 "bill_id": "HB0001"}
```

(Shown wrapped; in the file each entry is one line.) `action.occurred_at` is the
government's date. `action.sources` is the bill's official page, copied onto every
action on purpose so a log line passed around on its own always leads back to the bill.

**Same action:** same `occurred_at`, same description ignoring whitespace (some
scrapers start emitting line breaks inside descriptions), same `jurisdiction_id`.
An action already in the file is never written again.

### `vote_event_logs.jsonl`

```json
{"id": "20250205T173055Z_vote_event_fail", "first_seen": "2025-11-25T00:00:00+00:00", "chamber": "upper",
 "vote_event": {"identifier": "", "motion_text": "SF0001S2002: Amendment failed", "start_date": "2025-02-05T17:30:55+00:00",
                "result": "fail", "organization": "~{\"classification\": \"upper\"}", "bill_identifier": "SF0001",
                "votes": [{"option": "yes", "voter_name": "Anderson", "voter_id": "~{\"name\": \"Anderson\"}", "note": ""}, "…"],
                "counts": [{"option": "yes", "value": 9}, "…"], "sources": ["…"], "extras": {}},
 "bill_id": "SF0001"}
```

`vote_event` is the OpenStates vote event as published (minus the scraper's `_id`
and `scraped_at`).

**Same vote:** same roll-call `identifier` when both have one; otherwise same
`start_date`, motion, chamber and counts (date + motion + chamber alone is not
unique: PA HB 1549 had two roll calls on one motion at the same moment).

**Corrections:** when a later scrape changes a vote's substance (result, counts,
member votes, motion), the corrected vote is appended as a new line with the
**same `id`**. The last line for an `id` is current; earlier ones are the history.
Changes that aren't substance (source URL format, a roll-call number filled in
later, voter row order, the scraper's internal bill UUID) are not corrections.

Every vote in each scrape is checked, whatever its date. (The old formatter only
took votes newer than the newest it had seen, and its filenames let one vote
overwrite another; together they lost 23% of votes in a 14-state check on
2026-11-24.)

### The old layout and converting a repo

Before 2026-11, each bill had a `logs/` folder with one file per action or vote
(`{timestamp}_{slug}.json`, `{timestamp}.classification.{c}.{chamber}.json`,
`{timestamp}.vote_event.pass.{chamber}.json`, `{timestamp}_vote_event_{result}.json`),
plus a symlink to each under `sessions/{session}/logs/`. Old action files hold either
the current action shape or OpenStates' own (`date`, `organization_id`,
`classification`); both convert to the current shape.

`python3 actions/format/convert_logs.py <repo>` converts a repo in place (idempotent;
unrecognised files are kept and listed). The formatter refuses to write to a repo
that still has old-style `logs/` folders, so a bill is never split across layouts.

---

## 📅 Event (`events/*.json`)

Legislative events (committee hearings, etc.) are saved in the session's `events/` directory.

### Filename Format

```
{ISO8601_timestamp}_{slugified_name}.json
```

Example: `20250420T100000Z_committee_hearing.json`

### Schema

```json
{
  "name": "string (required)",
  "description": "string",
  "start_date": "ISO 8601 datetime (required)",
  "end_date": "ISO 8601 datetime (optional)",
  "location": {
    "name": "string",
    "note": "string"
  },
  "status": "string (confirmed/tentative/cancelled)",
  "classification": "string",
  "media": [
    {
      "name": "string",
      "type": "string",
      "links": [
        {
          "url": "string (required)",
          "media_type": "string"
        }
      ]
    }
  ],
  "agenda": [
    {
      "description": "string",
      "order": "integer",
      "subjects": ["array of strings"],
      "related_entities": [
        {
          "entity_type": "bill",
          "entity_id": "string",
          "note": "string"
        }
      ]
    }
  ],
  "participants": [
    {
      "name": "string",
      "entity_type": "person",
      "note": "string"
    }
  ]
}
```

### Example

```json
{
  "name": "Committee Hearing on Healthcare Reform",
  "description": "Discussion of proposed amendments to the Affordable Care Act",
  "start_date": "2025-04-20T10:00:00+00:00",
  "end_date": "2025-04-20T14:00:00+00:00",
  "location": {
    "name": "Room 216, Hart Senate Office Building"
  },
  "status": "confirmed",
  "classification": "committee-meeting",
  "agenda": [
    {
      "description": "Opening statements",
      "order": 1,
      "subjects": ["Healthcare"],
      "related_entities": [
        {
          "entity_type": "bill",
          "entity_id": "S 567",
          "note": "Primary bill under discussion"
        }
      ]
    }
  ]
}
```

---

## 📁 Bill Text Files (`files/`)

Extracted bill text and original source files are stored in the bill's `files/` directory.

### File Naming Conventions

| File Type          | Naming Pattern                           | Example                      |
| ------------------ | ---------------------------------------- | ---------------------------- |
| **Original XML**   | `{bill_id}_text.xml`                     | `HR1234_text.xml`            |
| **Original PDF**   | `{bill_id}_text.pdf`                     | `HR1234_text.pdf`            |
| **Original HTML**  | `{bill_id}_text.html`                    | `HR1234_text.html`           |
| **Extracted Text** | `{bill_id}_text_extracted.txt`           | `HR1234_text_extracted.txt`  |
| **Amendment PDF**  | `{bill_id}_{amendment_id}.pdf`           | `HR1234_SA123.pdf`           |
| **Amendment Text** | `{bill_id}_{amendment_id}_extracted.txt` | `HR1234_SA123_extracted.txt` |

### Extracted Text Format

Plain text (.txt) files with:

- UTF-8 encoding
- Original formatting preserved where possible
- Strikethrough text marked with `[STRUCK: text]` tags
- Inserted text marked with `[INSERTED: text]` tags (where detectable)

### Example

```
H. R. 1234

IN THE HOUSE OF REPRESENTATIVES

April 15, 2025

Mr. Smith introduced the following bill:

A BILL

To amend title XVIII of the Social Security Act to expand coverage...

Section 1. Short Title

This Act may be cited as the "Healthcare Expansion Act of 2025".

Section 2. Findings

Congress finds the following:
(1) Access to healthcare remains a critical issue...
```

---

## 🩺 Orphaned Placeholders Tracking

Monitors bills that have vote/event data but no bill metadata (data quality issue).

### File Location

```
.windycivi/errors/orphaned_placeholders_tracking.json
```

Located in the `.windycivi/errors/` folder alongside other data quality issues and processing errors.

### Schema

```json
{
  "{bill_id}": {
    "first_seen": "ISO 8601 datetime",
    "last_seen": "ISO 8601 datetime",
    "occurrence_count": "integer",
    "session": "string",
    "vote_count": "integer",
    "event_count": "integer",
    "path": "string (relative path to bill folder)"
  }
}
```

### Example

```json
{
  "HB999": {
    "first_seen": "2025-10-21T12:00:00Z",
    "last_seen": "2025-10-23T14:30:00Z",
    "occurrence_count": 3,
    "session": "103",
    "vote_count": 2,
    "event_count": 1,
    "path": "country:us/state:il/sessions/103/bills/HB999" // Relative to repo root
  }
}
```

**Chronic orphans** (occurrence_count >= 3) indicate:

- Typos in bill identifiers
- Bills referenced but not scraped
- Data quality issues from source

---

## ⏰ Processing Metadata (`_processing`)

All processed data includes `_processing` fields to track when updates occurred.

### Bill-Level Processing

```json
{
  "_processing": {
    "logs_latest_update": "ISO 8601 datetime",
    "text_extraction_latest_update": "ISO 8601 datetime (optional)"
  }
}
```

- **logs_latest_update**: When log files were last created/updated
- **text_extraction_latest_update**: When bill text was last extracted

### Action-Level Processing

```json
{
  "actions": [
    {
      "description": "...",
      "date": "...",
      "_processing": {
        "log_file_created": "ISO 8601 datetime"
      }
    }
  ]
}
```

- **log_file_created**: When this specific action's log file was created

### Why Two Levels?

- **Bill-level**: Quick check if any new activity (incremental processing)
- **Action-level**: Track exactly which actions are new vs. existing

---

## 🔍 Data Validation

### Required Fields

**Bill:**

- `identifier` (must be unique within session)
- `legislative_session`
- `title`

**Action:**

- `description`
- `date`

**Vote Event:**

- `bill_identifier`
- `start_date`
- `result`

**Event:**

- `name`
- `start_date`

### Timestamps

All timestamps use **ISO 8601** format:

- `2025-04-09T04:00:00+00:00` (with timezone)
- `2025-10-21T03:26:28Z` (UTC)

### Identifiers

Bill identifiers should:

- Be normalized (spaces preserved as in source)
- Include chamber prefix (HR, S, HB, SB, etc.)
- Match source system format

---

## 📋 Field Definitions

### Common Enumerations

**Bill Classification:**

- `bill` - Standard legislation
- `resolution` - Simple resolution
- `concurrent_resolution` - Concurrent resolution
- `joint_resolution` - Joint resolution

**Action Classification:**

- `introduction` - Bill introduced
- `reading-1`, `reading-2`, `reading-3` - Legislative readings
- `committee-referral` - Sent to committee
- `committee-passage` - Passed committee
- `passage` - Passed chamber
- `executive-signature` - Signed by executive
- `became-law` - Enacted into law

**Sponsorship Classification:**

- `primary` - Primary/lead sponsor
- `cosponsor` - Co-sponsor

**Entity Types:**

- `person` - Individual legislator
- `organization` - Legislative body/committee
- `bill` - Reference to another bill

---

## 🔗 Related Documentation

- **[Incremental Processing](incremental_processing/)** - How updates work
- **[Orphan Tracking](orphan_tracking.md)** - Data quality monitoring
- **[Text Extraction](../text_extraction/)** - How text is extracted

---

## 📝 Notes

1. **OpenStates Compatibility**: These structures maintain compatibility with OpenStates schema while adding Windy Civi-specific `_processing` fields.

2. **Versioning**: This is v1 of the data structure spec. Breaking changes will be documented here.

3. **Consumers**: These structures are consumed by:

   - BlueSky bots (engagement layer)
   - AI summarization tools (intelligence layer)
   - Web apps and APIs (presentation layer)

4. **Validation**: Consider adding JSON Schema files for automated validation.

---

## 🔄 Migration Guide (v1 → v2)

### Path Changes

| Old Path (v1)                                                            | New Path (v2)                                           |
| ------------------------------------------------------------------------ | ------------------------------------------------------- |
| `data_output/data_processed/country:us/congress/sessions/119/bills/HR1/` | `country:us/state:usa/sessions/119/bills/HR1/`          |
| `data_output/data_processed/country:us/state:il/sessions/103/bills/HB1/` | `country:us/state:il/sessions/103/bills/HB1/`           |
| `data_output/data_not_processed/`                                        | `.windycivi/errors/`                                    |
| `bill_session_mapping/{state}.json`                                      | `.windycivi/bill_session_mapping.json`                  |
| `sessions/{state}.json`                                                  | `.windycivi/sessions.json`                              |
| `data_output/latest_timestamp_seen.txt`                                  | `.windycivi/latest_timestamp_seen.txt`                  |
| `data_output/orphaned_placeholders_tracking.json`                        | `.windycivi/errors/orphaned_placeholders_tracking.json` |

### Code Changes Required

**1. Update Path Builders** (`scrape_and_format/utils/path_utils.py`):

```python
# OLD:
data_processed_folder / "country:us" / "congress" / "sessions" / ...

# NEW:
repo_root / "country:us" / f"state:{state}" / "sessions" / ...
```

**2. Remove Folder Wrappers**:

- All references to `data_output/` → repo root
- All references to `data_processed/` → repo root
- All references to `data_not_processed/` → `.windycivi/errors/`
- Move `bill_session_mapping/{state}.json` → `.windycivi/bill_session_mapping.json`
- Move `sessions/{state}.json` → `.windycivi/sessions.json`
- Move `latest_timestamp_seen.txt` → `.windycivi/latest_timestamp_seen.txt`
- Move `orphaned_placeholders_tracking.json` → `.windycivi/errors/orphaned_placeholders_tracking.json`

**3. Standardize Federal Naming**:

```python
# OLD:
is_usa = state_abbr.lower() == "usa"
if is_usa:
    path = ... / "congress" / ...

# NEW:
# No special case! Federal is just another state
path = ... / f"state:{state_abbr}" / ...
```

### Migration Steps

1. **Update `path_utils.py`** - Remove special `congress` handling
2. **Update action inputs** - Change `--git-repo-folder` expectations
3. **Update all file I/O** - Point to `.windycivi/` subfolder structure
4. **Update GitHub Actions** - Ensure `.windycivi/` is committed each run:
   ```yaml
   - name: Commit changes
     run: |
       git add country:us/ .windycivi/
       git commit -m "Update legislative data"
   ```
5. **Update documentation** - All examples use new paths
6. **Migrate existing repos** - One-time path restructure
7. **Update caller workflows** - Point to new root structure

### Critical: Git Workflow for `.windycivi/`

**Every GitHub Action run must:**

1. **Pull** `.windycivi/` at start (get latest session mappings, timestamps)
2. **Update** files during processing (sessions, mappings, timestamps)
3. **Commit** `.windycivi/` at end (preserve for next run)

**Example workflow step:**

```yaml
- name: Commit processed data
  run: |
    git pull origin main  # Get latest .windycivi/ metadata
    git add country:us/ .windycivi/
    git commit -m "📊 Update legislative data - $(date -u +%Y-%m-%dT%H:%M:%SZ)"
    git push origin main
```

**Why this matters:** Without committing `.windycivi/`, incremental processing breaks - the pipeline forgets what it processed and re-does everything!

### Backward Compatibility

**Breaking change:** Existing state pipeline repos will need to:

1. Reorganize directory structure (git mv)
2. Update any scripts that reference old paths
3. Update `.gitignore` if it references `data_output/`

**Suggested approach:**

- Implement in new state pipelines first
- Migrate existing pipelines one at a time
- Keep v1 structure documented for reference

---

## 📐 Complete Structure Reference

### v2.0 Structure (Simplified)

```
{state}-data-pipeline/
│
├── .github/workflows/              ← GitHub Actions
│
├── country:us/state:{state}/sessions/{session}/
│   ├── bills/{bill_id}/
│   │   ├── metadata.json           ← Main bill data
│   │   ├── action_logs.jsonl       ← Actions (append-only, one per line)
│   │   ├── vote_event_logs.jsonl   ← Roll calls (append-only, one per line)
│   │   └── files/*                 ← Bill text (PDF, XML, extracted)
│   └── events/*.json               ← Committee hearings
│
└── .windycivi/                     ← Pipeline metadata (MUST commit!)
    ├── errors/                     ← All errors & quality issues
    │   ├── missing_session/
    │   ├── text_extraction_errors/
    │   ├── event_archive/
    │   └── orphaned_placeholders_tracking.json
    ├── bill_session_mapping.json   ← Flattened (state-specific repo)
    ├── sessions.json               ← Flattened (state-specific repo)
    └── latest_timestamp_seen.txt
```

### What Goes Where?

| Data Type                | Location                                                | Committed? | Purpose                             |
| ------------------------ | ------------------------------------------------------- | ---------- | ----------------------------------- |
| **Bills, votes, events** | `country:us/state:{state}/`                             | ✅ Yes     | Legislative data                    |
| **Extracted text**       | `country:us/.../bills/{id}/files/`                      | ✅ Yes     | Bill text                           |
| **Processing errors**    | `.windycivi/errors/`                                    | ✅ Yes     | Debugging, quality monitoring       |
| **Session mappings**     | `.windycivi/sessions.json`                              | ✅ Yes     | Required for incremental processing |
| **Timestamp tracking**   | `.windycivi/latest_timestamp_seen.txt`                  | ✅ Yes     | Prevents reprocessing               |
| **Bill-session links**   | `.windycivi/bill_session_mapping.json`                  | ✅ Yes     | Maps bills without session metadata |
| **Orphan tracking**      | `.windycivi/errors/orphaned_placeholders_tracking.json` | ✅ Yes     | Data quality monitoring             |

**Everything is committed to git** - no local-only files. This ensures the pipeline can resume from where it left off.

---

**Version:** 2.0 (Planned)
**Last Updated:** 2025-10-21
**Part of:** [Windy Civi](https://github.com/windy-civi) ecosystem
