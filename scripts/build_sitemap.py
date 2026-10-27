#!/usr/bin/env python3
"""Make the built site (docs/book) easy for search engines and AI assistants to read:
write sitemap.xml, copy in llms.txt and catalog.json (kept at the repo root so GitHub readers
see them too), and finish each page's <head>: a canonical address, social-share tags built from
the page's own title and description, a real title on the landing page, and FAQ markup made from
the landing page's visible questions (so the markup can never say anything the page doesn't).

    python3 scripts/build_sitemap.py --book docs/book

The site's pages are every .html file in the build except the ones that should not be listed:
the redirect pages (meta refresh, e.g. the elections pages that forward to Know Your Ballot),
pages that ask not to be indexed, and mdBook's print/toc/404 helpers. No <lastmod> is written:
the pages carry no trustworthy "last changed" date of their own, and a wrong one is worse than
none. Stdlib only; tested offline by test_build_sitemap.py.
"""

import argparse
import html
import json
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
LANDING_TITLE = "Govbot: every U.S. legislature as open data you can clone"
TITLE = re.compile(r"<title>(.*?)</title>", re.S)
DESCRIPTION = re.compile(r'<meta name="description" content="([^"]*)"', re.I)
FAQ_ITEM = re.compile(r"<details[^>]*>\s*<summary>(.*?)</summary>\s*<p>(.*?)</p>\s*</details>", re.S)
FAQ_BLOCK = re.compile(r'<div class="gl-faq">(.*?)</div>', re.S)


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


def plain(fragment: str) -> str:
    """A fragment of page HTML as the text a reader sees."""
    return " ".join(html.unescape(re.sub(r"<[^>]+>", "", fragment)).split())


def faq_json_ld(page_html: str) -> str | None:
    """FAQPage markup made from the landing page's visible questions, word for word; None when there are none."""
    block = FAQ_BLOCK.search(page_html)
    items = FAQ_ITEM.findall(block.group(1)) if block else []
    if not items:
        return None
    data = {"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": [
        {"@type": "Question", "name": plain(q), "acceptedAnswer": {"@type": "Answer", "text": plain(a)}} for q, a in items]}
    # "<" is escaped so no text can close the script tag.
    return '<script type="application/ld+json">' + json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c") + "</script>"


def enrich(rel: Path, text: str) -> str:
    """The page with what it lacks added to its <head>; pages that have it already are left alone, so running twice changes nothing."""
    add = []
    url = page_url(rel)
    if not re.search(r'<link[^>]+rel=["\']canonical', text, re.I):
        add.append(f'<link rel="canonical" href="{url}">')
    if rel.as_posix() == "index.html":
        text = TITLE.sub(f"<title>{LANDING_TITLE}</title>", text, count=1)
    title, desc = TITLE.search(text), DESCRIPTION.search(text)
    if title and 'property="og:title"' not in text:
        add += ['<meta property="og:type" content="website">', '<meta property="og:site_name" content="Govbot">',
                f'<meta property="og:title" content="{html.escape(html.unescape(title.group(1)), quote=True)}">', f'<meta property="og:url" content="{url}">']
        if desc:
            add.append(f'<meta property="og:description" content="{desc.group(1)}">')
        add.append('<meta name="twitter:card" content="summary">')
    if rel.as_posix() == "index.html" and 'application/ld+json">{"@context":"https://schema.org","@type":"FAQPage"' not in text:
        ld = faq_json_ld(text)
        if ld:
            add.append(ld)
    return text.replace("</head>", "\n".join(add) + "\n</head>", 1) if add else text


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
    # Finish every listed page's <head> first (a page that asks not to be listed, or only redirects, is left as it is).
    for page in book.rglob("*.html"):
        text = page.read_text(encoding="utf-8", errors="replace")
        if listed(page, text):
            done = enrich(page.relative_to(book), text)
            if done != text:
                page.write_text(done, encoding="utf-8")
    urls = build(book)
    (book / "sitemap.xml").write_text(sitemap_xml(urls), encoding="utf-8")
    for name in ROOT_FILES:
        shutil.copyfile(root / name, book / name)
    print(f"sitemap.xml: {len(urls)} pages; copied {', '.join(ROOT_FILES)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
