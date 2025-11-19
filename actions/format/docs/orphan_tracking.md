# Orphaned Placeholder Tracking

## Overview

When vote events or legislative events come through **before** their corresponding bill data, the system creates a `placeholder.json` file to hold the folder structure. This feature tracks these "orphaned" placeholders across runs to identify data quality issues.

## How It Works

### Automatic Cleanup (Post-Processing)

After all bills, votes, and events are processed, the cleanup runs automatically:

1. **Scan** for all `placeholder.json` files
2. **Check** if the bill now has `metadata.json` (real bill data)
3. **Delete** the placeholder if the bill exists
4. **Track** orphans that remain (bills that never arrived)

### Persistent Tracking

Orphans are tracked in `data_output/data_processed/orphaned_placeholders_tracking.json`:

```json
{
  "HR999": {
    "first_seen": "2025-10-21T12:00:00Z",
    "last_seen": "2025-10-23T14:30:00Z",
    "occurrence_count": 3,
    "session": "119",
    "vote_count": 2,
    "event_count": 0,
    "path": "country:us/congress/sessions/119/bills/HR999"
  }
}
```

### Key Features

- **First Seen**: When the orphan was first detected
- **Last Seen**: Most recent run where it was still orphaned
- **Occurrence Count**: How many times we've seen this orphan
- **Vote/Event Counts**: What data exists for the missing bill
- **Auto-Resolution**: When a bill finally arrives, the orphan is removed from tracking with a 🎉 message

### Chronic Orphans

Bills that appear as orphans **3+ times** are flagged as "chronic orphans" in the output. These likely indicate:

- **Typos** in vote/event bill identifiers (e.g., "HR 999" vs "HR999")
- **Missing bills** that weren't scraped but had related activity
- **Data quality issues** from the source API

## Example Output

```
🧹 Cleaning up placeholder files...
   ✓ Deleted placeholder for HR1 (bill exists)
   🆕 New orphan: HR999 (session 119) - 2 votes, 0 events
   ⚠️  Orphan: HJRES105 (session 119) - seen 3 times, 1 votes, 0 events
   🎉 Resolved orphan: HR2025 (was orphaned for 2 runs)

📋 Orphan tracking updated: orphaned_placeholders_tracking.json
   Total orphans being tracked: 45
   ⚠️  Chronic orphans (3+ occurrences): 12
      - HJRES105: 5 times
      - S2500: 4 times
      - HR3999: 3 times

✨ Placeholder cleanup complete:
   Found: 50
   Deleted: 5 (bills exist)
   Orphaned: 45 (bills missing)
   New orphans: 3
   Resolved: 2 🎉
```

## Investigating Orphans

### Review the Tracking File

Check `data_output/data_processed/orphaned_placeholders_tracking.json` for:

1. **High occurrence counts** → Chronic problems
2. **Recent first_seen dates** → May resolve naturally on next scrape
3. **Bill ID patterns** → Potential identifier format mismatches

### Check the Bill Folders

Orphaned bills still have folders with votes/events:

```
data_output/data_processed/country:us/congress/sessions/119/bills/HR999/
├── placeholder.json         # Placeholder (no real bill data)
└── logs/
    ├── 20250121T120000Z_vote_event_passed.json
    └── 20250122T140000Z_vote_event_failed.json
```

### Common Issues

1. **Case sensitivity**: Bill IDs from events might not match folder names

   - Vote says "HR 999" but folder is "HR999"
   - Solution: Normalize identifiers in vote/event handlers

2. **Missing bills**: Some bills referenced but never scraped

   - Check source API for these specific bills
   - Verify scraper is capturing all bill types

3. **Timing**: Bill just hasn't been scraped yet
   - Wait for next run - should auto-resolve

## Testing

Run the test suite:

```bash
python testing/scripts/test_placeholder_cleanup.py
```

This simulates:

- First run (new orphans)
- Second run (incrementing counts)
- Third run (resolving an orphan)

## Integration

The cleanup runs automatically at the end of `scrape_and_format/main.py`:

```python
# 6. Cleanup placeholder files (post-processing)
cleanup_stats = cleanup_placeholders(DATA_PROCESSED_FOLDER)
```

No configuration needed - it just works! ✨
