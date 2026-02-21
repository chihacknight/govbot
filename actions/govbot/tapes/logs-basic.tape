# govbot logs output with mock data
# Dual-mode: TEST_MODE=mock asserts output matches expected file
#            TEST_MODE=prod (default) just asserts non-empty output
# GOVBOT_DIR: path to .govbot directory (default: mocks/.govbot)
Output tapes/logs-basic.gif

Set Shell bash
Set FontSize 12
Set Width 1200
Set Height 600
Set Padding 20

# Define assertion helper
Type "sk() { if [ ${TEST_MODE:-prod} = mock ]; then diff $1 $2 && echo SNAP_OK || echo SNAP_FAIL; else [ -s $1 ] && echo SNAP_OK || echo SNAP_FAIL; fi; }"
Enter
Sleep 500ms

Type "GD=${GOVBOT_DIR:-mocks/.govbot}; govbot logs --govbot-dir $GD > /tmp/lb.txt 2>&1 && cat /tmp/lb.txt"
Enter
Sleep 3s

Type "clear"
Enter
Sleep 500ms

Type "sk /tmp/lb.txt tapes/expected/logs-basic.txt"
Enter
Wait+Screen@5s /SNAP_OK/
Sleep 1s
