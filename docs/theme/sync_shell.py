#!/usr/bin/env python3
"""Write the one shared site shell — header, mobile drawer and footer — into every page.

Sources: docs/theme/header.html (header + drawer) and docs/theme/footer.html. The homepage + doc
pages get them via docs/theme/index.hbs; the dashboards are standalone HTML, so each carries its own
copy. This keeps all of them identical apart from relative paths.

  python3 docs/theme/sync_shell.py           # rewrite the blocks in place
  python3 docs/theme/sync_shell.py --check   # exit 1 if any page has drifted (no writes)
"""
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
THEME = ROOT / "docs/theme"

# (template file, the block's opening tag, its closing line) — blocks are matched from the opening
# tag to the first closing tag at the same indentation, so nested elements don't end them early.
BLOCKS = [
    ("header.html", '<header class="gb-header">', "</header>"),
    ("header.html", '<div class="gb-drawer" data-gb-drawer>', "</div>"),
    ("footer.html", '<footer class="gb-footer">', "</footer>"),
]

# page -> (site root folder, homepage, dashboard folder), as seen from that page. mdbook's
# path_to_root is "" on top-level pages, so the homepage needs an explicit index.html there
# (a bare "" href would point back at the current page).
TARGETS = {"docs/theme/index.hbs": ("{{ path_to_root }}", "{{ path_to_root }}index.html", "{{ path_to_root }}dashboard/")}
for page in sorted((ROOT / "docs/src/dashboard").glob("*.html")):
    TARGETS[str(page.relative_to(ROOT))] = ("../", "../", "")


def block_re(open_tag, close):
    return re.compile(r"^([ \t]*)" + re.escape(open_tag) + r".*?^\1" + re.escape(close), re.S | re.M)


def template_block(name, open_tag, close):
    body = (THEME / name).read_text()
    body = body[body.index("-->") + 3:]  # drop the template's header comment
    m = block_re(open_tag, close).search(body)
    return m.group(0)


def render(block, root, home, dash, indent):
    block = block.replace("{HOME}", home).replace("{ROOT}", root).replace("{DASH}", dash)
    return "\n".join((indent + line) if line else line for line in block.split("\n"))


def main(check):
    drift = []
    for rel, (root, home, dash) in TARGETS.items():
        path = ROOT / rel
        text = orig = path.read_text()
        for name, open_tag, close in BLOCKS:
            m = block_re(open_tag, close).search(text)
            if not m:  # e.g. the tiny redirect page has no shell
                continue
            new = render(template_block(name, open_tag, close), root, home, dash, m.group(1))
            text = text[:m.start()] + new + text[m.end():]
        if text != orig:
            drift.append(rel)
            if not check:
                path.write_text(text)
    if check and drift:
        print("site shell out of sync (run python3 docs/theme/sync_shell.py):", *drift, sep="\n  ")
        return 1
    print("in sync" if check else "updated: " + (", ".join(drift) or "nothing"))
    return 0


if __name__ == "__main__":
    sys.exit(main("--check" in sys.argv))
