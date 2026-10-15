#!/usr/bin/env python3
"""Render the before/after section of a loop PR, and optionally write it into the PR.

    pr-captures.py --before <dir> --after <dir> --before-urls <tsv> --after-urls <tsv> \
                   [--verdicts <json>] [--apply <pr-number>]

<dir>s are desktop-capture.sh output roots (one folder per scenario with meta.json
and trace.jsonl). The url TSVs are what publish-captures.sh printed. --verdicts is
{"<scenario-id>": "one line judging the after capture against its `expect`"}.

With --apply, the section replaces whatever sits between the capture markers in the
PR body (the PR template has them), so re-capturing after review feedback updates
the same table instead of stacking new ones.
"""

import argparse
import json
import subprocess
from pathlib import Path

START, END = "<!-- mcp-loop:captures:start -->", "<!-- mcp-loop:captures:end -->"


def urls(path: str | None) -> dict:
    if not path:
        return {}
    lines = Path(path).read_text().splitlines()
    return dict(line.split("\t", 1) for line in lines if "\t" in line)


def calls(root: str, scenario: str) -> list[str]:
    trace = Path(root) / scenario / "trace.jsonl"
    if not trace.exists():
        return []
    out = []
    for line in trace.read_text().splitlines():
        record = json.loads(line)
        args = json.dumps(record["args"], separators=(",", ":"))
        flag = " ⚠️ error" if record["isError"] else ""
        out.append(f"`{record['tool']}` {args[:120]} — {record['ms']} ms{flag}")
    return out


def meta(root: str, scenario: str) -> dict:
    path = Path(root) / scenario / "meta.json"
    return json.loads(path.read_text()) if path.exists() else {}


def render(args) -> str:
    before_urls, after_urls = urls(args.before_urls), urls(args.after_urls)
    verdicts = json.loads(Path(args.verdicts).read_text()) if args.verdicts else {}
    scenarios = sorted(set(before_urls) | set(after_urls))

    lines = [START, "", "### Claude Desktop, before → after", ""]
    if not scenarios:
        lines += ["_Screenshots pending — captured on the next loop tick when this Mac is idle._", "", END]
        return "\n".join(lines)

    lines += ["| Scenario | Before | After |", "|---|---|---|"]
    for s in scenarios:
        b = f"![before]({before_urls[s]})" if s in before_urls else "—"
        a = f"![after]({after_urls[s]})" if s in after_urls else "—"
        lines.append(f"| [`{s}`]({args.scenario_url}/{s}.yml) | {b} | {a} |")

    lines += ["", "#### Against each scenario's `expect`", ""]
    for s in scenarios:
        m = meta(args.after, s)
        note = " (timed out — reply may be cut off)" if m.get("timed_out") else ""
        lines.append(f"- **{s}**: {verdicts.get(s, '_not judged_')}{note}")

    lines += ["", "<details><summary>Tool calls, before → after</summary>", ""]
    for s in scenarios:
        lines.append(f"**{s}**")
        lines.append("")
        lines.append("Before:" if calls(args.before, s) else "Before: _no tool calls_")
        lines += [f"1. {c}" for c in calls(args.before, s)]
        lines.append("")
        lines.append("After:" if calls(args.after, s) else "After: _no tool calls_")
        lines += [f"1. {c}" for c in calls(args.after, s)]
        lines.append("")
    lines += ["</details>", "", END]
    return "\n".join(lines)


def apply(pr: str, section: str) -> None:
    body = subprocess.run(["gh", "pr", "view", pr, "--json", "body", "-q", ".body"],
                          check=True, capture_output=True, text=True).stdout
    if START in body and END in body:
        head, rest = body.split(START, 1)
        _, tail = rest.split(END, 1)
        body = head + section + tail
    else:
        body = body.rstrip() + "\n\n" + section + "\n"
    subprocess.run(["gh", "pr", "edit", pr, "--body-file", "-"], input=body, check=True, text=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--before", default="")
    parser.add_argument("--after", default="")
    parser.add_argument("--before-urls")
    parser.add_argument("--after-urls")
    parser.add_argument("--verdicts")
    parser.add_argument("--apply", metavar="PR")
    parser.add_argument("--scenario-url",
                        default="https://github.com/chihacknight/govbot/blob/main/actions/mcp/scenarios")
    args = parser.parse_args()
    section = render(args)
    if args.apply:
        apply(args.apply, section)
    print(section)


if __name__ == "__main__":
    main()
