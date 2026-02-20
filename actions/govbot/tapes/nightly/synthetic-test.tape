# End-to-end test: govbot wizard + pipeline
# Exercises the full flow:
#   1. Runs the interactive wizard to generate govbot.yml
#   2. Runs the pipeline (clone → tag → build) with stderr redirected
#   3. Verifies outputs exist
#
# The govbot binary is built from source and placed on PATH by the
# synthetic-test.yml workflow before this tape runs.
#
# Pipeline stderr is redirected to a file to avoid VHS PTY deadlock
# caused by git clone progress output.

Output "/tmp/govbot-synthetic-test.gif"

Set Shell bash
Set FontSize 14
Set Width 1200
Set Height 800
Set Padding 20

# Work in a clean directory
Type "mkdir -p /tmp/govbot-test && cd /tmp/govbot-test"
Enter
Sleep 1s

# Launch govbot — no govbot.yml exists, so the wizard starts.
# After the wizard generates config files, govbot exits and tells the
# user to run `govbot` again to start the pipeline.
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
# The wizard writes govbot.yml and exits cleanly.
Enter
Wait+Screen@10s /Setup complete/
Sleep 2s

# Run pipeline with stderr redirected to avoid PTY deadlock.
# Trick: typed text has "rc:%d" but output has "rc:0", so Wait+Screen
# won't match the typed command text prematurely.
Type "govbot 2>/tmp/pipeline.log; printf 'rc:%d\n' $?"
Enter
Wait+Screen@300s /rc:0/
Sleep 1s

# Show pipeline result
Type "tail -5 /tmp/pipeline.log"
Enter
Wait+Screen@5s /Pipeline complete/
Sleep 1s

# Verify outputs
Type "ls .govbot/repos/"
Enter
Wait+Screen@5s /gu/

Type "ls docs/"
Enter
Wait+Screen@5s /feed.xml/
Sleep 2s
