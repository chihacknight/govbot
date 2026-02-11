# 2025 Bill Blockchain

## Open Civic Data Blockchain Proposal

This proposal outlines a decentralized, peer-to-peer system for managing and publishing civic data using a blockchain-like append-only log. Built on the Open Civic Data schema and powered by Git, this architecture enables transparency, tamper-resistance, and flexibility in how public information is stored, shared, and consumed. By treating government data as a series of verifiable, timestamped events, we create an ecosystem where organizations and individuals can build custom civic feeds, automate updates, and uncover hidden dynamics in governance—all without relying on centralized servers.

## Why Use a Hashed Append-Only Log?

- 🔐 **Truly Peer-to-Peer**  
  Everyone keeps their own copy of the data—no central server needed, no extra cost.

- 📜 **The Constitution Is Basically a Blockchain**  
  Government changes through amendments. Our log reflects this: permanent, append-only, and transparent.

- 💻 **Highly Tailored Custom Feeds Built With Code + AI**  
  Composable event logs will be easy to filter, tag, and summarize. Orgs can compose those feeds too in order to make highly tailored feeds for publishing.

- 🤖 **Publish Everywhere with Bots**  
  Organizations can automate updates to any number of platforms easily, from Blue Sky Bot Alert posters —think Reddit replies or Bluesky posts—on top of each other. In addition, we can make tooling to have public RSS feeds that can then be imported by news organizations.

