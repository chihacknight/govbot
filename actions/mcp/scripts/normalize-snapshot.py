#!/usr/bin/env python3
"""Strip machine- and release-specific values out of a captured MCP session.

Snapshots exist to make changes to the tool surface reviewable. Anything that
varies between runs — a version number, a temp path, the length of the
instructions blob — is noise that would make every diff unreadable, so it is
replaced with a placeholder here.
"""

import json
import sys


def normalize(messages: list) -> list:
    for message in messages:
        result = message.get("result")
        if not isinstance(result, dict):
            continue
        if "serverInfo" in result:
            result["serverInfo"]["version"] = "<version>"
            instructions = result.get("instructions", "")
            result["instructions"] = f"<{len(instructions)} characters>"
    return messages


if __name__ == "__main__":
    json.dump(normalize(json.load(sys.stdin)), sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
