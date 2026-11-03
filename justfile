# govbot repo-level tasks (issue #24: AI-onboardable dev workflows)
# Install just: cargo install just  (or https://just.systems)
# Then run: just --list
# Per-action workflows live in actions/govbot/justfile; this file covers the
# offline Python suites + delegation so agents can discover and run everything
# from the repo root.

# Default task: show help
default:
    @just --list

# Run all offline Python test suites (stdlib only, no network)
test:
    #!/usr/bin/env bash
    set -e
    PY="$(command -v python3 || command -v python)"
    echo "==> scrape-hearings"; "$PY" actions/scrape-hearings/test_scrape_hearings.py
    echo "==> scrape-elections"; "$PY" actions/scrape-elections/test_scrape_elections.py
    echo "==> people roster"; "$PY" scripts/test_build_people_roster.py
    echo "==> dashboard tags"; "$PY" scripts/test_dashboard_tags.py
    echo "==> scrape-maps self-test"; "$PY" actions/scrape-maps/main.py --self-test
    echo ""
    echo "All offline Python suites passed."

# Rust CLI checks: fmt + clippy + snapshot tests (needs Rust toolchain + just)
check:
    #!/usr/bin/env bash
    set -e
    if ! command -v cargo &> /dev/null; then
        echo "Rust/Cargo not installed (see https://rustup.rs/) — skipping Rust checks."
        exit 0
    fi
    cd actions/govbot && just check

# Run the Rust CLI test suite only (needs Rust toolchain)
test-govbot:
    #!/usr/bin/env bash
    set -e
    if ! command -v cargo &> /dev/null; then
        echo "Rust/Cargo not installed (see https://rustup.rs/) — skipping govbot tests."
        exit 0
    fi
    cd actions/govbot && cargo test

# Show toolchain status + available tasks
info:
    #!/usr/bin/env bash
    echo "Project: govbot (repo root)"
    command -v python3 &> /dev/null && python3 --version || echo "python3: missing"
    command -v cargo &> /dev/null && (rustc --version && cargo --version) || echo "cargo: missing"
    echo ""
    echo "Available tasks:"
    just --list
