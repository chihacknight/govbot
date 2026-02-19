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
Type "curl -fsSL https://raw.githubusercontent.com/chihacknight/govbot/main/actions/govbot/scripts/install-nightly.sh | bash"
Enter
Wait+Screen@60s /govbot installed at/

# Work in a clean directory
Type "mkdir -p /tmp/govbot-test && cd /tmp/govbot-test"
Enter
Sleep 2s

# Step 2: Launch govbot — no govbot.yml exists, so the wizard starts
Type "govbot"
Enter
Wait@10s /What data sources do you want to track/

# Wizard Step 1: Select "Select specific states" (move down from default)
Down
Enter
Wait@5s /Enter state codes/

# Enter state codes: gu (Guam) and wy (Wyoming)
Type "gu wy"
Enter
Wait@5s /How would you like to set up tags/

# Wizard Step 2: Use the example "education" tag (default selection)
Enter
Wait@5s /Base URL for your feeds/

# Wizard Step 3: Accept default base URL (https://example.com)
Enter
Wait@10s /Setup complete/

# Step 3: Run govbot again — govbot.yml exists, so the pipeline runs
# Pipeline: clone repos → tag bills → build RSS feeds
Type "govbot"
Enter
Hide
Wait+Screen@300s /Pipeline complete/
Show
Sleep 2s

# Verify outputs
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
Wait@5s /E2E test complete/
