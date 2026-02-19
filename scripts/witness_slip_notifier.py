#!/usr/bin/env python3
"""
IL Witness Slip Notifier - Transportation & Housing Focus
Privacy-first: No config files, uses environment variables only
Parses OpenStates data directly (not metadata.json)
"""

import json
import os
import sys
import urllib.parse
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Set
from enum import Enum
from pathlib import Path
import argparse
import requests
import tempfile
import smtplib
from email.message import EmailMessage




class BillReading(Enum):
    FIRST = "First Reading"
    SECOND = "Second Reading"
    THIRD = "Third Reading"


class Chamber(Enum):
    HOUSE = "House"
    SENATE = "Senate"


class Bill:
    """Illinois state bill with topic filtering"""
    
    def __init__(self, bill_number: str, chamber: Chamber, title: str,
                 sponsor: str, next_reading: BillReading,
                 subjects: List[str] = None,
                 committee_hearing_date: Optional[datetime] = None,
                 committee_name: Optional[str] = None,
                 ilga_url: Optional[str] = None):
        self.bill_number = bill_number
        self.chamber = chamber
        self.title = title
        self.sponsor = sponsor
        self.next_reading = next_reading
        self.subjects = subjects or []
        self.committee_hearing_date = committee_hearing_date
        self.committee_name = committee_name
        self.ilga_url = ilga_url or self.get_bill_status_url()
    
    def matches_topics(self, topic_list: List[str]) -> bool:
        """Case-insensitive partial matching"""
        if not self.subjects:
            return False
        
        normalized_subjects = [s.lower() for s in self.subjects]
        normalized_topics = [t.lower().strip() for t in topic_list]
        
        for subject in normalized_subjects:
            for topic in normalized_topics:
                if topic in subject or subject in topic:
                    return True
        return False
    
    def get_witness_slip_url(self) -> str:
        base_url = "https://ilga.gov"
        chamber_path = self.chamber.value.lower()
        return f"{base_url}/{chamber_path}/hearings"
    
    def get_bill_status_url(self) -> str:
        doc_type = "HB" if self.chamber == Chamber.HOUSE else "SB"
        bill_num = self.bill_number.replace(doc_type, "").replace("SB", "").replace("HB", "")
        return f"https://www.ilga.gov/legislation/BillStatus?DocTypeID={doc_type}&DocNum={bill_num}"


