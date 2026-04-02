#!/usr/bin/env python3
"""
IL Witness Slip Notifier - Urbanist Focus
  Topics: Housing, Transportation, Biking, Safe Streets, Transit, and more
Privacy-first: No config files, uses environment variables only.

Two input modes:
  --feed <path>      Read the RSS feed produced by `govbot build` (preferred).
                     Bills are already tagged by govbot; this script finds the
                     ones with upcoming committee hearings, resolves witness
                     slip URLs, and builds the activist email digest.
  --data-dir <path>  Legacy mode: parse raw OpenStates JSON directly.
  --sample           Download a small sample from GitHub for local testing.
"""

import json
import os
import sys
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Set
from enum import Enum
from pathlib import Path
import argparse
import requests
import tempfile
import smtplib
from email.message import EmailMessage




# Strong Towns Chicago tracked bills — 104th General Assembly
# Always included in digest regardless of govbot keyword tagging.
# Format: normalized_bill_number -> (category, plain_description, stance)
STC_TRACKED_BILLS = {
    "HB5626": ("Housing",      "BUILD Act (Omnibus) — House omnibus housing bill",                 "Proponent"),
    "SB4061": ("Housing",      "BUILD Act — Single stair reform",                                 "Proponent"),
    "SB4064": ("Housing",      "BUILD Act — Parking reform (caps minimums)",                     "Proponent"),
    "SB4062": ("Housing",      "BUILD Act — Impact fee modernization",                            "Proponent"),
    "SB4060": ("Housing",      "BUILD Act — 2–8 units by right (missing middle)",                 "Proponent"),
    "SB4071": ("Housing",      "BUILD Act — Legalizes ADUs statewide",                           "Proponent"),
    "SB4063": ("Housing",      "BUILD Act — Third-party review for housing permits",              "Proponent"),
    "HB5083": ("Housing",      "YIGBY — Faith-based housing & mixed-use by-right",               "Proponent"),
    "SB3187": ("Housing",      "YIGBY — Faith-based housing & mixed-use by-right",               "Proponent"),
    "HB4835": ("Housing",      "Adaptive reuse of commercial buildings",                         "Proponent"),
    "HB5198": ("Housing",      "AHPAA Improvement Act",                                          "Proponent"),
    "SB3478": ("Biking",       "Bike grid enabling legislation",                                 "Proponent"),
    "HB2454": ("Biking",       "Adds bicycles as intended users of roadways",                   "Proponent"),
    "HB4660": ("Biking",       "Idaho Stop — legalizes yield-at-stop for cyclists",              "Proponent"),
    "HB4925": ("Biking",       "Class 3 e-bike: 18+ to carry passenger under 18",               "Proponent"),
    "HB2934": ("Safe Streets", "Lowers urban speed limit 30→20 mph / alley 15→10 mph",           "Proponent"),
    "HB4281": ("Safe Streets", "Speed cameras in Cook County cities 25k+ population",           "Proponent"),
    "HB4333": ("Safe Streets", "Lowers DUI BAC threshold 0.08% → 0.05%",                        "Proponent"),
    "HB4759": ("Transit",      "Green Light for Buses — transit signal priority",               "Proponent"),
    "SB3627": ("Safe Streets", "Quick Build — IDOT must accept quick-build safety infra",       "Proponent"),
    "HB5081": ("Safe Streets", "REMOVES safety zones when speed limit lowered to 20 mph",       "Opponent"),
}


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
        """Return the most specific witness slip URL available.

        Priority:
          1. ilga_url from OpenStates sources (already points to the ILGA
             BillStatus page which has a 'Witness Slips' tab).
          2. Constructed BillStatus URL with #tab=witnessSlips anchor.
          3. Generic chamber hearings page as a last resort.
        """
        if self.ilga_url and "ilga.gov" in self.ilga_url:
            # Append the Witness Slips tab anchor if not already there
            if "#" not in self.ilga_url:
                return f"{self.ilga_url}#tab=witnessSlips"
            return self.ilga_url
        # Fallback: constructed BillStatus URL
        bill_status = self.get_bill_status_url()
        if bill_status:
            return f"{bill_status}#tab=witnessSlips"
        # Last resort: chamber hearings landing page
        chamber_path = self.chamber.value.lower()
        return f"https://ilga.gov/{chamber_path}/hearings"

    def get_bill_status_url(self) -> str:
        doc_type = "HB" if self.chamber == Chamber.HOUSE else "SB"
        bill_num = self.bill_number.replace("HB", "").replace("SB", "").strip()
        return f"https://www.ilga.gov/legislation/BillStatus.asp?DocTypeID={doc_type}&DocNum={bill_num}&GAID=18&SessionID=114"


