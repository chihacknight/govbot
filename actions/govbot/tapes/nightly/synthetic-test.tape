# Nightly real world end-to-end test: govbot install → wizard → pipeline
# Exercises the full user journey from scratch:
#   1. Installs govbot via the 1-click installer
#   2. Runs the interactive wizard to generate govbot.yml
#   3. Runs govbot again to execute the full pipeline (clone → tag → build)
#
# This tape is run by the synthetic-test.yml workflow on a nightly schedule.
# It lives in tapes/nightly/ to avoid being picked up by terminal-screenshots.yml.

Output "/tmp/govbot-synthetic-test.gif"

Set Shell bash
Set FontSize 14
Set Width 1200
Set Height 800
Set Padding 20

# Step 1: Install govbot via the 1-click installer
Type "curl -fsSL https://raw.githubusercontent.com/chihacknight/govbot/main/actions/govbot/scripts/install-nightly.sh | sh"
Enter
Sleep 15s

# Work in a clean directory
Type "mkdir -p /tmp/govbot-test && cd /tmp/govbot-test"
Enter
Sleep 1s

# Step 2: Launch govbot — no govbot.yml exists, so the wizard starts
Type "govbot"
Enter
Sleep 3s

# Wizard Step 1: Select "Select specific states" (move down from default)
Down
Enter
Sleep 2s

# Enter state codes: gu (Guam) and wy (Wyoming)
Type "gu wy"
Enter
Sleep 2s

# Wizard Step 2: Use the example "education" tag (default selection)
Enter
Sleep 2s

# Wizard Step 3: Accept default base URL (https://example.com)
Enter
Sleep 3s

# Step 3: Run govbot again — govbot.yml exists, so the pipeline runs
# Pipeline: clone repos → tag bills → build RSS feeds
Type "govbot"
Enter
Hide
Sleep 120s
Show
Sleep 5s

# Verify outputs
Type "cat govbot.yml"
Enter
Sleep 3s

Type "ls .govbot/repos/"
Enter
Sleep 2s

Type "ls docs/"
Enter
Sleep 2s

Type "echo 'E2E test complete'"
Enter
Sleep 2s