class OpenStatesParser:
    """Parse OpenStates IL data directly"""
    
    @staticmethod
    def parse_data_directory(data_dir: str) -> List[Bill]:
        print(f"📂 Parsing OpenStates data from: {data_dir}")
        data_path = Path(data_dir)
        
        if not data_path.exists():
            print(f"❌ Data directory not found: {data_dir}")
            return []
        
        bills = []
        bill_files = list(data_path.glob("**/*.json"))
        
        print(f"📄 Found {len(bill_files)} JSON files")
        
        for bill_file in bill_files:
            # Skip metadata.json - we want OpenStates source data
            if bill_file.name == 'metadata.json':
                continue
            
            try:
                with open(bill_file, 'r') as f:
                    data = json.load(f)
                    
                    if isinstance(data, list):
                        for bill_data in data:
                            bill = OpenStatesParser._parse_bill(bill_data)
                            if bill:
                                bills.append(bill)
                    else:
                        bill = OpenStatesParser._parse_bill(data)
                        if bill:
                            bills.append(bill)
            except Exception as e:
                print(f"⚠️  Error parsing {bill_file.name}: {e}")
                continue
        
        # Deduplicate
        seen = set()
        unique_bills = []
        for bill in bills:
            if bill.bill_number not in seen:
                seen.add(bill.bill_number)
                unique_bills.append(bill)
        
        print(f"✅ Parsed {len(unique_bills)} unique bills")
        return unique_bills
    
    @staticmethod
    def _parse_bill(bill_data: dict) -> Optional[Bill]:
        """Parse OpenStates JSON format"""
        try:
            identifier = bill_data.get('identifier') or bill_data.get('bill_id')
            if not identifier:
                return None
            
            # Chamber
            chamber_str = bill_data.get('from_organization', {}).get('classification', '')
            if 'upper' in chamber_str.lower() or 'senate' in chamber_str.lower():
                chamber = Chamber.SENATE
            else:
                chamber = Chamber.HOUSE
            
            # Title
            title = bill_data.get('title', 'Unknown')
            if isinstance(title, list):
                title = title[0] if title else 'Unknown'
            
            # Sponsor
            sponsors = bill_data.get('sponsorships', [])
            sponsor = "Unknown"
            if sponsors:
                primary = next((s for s in sponsors if s.get('primary')), sponsors[0])
                sponsor = primary.get('name', 'Unknown')
            
            # **SUBJECTS - from OpenStates source data**
            subjects = bill_data.get('subject', [])
            if isinstance(subjects, str):
                subjects = [subjects]
            
            # Reading stage
            next_reading = BillReading.FIRST
            actions = bill_data.get('actions', [])
            for action in reversed(actions):
                desc = action.get('description', '').lower()
                if 'third reading' in desc:
                    next_reading = BillReading.THIRD
                    break
                elif 'second reading' in desc:
                    next_reading = BillReading.SECOND
                    break
            
            # Committee info
            committee_date = None
            committee_name = None
            for action in actions:
                desc = action.get('description', '').lower()
                if 'committee' in desc and 'hearing' in desc:
                    date_str = action.get('date')
                    if date_str:
                        try:
                            committee_date = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                        except:
                            pass
                    org = action.get('organization', {})
                    committee_name = org.get('name')
                    break
            
            # URL
            sources = bill_data.get('sources', [])
            ilga_url = sources[0].get('url') if sources else None
            
            return Bill(
                bill_number=identifier,
                chamber=chamber,
                title=title,
                sponsor=sponsor,
                next_reading=next_reading,
                subjects=subjects,
                committee_hearing_date=committee_date,
                committee_name=committee_name,
                ilga_url=ilga_url
            )
        
        except Exception as e:
            print(f"⚠️  Error parsing bill: {e}")
            return None


def fetch_sample_bills() -> str:
    """Download 3-5 sample bills from GitHub for testing"""
    print("📥 Fetching sample bills from GitHub...")
    
    # Create temp directory for samples
    temp_dir = Path(tempfile.gettempdir()) / "witness-slip-test-data"
    temp_dir.mkdir(exist_ok=True)
    
    # Real bill URLs from the actual GitHub repo
    base_url = "https://raw.githubusercontent.com/govbot-openstates-scrapers/il-legislation/main/_data/il"
    
    # Sample bills - picking a few from the repo
    sample_bills = [
        f"{base_url}/bills/ocd-bill-1.json",
        f"{base_url}/bills/ocd-bill-2.json", 
        f"{base_url}/bills/ocd-bill-3.json",
        f"{base_url}/bills/ocd-bill-4.json",
        f"{base_url}/bills/ocd-bill-5.json",
    ]
    
    downloaded = 0
    for url in sample_bills:
        filename = url.split('/')[-1]
        try:
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                (temp_dir / filename).write_text(response.text)
                print(f"  ✅ Downloaded {filename}")
                downloaded += 1
            else:
                print(f"  ⚠️  Skipped {filename} (HTTP {response.status_code})")
        except Exception as e:
            print(f"  ⚠️  Failed to download {filename}: {e}")
    
    if downloaded == 0:
        print("❌ No sample bills downloaded. Check GitHub repo URL.")
        sys.exit(1)
    
    print(f"✅ Using {downloaded} sample bill(s) from: {temp_dir}")
    return str(temp_dir)