class GovbotFeedParser:
    """Parse the RSS feed produced by `govbot build`.

    govbot emits a standard RSS 2.0 feed where each <item> represents one
    bill action log entry.  The tags applied by `govbot tag` are stored in
    <category> elements, and the ILGA BillStatus URL lives in <link>.

    We rebuild a minimal Bill object from each item so the rest of the
    notifier pipeline (hearing detection, witness slip URL resolution,
    email generation) is unchanged.
    """

    # RSS namespace govbot uses for extensions
    _NS = {
        'content': 'http://purl.org/rss/1.0/modules/content/',
        'dc':      'http://purl.org/dc/elements/1.1/',
        'atom':    'http://www.w3.org/2005/Atom',
    }

    @classmethod
    def parse_feed(cls, feed_path: str) -> List["Bill"]:
        """Return a deduplicated list of Bill objects from the govbot RSS feed."""
        path = Path(feed_path)
        if not path.exists():
            print(f"❌ Feed file not found: {feed_path}")
            return []

        print(f"📡 Parsing govbot RSS feed: {feed_path}")
        try:
            tree = ET.parse(path)
        except ET.ParseError as exc:
            print(f"❌ Could not parse feed XML: {exc}")
            return []

        root = tree.getroot()
        channel = root.find('channel')
        if channel is None:
            print("❌ No <channel> element in feed.")
            return []

        items = channel.findall('item')
        print(f"📄 Found {len(items)} feed items")

        # Debug: print first item's raw fields so we can see real GUID format
        if items:
            def _t(el, tag):
                e = el.find(tag); return e.text.strip() if e is not None and e.text else ''
            sample = items[0]
            print(f"  [debug] title:  {_t(sample,'title')[:80]}")
            print(f"  [debug] guid:   {_t(sample,'guid')[:120]}")
            print(f"  [debug] link:   {_t(sample,'link')[:120]}")
            cats = [c.text.strip() for c in sample.findall('category') if c.text]
            print(f"  [debug] cats:   {cats}")

        # Deduplicate by bill identifier — one Bill object per bill.
        seen: dict[str, "Bill"] = {}

        for item in items:
            bill = cls._item_to_bill(item)
            if bill is None:
                continue
            if bill.bill_number not in seen:
                seen[bill.bill_number] = bill
            else:
                # Merge: keep the earliest upcoming hearing date
                existing = seen[bill.bill_number]
                if (bill.committee_hearing_date and
                        (existing.committee_hearing_date is None or
                         bill.committee_hearing_date < existing.committee_hearing_date)):
                    existing.committee_hearing_date = bill.committee_hearing_date
                    existing.committee_name = bill.committee_name
                # Merge subjects / govbot tags
                for s in bill.subjects:
                    if s not in existing.subjects:
                        existing.subjects.append(s)

        bills = list(seen.values())
        print(f"✅ Parsed {len(bills)} unique bills from feed")
        return bills

    @classmethod
    def _item_to_bill(cls, item: ET.Element) -> Optional["Bill"]:
        """Convert a single RSS <item> to a Bill, or None if unparseable.

        Feed format (from govbot build):
          <title>Tag1, Tag2 - repo - BILL TITLE</title>
          <link>https://example.com/.../bills/HB1234/metadata.json</link>
          <description><![CDATA[
            id: HB1234
            log:
              action:
                description: Some action text
                date: 2025-05-31
            bill:
              identifier: HB1234
              title: ACTUAL BILL TITLE
              abstract: ...
          ]]></description>
          <category>Biking</category>
          <guid>repo/.../bills/HB1234/logs/...json</guid>
        """
        import re

        def text(tag):
            el = item.find(tag)
            return el.text.strip() if el is not None and el.text else ""

        title_raw   = text('title')
        guid        = text('guid')
        description = text('description')
        # note: link is example.com placeholder in govbot feed — ignore it

        # ── Extract bill identifier ──────────────────────────────────────
        # govbot GUID format:
        #   il-legislation/country:us/state:il/sessions/104th/bills/HB2270/logs/...
        #   il-legislation/country:us/state:il/sessions/104th/bills/AM1030415/logs/...
        #
        # For HB/SB bills: use the GUID path segment directly.
        # For AM (amendment) bills: fall back to the title which contains the
        # underlying bill number as "HB NNNN" or "SB NNNN".
        # Title format: "Tag1, Tag2 - repo - BILL-TYPE IDENTIFIER: TITLE"
        #   e.g. "Housing, Transportation - il-legislation - APPOINT-ASHISH SHARMA"
        #   e.g. "Biking - il-legislation - HB 2454: BICYCLES-ROADWAYS"

        BILL_RE   = re.compile(r'\b([HS][BCR]\d+)\b', re.I)   # HB/SB/HR/SR
        AM_RE     = re.compile(r'\bAM(\d+)\b', re.I)           # amendment IDs
        GUID_BILL = re.compile(r'/bills/([A-Z]{2,3}\d+)/', re.I) # anything in /bills/.../

        bill_id = None

        # 1. Prefer standard bill IDs from GUID path
        gm = GUID_BILL.search(guid)
        if gm:
            raw = gm.group(1).upper()
            if BILL_RE.match(raw):
                bill_id = raw
            # If it's an AM id, try extracting HB/SB from title
            elif AM_RE.match(raw):
                tm2 = BILL_RE.search(title_raw)
                if tm2:
                    bill_id = tm2.group(1).upper()

        # 2. Fallback: scan title for HB/SB pattern
        if not bill_id:
            tm2 = BILL_RE.search(title_raw)
            if tm2:
                bill_id = tm2.group(1).upper()

        if not bill_id:
            # Skip silently — AM appointments, proclamations, etc.
            return None

        # ── Build ILGA URL from GUID (never trust the example.com link) ──
        num_only  = re.sub(r'[^\d]', '', bill_id)
        doc_type  = 'HB' if bill_id.startswith('H') else 'SB'
        ilga_base = (
            f"https://www.ilga.gov/legislation/BillStatus.asp"
            f"?DocTypeID={doc_type}&DocNum={num_only}&GAID=18&SessionID=114"
        )

        categories  = [c.text.strip() for c in item.findall('category') if c.text]
        chamber     = Chamber.HOUSE if bill_id.startswith('H') else Chamber.SENATE

        bill_title = action_desc = action_date_str = ''
        if description:
            tm  = re.search(r'\btitle:\s*(.+)$',       description, re.M)
            acm = re.search(r'\bdescription:\s*(.+)$', description, re.M)
            if tm:  bill_title  = tm.group(1).strip()
            if acm: action_desc = acm.group(1).strip()

        if not bill_title:
            parts = title_raw.split(' - ')
            bill_title = parts[-1].strip() if parts else title_raw

        committee_name = None
        if action_desc:
            cm = re.search(
                r'(?:assigned to|referred to|re-referred to)\s+(.+?)(?:\s+committee)?$',
                action_desc, re.I)
            if cm:
                committee_name = cm.group(1).strip()

        ad = action_desc.lower()
        reading = (BillReading.THIRD if 'third reading' in ad
                   else BillReading.SECOND if 'second reading' in ad
                   else BillReading.FIRST)

        return Bill(
            bill_number=bill_id, chamber=chamber, title=bill_title,
            sponsor='Unknown', next_reading=reading, subjects=categories,
            committee_hearing_date=None, committee_name=committee_name,
            ilga_url=ilga_base,
        )


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
        # Each bill lives in its own subdirectory with a metadata.json.
        # That single file contains the bill's title, subjects, actions,
        # sponsorships, and ILGA source URL — everything we need.
        # The other JSON files under each bill dir are govbot log-event
        # files; they contain no subject/category data and should be skipped.
        bill_files = list(data_path.glob("*/metadata.json"))

        print(f"📄 Found {len(bill_files)} bills (metadata.json files)")

        for bill_file in bill_files:
            
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
    """Download sample IL bills via the GitHub Contents API.

    Uses the GitHub API (which returns JSON with download_url fields) rather
    than trying to scrape a raw directory listing — raw.githubusercontent.com
    does not serve HTML indexes.
    """
    print("📥 Fetching sample IL bills via GitHub Contents API...")

    temp_dir = Path(tempfile.gettempdir()) / "witness-slip-test-data"
    temp_dir.mkdir(exist_ok=True)

    # GitHub Contents API for the il-legislation data repo
    api_url = (
        "https://api.github.com/repos/govbot-openstates-scrapers/il-legislation/contents/"
        "_data/il"
    )
    headers = {"Accept": "application/vnd.github+json"}
    github_token = os.getenv("GITHUB_TOKEN", "")
    if github_token:
        headers["Authorization"] = f"Bearer {github_token}"

    try:
        resp = requests.get(api_url, headers=headers, timeout=15)
        resp.raise_for_status()
        entries = resp.json()
    except Exception as e:
        print(f"⚠️  GitHub API request failed: {e}")
        entries = []

    downloaded = 0
    for entry in entries[:10]:  # grab up to 10 sample bills
        download_url = entry.get("download_url")
        if not download_url:
            continue
        filename = entry.get("name", download_url.split("/")[-1])
        try:
            file_resp = requests.get(download_url, timeout=15)
            if file_resp.status_code == 200:
                (temp_dir / filename).write_text(file_resp.text)
                print(f"  ✅ Downloaded {filename}")
                downloaded += 1
            else:
                print(f"  ⚠️  Skipped {filename} (HTTP {file_resp.status_code})")
        except Exception as e:
            print(f"  ⚠️  Failed {filename}: {e}")

    if downloaded == 0:
        print("❌ No sample bills downloaded. Verify the repo name/path and try again.")
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
                        'Transportation,Public Transit,Roads,Highways,Traffic,Commuter Rail,Metra,CTA,RTA').split(',')],
                    'recipients': [r.strip() for r in os.getenv('RECIPIENTS_TRANSPORTATION', '').split(',') if r.strip()]
                },
                'transit': {
                    'topics': [t.strip() for t in os.getenv('TOPICS_TRANSIT',
                        'Transit,Bus,Rail,Subway,Light Rail,Rapid Transit,Bus Rapid Transit,BRT,PACE,CTA,Metra,RTA').split(',')],
                    'recipients': [r.strip() for r in os.getenv('RECIPIENTS_TRANSIT', '').split(',') if r.strip()]
                },
                'biking': {
                    'topics': [t.strip() for t in os.getenv('TOPICS_BIKING',
                        'Bicycle,Biking,Bike Lane,Cycling,Micromobility,E-Bike,Scooter,Active Transportation').split(',')],
                    'recipients': [r.strip() for r in os.getenv('RECIPIENTS_BIKING', '').split(',') if r.strip()]
                },
                'safe_streets': {
                    'topics': [t.strip() for t in os.getenv('TOPICS_SAFE_STREETS',
                        'Pedestrian,Safe Streets,Vision Zero,Traffic Safety,Crosswalk,Speed Limit,Complete Streets,Sidewalk').split(',')],
                    'recipients': [r.strip() for r in os.getenv('RECIPIENTS_SAFE_STREETS', '').split(',') if r.strip()]
                },
                'housing': {
                    'topics': [t.strip() for t in os.getenv('TOPICS_HOUSING',
                        'Housing,Affordable Housing,Real Estate,Zoning,Land Use,Development,TOD,Transit-Oriented,Upzoning,ADU').split(',')],
                    'recipients': [r.strip() for r in os.getenv('RECIPIENTS_HOUSING', '').split(',') if r.strip()]
                },
                'all_recipients': [r.strip() for r in os.getenv('RECIPIENTS_ALL', '').split(',') if r.strip()],
                'tracked_bills': [b.strip() for b in os.getenv('TRACKED_BILLS', '').split(',') if b.strip()]
            },
            'settings': {
                'urgency_threshold_days': int(os.getenv('URGENCY_THRESHOLD_DAYS') or '7')
            }
        }

