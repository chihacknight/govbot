# govbot help output
# Dual-mode: TEST_MODE=mock asserts output matches expected file
#            TEST_MODE=prod (default) just asserts non-empty output
Output tapes/govbot-help.gif

Set Shell bash
Set FontSize 14
Set Width 900
Set Height 500
Set Padding 20

# Define assertion helper (short name to minimize typing time)
Type "sk() { if [ ${TEST_MODE:-prod} = mock ]; then diff $1 $2 && echo SNAP_OK || echo SNAP_FAIL; else [ -s $1 ] && echo SNAP_OK || echo SNAP_FAIL; fi; }"
Enter
Sleep 500ms

Type "govbot --help > /tmp/gh.txt 2>&1 && cat /tmp/gh.txt"
Enter
Sleep 2s

Type "clear"
Enter
Sleep 500ms

Type "sk /tmp/gh.txt tapes/expected/govbot-help.txt"
Enter
Wait+Screen@5s /SNAP_OK/
Sleep 1s
