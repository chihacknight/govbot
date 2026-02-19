# End-to-end test: govbot wizard
# Exercises the interactive wizard flow:
#   1. Runs the interactive wizard to generate govbot.yml
#   2. Verifies config files were created
#
# The govbot binary is built from source and placed on PATH by the
# synthetic-test.yml workflow before this tape runs.
#
# The pipeline step (clone → tag → build) runs outside VHS in the
# workflow because git clone progress output deadlocks the VHS PTY.

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
Sleep 1s

# Verify wizard created govbot.yml
Type "cat govbot.yml"
Enter
Wait+Screen@5s /output_dir/

Type "echo 'Wizard test complete'"
Enter
Wait+Screen@5s /Wizard test complete/
