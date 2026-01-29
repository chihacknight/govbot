#!/bin/bash
# Default $1 to __snapshots__ if not provided
if [ $# -eq 0 ]; then
    set -- "__snapshots__"
fi

# Combine $1 with current working directory
SNAPSHOTS_PATH="$(pwd)/$1"

if [ -e "$SNAPSHOTS_PATH" ]; then
    rm -rf "$SNAPSHOTS_PATH"
fi
