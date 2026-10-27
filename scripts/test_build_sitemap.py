#!/usr/bin/env python3
"""Offline tests for build_sitemap.py — the right pages are listed, redirects and helpers are not,
and each page's <head> is finished without changing what a page already says."""

import json
import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_sitemap as m  # noqa: E402


def write(base: Path, rel: str, text: str = "<html><head><title>x</title></head></html>"):
    p = base / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def run():
    with tempfile.TemporaryDirectory() as t:
        book, root = Path(t) / "book", Path(t) / "root"
        root.mkdir()
        (root / "llms.txt").write_text("# govbot\n", encoding="utf-8")
        (root / "catalog.json").write_text("{}", encoding="utf-8")
        write(book, "index.html")
        write(book, "about.html")
        write(book, "dashboard/legislation.html")
        write(book, "dashboard/hearings.html")
        write(book, "2025-Decentralize/index.html")
        write(book, "print.html")
        write(book, "toc.html")
        write(book, "404.html")
        write(book, "dashboard/index.html", '<meta http-equiv="refresh" content="0; url=../">')
        write(book, "dashboard/illinois-elections.html", "<meta http-equiv='refresh' content='0'>")
        write(book, "dashboard/illinois-elections-v1.html", '<meta name="robots" content="noindex, follow">')
        assert m.main(["--book", str(book), "--root", str(root)]) == 0
        xml = (book / "sitemap.xml").read_text(encoding="utf-8")
        locs = [line.split("<loc>")[1].split("</loc>")[0] for line in xml.splitlines() if "<loc>" in line]
        want = [
            "https://chihacknight.github.io/govbot/",
            "https://chihacknight.github.io/govbot/2025-Decentralize/",
            "https://chihacknight.github.io/govbot/about.html",
            "https://chihacknight.github.io/govbot/dashboard/hearings.html",
            "https://chihacknight.github.io/govbot/dashboard/legislation.html",
        ]
        assert locs == want, locs
        assert "lastmod" not in xml
        assert (book / "llms.txt").read_text(encoding="utf-8") == "# govbot\n"
        assert (book / "catalog.json").read_text(encoding="utf-8") == "{}"
        # No built book: a clear error, nothing written.
        assert m.main(["--book", str(Path(t) / "none"), "--root", str(root)]) == 1
    # <head> finishing: canonical, social tags, landing title and FAQ markup made from the visible questions.
    with tempfile.TemporaryDirectory() as t:
        book, root = Path(t) / "book", Path(t) / "root"
        root.mkdir()
        (root / "llms.txt").write_text("x", encoding="utf-8")
        (root / "catalog.json").write_text("{}", encoding="utf-8")
        faq = ('<div class="gl-faq">\n<details open><summary>What is Govbot?</summary><p>An <b>open</b> toolkit &amp; dataset.</p></details>\n'
               '<details><summary>Is it free?</summary><p>Yes, see <a href="x">the license ↗</a>. Use <span class="gl-mono">govbot</span>.</p></details>\n</div>')
        write(book, "index.html", f'<html><head><title>Home - govbot</title><meta name="description" content="A &amp; B"></head><body>{faq}</body></html>')
        write(book, "about.html", '<html><head><title>About - govbot</title><meta name="description" content="About it"></head></html>')
        write(book, "dashboard/hearings.html", '<html><head><title>Govbot — Hearings &amp; Comment</title><meta property="og:title" content="Have your say"><link rel="canonical" href="https://example.test/own"></head></html>')
        write(book, "dashboard/illinois-elections.html", '<html><head><title>x</title><link rel="canonical" href="https://other.test/il"><meta http-equiv="refresh" content="0"></head></html>')
        write(book, "dashboard/illinois-elections-v1.html", '<html><head><title>old</title><meta name="robots" content="noindex"></head></html>')
        assert m.main(["--book", str(book), "--root", str(root)]) == 0
        home = (book / "index.html").read_text(encoding="utf-8")
        assert f"<title>{m.LANDING_TITLE}</title>" in home and "Home - govbot" not in home
        assert '<link rel="canonical" href="https://chihacknight.github.io/govbot/">' in home
        assert '<meta property="og:description" content="A &amp; B">' in home
        ld = json.loads(re.search(r'<script type="application/ld\+json">(.*?)</script>', home, re.S).group(1))
        got = [(q["name"], q["acceptedAnswer"]["text"]) for q in ld["mainEntity"]]
        assert got == [("What is Govbot?", "An open toolkit & dataset."), ("Is it free?", "Yes, see the license ↗. Use govbot.")], got
        about = (book / "about.html").read_text(encoding="utf-8")
        assert 'href="https://chihacknight.github.io/govbot/about.html"' in about and "ld+json" not in about
        hear = (book / "dashboard/hearings.html").read_text(encoding="utf-8")
        assert hear.count("canonical") == 1 and hear.count("og:title") == 1 and "example.test/own" in hear
        for name in ("illinois-elections.html", "illinois-elections-v1.html"):
            assert "govbot/dashboard" not in (book / "dashboard" / name).read_text(encoding="utf-8")
        before = {p.name: p.read_text(encoding="utf-8") for p in book.rglob("*.html")}
        assert m.main(["--book", str(book), "--root", str(root)]) == 0
        assert before == {p.name: p.read_text(encoding="utf-8") for p in book.rglob("*.html")}, "running twice must change nothing"
    assert m.page_url(Path("a/b/index.html")) == "https://chihacknight.github.io/govbot/a/b/"
    assert m.sitemap_xml(["https://x/?a=1&b=2"]).count("&amp;") == 1
    print("ok")


if __name__ == "__main__":
    run()
