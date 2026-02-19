# Nightly synthetic test: govbot wizard → clone flow
# Exercises the production nightly binary end-to-end:
#   1. Runs the interactive wizard to generate govbot.yml
#   2. Clones a small jurisdiction (Guam) to verify data download
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

# Wizard Step 1: Select "Select specific states" (move down from default "All states")
Down
Enter
Sleep 2s

# Enter state code: gu (Guam — small dataset for fast CI)
Type "gu"
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

# Clone the repo specified in the config
Type "govbot clone gu"
Enter
Sleep 90s

# Verify cloned content exists
Type "ls .govbot/repos/"
Enter
Sleep 2s

Type "echo 'Synthetic test complete'"
Enter
Sleep 2s
