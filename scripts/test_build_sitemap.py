#!/usr/bin/env python3
"""Offline tests for build_sitemap.py — the right pages are listed, redirects and helpers are not."""

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
    assert m.page_url(Path("a/b/index.html")) == "https://chihacknight.github.io/govbot/a/b/"
    assert m.sitemap_xml(["https://x/?a=1&b=2"]).count("&amp;") == 1
    print("ok")


if __name__ == "__main__":
    run()
