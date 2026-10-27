#!/usr/bin/env python3
"""Write sitemap.xml for the built site (docs/book) and copy in the plain files crawlers and
AI assistants look for at the site's root: llms.txt and catalog.json (kept at the repo root so
GitHub readers see them too) and robots.txt.

    python3 scripts/build_sitemap.py --book docs/book

The site's pages are every .html file in the build except the ones that should not be listed:
the redirect pages (meta refresh, e.g. the elections pages that forward to Know Your Ballot),
pages that ask not to be indexed, and mdBook's print/toc/404 helpers. No <lastmod> is written:
the pages carry no trustworthy "last changed" date of their own, and a wrong one is worse than
none. Stdlib only; tested offline by test_build_sitemap.py.
"""

import argparse
import re
import shutil
import sys
from pathlib import Path
from xml.sax.saxutils import escape

SITE = "https://chihacknight.github.io/govbot/"
HELPERS = {"print.html", "toc.html", "404.html"}
REFRESH = re.compile(r'http-equiv=["\']refresh["\']', re.I)
NOINDEX = re.compile(r'<meta[^>]+name=["\']robots["\'][^>]+noindex', re.I)
ROOT_FILES = ("llms.txt", "catalog.json")


def listed(path: Path, text: str) -> bool:
    """Whether a built page belongs in the sitemap."""
    return path.name not in HELPERS and not REFRESH.search(text) and not NOINDEX.search(text)


def page_url(rel: Path) -> str:
    """index.html -> its folder's address, anything else -> its own."""
    parts = list(rel.parts)
    if parts[-1] == "index.html":
        parts = parts[:-1]
        return SITE + "/".join(parts) + ("/" if parts else "")
    return SITE + "/".join(parts)


def build(book: Path) -> list[str]:
    urls = []
    for p in book.rglob("*.html"):
        rel = p.relative_to(book)
        if listed(p, p.read_text(encoding="utf-8", errors="replace")):
            urls.append(page_url(rel))
    return sorted(urls)


def sitemap_xml(urls: list[str]) -> str:
    rows = "".join(f"  <url><loc>{escape(u)}</loc></url>\n" for u in urls)
    return f'<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n{rows}</urlset>\n'


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--book", default="docs/book", help="the built site")
    ap.add_argument("--root", default=".", help="repo root holding llms.txt and catalog.json")
    args = ap.parse_args(argv)
    book, root = Path(args.book), Path(args.root)
    if not (book / "index.html").exists():
        print(f"error: {book}/index.html not found; build the book first", file=sys.stderr)
        return 1
    urls = build(book)
    (book / "sitemap.xml").write_text(sitemap_xml(urls), encoding="utf-8")
    for name in ROOT_FILES:
        shutil.copyfile(root / name, book / name)
    print(f"sitemap.xml: {len(urls)} pages; copied {', '.join(ROOT_FILES)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
