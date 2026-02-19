# Wizard: specific repos (il, ca, ny) + example tag
# User picks specific states instead of "all"
Output tapes/wizard-specific-states.gif

Set Shell bash
Set FontSize 14
Set Width 900
Set Height 800
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

# Step 1: Sources — select "Select specific states"
Down
Sleep 300ms
Enter
Sleep 500ms

# Type state codes
Type "il ca ny"
Enter
Sleep 500ms

# Step 2: Tags — accept default "Use the example education tag"
Enter
Sleep 500ms

# Step 3: Publishing — type a custom base URL
Type "https://myuser.github.io/my-govbot"
Enter
Sleep 1s

# Show the generated govbot.yml
Sleep 500ms
Type "cat govbot.yml"
Enter
Sleep 3s
