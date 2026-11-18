---
name: Govbot
description: Every U.S. legislature's activity as open data you can clone, query and build on.
tags: [Legislation, Open Data, Rust, Python, AI, DuckDB, GitHub Actions]
needs: Looking for scraper/data engineers, Rust and Python devs, and front-end/design help
status: active
website: https://chihacknight.github.io/govbot/
repo: https://github.com/chihacknight/govbot
---

# Govbot

Govbot turns the activity of 56 legislatures — all 50 states, Congress, DC and 4 territories — into
git repositories anyone can clone in under a minute, tag with free local AI models, and query with
SQL. On top of that data we run a public website (bills, hearings, Illinois elections), Bluesky bots
that post bills by topic, and a Claude Desktop extension.

## What we're working on

- **Moving scraping to a new system.** The Open States scrapers are paused while we migrate, so
  fresher, more complete data is the top priority ([#111](https://github.com/chihacknight/govbot/issues/111),
  [#33](https://github.com/chihacknight/govbot/issues/33), [#34](https://github.com/chihacknight/govbot/issues/34)).
- **Govbot for Claude** — an MCP server so you can ask questions about legislation from Claude
  Desktop ([#25](https://github.com/chihacknight/govbot/issues/25)).
- **More of government** — executive actions, city councils and full bill text
  ([#28](https://github.com/chihacknight/govbot/issues/28), [#30](https://github.com/chihacknight/govbot/issues/30),
  [#31](https://github.com/chihacknight/govbot/issues/31)).
- **Know Your Ballot**, a nonpartisan voter guide built on Govbot's elections data.

## What we're using

- **Rust** — the `govbot` command-line tool (clone, logs, tag, load, build)
- **Python** — scrapers and data pipelines for hearings, elections, maps and summaries
- **TypeScript** — the MCP server for Claude Desktop
- **DuckDB** — SQL across every state at once
- **GitHub Actions + GitHub Pages** — every pipeline runs on free CI; the site is built with mdBook
- **Git repos as datasets** — one repo per jurisdiction in the [govbot-data](https://github.com/orgs/govbot-data/repositories) org

## What new people can work on

- Pick a [`good first issue`](https://github.com/chihacknight/govbot/issues?q=is%3Aopen+label%3A%22good+first+issue%22):
  publish to Homebrew ([#19](https://github.com/chihacknight/govbot/issues/19)) or npm
  ([#20](https://github.com/chihacknight/govbot/issues/20)), add executive actions
  ([#28](https://github.com/chihacknight/govbot/issues/28)), or add a Chicago City Council catalog
  ([#30](https://github.com/chihacknight/govbot/issues/30)).
- **Build something on the data.** Clone a state and make a bot, a map or an analysis — see the
  [Quick Start](README.md#quick-start).
- **Check the data.** Compare a state's bills against its legislature's website and report what's
  missing or wrong.
- **Improve the docs** for newcomers ([#27](https://github.com/chihacknight/govbot/issues/27)).

Come find us at Chi Hack Night, or open an issue to say hello.
