# govbot

`govbot` enables distributed data anaylsis of government updates via a friendly terminal interface. Git repos function as datasets, including the legislation of all 47 states/jurisdictions.

## 1 Line Install

```bash
sh -c "$(curl -fsSL https://raw.githubusercontent.com/windy-civi/toolkit/main/actions/govbot/scripts/install-nightly.sh)"
```

```bash
govbot # to see help
govbot clone # to show
govbot clone {{locale}} {{locale}} # to download specific items
govbot delete {{locale}} # to delete specific items
govbot delete all # to delete everything
```

## Contribute

This is Rust land, & it uses `just`. `just setup` to start, and then `just govbot ...` to develop the cli.

### Prerequisites

1. **Rust & Cargo**: Install the [Rust Toolchain](https://rustup.rs/)
2. **Just**: Install the task runner: `cargo install just`

### Development Workflow

Use `just govbot ...` as your cli "dev" environment.

### Other Useful Commands

- `just` - See all available tasks
- `just test` - Run all tests
- `just review` - Review snapshot test changes
- `just mocks [LOCALES...]` - Update mock data for testing

We build snapshots off `examples`. Add examples to make a test.

## Advanced

```bash
GOVBOT_REPO_URL_TEMPLATE="https://gitsite.com/org/{locale}.git" govbot ...
```
