# Nightly real world end-to-end test: govbot install → wizard → pipeline
# Exercises the full user journey from scratch:
#   1. Installs govbot via the 1-click installer
#   2. Runs the interactive wizard to generate govbot.yml
#   3. The same govbot invocation then runs the full pipeline (clone → tag → build)
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
Type "curl -fsSL https://raw.githubusercontent.com/chihacknight/govbot/main/actions/govbot/scripts/install-nightly.sh | bash"
Enter
Wait+Screen@60s /govbot installed at/

# Source profile so govbot is on PATH (installer updates profile in a subshell)
Type "export PATH=$HOME/.govbot/bin:$PATH"
Enter
Sleep 1s

# Work in a clean directory
Type "mkdir -p /tmp/govbot-test && cd /tmp/govbot-test"
Enter
Sleep 1s

# Step 2: Launch govbot — no govbot.yml exists, so the wizard starts.
# After the wizard, govbot immediately runs the pipeline in the same process.
Type "govbot"
Enter
Wait+Screen@10s /What data sources do you want to track/

# Wizard Step 1: Select "Select specific states" (move down from default)
Down
Enter
Wait+Screen@5s /Enter state codes/

# Enter state codes: gu (Guam) and wy (Wyoming)
Type "gu wy"
Enter
Wait+Screen@5s /How would you like to set up tags/

# Wizard Step 2: Use the example "education" tag (default selection)
Enter
Wait+Screen@5s /Base URL for your feeds/

# Wizard Step 3: Accept default base URL (https://example.com)
# After this Enter, the wizard writes config files and the pipeline starts
# automatically (clone → tag → build).
Enter
Wait+Screen@300s /Pipeline complete/
Sleep 2s

# Verify outputs (govbot has exited, shell is back)
Type "cat govbot.yml"
Enter
Wait+Screen@5s /output_dir/

Type "ls .govbot/repos/"
Enter
Wait+Screen@5s /gu/

Type "ls docs/"
Enter
Wait+Screen@5s /feed.xml/

Type "echo 'E2E test complete'"
Enter
Wait+Screen@5s /E2E test complete/
