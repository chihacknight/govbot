#!/usr/bin/env python3
"""Write the one shared site footer (docs/theme/footer.html) into every page that shows it.

The homepage + doc pages get it via docs/theme/index.hbs; the dashboards are standalone HTML, so
each carries its own copy. This keeps all of them byte-identical apart from relative paths.

  python3 docs/theme/sync_footer.py           # rewrite the footers in place
  python3 docs/theme/sync_footer.py --check   # exit 1 if any page has drifted (no writes)
"""
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "docs/theme/footer.html"
FOOTER_RE = re.compile(r'^([ \t]*)<footer class="gb-footer">.*?</footer>', re.S | re.M)

# page -> (path to the site root, path to the dashboard folder), as seen from that page
TARGETS = {"docs/theme/index.hbs": ("{{ path_to_root }}", "{{ path_to_root }}dashboard/")}
for page in sorted((ROOT / "docs/src/dashboard").glob("*.html")):
    TARGETS[str(page.relative_to(ROOT))] = ("../", "")


def render(root, dash, indent):
    body = TEMPLATE.read_text()
    body = body[body.index("-->") + 3:].strip("\n")  # drop the template's header comment
    body = body.replace("{ROOT}", root).replace("{DASH}", dash)
    return "\n".join((indent + line) if line else line for line in body.split("\n"))


def main(check):
    drift = []
    for rel, (root, dash) in TARGETS.items():
        path = ROOT / rel
        text = path.read_text()
        m = FOOTER_RE.search(text)
        if not m:  # e.g. the tiny redirect page has no footer
            continue
        new = text[:m.start()] + render(root, dash, m.group(1)) + text[m.end():]
        if new != text:
            drift.append(rel)
            if not check:
                path.write_text(new)
    if check and drift:
        print("footer out of sync (run python3 docs/theme/sync_footer.py):", *drift, sep="\n  ")
        return 1
    print(("in sync" if check else "updated: " + (", ".join(drift) or "nothing")))
    return 0


if __name__ == "__main__":
    sys.exit(main("--check" in sys.argv))
