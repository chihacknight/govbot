#!/bin/bash
# Test script with actual email sending (using MailHog)
# Requires: MailHog running (docker-compose up mailhog)

set -e

echo "📧 Testing with MailHog Email Capture"
echo "====================================="
echo ""

# Check if MailHog is running
if ! curl -s http://localhost:8025 > /dev/null 2>&1; then
    echo "⚠️  MailHog not detected. Starting with Docker..."
    echo ""
    
    if command -v docker &> /dev/null; then
        docker run -d -p 1025:1025 -p 8025:8025 --name govbot-mailhog mailhog/mailhog
        echo "✅ MailHog started"
        echo "   Web UI: http://localhost:8025"
        echo ""
        sleep 2
    else
        echo "❌ Docker not found. Please install MailHog:"
        echo "   brew install mailhog  (macOS)"
        echo "   Or run: docker run -d -p 1025:1025 -p 8025:8025 mailhog/mailhog"
        exit 1
    fi
fi

# Set environment for testing
export USER_NAME="${USER_NAME:-Test Urbanist}"
export USER_EMAIL="${USER_EMAIL:-[email protected]}"
export USER_ORG="${USER_ORG:-Chicago Urbanists}"

export TOPICS_TRANSPORTATION="Transportation,Public Transit,Roads,Highways,Bicycle,Pedestrian,Traffic"
export TOPICS_HOUSING="Housing,Affordable Housing,Real Estate,Zoning,Land Use,Development"

export RECIPIENTS_TRANSPORTATION="[email protected]"
export RECIPIENTS_HOUSING="[email protected]"

# MailHog SMTP settings
export MAIL_SERVER="localhost"
export MAIL_PORT="1025"
export MAIL_USERNAME="test"
export MAIL_PASSWORD="test"
export MAIL_FROM="[email protected]"
export NOTIFICATION_RECIPIENTS="[email protected],[email protected]"

# Download sample data if needed
if [ ! -d "data/il" ] || [ ! "$(ls -A data/il)" ]; then
    echo "📥 Downloading sample IL data..."
    ./local_test.sh > /dev/null 2>&1 || true
fi

echo "🔧 Running notifier with email sending..."
echo ""

# Run the notifier
python scripts/witness_slip_notifier.py --mode github-action --data-dir data/il

# Send email using Python
echo ""
echo "📨 Sending email via MailHog..."
echo ""

python3 << 'PYEOF'
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
import os
from pathlib import Path

# Read generated content
plain_text = Path('notifications_output.txt').read_text()
html_content = Path('notifications_output.html').read_text()

# Create message
msg = MIMEMultipart('alternative')
msg['Subject'] = '[Govbot TEST] 🚇🏘️ IL Transportation & Housing Bills'
msg['From'] = os.getenv('MAIL_FROM')
msg['To'] = os.getenv('NOTIFICATION_RECIPIENTS')

# Attach plain text and HTML
msg.attach(MIMEText(plain_text, 'plain'))
msg.attach(MIMEText(html_content, 'html'))

# Attach JSON file
if Path('witness_slip_notifications.json').exists():
    with open('witness_slip_notifications.json', 'rb') as f:
        part = MIMEBase('application', 'json')
        part.set_payload(f.read())
        encoders.encode_base64(part)
        part.add_header('Content-Disposition', 
                       'attachment; filename=witness_slip_notifications.json')
        msg.attach(part)

# Send email
try:
    server = smtplib.SMTP(os.getenv('MAIL_SERVER'), int(os.getenv('MAIL_PORT')))
    server.sendmail(
        os.getenv('MAIL_FROM'),
        os.getenv('NOTIFICATION_RECIPIENTS').split(','),
        msg.as_string()
    )
    server.quit()
    print("✅ Email sent successfully!")
except Exception as e:
    print(f"❌ Error sending email: {e}")
    exit(1)
PYEOF

echo ""
echo "✅ Test complete!"
echo ""
echo "📬 View captured email at: http://localhost:8025"
echo ""
echo "To stop MailHog:"
echo "  docker stop govbot-mailhog && docker rm govbot-mailhog"
