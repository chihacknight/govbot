# Nightly synthetic test: govbot wizard → clone flow
# Exercises the production nightly binary end-to-end:
#   1. Runs the interactive wizard to generate govbot.yml
#   2. Clones all 47 jurisdictions to verify data download
#
# This tape is run by the synthetic-test.yml workflow on a nightly schedule.
# It lives in tapes/nightly/ to avoid being picked up by terminal-screenshots.yml.

Output /tmp/govbot-synthetic-test.gif

Set Shell bash
Set FontSize 14
Set Width 1200
Set Height 800
Set Padding 20

# Work in a clean directory
Type "mkdir -p /tmp/govbot-test && cd /tmp/govbot-test"
Enter
Sleep 1s

# Launch govbot — no govbot.yml exists, so the wizard starts
Type "govbot"
Enter
Sleep 3s

# Wizard Step 1: "All states (47 jurisdictions)" is the default — accept it
Enter
Sleep 2s

# Wizard Step 2: Use the example "education" tag (default selection)
Enter
Sleep 2s

# Wizard Step 3: Accept default base URL (https://example.com)
Enter
Sleep 3s

# Show the generated config
Type "cat govbot.yml"
Enter
Sleep 3s

# Clone all jurisdictions from the config
# Hide recording during the long clone to keep the GIF small
Type "govbot clone all"
Enter
Hide
Sleep 600s
Show

# Verify cloned content exists
Type "ls .govbot/repos/"
Enter
Sleep 2s

Type "echo 'Synthetic test complete'"
Enter
Sleep 2s
