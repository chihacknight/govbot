# govbot clone --list output
# Dual-mode: TEST_MODE=mock asserts output matches expected file
#            TEST_MODE=prod (default) just asserts non-empty output
Output tapes/govbot-clone-list.gif

Set Shell bash
Set FontSize 14
Set Width 900
Set Height 800
Set Padding 20

# Define assertion helper
Type "sk() { if [ ${TEST_MODE:-prod} = mock ]; then diff $1 $2 && echo SNAP_OK || echo SNAP_FAIL; else [ -s $1 ] && echo SNAP_OK || echo SNAP_FAIL; fi; }"
Enter
Sleep 500ms

Type "govbot clone --list > /tmp/gcl.txt 2>&1 && cat /tmp/gcl.txt"
Enter
Sleep 2s

Type "clear"
Enter
Sleep 500ms

Type "sk /tmp/gcl.txt tapes/expected/govbot-clone-list.txt"
Enter
Wait+Screen@5s /SNAP_OK/
Sleep 1s
