# Known Problems

This directory tracks known issues with state scrapers and our formatter code.

## 📂 Organization

- **`scraper/`** - Issues with OpenStates scrapers (upstream)
- **`formatter/`** - Issues with our formatting code

## 🔴 Active Scraper Issues

### Infrastructure/Network Issues

- [Connecticut (ct) - FTP Server Timeout](scraper/ct.md)

### Docker Image Issues

- [California (ca) - Missing sqlalchemy Dependency](scraper/ca.md)

## 🟡 Active Formatter Issues

None documented yet.

## 📝 Adding New Issues

1. Create a new `.md` file in the appropriate folder (`scraper/` or `formatter/`)
2. Include: status, error message, root cause, workaround/solution
3. Update this README to link to the new issue
4. Use clear titles: `{state}_{issue_description}.md`

---

**Last Updated:** October 23, 2025
