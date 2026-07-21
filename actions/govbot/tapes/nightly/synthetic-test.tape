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
# from git clone progress. Stdout stays on screen to prevent idle timeout.

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

# Run the pipeline with BOTH stdout and stderr redirected to files.
# - stderr carries git-clone progress (carriage returns) that can PTY-deadlock VHS.
# - stdout carries raw bill JSON; a burst of it (e.g. a long/awkward bill record)
#   wedges the ttyd terminal so later output never renders — which meant the rc:0
#   completion sentinel was silently lost and this test hung until timeout.
# So we run the pipeline in the background, print a '.' heartbeat every 2s so the
# VHS screen keeps updating (no idle timeout, no JSON on screen), then echo a
# clean rc:0 sentinel once it exits.
# Wait+Screen won't prematch the typed text because "rc:$?" (typed) doesn't match
# regex /rc:0/ — only the output "rc:0" does.
Type "govbot >/tmp/pipeline.out 2>/tmp/pipeline.log & BGPID=$!; while kill -0 $BGPID 2>/dev/null; do printf '.'; sleep 2; done; wait $BGPID; echo rc:$?"
Enter
Wait+Screen@300s /rc:0/
Sleep 1s

# Clear the screen so verification output is visible — the wizard
# output fills the VHS screen buffer and pushes new lines off-screen.
Type "clear"
Enter
Sleep 500ms

# Show pipeline result
Type "tail -5 /tmp/pipeline.log"
Enter
Wait+Screen@5s /Pipeline complete/
Sleep 1s

# Verify outputs
Type "ls govbot_data/repos/"
Enter
Wait+Screen@5s /gu/

Type "ls docs/"
Enter
Wait+Screen@5s /feed.xml/
Sleep 2s