class EnvironmentConfig:
    """Load configuration from environment variables (GitHub Secrets)"""
    
    @staticmethod
    def load():
        return {
            'user': {
                'name': os.getenv('USER_NAME', 'Urbanist Advocate'),
                'email': os.getenv('USER_EMAIL', '[email protected]'),
                'organization': os.getenv('USER_ORG', 'Chicago Urbanists')
            },
            'subscriptions': {
                'transportation': {
                    'topics': [t.strip() for t in os.getenv('TOPICS_TRANSPORTATION', 
                        'Transportation,Public Transit,Roads,Highways,Bicycle,Pedestrian,Traffic').split(',')],
                    'recipients': [r.strip() for r in os.getenv('RECIPIENTS_TRANSPORTATION', '').split(',') if r.strip()]
                },
                'housing': {
                    'topics': [t.strip() for t in os.getenv('TOPICS_HOUSING',
                        'Housing,Affordable Housing,Real Estate,Zoning,Land Use,Development').split(',')],
                    'recipients': [r.strip() for r in os.getenv('RECIPIENTS_HOUSING', '').split(',') if r.strip()]
                },
                'all_recipients': [r.strip() for r in os.getenv('RECIPIENTS_ALL', '').split(',') if r.strip()],
                'tracked_bills': [b.strip() for b in os.getenv('TRACKED_BILLS', '').split(',') if b.strip()]
            },
            'settings': {
                'urgency_threshold_days': int(os.getenv('URGENCY_THRESHOLD_DAYS', '7'))
            }
        }

def send_email(subject: str, plain_body: str, html_body: str, recipients: List[str]) -> None:
    """Send email via SMTP (MailHog in local dev)."""
    if not recipients:
        return

    host = os.getenv("SMTP_HOST", "localhost")
    port = int(os.getenv("SMTP_PORT", "1025"))
    username = os.getenv("SMTP_USER", "")
    password = os.getenv("SMTP_PASSWORD", "")

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = os.getenv("USER_EMAIL", "[email protected]")
    msg["To"] = ", ".join(recipients)
    msg.set_content(plain_body)
    msg.add_alternative(html_body, subtype="html")

    with smtplib.SMTP(host, port) as server:
        if username and password:
            server.starttls()
            server.login(username, password)
        server.send_message(msg)

    print(f"📧 Sent email to: {msg['To']}")


