# 🏛️ Windy Civi

**AI-Based Updates For Local / State / Federal Bills**

[windycivi.com](https://windycivi.com)

---

## 🎯 Legislative Data Pipeline

**👉 The active development work for the legislative data pipeline is in the `toolkit/` folder:**

### **`toolkit/`** ⭐ (in this repository)

This folder contains the **core toolkit** that powers all state and federal legislative data pipelines. It includes:

- **GitHub Actions** for scraping, formatting, and text extraction
- **Python modules** for processing OpenStates data into blockchain-style structures
- **Documentation** and templates for setting up state pipelines
- **Incremental processing** logic to handle 50+ US jurisdictions efficiently

### What It Does

The toolkit provides a **GitHub Actions-powered pipeline** that:

1. **Scrapes** legislative data from OpenStates scrapers
2. **Formats** it into a versioned, blockchain-style structure
3. **Extracts** full text from bills (PDFs, XMLs, HTMLs)
4. **Monitors** data quality and tracks orphaned bills
5. **Auto-saves** progress to survive GitHub's 6-hour timeout limits

### Key Features

- 🔄 **Incremental Processing** - Only processes new/updated bills
- 💾 **Auto-Save Failsafe** - Commits every 30 minutes during long runs
- 🩺 **Data Quality Monitoring** - Tracks orphaned bills and data issues
- 🔗 **Bill-Event Linking** - Automatically connects hearings to bills
- ⏱️ **Timestamp Tracking** - Two-level timestamps for logs and extraction
- 🎯 **Multi-Format Text Extraction** - XML → HTML → PDF with fallbacks

### State Pipeline Repositories

The toolkit is used by **50+ state pipeline repositories** under the [windy-civi-pipelines](https://github.com/orgs/windy-civi-pipelines) organization, each running nightly to collect and process legislative data for a specific US state or territory.

---

## 📁 Repository Structure

This is the **main repository** for the Windy Civi project. It contains:

- **Monorepo structure** with multiple components:

  - **`toolkit/`** ⭐ - Legislative data pipeline (scraping, formatting, text extraction)
    - Powers 50+ state pipeline repositories
    - GitHub Actions for automated data processing
    - See `toolkit/README.md` for full documentation
  - `web-app` - Progressive Web App (React/Tailwind/TypeScript/Vite)
  - `native-app` - Expo React Native App
  - `scraper` - Data scraping and GPT summarization
  - `storage` - GitHub releases and filesystem data management
  - `workflow` - Workflow automation
  - `bluesky-bot` - Social media bot integration
  - `domain` - Core business logic (domain-driven design)

- **Development setup** optimized for GitHub Codespaces
- **CI/CD workflows** for all components

---

## 🌍 Project Vision

**Windy Civi** is a civic tech initiative based in Chicago focused on making legislative data transparent, permanent, and accessible. The goal is to create a **decentralized, verifiable record** of bills, votes, and actions—structured like a blockchain for traceability and accountability.

Democracy relies on accessible information. Legislative data in the U.S. is often fragmented, inconsistently formatted, and easily lost when administrations change or sites go offline. Windy Civi solves that problem by creating a permanent, public archive of civic data.

---

## 🚀 Getting Started

### For the Legislative Data Pipeline

👉 **See the [`toolkit/`](toolkit/) folder** in this repository:

- Installation instructions (`toolkit/README.md`)
- Setup guides for state pipelines
- Example workflows
- Technical documentation

### For the Full Application

**Easiest:** Use GitHub Codespaces. The development environment is pre-configured.

**Local Development:**

```bash
# Navigate to the component you want to work on
cd web-app  # or native-app, scraper, etc.

# Install dependencies
npm install  # or pip install, etc.
```

---

## 🧠 Development Philosophy

This project was developed with the help of AI tools like **ChatGPT** and **Cursor**, used as active collaborators rather than shortcuts. They were especially helpful when exploring architecture decisions, discussing different ways to structure functions, design data flows, and think through tradeoffs.

The process dramatically improved debugging skills by breaking problems into smaller conversations and exploring edge cases in real time. Coding with AI has been less about automation—and more about becoming a sharper, more reflective engineer.

---

## 🤝 Contributing

We welcome collaborators, contributors, and curious minds!

- 🐙 [Open an Issue](https://github.com/windy-civi/windy-civi/issues) in this repo
- 📬 Submit a PR
- 🌱 Help design future civic pipelines
- 💬 Join the conversation about civic tech

---

## 📜 License

MIT License - feel free to use, modify, and build upon this work.

**Built with care, code, and curiosity.** 🏛️✨

---

## 🔗 Quick Links

- **Legislative Data Pipeline**: [`toolkit/`](toolkit/) folder in this repo ⭐
- **State Pipelines**: [windy-civi-pipelines organization](https://github.com/orgs/windy-civi-pipelines)
- **Website**: [windycivi.com](https://windycivi.com)

---

_Part of the [Windy Civi](https://github.com/windy-civi) ecosystem - Making civic data transparent and accessible._

