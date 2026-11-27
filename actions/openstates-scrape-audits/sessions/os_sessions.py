#!/usr/bin/env python3
"""Every legislative session that any version of a state's OpenStates jurisdiction file listed.

    python3 os_sessions.py <raw-scrapers dir> <out.json>

Reads each raw repo's _data/<st>/jurisdiction_*.json at every commit that changed it (git log
--raw on that path only, then one cat-file --batch); writes {state: [session, ...]}. Read-only.
lists.py uses the start dates to tell whether OpenStates lists a calendar special at all.
"""
import glob
import json
import subprocess
import sys

R = sys.argv[1]
out = {}
for repo in sorted(glob.glob(R + "/*-legislation")):
    st = repo.rsplit('/', 1)[1].split('-')[0]
    log = subprocess.run(["git", "-C", repo, "log", "--format=", "--raw", "--no-abbrev", "--", f"_data/{st}/jurisdiction_*"],
                         capture_output=True, text=True).stdout.splitlines()
    blobs = {l.split()[3] for l in log if l.startswith(":") and "/jurisdiction_" in l and l.split()[3] != "0" * 40}
    seen = {}
    if blobs:
        p = subprocess.run(["git", "-C", repo, "cat-file", "--batch"], input="\n".join(blobs) + "\n",
                           capture_output=True, text=True).stdout
        i = 0
        while i < len(p):
            nl = p.index("\n", i); hdr = p[i:nl].split()
            if len(hdr) < 3: break
            n = int(hdr[2]); body = p[nl + 1:nl + 1 + n]; i = nl + 1 + n + 1
            try:
                for s in json.loads(body).get("legislative_sessions", []):
                    seen[s.get("identifier")] = s
            except Exception:
                pass
    out[st] = list(seen.values())
json.dump(out, open(sys.argv[2], "w"), indent=1)
print(sum(len(v) for v in out.values()), "sessions")
