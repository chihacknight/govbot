# Wizard: all repos + "I'll create my own tags later" (shows AI prompt template)
Output tapes/wizard-all-own-tags.gif

Set Shell bash
Set FontSize 14
Set Width 900
Set Height 900
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

# Step 1: Sources — accept default "All states"
Enter
Sleep 500ms

# Step 2: Tags — select "I'll create my own tags later"
Down
Sleep 300ms
Enter
Sleep 500ms

# Step 3: Publishing — accept default base URL
Enter
Sleep 3s
