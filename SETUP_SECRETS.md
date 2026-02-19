# Setup Guide - Privacy-First Configuration

## Overview

This system uses **GitHub Secrets** (encrypted) instead of config files. No emails or personal info stored in the repository!

## Required Secrets

Go to your repo → Settings → Secrets and variables → Actions → New repository secret

### Email Configuration (Required)

```
MAIL_SERVER=smtp.gmail.com
MAIL_PORT=587
MAIL_USERNAME=your-email@gmail.com
MAIL_PASSWORD=your-app-password
MAIL_FROM=[email protected]
NOTIFICATION_RECIPIENTS=[email protected],[email protected]
```

### User Information (Optional - has defaults)

```
WITNESS_SLIP_USER_NAME=Jane Urbanist
WITNESS_SLIP_USER_EMAIL=[email protected]
WITNESS_SLIP_ORG=Chicago Urbanists
```

### Transportation Subscription

```
TOPICS_TRANSPORTATION=Transportation,Public Transit,Roads,Highways,Bicycle,Pedestrian,Traffic,Rail
RECIPIENTS_TRANSPORTATION=[email protected],[email protected]
```

### Housing Subscription

```
TOPICS_HOUSING=Housing,Affordable Housing,Real Estate,Zoning,Land Use,Development,Urban Planning
RECIPIENTS_HOUSING=[email protected],[email protected]
```

### Optional Settings

```
TRACKED_BILLS=HB1234,SB5678
URGENCY_THRESHOLD_DAYS=7
RECIPIENTS_ALL=[email protected]
```

## Local Testing

Create `.env.local` (gitignored):

```bash
export USER_NAME="Your Name"
export USER_EMAIL="[email protected]"
export USER_ORG="Your Organization"
export TOPICS_TRANSPORTATION="Transportation,Public Transit,Bicycle"
export TOPICS_HOUSING="Housing,Zoning,Land Use"
export RECIPIENTS_TRANSPORTATION="[email protected]"
export RECIPIENTS_HOUSING="[email protected]"
```

Run locally:

```bash
source .env.local
python scripts/witness_slip_notifier.py --mode local --data-dir path/to/data/il
```

## Gmail Setup

1. Enable 2FA on Google Account
2. Generate App Password:
   - Google Account → Security → 2-Step Verification → App passwords
   - Select "Mail" and "Other (Custom name)"
   - Copy generated password
3. Use as `MAIL_PASSWORD` secret

## Testing with MailHog (Open Source Dummy Email)

**MailHog** captures emails without sending them - perfect for testing!

### Option 1: Docker (Easiest)

```bash
# Start MailHog
docker run -d -p 1025:1025 -p 8025:8025 mailhog/mailhog

# Use these settings
MAIL_SERVER=localhost
MAIL_PORT=1025
MAIL_USERNAME=test
MAIL_PASSWORD=test
MAIL_FROM=[email protected]
NOTIFICATION_RECIPIENTS=[email protected]

# View captured emails at: http://localhost:8025
```

### Option 2: Direct Install

```bash
# macOS
brew install mailhog
mailhog

# Linux
wget https://github.com/mailhog/MailHog/releases/download/v1.0.1/MailHog_linux_amd64
chmod +x MailHog_linux_amd64
./MailHog_linux_amd64

# View emails at: http://localhost:8025
```

### Option 3: Mailpit (Modern MailHog Alternative)

```bash
# Docker
docker run -d -p 1025:1025 -p 8025:8025 axllent/mailpit

# Or download binary from: https://github.com/axllent/mailpit/releases

# View at: http://localhost:8025
```

## Privacy Benefits

✅ No config files in repo  
✅ Encrypted secrets in GitHub  
✅ No email addresses in code  
✅ Easy to rotate credentials  
✅ Different recipients per topic  
✅ Test with dummy email tools  

## Testing Without Email

Run workflow with `test_mode`:

1. Actions → IL Witness Slip Notifications
2. Run workflow
3. Set `test_mode` to `true`
4. Check artifacts for output
