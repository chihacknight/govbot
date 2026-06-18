# End-to-end test: govbot wizard + pipeline
# Exercises the full flow:
#   1. Runs the interactive wizard to generate govbot.yml
#   2. Runs the pipeline (clone → tag → build) with stderr redirected
#   3. Verifies outputs exist
#
# Dual-mode:
#   TEST_MODE=mock  → Pre-populates repos from mocks, skips clone, snapshot assertions
#   TEST_MODE=prod  → Clones live repos, smoke assertions (default)
#
# GOVBOT_SRC: path to the govbot source directory (for mock data)
#             Only needed in mock mode. Default: current directory.
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

# In mock mode: pre-populate repos from mock data so clone is unnecessary
Type "TM=${TEST_MODE:-prod}; if [ $TM = mock ]; then SRC=${GOVBOT_SRC:-.}; mkdir -p .govbot/repos && cp -r $SRC/mocks/.govbot/repos/* .govbot/repos/ && echo MOCK_REPOS_READY; fi"
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

# Run pipeline: in mock mode run individual steps (skip clone),
# in prod mode run the full pipeline.
# In both modes stderr is redirected to avoid PTY deadlock.
Type "TM=${TEST_MODE:-prod}; if [ $TM = mock ]; then govbot logs | govbot tag 2>/tmp/pipeline.log; govbot build 2>>/tmp/pipeline.log; echo rc:$?; else govbot 2>/tmp/pipeline.log; echo rc:$?; fi"
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
Sleep 2s

# Verify outputs
Type "ls .govbot/repos/"
Enter
Wait+Screen@5s /gu/

Type "ls docs/"
Enter
Wait+Screen@5s /feed.xml/

# Final assertion
Type "TM=${TEST_MODE:-prod}; if [ $TM = mock ]; then test -f govbot.yml && test -f docs/feed.xml && test -d .govbot/repos/gu-legislation && test -d .govbot/repos/wy-legislation && echo SNAP_OK || echo SNAP_FAIL; else test -f docs/feed.xml && echo SNAP_OK || echo SNAP_FAIL; fi"
Enter
Wait+Screen@5s /SNAP_OK/
Sleep 2s