- ⛓️ **Blockchain without the Cringe or Cost**  
  Blockchain hashes + public key signatures let users verify data themselves without expensive proof algorithms. For IDs, [Decentralized Identifiers](https://www.w3.org/TR/did-1.0/) are the new standard, and interop with Bluesky.

- ☎️ **Network Agnostic**  
  Supports everything: peer-to-peer, pub-sub, polling, WebRTC, email, RSS, push—notifications, etc. They will all work naturally.

- 📱 **Our App Becomes A Glorified P2P Feed Reader With Civic Tendencies**  
  By being a P2P feed reader with special features around civic data, we simplify the app itself, and allow others to make their own client apps.

- 🛜 **RSS Feeds Just Work**  
  Feed-based design lets us easily pull in existing sources like Executive Orders or court decisions via RSS, and allows organizations to pull news website feeds.

- ⏪ **Bonus: Reveal Power Dynamics**  
  Replay legislative logs to uncover hidden patterns—who votes when, with whom, and under whose influence.

## Why [Open Civic Data](https://open-civic-data.readthedocs.io/en/latest/) as the Base Schema?

- 🤝 **Plug Into the Civic Tech Ecosystem**  
  Uses familiar Open Civic Data formats, making it easy to integrate with existing tools and scrapers.

- 🔄 **Reuse Existing Data**  
  Works with platforms like OpenStates and Councilmatic, giving us access to many data sources.

## Why Git for Data Storage?

- 📁 **Folders + Files = Maximum Portability**  
  The most universal data structure—easy to read, edit, and share across tools and platforms.

- 🔄 **Git Is Already Peer-to-Peer**  
  Git is built on a distributed log. `git pull` works seamlessly in our app and AI workflows.

- 🌐 **GitHub = Easy Browsing**  
  Markdown rendering and file previews make GitHub a friendly UI for exploring without needing to clone. We can also expose RSS feeds via GHPages.

- 🧩 **Submodules Keep Repos Lean**  
  Git submodules let us split large datasets across repos, so no single repo gets bloated.

## Folder Structure + Filename Convention

```
/open-civic-data-blockchain/
├── country:us/                                 # United States
│   ├── state:il/                               # Illinois state
│   │   ├── sessions/                           # Legislative sessions
│   │   │   ├── ocd-session/country:us/state:il/2023-2024/  # Full OCD session ID
│   │   │   │   ├── bills/                      # Bills in this session
│   │   │   │   │   ├── sb1234/                 # Senate Bill 1234
│   │   │   │   │   │   ├── logs/               # Event logs folder
│   │   │   │   │   │   │   ├── 20240115T123045Z_session_bill_created.json  # Initial bill creation in session
│   │   │   │   │   │   │   ├── 20240115T123045Z_metadata_created.json      # Initial metadata creation
│   │   │   │   │   │   │   ├── 20240117T143022Z_metadata_updated.json      # Metadata update with field mask
│   │   │   │   │   │   │   ├── 20240117T143156Z_sponsor_added.json         # Sponsors added
│   │   │   │   │   │   │   ├── 20240120T092133Z_version_added.json         # Version document added
│   │   │   │   │   │   │   ├── 20240130T152247Z_action_added.json          # Action recorded
│   │   │   │   │   │   │   ├── 20240215T103045Z_doc_added.json             # Supporting document added
│   │   │   │   │   │   │   ├── 20240315T140011Z_vote_initiated.json        # Vote started
│   │   │   │   │   │   │   ├── 20240315T143022Z_vote_updated.json          # Vote partial results
│   │   │   │   │   │   │   └── 20240315T150537Z_vote_finalized.json        # Vote complete
│   │   │   │   │   │   └── files/              # Raw file storage
│   │   │   │   │   │       ├── bill_introduced.pdf      # Original version document
│   │   │   │   │   │       ├── bill_amended.pdf         # Amended version document
│   │   │   │   │   │       └── fiscal_note.pdf          # Supporting document
│   │   │   │   │   ├── hb0789/                 # House Bill 789
│   │   │   │   │   │   ├── logs/               # Event logs folder
│   │   │   │   │   │   │   ├── 20240118T090023Z_session_bill_created.json  # Initial bill creation in session
│   │   │   │   │   │   │   ├── 20240118T090023Z_metadata_created.json      # Initial metadata creation
│   │   │   │   │   │   │   └── ...
│   │   │   │   │   │   └── files/              # Raw file storage
│   │   │   │   │   │       └── ...
│   │   │   │   │   └── ...
│   │   │   │   └── events/                     # Events for this session
│   │   │   │       ├── 2024-04-15-senate-appropriations-hearing.json  # Senate committee hearing
│   │   │   │       ├── 2024-02-22-house-floor-session.json            # House floor session
│   │   │   │       └── ...
│   │   │   ├── ocd-session/country:us/state:il/2021-2022/  # Previous session
│   │   │   │   └── ...
│   │   │   └── ...
│   │   └── events/                            # Events not tied to a specific session
│   │       ├── 2024-07-15-joint-commission-meeting.json  # Joint commission meeting
│   │       ├── 2024-08-20-special-task-force.json        # Special task force meeting
│   │       └── ...
│   ├── state:ca/                               # California state
│   │   └── ...
│   └── state:ny/                               # New York state
│       └── ...
└── country:ca/                                 # Canada
    └── ...
```

## Git Architecture

We plan to auto-generate many git repos.

### Session Git Repo

This repo should be a blockchain-like append only log, making syncing data as easy as `git pull`.

**Question:** what about the files like PDFS? They feel right to keep in here as a copy, but also, would balloon the size of these. Maybe yet another submodule for session files?

```
/
├── README.md                  # Session-specific information
├── bills/                     # Bills in this session
│   ├── sb1234/                # Senate Bill 1234
│   │   ├── logs/              # Event logs folder
│   │   │   ├── 20240115T123045Z_session_bill_created.json
│   │   │   ├── 20240115T123045Z_metadata_created.json
│   │   │   ├── 20240117T143022Z_metadata_updated.json
│   │   │   └── ...
│   │   └── files/             # Raw file storage
│   │       ├── bill_introduced.pdf
│   │       ├── bill_amended.pdf
│   │       └── fiscal_note.pdf
│   ├── hb0789/                # House Bill 789
│   │   ├── logs/
│   │   │   └── ...
│   │   └── files/
│   │       └── ...
│   └── ...
└── events/                    # Events for this session
    ├── 2024-04-15-senate-appropriations-hearing.json
    ├── 2024-02-22-house-floor-session.json
    └── ...
```

### Locale Git Repo
Overall locale repo (also generated). Contain links to git submodules that have event logs for different sessions/events. Will also contain scripts to rebuild data into Open Civic Data formats.

```
ocd-blockchain-illinois/
├── .gitmodules
├── README.md
├── scripts/
│   ├── scrape.py # Shortcut to directly scrape for this locale
|   └── rebuild.py # To rebuild OCD data from blockchain logs
├── sessions/
│   ├── ocd-blockchain-illinois/ocd-session/country:us/state:il/2023-2024/
│   ├── ocd-blockchain-illinois/ocd-session/country:us/state:il/2021-2022/
│   └── ocd-blockchain-illinois/ocd-session/country:us/state:il/2019-2020/
└── events/
   ├── 2022-2026/
   ├── 2018-2022/
   └── 2014-2018/
```

### Main Repo
The primary repo (also generated) that people can clone to get all civic data easily via the submodules.

```
open-civic-data-blockchain/
├── .gitmodules
├── README.md
├── scripts/
│   ├── update_all.sh
│   ├── integrity_check.py
│   └── generate_cross_jurisdictional_report.py
└── jurisdictions/
    ├── country:us/
    │   ├── state:il/                           # Illinois submodule
    │   ├── state:ca/                           # California submodule
    │   ├── state:ny/                           # New York submodule
    │   ├── district:dc/                        # Washington DC submodule
    │   ├── county:us/state:va/fairfax/         # Fairfax County submodule
    │   └── place:us/state:tx/austin/           # City of Austin submodule
    ├── country:ca/
    │   ├── province:on/                        # Ontario province submodule
    │   └── province:bc/                        # British Columbia submodule
    └── country:uk/
        ├── england/                            # England submodule
        └── scotland/                           # Scotland submodule
```

## TODO List

- [ ] **Timestamps: Scrape-Oriented vs. Gov-Oriented**  
  Are log timestamps the time we scraped the data, or the time of the actual government update?  
  What if a specific event doesn't have a timestamp?  
  ➤ [Open Civic Data also discussed this](https://open-civic-data.readthedocs.io/en/latest/proposals/0101.html)
- [ ] **Unique IDs**  
  OpenStates uses a lot of generated UUIDs. Ideally, our folder/file structure and naming conventions should follow official legislative data.  
  - **Jurisdiction ID**: Follows OCD naming convention — `country:us/state:fl/government`
  - **Session ID**: TODO
  - **Bill ID**: `jurisdiction_id/sessions/:session_id/bill.identifier` — use official ID like `HB250`
  - **Vote Event ID**: TODO
  - **Person ID**: TODO
  - **Event ID**: TODO
- [ ] **Bill Folder + Filename Convention**  
  - `bill.metadata`: `bill_id/log/metadata_update_{TODO}.json`
  - `bill.actions`: `bill_id/log/action_{TODO}.json`
  - `bill.votes`: `bill_id/log/vote_{TODO}.json`
  - `bill.sponsors`: `bill_id/log/sponsor_update_{TODO}.json`
  - `bill.versions`:  
    - File: `bill_id/files/version_{TODO}.pdf`  
    - Log: `bill_id/log/version_add_{TODO}.json` (we can extract PDF content to JSON)
  - `bill.documents`:  
    - File: `bill_id/files/documents_{TODO}.pdf`  
    - Log: `bill_id/log/document_add_{TODO}.json` (we can extract PDF content to JSON)
- [ ] **Event Folder Convention**  
  Events tied to sessions should live inside the session folder.  
  Out-of-session events: can we define a reliable alternate time span for organization?
- [ ] **How to Handle Metadata Changes**  
  Metadata (like `bill`) may change from scrape to scrape.  
  Use `fieldMask` for lightweight updates, or consider JSON Patch.  
  ➤ https://jsonpatch.com  
  ```json
  // bill.metadata_events
  {
    "fieldMask": ["from_organization"],
    "bill": {
      "from_organization": ""
    }
  }
  ```

## Environment Setup

For now, we aren't doing any coding that touches the previous code. All code/decisions should be in this `scraper_next` folder as an isolated experiment. If you don't have git access, message @sartaj.

### Easy: Download Data and Explore With SQL Explorers

- [OpenState Illinois Scraper Output Files](https://chihacknight.slack.com/files/U08L58C7ZTJ/F08NL4DGGSU/il_openstates.zip)
- [State/Federal OpenStates Data Explorer](https://jstrieb.github.io/link-lock/#eyJ2IjoiMC4wLjEiLCJlIjoia1V2WEx4YUJnWlUzaXFYODdGbTM4TEd6ajVKVXYyK01tVUxFWXBjSHpoalBqZEZRVE4vRGFGU2hZRjRpRTdxMjBWU3poaS9RNG1wNiIsInMiOiJUTnROd2J3dHNxdjQrSEdlVnV3SzhRPT0iLCJpIjoieEZoK2xtZXJlZTRRMk1JQSJ9)
  - password is ChiHackNight closing group phrase all lowercase
- [Chicago OCD Data Explorer](https://puddle.datamade.us/chicago_council-347e82e) Explore Councilmatic PG Dump for Chicago OCD data

### Advanced: Running Scrapers / Importing PG Dumps
- Open States
  - [via Scraper](https://docs.openstates.org/contributing/scrapers/#running-your-first-scraper). We are using this for v1. [By running the scrapers directly](https://github.com/openstates/openstates-scrapers), data will be much more up to date as it scrapes data directly. It also allow us to run certain scrapers, like USA, multiple times a day.
  - [via SQL Dump](https://open.pluralpolicy.com/data/), which updates every few days, and has bill full text, in addition to a lot of other content like maps data.
- [Chicago SQL Dump](https://github.com/datamade/chicago-council-scrapers/releases). This updates every night and is managed by Datamade, who we have already been collaborating with on Chicago data. They also do stuff like AI summaries that we can pre-pull.

## Prior Art

- [Washington DC made Github](https://github.com/DCCouncil/law-xml) their official law source of truth. It looks immutable.
- [How append-only logs](https://scuttlebot.io/more/protocols/secure-scuttlebutt.html) are used in p2p/blockchain applications.
- [Beginners guide](https://www.kurrent.io/event-sourcing) to event sourced databases and their benefits.
- [Bluesky LGBTQ+ Legislation Alerts](https://bsky.app/profile/legialerts.org) This incredible team has manually created a system that I think we can make tooling for that they would potentially want to use.

## Communications

- [Discussion via Slack](https://chihacknight.slack.com/archives/C047500M5RS/p1744230231887699)
- [Task Board via Slack](https://chihacknight.slack.com/lists/T04KM9VQY/F07ECPCHH5M?view_id=View08NQ33E5R7)
- (this file) [Collaborative Brainstorming via Git](https://github.com/windy-civi/windy-civi/blob/60-blockchain-open-civic-data/scraper_next/readme.md): Feel free to edit.