class NotificationGenerator:
    """Generate email notifications"""
    
    def __init__(self, config: dict):
        self.config = config
        self.user = config['user']
    
    def generate_notifications(self, bills: List[Bill]) -> tuple:
        """Generate plain text and HTML emails"""
        
        # Route bills to subscriptions
        routed = self._route_bills(bills)
        
        if not routed:
            return ("No bills matched subscriptions.\n", "<p>No bills matched.</p>")
        
        plain = self._generate_plain(routed)
        html = self._generate_html(routed)
        
        return plain, html
    
    def _route_bills(self, bills: List[Bill]) -> Dict:
        """Route bills to subscriptions"""
        subs = self.config['subscriptions']
        routed = {}
        matched = set()
        
        # Specific bill tracking
        for bill in bills:
            if bill.bill_number in subs['tracked_bills']:
                if '🎯 Tracked Bills' not in routed:
                    routed['🎯 Tracked Bills'] = []
                routed['🎯 Tracked Bills'].append(bill)
                matched.add(bill.bill_number)
        
        # Transportation
        trans_recipients = subs['transportation']['recipients']
        if trans_recipients:
            trans_bills = [b for b in bills if b.bill_number not in matched 
                          and b.matches_topics(subs['transportation']['topics'])]
            if trans_bills:
                routed['🚇 Transportation & Transit'] = trans_bills
                for b in trans_bills:
                    matched.add(b.bill_number)
        
        # Housing
        housing_recipients = subs['housing']['recipients']
        if housing_recipients:
            housing_bills = [b for b in bills if b.bill_number not in matched
                            and b.matches_topics(subs['housing']['topics'])]
            if housing_bills:
                routed['🏘️ Housing & Development'] = housing_bills
                for b in housing_bills:
                    matched.add(b.bill_number)
        
        return routed
    
    def _generate_plain(self, routed: Dict) -> str:
        total = sum(len(bills) for bills in routed.values())
        
        text = f"""🔔 URGENT: Illinois Witness Slip Action Needed

{total} bill(s) require witness slip submissions for urbanist priorities.

{'='*70}

"""
        
        for category, bills in routed.items():
            text += f"\n{category}\n{'='*70}\n"
            text += f"{len(bills)} bill(s)\n\n"
            
            for i, bill in enumerate(bills, 1):
                urgency = ""
                if bill.committee_hearing_date:
                    days = (bill.committee_hearing_date - datetime.now()).days
                    if days <= self.config['settings']['urgency_threshold_days']:
                        urgency = f" ⚠️ URGENT ({days} days)"
                
                topics_str = f"\n  🏷️  Topics: {', '.join(bill.subjects)}" if bill.subjects else ""
                hearing_str = ""
                if bill.committee_hearing_date:
                    hearing_str = f"\n  📅 Hearing: {bill.committee_hearing_date.strftime('%B %d, %Y at %I:%M %p')}"
                    if bill.committee_name:
                        hearing_str += f"\n  🏛️  Committee: {bill.committee_name}"
                
                text += f"""{i}. {bill.bill_number} - {bill.title}{urgency}
{'-'*70}
  👤 Sponsor: {bill.sponsor}
  🏛️  Chamber: {bill.chamber.value}
  📖 Next Reading: {bill.next_reading.value}{topics_str}{hearing_str}
  
  📋 File Witness Slip: {bill.get_witness_slip_url()}
  📊 Bill Status: {bill.ilga_url}

"""
        
        text += f"""
{'='*70}
📝 HOW TO FILE
{'='*70}

1. Click witness slip link above
2. Find scheduled hearing
3. Click "Create Witness Slip"
4. Fill in:
   • Name: {self.user['name']}
   • Organization: {self.user['organization']}
   • Position: Select stance
   • Testimony: "Record of Appearance Only"
5. Submit

⏰ File BEFORE hearing concludes!

---
Govbot Urbanist Notification System
Generated: {datetime.now().strftime('%Y-%m-%d %I:%M %p CST')}
"""
        return text
    
    def _generate_html(self, routed: Dict) -> str:
        total = sum(len(bills) for bills in routed.values())
        
        html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<style>
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Arial, sans-serif; line-height: 1.6; color: #333; max-width: 900px; margin: 0 auto; padding: 20px; background: #f9fafb; }}
.header {{ background: linear-gradient(135deg, #0891b2 0%, #06b6d4 100%); color: white; padding: 30px; border-radius: 12px; margin-bottom: 30px; text-align: center; }}
.category {{ background: white; border-radius: 12px; padding: 24px; margin-bottom: 30px; border-left: 5px solid #0891b2; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
.category-header {{ background: #ecfeff; padding: 15px; border-radius: 8px; margin: -24px -24px 20px -24px; }}
.bill-card {{ border: 2px solid #e5e7eb; border-radius: 10px; padding: 20px; margin-bottom: 20px; background: #fafafa; }}
.bill-header {{ background: #0891b2; color: white; padding: 12px 20px; border-radius: 8px; margin: -20px -20px 15px -20px; }}
.topic-badge {{ display: inline-block; background: #fef3c7; color: #92400e; padding: 4px 10px; border-radius: 12px; font-size: 0.8em; margin: 2px; font-weight: 600; }}
.urgent {{ background: #ef4444; color: white; padding: 4px 12px; border-radius: 12px; font-size: 0.75em; margin-left: 10px; }}
.action-btn {{ display: inline-block; background: #10b981; color: white; padding: 12px 24px; text-decoration: none; border-radius: 8px; margin: 5px 5px 5px 0; font-weight: bold; }}
.stats {{ background: #ecfeff; border: 2px solid #0891b2; border-radius: 8px; padding: 15px; margin-bottom: 30px; text-align: center; }}
</style>
</head>
<body>
<div class="header">
<h1>🚇🏘️ IL Urbanist Witness Slip Action</h1>
<p>Transportation & Housing Priorities</p>
</div>

<div class="stats">
<strong style="font-size: 2em; color: #0891b2;">{total}</strong>
<p style="margin: 5px 0 0 0; color: #6b7280;">Bills Requiring Action</p>
</div>
"""
        
        for category, bills in routed.items():
            html += f"""
<div class="category">
<div class="category-header">
<h2 style="margin: 0; color: #0891b2;">{category}</h2>
<p style="margin: 5px 0 0 0; color: #6b7280;">{len(bills)} bill(s)</p>
</div>
"""
            
            for bill in bills:
                urgency_badge = ""
                if bill.committee_hearing_date:
                    days = (bill.committee_hearing_date - datetime.now()).days
                    if days <= self.config['settings']['urgency_threshold_days']:
                        urgency_badge = f'<span class="urgent">⚠️ {days} days</span>'
                
                topics_html = ""
                if bill.subjects:
                    topics_html = '<div style="margin: 10px 0;">'
                    for topic in bill.subjects:
                        topics_html += f'<span class="topic-badge">🏷️ {topic}</span>'
                    topics_html += '</div>'
                
                html += f"""
<div class="bill-card">
<div class="bill-header">
<strong>{bill.bill_number}</strong> - {bill.title} {urgency_badge}
</div>
<p><strong>👤 Sponsor:</strong> {bill.sponsor}</p>
<p><strong>🏛️ Chamber:</strong> {bill.chamber.value}</p>
<p><strong>📖 Next Reading:</strong> {bill.next_reading.value}</p>
"""
                
                if bill.committee_hearing_date:
                    html += f'<p><strong>📅 Hearing:</strong> {bill.committee_hearing_date.strftime("%A, %B %d, %Y at %I:%M %p")}</p>'
                    if bill.committee_name:
                        html += f'<p><strong>🏛️ Committee:</strong> {bill.committee_name}</p>'
                
                html += topics_html
                html += f"""
<div style="margin-top: 15px;">
<a href="{bill.get_witness_slip_url()}" class="action-btn">📋 File Witness Slip</a>
<a href="{bill.ilga_url}" class="action-btn" style="background: #6366f1;">📊 Bill Status</a>
</div>
</div>
"""
            
            html += "</div>"
        
        html += f"""
<div style="background: #fef3c7; border-left: 4px solid #f59e0b; padding: 20px; margin: 30px 0; border-radius: 8px;">
<h3 style="margin-top: 0;">📝 How to File</h3>
<ol>
<li>Click "File Witness Slip" button</li>
<li>Navigate to committee hearing</li>
<li>Click "Create Witness Slip"</li>
<li>Fill in: Name ({self.user['name']}), Organization ({self.user['organization']}), Position, Testimony</li>
<li>Submit</li>
</ol>
</div>

<div style="text-align: center; color: #6b7280; font-size: 0.9em; margin-top: 40px; padding-top: 20px; border-top: 2px solid #e5e7eb;">
<p><strong>Govbot Urbanist Notification System</strong></p>
<p>Transportation & Housing • Data: govbot-openstates-scrapers/il-legislation</p>
<p>Generated: {datetime.now().strftime('%Y-%m-%d %I:%M %p CST')}</p>
</div>
</body>
</html>
"""
        return html
    
    def generate_json(self, bills: List[Bill]) -> List[Dict]:
        """Generate JSON output for artifacts"""
        routed = self._route_bills(bills)
        
        output = []
        for category, bills in routed.items():
            for bill in bills:
                output.append({
                    'category': category,
                    'bill_number': bill.bill_number,
                    'title': bill.title,
                    'topics': bill.subjects,
                    'chamber': bill.chamber.value,
                    'sponsor': bill.sponsor,
                    'next_reading': bill.next_reading.value,
                    'witness_slip_url': bill.get_witness_slip_url(),
                    'bill_status_url': bill.ilga_url,
                    'committee_hearing': bill.committee_hearing_date.isoformat() if bill.committee_hearing_date else None,
                    'committee_name': bill.committee_name
                })
        
        return output


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--mode', choices=['github-action', 'local'], default='local')
    parser.add_argument(
    '--sample',
    action='store_true',
    help='Download sample bills from GitHub for testing (no local repo needed)'
)

    parser.add_argument('--data-dir', default='data/il')
    args = parser.parse_args()

    # Handle --sample flag
    if args.sample:
        args.data_dir = fetch_sample_bills()
    elif not args.data_dir:
        print("❌ Error: --data-dir required (or use --sample for testing)")
        sys.exit(1)

    
    print("\n" + "="*70)
    print("🚇🏘️ IL URBANIST WITNESS SLIP NOTIFIER")
    print("="*70 + "\n")
    
    # Load config from environment
    config = EnvironmentConfig.load()
    print(f"👤 User: {config['user']['name']}")
    print(f"🏢 Organization: {config['user']['organization']}\n")
    
    # Parse bills
    bills = OpenStatesParser.parse_data_directory(args.data_dir)
    
    if not bills:
        print("✅ No bills found in data directory.")
        if args.mode == 'github-action':
            Path('notifications_output.txt').write_text("No bills found.\n")
            Path('notifications_output.html').write_text("<p>No bills found.</p>")
            Path('witness_slip_notifications.json').write_text("[]")
        sys.exit(0)
    
    # Filter actionable bills
    now = datetime.now()
    future = now + timedelta(days=30)
    actionable = [b for b in bills if 
                  (b.committee_hearing_date and now <= b.committee_hearing_date <= future) or
                  b.next_reading in [BillReading.FIRST, BillReading.SECOND]]
    
    print(f"📊 Total bills: {len(bills)}")
    print(f"📊 Actionable: {len(actionable)}\n")
    
    if not actionable:
        print("✅ No actionable bills.")
        if args.mode == 'github-action':
            Path('notifications_output.txt').write_text("No actionable bills.\n")
            Path('notifications_output.html').write_text("<p>No actionable bills.</p>")
            Path('witness_slip_notifications.json').write_text("[]")
        sys.exit(0)
    
    # Generate notifications
    generator = NotificationGenerator(config)
    plain, html = generator.generate_notifications(actionable)
    json_output = generator.generate_json(actionable)
    
    if not json_output:
        print("✅ No bills matched subscriptions.")
        if args.mode == 'github-action':
            Path('notifications_output.txt').write_text("No matches.\n")
            Path('notifications_output.html').write_text("<p>No matches.</p>")
            Path('witness_slip_notifications.json').write_text("[]")
        sys.exit(0)
    
    print(f"✅ Matched {len(json_output)} bills\n")
    
    if args.mode == 'github-action':
        Path('notifications_output.txt').write_text(plain)
        Path('notifications_output.html').write_text(html)
        Path('witness_slip_notifications.json').write_text(json.dumps(json_output, indent=2))
        print("✅ Generated notification files")
    else:
        print(plain)
        # combine all configured recipients
        all_recipients = (
            config['subscriptions']['transportation']['recipients']
            + config['subscriptions']['housing']['recipients']
            + config['subscriptions']['all_recipients']
        )
        send_email(
            subject="IL Witness Slip Alerts – Urbanist Bills",
            plain_body=plain,
            html_body=html,
            recipients=all_recipients,
        )



if __name__ == "__main__":
    main()
