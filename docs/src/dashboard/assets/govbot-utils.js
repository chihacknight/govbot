/* Govbot shared helpers — one copy of the small functions several pages need.
   Loaded before each page's own script (the dashboards, and the mdbook theme for
   the landing page), and exposed as window.GB. Plain ES5 so it runs anywhere the
   pages do. */
(function () {
  "use strict";

  // A bill's unique key (state + session + id). The legislation page opens
  // `legislation.html#bill=<key>` straight to that one bill, so every page that
  // links to a bill must build the key this exact way.
  function billKey(b) {
    return encodeURIComponent(b.state || "") + "~" +
      encodeURIComponent(b.session || "") + "~" + encodeURIComponent(b.id || "");
  }

  // Match a sponsor's name to exactly one legislator in a jurisdiction's roster
  // (people.json[state]: { "<surname lower>": [[given, full, party, area], …] }),
  // returning that [given, full, party, area] entry — or null when the name can't
  // be pinned to a single person. Handles a surname only ("Hall"), a surname with
  // initials ("Campbell, K") and a full "First Last" (matched on the last word,
  // disambiguated by first initial). We never guess: an ambiguous surname with no
  // distinguishing initial returns null.
  function matchLegislator(roster, name) {
    if (!name || !roster) return null;
    // Strip a trailing generational suffix ("Jr."/"Sr."/"II"/"III"/"IV"/"V"),
    // whether comma-separated ("Marcus C. Evans, Jr.") or trailing ("Addabbo Jr."),
    // so the surname isn't misread as the suffix.
    var raw = String(name).trim().replace(/,?\s*(?:jr|sr|ii|iii|iv|v)\.?\s*$/i, "").trim();
    var family = raw, first = "", parts = raw.split(/\s+/);
    var comma = raw.indexOf(",");
    if (comma !== -1) {
      family = raw.slice(0, comma).trim();
      first = raw.slice(comma + 1).replace(/[^A-Za-z]/g, "");
    } else if (parts.length > 1) {
      first = parts[0];
      family = parts[parts.length - 1];
    }
    // Try the last word as the surname key, then — for two-word surnames the
    // roster keys whole ("Ochoa Bogh", "Avila Farias") — the last two words.
    var keys = [family.toLowerCase()];
    if (comma === -1 && parts.length >= 2) {
      keys.push((parts[parts.length - 2] + " " + parts[parts.length - 1]).toLowerCase());
    }
    for (var k = 0; k < keys.length; k++) {
      var cands = roster[keys[k]];
      if (!cands || !cands.length) continue;
      if (cands.length === 1) return cands[0];
      if (first) {
        var fi = first.charAt(0).toLowerCase();
        var hits = cands.filter(function (c) { return (c[0] || "").trim().toLowerCase().charAt(0) === fi; });
        if (hits.length === 1) return hits[0];
      }
    }
    return null;  // several legislators share the surname — don't guess
  }

  var AP_MONTHS = ["Jan.", "Feb.", "March", "April", "May", "June",
                   "July", "Aug.", "Sept.", "Oct.", "Nov.", "Dec."];
  // "Sept. 20, 2026, 10:28 PM CDT" for the given Date in America/Chicago, or null
  // if Intl can't resolve the zone (very old engines) — the UTC label still
  // stands alone. The full date is included because the Central calendar day can
  // differ from the UTC date on late-evening builds.
  function centralTime(d) {
    try {
      var parts = new Intl.DateTimeFormat("en-US", {
        timeZone: "America/Chicago", year: "numeric", month: "numeric", day: "numeric",
        hour: "numeric", minute: "2-digit", hour12: true, timeZoneName: "short"
      }).formatToParts(d);
      var p = {};
      parts.forEach(function (part) { p[part.type] = part.value; });
      return AP_MONTHS[Number(p.month) - 1] + " " + p.day + ", " + p.year + ", " +
        p.hour + ":" + p.minute + " " + String(p.dayPeriod || "").toUpperCase() +
        " " + p.timeZoneName;
    } catch (e) {
      return null;
    }
  }
  // ISO "2026-09-21T03:28:00Z" -> "Sept. 21, 2026, 03:28 UTC (Sept. 20, 2026,
  // 10:28 PM CDT)"; robust to a bare date or a bad value (falls back to the raw
  // string, then null). Central time because this is a Chicago-based project and
  // the RSS feeds publish in America/Chicago too (CST or CDT, set by the zone).
  function formatAsOf(iso) {
    if (!iso) return null;
    var d = new Date(iso);
    if (isNaN(d)) return typeof iso === "string" ? iso : null;
    var s = AP_MONTHS[d.getUTCMonth()] + " " + d.getUTCDate() + ", " + d.getUTCFullYear();
    if (/T\d/.test(iso)) {
      s += ", " + String(d.getUTCHours()).padStart(2, "0") +
           ":" + String(d.getUTCMinutes()).padStart(2, "0") + " UTC";
      var central = centralTime(d);
      if (central) s += " (" + central + ")";
    }
    return s;
  }

  window.GB = { billKey: billKey, matchLegislator: matchLegislator, formatAsOf: formatAsOf };
})();
