# Web quality skills (vendored)

Twelve Claude Code skills for measuring and improving the site's speed,
Core Web Vitals, accessibility, SEO and best practices. They're copied into
the repo (not installed per machine) so every contributor and every Claude
session gets the same version. Each folder keeps its MIT licence.

| Skills | From | Commit |
|---|---|---|
| performance, core-web-vitals, accessibility, seo, best-practices, web-quality-audit | [addyosmani/web-quality-skills](https://github.com/addyosmani/web-quality-skills) | `afa8da9` |
| webperf, webperf-core-web-vitals, webperf-loading, webperf-interaction, webperf-media, webperf-resources | [nucliweb/webperf-snippets](https://github.com/nucliweb/webperf-snippets) | `95b33f1` |

**Use them:** ask Claude Code to "audit performance", "fix Core Web Vitals", "run an
accessibility review" or "measure LCP on /2027-02/chicago", or name one (`/performance`).
The webperf-* skills run deterministic in-page measurements: with Chrome DevTools MCP,
or headless with `npx webperf-snippets <url> --snippet <Name> --json` (needs Playwright).

**Measure first, both ways:** lab (Lighthouse, mobile profile) for what to fix, and
field data (CrUX, real visitors) for whether it matters. Low-traffic pages may have no
CrUX data; then the lab numbers are the guide.

**Update:** copy the `skills/<name>` folders from the newer commit over these and
change the commit above. Read the diff first: skills are instructions Claude follows.
