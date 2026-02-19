# IL Witness Slip Notification System

## What This Does

Automatically monitors Illinois state legislation and sends email notifications when housing or transportation bills are scheduled for committee hearings. Witness slips are most useful before committee hearings - this system helps you never miss the deadline.

## How It Works

1. Reads OpenStates JSON data from `govbot-openstates-scrapers/il-legislation`
2. Filters bills by topic keywords (housing, transportation, zoning, transit, etc.)
3. Identifies bills with upcoming committee hearings (next 30 days)
4. Generates email notifications with witness slip filing instructions
5. Outputs text, HTML, and JSON formats

## Local Testing with MailHog

MailHog catches all outbound emails locally so you can test without spamming real addresses.

### Local email sending

In `--mode local`, the script now sends a real email (through MailHog) in addition to printing the plain-text body.

### Install MailHog

    brew install mailhog

### Start MailHog

    mailhog

Access web interface at http://localhost:8025

### Configure SMTP

Set these environment variables:

    export SMTP_HOST=localhost
    export SMTP_PORT=1025
    export SMTP_USER=""
    export SMTP_PASSWORD=""

    export USER_EMAIL="witness.slip.sender@notrealemail.lol"
    export RECIPIENTS_TRANSPORTATION="witness.slip.test@notrealemail.lol"
    export RECIPIENTS_HOUSING="witness.slip.test@notrealemail.lol"


### Run the notifier against local demo 

    python scripts/witness_slip_notifier.py --data-dir test-data --mode local

Then open http://localhost:8025 to see the captured email.

## Environment Variables

### Required

- `RECIPIENTS_TRANSPORTATION` - Comma-separated email addresses for transportation bills
- `RECIPIENTS_HOUSING` - Comma-separated email addresses for housing bills

### Optional

- `USER_NAME` - Your name (default: "Urbanist Advocate")
- `USER_EMAIL` - Your email (default: "[email protected]")
- `USER_ORG` - Organization name (default: "Chicago Urbanists")
- `TOPICS_TRANSPORTATION` - Keywords to match (default: "Transportation,Public Transit,Roads,Highways,Bicycle,Pedestrian,Traffic")
- `TOPICS_HOUSING` - Keywords to match (default: "Housing,Affordable Housing,Real Estate,Zoning,Land Use,Development")
- `TRACKED_BILLS` - Specific bills to always include (e.g., "HB1234,SB5678")
- `URGENCY_THRESHOLD_DAYS` - Days before hearing to mark urgent (default: 7)

## Running Locally

### Basic Test

    python scripts/witness_slip_notifier.py --data-dir ../govbot-openstates-scrapers/il-legislation --mode local

### With Custom Environment

    export RECIPIENTS_HOUSING="[email protected]"
    export TOPICS_HOUSING="Zoning,Affordable Housing"
    python scripts/witness_slip_notifier.py --data-dir ../govbot-openstates-scrapers/il-legislation --mode local

### GitHub Actions Mode

    python witness_slip_notifier.py --data-dir ../govbot-openstates-scrapers/il-legislation --mode github-action

Outputs three files:

- `notifications_output.txt` - Plain text email
- `notifications_output.html` - HTML email
- `witness_slip_notifications.json` - Structured data

## Troubleshooting

### Permission Denied Error

**Error:** `PermissionError: [Errno 13] Permission denied`

**Fix:** Make script executable

    chmod +x witness_slip_notifier.py

### Data Directory Not Found

**Error:** `âŒ Data directory not found`

**Fix:** Use absolute path

    python scriptswitness_slip_notifier.py --data-dir /Users/eddie_chacha/govbot-openstates-scrapers/il-legislation --mode local

### No Bills Matched

**Symptom:** `âœ… No bills matched subscriptions`

**Causes:**
- No recipients configured
- Topics don't match bill subjects
- No bills have upcoming hearings

**Fix:** Check your environment variables

    echo $RECIPIENTS_HOUSING
    echo $TOPICS_HOUSING

### JSON Decode Error

**Error:** `âš ï¸ JSON decode error in file.json`

**Fix:** Validate JSON file

    python -m json.tool ../govbot-openstates-scrapers/il-legislation/problematic-file.json

Re-download from OpenStates if corrupted.

### SMTP Connection Failed

**Error:** `SMTPException: SMTP connection failed`

**Fix:** Verify MailHog is running

    mailhog

Check http://localhost:8025 is accessible.

## Output Format

### Plain Text Email

    ðŸ”” URGENT: Illinois Witness Slip Action Needed
    3 bill(s) require witness slip submissions

    ðŸš‡ Transportation & Transit
    ======================================================================
    2 bill(s)

    1. HB1234 - Public Transit Funding Act âš ï¸ URGENT (5 days)
       ðŸ‘¤ Sponsor: Rep. Jane Doe
       ðŸ›ï¸ Chamber: House
       ðŸ“… Hearing: March 15, 2026 at 2:00 PM
       ðŸ›ï¸ Committee: Transportation Committee
       ðŸ“‹ File Witness Slip: https://ilga.gov/house/hearings

### JSON Output

    [
      {
        "bill_number": "HB1234",
        "title": "Public Transit Funding Act",
        "sponsor": "Rep. Jane Doe",
        "chamber": "House",
        "hearing_date": "2026-03-15T14:00:00",
        "committee": "Transportation Committee",
        "witness_slip_url": "https://ilga.gov/house/hearings",
        "categories": ["Transportation & Transit"]
      }
    ]

## Bill Status and Witness Slip links

Each bill in the email includes:

- **File Witness Slip** – a generic hearings page for the correct chamber:
  - House bills → https://ilga.gov/house/hearings
  - Senate bills → https://ilga.gov/senate/hearings
- **Bill Status** – a direct link to the Illinois General Assembly bill page.

The notifier prefers the ILGA URL supplied by OpenStates (`bill_data["sources"][0]["url"]`). This usually points to the official Bill Status page, which includes tabs for "Bill Status", "Full Text", "Actions", and "Witness Slips". If no `sources` URL is present, the script falls back to a best‑guess BillStatus URL using the bill number and chamber.

From the Bill Status page, users can click the **“Witness Slips”** tab to see hearings and file a slip for the specific agenda item.


## Data Flow

1. Script reads JSON files from OpenStates scraper output
2. Parses bill data (identifier, title, sponsor, subjects, actions)
3. Extracts committee hearing dates from actions array
4. Matches bill subjects against configured topics
5. Routes matching bills to appropriate subscription categories
6. Generates notifications with filing instructions

## Testing Checklist

- [ ] MailHog running on localhost:1025
- [ ] Environment variables set
- [ ] OpenStates data directory exists
- [ ] Script runs without syntax errors
- [ ] Email appears in MailHog web interface
- [ ] Bill data parsed correctly
- [ ] Topic matching works as expected
- [ ] Output files generated (GitHub Actions mode)