def send_email(subject: str, plain_body: str, html_body: str, recipients: List[str]) -> None:
    """Send email via SMTP (MailHog in local dev)."""
    if not recipients:
        return

    host = os.getenv("SMTP_HOST", "localhost")
    port = int(os.getenv("SMTP_PORT") or "1025")
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
    
    # Maps subscription key → (emoji label, env-var suffix)
    SUBSCRIPTION_CATEGORIES = [
        ('tracked_bills',  None,           None),          # handled separately
        ('transportation', '🚗 Transportation', 'TRANSPORTATION'),
        ('transit',        '🚇 Transit',        'TRANSIT'),
        ('biking',         '🚲 Biking',          'BIKING'),
        ('safe_streets',   '🚶 Safe Streets',    'SAFE_STREETS'),
        ('housing',        '🏘️ Housing & Development', 'HOUSING'),
    ]

    def _route_bills(self, bills: List[Bill]) -> Dict:
        """Route bills into urbanist topic buckets.

        A bill can appear in multiple categories (a transit-oriented housing
        bill belongs in both Transit and Housing).  Tracked bills are always
        listed first regardless of topic.
        """
        subs = self.config['subscriptions']
        routed = {}

        # Specific bill tracking (pinned at the top)
        for bill in bills:
            if bill.bill_number in subs['tracked_bills']:
                routed.setdefault('🎯 Tracked Bills', []).append(bill)

        # Topic categories — a bill may appear in more than one
        for key, label, _ in self.SUBSCRIPTION_CATEGORIES:
            if label is None:
                continue
            sub = subs.get(key, {})
            if not sub.get('recipients') and not subs.get('all_recipients'):
                continue
            matched = [b for b in bills if b.matches_topics(sub.get('topics', []))]
            if matched:
                routed[label] = matched

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
    parser = argparse.ArgumentParser(
        description="IL Urbanist Witness Slip Notifier"
    )
    parser.add_argument('--mode', choices=['github-action', 'local'], default='local')
    # --- Input source (pick one) ---
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        '--feed',
        metavar='PATH',
        help='Path to the RSS feed produced by `govbot build` (preferred)'
    )
    group.add_argument(
        '--data-dir',
        metavar='PATH',
        default='data/il',
        help='Legacy: parse raw OpenStates JSON files directly'
    )
    group.add_argument(
        '--sample',
        action='store_true',
        help='Download a small sample from GitHub for local smoke-testing'
    )
    args = parser.parse_args()

    print("\n" + "="*70)
    print("🚲🚇🏘️ IL URBANIST WITNESS SLIP NOTIFIER")
    print("="*70 + "\n")

    # Load config from environment
    config = EnvironmentConfig.load()
    print(f"👤 User: {config['user']['name']}")
    print(f"🏢 Organization: {config['user']['organization']}\n")

    # --- Parse bills from the chosen source ---
    if args.feed:
        # PRIMARY PATH: govbot RSS feed (clone → tag → RSS already done)
        print("📡 Input mode: govbot RSS feed")
        bills = GovbotFeedParser.parse_feed(args.feed)
    elif args.sample:
        # TESTING PATH: pull a handful of bills from GitHub
        print("🧪 Input mode: sample download")
        sample_dir = fetch_sample_bills()
        bills = OpenStatesParser.parse_data_directory(sample_dir)
    else:
        # LEGACY PATH: raw OpenStates JSON directory
        print(f"📂 Input mode: raw data directory ({args.data_dir})")
        bills = OpenStatesParser.parse_data_directory(args.data_dir)
    

    # ── Merge STC tracked bills first (before any early-exit) ─────────────────────
    # This ensures tracked bills always appear in the digest even when the
    # govbot feed is stale, empty, or contains only amendment/appointment items.
    import re as _re
    feed_ids = {b.bill_number for b in bills}
    stc_added = 0
    for bill_num, (category, stc_desc, stance) in STC_TRACKED_BILLS.items():
        norm = _re.sub(r'\s+', '', bill_num.upper())
        if norm not in feed_ids:
            _chamber = Chamber.HOUSE if norm.startswith('H') else Chamber.SENATE
            _num     = _re.sub(r'[^\d]', '', norm)
            _dt      = 'HB' if _chamber == Chamber.HOUSE else 'SB'
            stub = Bill(
                bill_number=norm, chamber=_chamber,
                title=stc_desc, sponsor='Unknown',
                next_reading=BillReading.FIRST,
                subjects=[category],
                ilga_url=(
                    f"https://www.ilga.gov/legislation/BillStatus.asp"
                    f"?DocTypeID={_dt}&DocNum={_num}&GAID=18&SessionID=114"
                ),
            )
            stub.stance = stance
            bills.append(stub)
            feed_ids.add(norm)
            stc_added += 1

    # Tag stance on all bills (feed bills that match STC list get their stance too)
    for b in bills:
        if not hasattr(b, 'stance'):
            info = STC_TRACKED_BILLS.get(b.bill_number)
            b.stance = info[2] if info else 'Proponent'

    feed_bills = len(bills) - stc_added
    print(f"📊 Feed bills parsed: {feed_bills} | STC stubs added: {stc_added} | Total: {len(bills)}")

    if not bills:
        msg = "No bills found and no tracked bills configured."
        print(f"⚠️  {msg}")
        if args.mode == 'github-action':
            Path('notifications_output.txt').write_text(msg + '\n')
            Path('notifications_output.html').write_text(f'<p>{msg}</p>')
            Path('witness_slip_notifications.json').write_text('[]')
        sys.exit(0)

    # ── Build actionable list ─────────────────────────────────────────────────────────
    # In feed mode: include all bills with at least one tag (STC stubs always
    # have a tag so they're always included). In data-dir mode: use date window.
    # Only include bills that matched an urbanist topic (have a subjects tag).
    # STC stubs always have a subject set, so they're always included.
    # In --data-dir mode, next_reading defaults to FIRST for every bill (no
    # reliable hearing-date data in metadata.json), so we cannot use a date
    # window — topic matching is the only meaningful filter.
    URBANIST_TOPICS = {'Housing', 'Biking', 'Safe Streets', 'Transit', 'Transportation'}
    now = datetime.now()
    if args.feed:
        actionable = [b for b in bills if b.subjects]
    else:
        actionable = [b for b in bills if
                      b.subjects and set(b.subjects) & URBANIST_TOPICS]

    if not actionable:
        msg = "No actionable bills (no tagged bills in feed and STC list is empty)."
        print(f"⚠️  {msg}")
        if args.mode == 'github-action':
            Path('notifications_output.txt').write_text(msg + '\n')
            Path('notifications_output.html').write_text(f'<p>{msg}</p>')
            Path('witness_slip_notifications.json').write_text('[]')
        sys.exit(0)

    # ── Group by category for display ───────────────────────────────────────────────
    from collections import defaultdict
    by_category = defaultdict(list)
    for b in actionable:
        cat = b.subjects[0] if b.subjects else 'Other'
        by_category[cat].append(b)

    CAT_ORDER = ['Housing', 'Biking', 'Safe Streets', 'Transit', 'Transportation', 'Other']
    STANCE_EMOJI = {'Proponent': '👍', 'Opponent': '🚫'}

    lines_txt  = []
    lines_html = ['<html><body>',
                  '<h2>🚲🚇🏘️ IL Urbanist Bills — Witness Slip Digest</h2>',
                  '<p><em>All bills below have active ILGA BillStatus pages. ']
    lines_html += ['Witness slip filing opens when a committee hearing is scheduled.</em></p>']

    total = 0
    for cat in CAT_ORDER:
        cat_bills = by_category.get(cat, [])
        if not cat_bills:
            continue
        lines_txt.append(f'\n{cat.upper()} ({len(cat_bills)} bills)')
        lines_txt.append('=' * 50)
        lines_html.append(f'<h3>{cat} ({len(cat_bills)} bills)</h3><ul>')
        for b in sorted(cat_bills, key=lambda x: x.bill_number):
            slip_url  = b.get_witness_slip_url()
            stance    = getattr(b, 'stance', 'Proponent')
            emoji     = STANCE_EMOJI.get(stance, '👍')
            hearing   = (
                b.committee_hearing_date.strftime(' | Hearing: %b %-d')
                if b.committee_hearing_date else ' | No hearing scheduled'
            )
            lines_txt.append(
                f'  {emoji} {b.bill_number}: {b.title[:70]}{hearing}\n'  # noqa
                f'     Stance: {stance} | Witness slip: {slip_url}'
            )
            lines_html.append(
                f'<li><strong>{b.bill_number}</strong> ({stance}) '  # noqa
                f'— {b.title[:80]}{hearing}<br>'
                f'<a href="{slip_url}">📝 File Witness Slip</a></li>'
            )
            total += 1
        lines_html.append('</ul>')

    lines_html.append('</body></html>')
    plain = '\n'.join(lines_txt)
    html  = '\n'.join(lines_html)

    print(f"✅ Digest ready: {total} bills across {len(by_category)} categories")
    for cat, cat_bills in sorted(by_category.items()):
        print(f"   {cat}: {len(cat_bills)} bills")

    # ── Write output files ─────────────────────────────────────────────────────────────
    json_output = [
        {'bill_number': b.bill_number,
         'chamber': b.chamber.value,
         'title': b.title,
         'category': b.subjects[0] if b.subjects else 'Other',
         'stance': getattr(b, 'stance', 'Proponent'),
         'witness_slip_url': b.get_witness_slip_url(),
         'committee_hearing_date': (
             b.committee_hearing_date.isoformat()
             if b.committee_hearing_date else None),
         'committee_name': b.committee_name,
         'source': 'stc_tracked' if b.bill_number in {_re.sub(r'\s+','',k.upper()) for k in STC_TRACKED_BILLS} else 'feed',
        }
        for b in actionable
    ]

    if args.mode == 'github-action':
        Path('notifications_output.txt').write_text(plain)
        Path('notifications_output.html').write_text(html)
        Path('witness_slip_notifications.json').write_text(
            json.dumps(json_output, indent=2, ensure_ascii=False)
        )
        print("✅ Output files written")
    else:
        print(plain)


if __name__ == "__main__":
    main()
