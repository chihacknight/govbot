<?xml version="1.0" encoding="UTF-8"?>
<!--
  Human-friendly browser rendering for govbot's RSS feeds.

  A raw RSS feed opened in a browser shows a scary "this XML file has no style
  information" tree. This XSLT is attached to every govbot feed via a
  <?xml-stylesheet?> processing instruction, so a browser renders a readable page
  instead — while feed readers keep parsing the underlying valid RSS 2.0.

  Pure XSLT 1.0 (the only version browsers implement). Self-contained: no external
  CSS/JS. Theme-aware via prefers-color-scheme.
-->
<xsl:stylesheet version="1.0"
    xmlns:xsl="http://www.w3.org/1999/XSL/Transform"
    xmlns:atom="http://www.w3.org/2005/Atom">
  <xsl:output method="html" encoding="UTF-8" indent="yes"
      doctype-system="about:legacy-compat"/>

  <xsl:template match="/">
    <html lang="en">
      <head>
        <meta charset="UTF-8"/>
        <meta name="viewport" content="width=device-width, initial-scale=1"/>
        <title><xsl:value-of select="/rss/channel/title"/></title>
        <style>
          :root {
            color-scheme: light dark;
            --bg: #f7f8fa; --card: #ffffff; --text: #1a1d21; --muted: #5b636e;
            --border: #e3e6ea; --accent: #2f6fed; --accent-soft: #eaf0fe;
            --rss: #f26a2e;
          }
          @media (prefers-color-scheme: dark) {
            :root {
              --bg: #0f1216; --card: #171b21; --text: #e8eaed; --muted: #9aa3af;
              --border: #262c34; --accent: #6ea0ff; --accent-soft: #16233d;
              --rss: #ff8a54;
            }
          }
          * { box-sizing: border-box; }
          body { margin: 0; background: var(--bg); color: var(--text);
            font: 15px/1.55 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; }
          .wrap { max-width: 760px; margin: 0 auto; padding: 28px 18px 60px; }
          header { display: flex; align-items: flex-start; gap: 12px; margin-bottom: 18px; }
          .rss-badge { flex: none; width: 34px; height: 34px; border-radius: 8px;
            background: var(--rss); display: flex; align-items: center; justify-content: center; }
          .rss-badge svg { width: 20px; height: 20px; }
          h1 { font-size: 20px; line-height: 1.3; margin: 0 0 3px; }
          .chan-desc { color: var(--muted); font-size: 13.5px; margin: 0; }
          .callout { background: var(--accent-soft); border: 1px solid var(--border);
            border-left: 4px solid var(--accent); border-radius: 10px;
            padding: 12px 14px; margin: 0 0 22px; font-size: 13.5px; }
          .callout b { color: var(--text); }
          .callout .url { display: block; margin-top: 7px; padding: 7px 9px;
            background: var(--card); border: 1px solid var(--border); border-radius: 7px;
            font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
            font-size: 12px; word-break: break-all; color: var(--accent); }
          .callout a { color: var(--accent); font-weight: 600; text-decoration: none; }
          .callout a:hover { text-decoration: underline; }
          .count { font-size: 12px; color: var(--muted); text-transform: uppercase;
            letter-spacing: .05em; font-weight: 700; margin: 0 0 10px; }
          .item { background: var(--card); border: 1px solid var(--border);
            border-radius: 10px; padding: 13px 15px; margin-bottom: 11px; }
          .item h2 { font-size: 15.5px; margin: 0 0 5px; line-height: 1.35; }
          .item h2 a { color: var(--text); text-decoration: none; }
          .item h2 a:hover { color: var(--accent); text-decoration: underline; }
          .item .meta { font-size: 12px; color: var(--muted); margin: 0 0 7px;
            display: flex; flex-wrap: wrap; gap: 4px 10px; }
          .item .meta .cat { color: var(--accent); font-weight: 600; }
          .item .desc { font-size: 13.5px; color: var(--muted); margin: 0; }
          .empty { background: var(--card); border: 1px dashed var(--border);
            border-radius: 10px; padding: 22px; text-align: center; color: var(--muted); font-size: 14px; }
          footer { margin-top: 26px; font-size: 12px; color: var(--muted); text-align: center; }
          footer a { color: var(--accent); text-decoration: none; }
        </style>
      </head>
      <body>
        <div class="wrap">
          <header>
            <span class="rss-badge" aria-hidden="true">
              <svg viewBox="0 0 24 24"><path fill="#fff" d="M4 11a9 9 0 0 1 9 9h2.5A11.5 11.5 0 0 0 4 8.5V11zm0 4a5 5 0 0 1 5 5h2.5A7.5 7.5 0 0 0 4 12.5V15zm1.6 2.4a1.9 1.9 0 1 0 0 3.8 1.9 1.9 0 0 0 0-3.8z"/></svg>
            </span>
            <div>
              <h1><xsl:value-of select="/rss/channel/title"/></h1>
              <p class="chan-desc"><xsl:value-of select="/rss/channel/description"/></p>
            </div>
          </header>

          <div class="callout">
            <b>📡 This is an RSS feed.</b> Paste this page's address into a feed
            reader (Feedly, Inoreader, NetNewsWire, Thunderbird…) to subscribe and
            get updates automatically.
            <span class="url"><xsl:value-of select="/rss/channel/atom:link/@href"/></span>
            <p style="margin:9px 0 0">
              ← Back to the
              <a href="{/rss/channel/link}">govbot dashboard</a>.
            </p>
          </div>

          <xsl:choose>
            <xsl:when test="/rss/channel/item">
              <p class="count">
                <xsl:value-of select="count(/rss/channel/item)"/>
                <xsl:text> </xsl:text>
                <xsl:choose>
                  <xsl:when test="count(/rss/channel/item) = 1">entry</xsl:when>
                  <xsl:otherwise>entries</xsl:otherwise>
                </xsl:choose>
              </p>
              <xsl:for-each select="/rss/channel/item">
                <div class="item">
                  <h2>
                    <a href="{link}"><xsl:value-of select="title"/></a>
                  </h2>
                  <p class="meta">
                    <xsl:if test="category">
                      <span class="cat"><xsl:value-of select="category"/></span>
                    </xsl:if>
                    <xsl:if test="pubDate">
                      <span><xsl:value-of select="pubDate"/></span>
                    </xsl:if>
                  </p>
                  <p class="desc"><xsl:value-of select="description"/></p>
                </div>
              </xsl:for-each>
            </xsl:when>
            <xsl:otherwise>
              <div class="empty">
                No entries yet — subscribe now and they'll appear here the moment
                there's something to report.
              </div>
            </xsl:otherwise>
          </xsl:choose>

          <footer>
            Generated by <a href="https://github.com/chihacknight/govbot">govbot</a>
            · refreshed twice daily
          </footer>
        </div>
      </body>
    </html>
  </xsl:template>
</xsl:stylesheet>
