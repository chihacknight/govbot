# Wizard: all repos + example education tag (default path)
# This is the simplest setup - user accepts all defaults
Output tapes/wizard-all-with-tag.gif

Set Shell bash
Set FontSize 14
Set Width 900
Set Height 700
Set Padding 20
Set TypingSpeed 50ms

Hide
Type "cd $(mktemp -d) && export PATH=$OLDPWD/target/release:$PATH"
Enter
Sleep 500ms
Show

Type "govbot"
Enter
Sleep 1s

# Step 1: Sources — accept default "All states (47 jurisdictions)"
Enter
Sleep 500ms

# Step 2: Tags — accept default "Use the example education tag"
Enter
Sleep 500ms

# Step 3: Publishing — accept default base URL
Enter
Sleep 1s

# Show the generated govbot.yml
Sleep 500ms
Type "cat govbot.yml"
Enter
Sleep 3s
