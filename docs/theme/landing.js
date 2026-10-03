/* Govbot homepage (the mdbook root, docs/src/readme.md) behaviour.
   Loaded on every mdbook page via book.toml additional-js; a no-op unless the
   civic landing (.gb-landing) is on the page. The live cards and the firehose
   animation are ported from the retired dashboard homepage
   (docs/src/dashboard/index.html before it became a redirect); only the
   fetch/link paths changed, since the landing sits one level above dashboard/. */
(function () {
  "use strict";
  var root = document.querySelector(".gb-landing");
  if (!root) return;
  // mdbook wraps every heading in a self-link (a.header) — on the landing that only dumps a long
  // "#see-what-your-…" hash into the URL. Unwrap them so headings are plain text (and not tab stops).
  var selfLinks = root.querySelectorAll("a.header");
  for (var h = 0; h < selfLinks.length; h++) {
    var hl = selfLinks[h];
    while (hl.firstChild) hl.parentNode.insertBefore(hl.firstChild, hl);
    hl.parentNode.removeChild(hl);
  }
  var BASE = "dashboard/";
  var MS_DAY = 86400000;
  var reduceMotion = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  function esc(s) { var e = document.createElement("div"); e.textContent = s == null ? "" : String(s); return e.innerHTML; }
  // Attribute-safe: esc() escapes <>& but not quotes, which would break out of a quoted attribute.
  function escAttr(s) { return esc(s).replace(/"/g, "&quot;").replace(/'/g, "&#39;"); }
  function getJSON(name) {
    return fetch(BASE + name).then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); });
  }
  // Shared govbot.css state component: empty / error with a recovery link.
  function stateHtml(kind, title, msg, href, linkText) {
    var icon = kind === "error"
      ? '<path d="M12 3l9 16H3z"/><path d="M12 10v4M12 17h.01"/>'
      : '<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M3 10h18M8 3v4M16 3v4"/>';
    return '<div class="gb-state' + (kind === "error" ? " gb-state--error" : "") + '">' +
      '<svg class="gb-state-ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' + icon + '</svg>' +
      '<h3>' + esc(title) + '</h3><p>' + esc(msg) + '</p>' +
      '<div class="gb-state-actions"><a class="gl-btn gl-btn-ghost" href="' + escAttr(href) + '">' + esc(linkText) + '</a></div></div>';
  }

  function ago(iso) {
    if (!iso) return "";
    var d = new Date(iso); if (isNaN(d)) return "";
    var diff = Date.now() - d.getTime();
    if (diff < 0) return "soon";
    var days = Math.floor(diff / MS_DAY);
    if (days <= 0) return Math.max(1, Math.floor(diff / 3600000)) + "h";
    if (days < 30) return days + "d";
    return Math.floor(days / 30) + "mo";
  }
  // Title-case a bill title for display. Legislative titles arrive ALL CAPS
  // ("AN ACT CONCERNING...") or lowercase; normalize each word to Title Case,
  // keeping minor words lowercase (except first), and preserving an existing
  // acronym (AI, CPS) only when the source is already mixed-case.
  var TC_MINOR = { a: 1, an: 1, and: 1, as: 1, at: 1, but: 1, by: 1, en: 1, for: 1, "if": 1,
    "in": 1, "of": 1, on: 1, or: 1, per: 1, the: 1, to: 1, via: 1, vs: 1, "with": 1, nor: 1 };
  function titleCase(s) {
    s = String(s == null ? "" : s).trim();
    if (!s) return s;
    var allCaps = /[A-Z]/.test(s) && s === s.toUpperCase();
    var n = 0;
    return s.replace(/[^\s]+/g, function (w) {
      var isFirst = n === 0; n++;
      if (!allCaps && w.length <= 5 && /[A-Z]/.test(w) && w === w.toUpperCase()) return w;
      var wl = w.toLowerCase();
      var key = wl.replace(/[^a-z]/g, "");
      if (!isFirst && TC_MINOR[key]) return wl;
      return wl.charAt(0).toUpperCase() + wl.slice(1);
    });
  }

  // ---- Projects › Legislation: recent activity, one bill per state ----
  // Resolve a sponsor to a single roster legislator [given, full, party, area],
  // or null when it can't be pinned to exactly one person (never guess). Mirrors
  // legislation.html's matcher: surname-only, "Surname, F", or "First Last".
  function matchLeg(state, name, people) {
    if (!name || !people) return null;
    var roster = people[state]; if (!roster) return null;
    var raw = String(name).trim(), family = raw, first = "", comma = raw.indexOf(",");
    if (comma !== -1) { family = raw.slice(0, comma).trim(); first = raw.slice(comma + 1).replace(/[^A-Za-z]/g, ""); }
    else if (/\s/.test(raw)) { var parts = raw.split(/\s+/); first = parts[0]; family = parts[parts.length - 1]; }
    var cands = roster[family.toLowerCase()];
    if (!cands || !cands.length) return null;
    if (cands.length === 1) return cands[0];
    if (first) { var fi = first.charAt(0).toLowerCase();
      var hits = cands.filter(function (c) { return (c[0] || "").trim().toLowerCase().charAt(0) === fi; });
      if (hits.length === 1) return hits[0]; }
    return null;
  }
  function partyMeta(party) {
    var p = (party || "").toLowerCase();
    if (p.indexOf("democrat") === 0) return { letter: "D", cls: "is-dem" };
    if (p.indexOf("republican") === 0) return { letter: "R", cls: "is-rep" };
    if (!party) return { letter: "", cls: "is-unk" };
    return { letter: party.charAt(0).toUpperCase(), cls: "is-oth" };
  }
  // Initials for the monogram fallback: first + last initial (or a single letter).
  function initialsOf(full) {
    var parts = String(full || "").trim().split(/\s+/).filter(Boolean);
    if (!parts.length) return "?";
    if (parts.length === 1) return parts[0].charAt(0).toUpperCase();
    return (parts[0].charAt(0) + parts[parts.length - 1].charAt(0)).toUpperCase();
  }
  // A bill's unique key (state + session + id) so the link opens that exact
  // bill's card on the legislation page. Must match legislation.html's billKey().
  function billKey(b) {
    return encodeURIComponent(b.state || "") + "~" +
      encodeURIComponent(b.session || "") + "~" + encodeURIComponent(b.id || "");
  }
  var activityEl = document.getElementById("activity-list");
  if (activityEl) {
    Promise.all([
      getJSON("data.json").catch(function () { return null; }),
      getJSON("people.json").catch(function () { return null; }),
      // Vendored sponsor headshots (built at deploy). Absent in local dev / before
      // the first deploy — everyone just gets monograms. Fail-soft.
      getJSON("legislator_images.json").catch(function () { return null; })
    ]).then(function (res) {
      if (!res[0]) {
        activityEl.innerHTML = stateHtml("error", "Recent bills didn't load", "The legislation dashboard still works.", BASE + "legislation.html", "Open legislation");
        return;
      }
      var people = res[1] || {}, photos = res[2] || {};
      var bills = res[0].bills || [];
      var dated = bills.filter(function (b) { return b.latest_action; })
        .sort(function (a, b) { return String(b.latest_action).localeCompare(String(a.latest_action)); });
      var pool = dated.length ? dated : bills;
      // The manifest stores paths relative to dashboard/ ("assets/legislators/…").
      function photoPath(state, full) {
        var p = photos[(state || "").toLowerCase() + ":" + String(full).trim().toLowerCase()];
        return p ? BASE + p : "";
      }
      // One bill per state (newest-first), up to 4 — no state monopolizes the list.
      var seen = {}, rows = [];
      for (var i = 0; i < pool.length && rows.length < 4; i++) {
        var stk = pool[i].state || "";
        if (seen[stk]) continue;
        seen[stk] = 1; rows.push(pool[i]);
      }
      if (!rows.length) {
        activityEl.innerHTML = stateHtml("empty", "No recent bills yet", "New activity shows up after the next refresh.", BASE + "legislation.html", "Browse all bills");
        return;
      }
      var MAX_SPON = 3;
      activityEl.innerHTML = rows.map(function (b) {
        var st = (b.state || "").toUpperCase();
        var title = titleCase((b.title || "").trim());
        var action = (b.latest_action_desc || "").trim();
        if (!title) { title = action; action = ""; }
        if (title.length > 96) title = title.slice(0, 94) + "…";
        if (action.length > 84) action = action.slice(0, 82) + "…";
        var tags = (b.tags || []).slice(0, 3).map(function (t) {
          return '<span class="ar-topic">' + esc(t) + '</span>';
        }).join("");
        var tagsHtml = tags ? '<div class="ar-tags">' + tags + '</div>' : "";
        // Picture every sponsor we can resolve to a real legislator (or that has a
        // vendored photo): a headshot when we have one, otherwise a party-tinted
        // initials monogram. An unresolved non-person string (e.g. a committee)
        // with no photo is skipped.
        var pics = [];
        (b.sponsors || []).forEach(function (name) {
          var m = matchLeg(b.state, name, people);
          var full = m ? m[1] : name;
          var photo = photoPath(b.state, full);
          if (!m && !photo) return;
          pics.push({ full: full, pm: partyMeta(m ? (m[2] || "") : ""), photo: photo });
        });
        var shown = pics.slice(0, MAX_SPON);
        var spItems = shown.map(function (p) {
          // A headshot (when vendored) overlays the initials; a load error just
          // removes the <img> so the monogram shows through.
          var img = p.photo ? '<img class="ar-av-img" src="' + escAttr(p.photo) + '" alt="" loading="lazy">' : "";
          var av = '<span class="ar-av ' + p.pm.cls + '">' + esc(initialsOf(p.full)) + img + '</span>';
          var pl = p.pm.letter ? ' <span class="ar-party ' + p.pm.cls + '">' + esc(p.pm.letter) + '</span>' : "";
          return '<span class="ar-spon">' + av + '<span class="ar-spon-name">' + esc(p.full) + pl + '</span></span>';
        }).join("");
        var moreN = pics.length - shown.length;
        var moreHtml = moreN > 0 ? '<span class="ar-more">+' + moreN + ' more</span>' : "";
        var sponHtml = spItems ? '<div class="ar-sponsors">' + spItems + moreHtml + '</div>' : "";
        var titleHtml = title ? '<span class="ar-title">' + esc(title) + '</span>' : "";
        var descHtml = action ? '<div class="desc">' + esc(action) + '</div>' : "";
        return '<a class="activity-row rich" href="' + BASE + 'legislation.html#bill=' + escAttr(billKey(b)) + '">' +
          '<div class="ar-head"><span class="ar-idtitle"><span class="tag">' + esc(st) + ' · ' + esc(b.id) + '</span>' +
          titleHtml + '</span><span class="when">' + esc(ago(b.latest_action)) + '</span></div>' +
          descHtml + tagsHtml + sponHtml + '</a>';
      }).join("");
      var imgs = activityEl.querySelectorAll(".ar-av-img");
      for (var j = 0; j < imgs.length; j++) imgs[j].onerror = function () { this.remove(); };
    });
  }

  // Jurisdiction code -> readable full name (federal reads "USA (Federal)").
  var JURIS = { us: "USA (Federal)", al: "Alabama", ak: "Alaska", az: "Arizona", ar: "Arkansas",
    ca: "California", co: "Colorado", ct: "Connecticut", de: "Delaware", fl: "Florida", ga: "Georgia",
    hi: "Hawaii", id: "Idaho", il: "Illinois", "in": "Indiana", ia: "Iowa", ks: "Kansas", ky: "Kentucky",
    la: "Louisiana", me: "Maine", md: "Maryland", ma: "Massachusetts", mi: "Michigan", mn: "Minnesota",
    ms: "Mississippi", mo: "Missouri", mt: "Montana", ne: "Nebraska", nv: "Nevada", nh: "New Hampshire",
    nj: "New Jersey", nm: "New Mexico", ny: "New York", nc: "North Carolina", nd: "North Dakota",
    oh: "Ohio", ok: "Oklahoma", or: "Oregon", pa: "Pennsylvania", ri: "Rhode Island", sc: "South Carolina",
    sd: "South Dakota", tn: "Tennessee", tx: "Texas", ut: "Utah", vt: "Vermont", va: "Virginia",
    wa: "Washington", wv: "West Virginia", wi: "Wisconsin", wy: "Wyoming", dc: "District of Columbia",
    pr: "Puerto Rico", gu: "Guam", vi: "Virgin Islands", as: "American Samoa", mp: "Northern Mariana Islands" };
  function jurisName(code) {
    var k = String(code || "").toLowerCase();
    return JURIS[k] || (code ? String(code).toUpperCase() : "");
  }

  // ---- Projects › Hearings: next hearings, calendar-figure dates ----
  var hearingsEl = document.getElementById("hearings-list");
  if (hearingsEl) {
    getJSON("hearings.json").then(function (h) {
      var now = Date.now();
      var up = ((h && h.hearings) || []).filter(function (x) {
        var t = new Date(x.scheduled_iso).getTime();
        return !isNaN(t) && t >= now - MS_DAY && x.status !== "canceled";
      }).sort(function (a, b) { return String(a.scheduled_iso).localeCompare(String(b.scheduled_iso)); }).slice(0, 3);
      if (!up.length) {
        hearingsEl.innerHTML = stateHtml("empty", "No hearings scheduled right now", "Follow a state to hear when one opens.", BASE + "hearings.html", "Browse all hearings");
        return;
      }
      hearingsEl.innerHTML = up.map(function (x) {
        var d = new Date(x.scheduled_iso), bad = isNaN(d);
        var day = bad ? "—" : d.getDate();
        var mon = bad ? "" : d.toLocaleString("en-US", { month: "short" });
        var sub = bad ? "soon" : (d.toLocaleString("en-US", { weekday: "short" }) + " · " + d.getFullYear());
        var label = x.committee || x.title || "Hearing";
        if (label.length > 70) label = label.slice(0, 68) + "…";
        var url = x.witness_slip_url || x.details_url || (BASE + "hearings.html");
        var ext = /^https?:/.test(url);
        return '<a class="activity-row hearing-row" href="' + escAttr(url) + '"' + (ext ? ' target="_blank" rel="noopener"' : "") + '>' +
          '<div class="mini-date"><div class="cal-band">' + esc(mon) + '</div>' +
          '<div class="cal-day">' + esc(day) + '</div><div class="cal-sub">' + esc(sub) + '</div></div>' +
          '<span class="hr-text"><span class="hr-title">' + esc(label) + (ext ? " ↗" : "") + '</span>' +
          '<span class="hr-juris">' + esc(jurisName(x.jurisdiction)) + '</span></span></a>';
      }).join("");
    }).catch(function () {
      hearingsEl.innerHTML = stateHtml("error", "Hearings didn't load", "The hearings page still works.", BASE + "hearings.html", "Open hearings");
    });
  }

  // ---- Projects › Elections: next ballot, countdown, what's on it ----
  var GROUP_SHORT = { il_exec: "Governor & statewide offices", us_senate: "U.S. Senate", us_house: "U.S. House",
    il_senate: "IL Senate", il_house: "IL House", cps_board: "CPS board", citywide: "Mayor & citywide offices",
    council: "City Council", police_district_council: "police district councils" };
  function prettyDate(ymd) {
    return new Date(ymd + "T00:00:00").toLocaleDateString("en-US", { month: "long", day: "numeric", year: "numeric" });
  }
  function setCountdown(ymd) {
    var el = document.getElementById("election-days");
    if (!el) return;
    var days = Math.ceil((new Date(ymd + "T00:00:00").getTime() - Date.now()) / MS_DAY);
    if (days < 0) { el.hidden = true; return; }
    el.textContent = days === 0 ? "Today" : days + (days === 1 ? " day" : " days") + " away";
    el.hidden = false;
  }
  setCountdown("2026-11-03");   // the static fallback date in the markup
  getJSON("elections.json").then(function (e) {
    var today = new Date().toISOString().slice(0, 10);
    var byDate = {};
    ((e && e.races) || []).forEach(function (r) {
      if (!r.ballot_date || r.ballot_date < today) return;
      var slot = byDate[r.ballot_date] || (byDate[r.ballot_date] = { n: 0, groups: [] });
      slot.n++;
      var g = r.office_group || r.group;
      if (g && slot.groups.indexOf(g) === -1) slot.groups.push(g);
    });
    var dates = Object.keys(byDate).sort();
    if (!dates.length) return;
    // Top of the ticket first (GROUP_SHORT's key order), unknown groups last.
    var ORDER = Object.keys(GROUP_SHORT);
    function rank(g) { var i = ORDER.indexOf(g); return i === -1 ? ORDER.length : i; }
    function what(slot) {
      return slot.groups.slice().sort(function (a, b) { return rank(a) - rank(b); })
        .map(function (g) { return GROUP_SHORT[g] || g; }).join(", ");
    }
    var next = dates[0];
    document.getElementById("election-date").textContent = prettyDate(next);
    document.getElementById("election-note").textContent = byDate[next].n + " races · " + what(byDate[next]) + ".";
    setCountdown(next);
    var thenEl = document.getElementById("election-then");
    if (dates[1]) thenEl.textContent = "Then: " + prettyDate(dates[1]) + " · " + what(byDate[dates[1]]);
    else thenEl.hidden = true;
  }).catch(function () { /* keep the static fallback copy */ });

  // ---- Projects carousel: a scroll-snap row (swipe/scroll work without JS) ----
  var car = document.getElementById("gl-car");
  var slides = car ? car.querySelectorAll(".gl-slide") : [];
  var chips = root.querySelectorAll(".gl-chip");
  var prevBtn = root.querySelector('[data-car="prev"]');
  var nextBtn = root.querySelector('[data-car="next"]');
  var countEl = document.getElementById("gl-count");
  var chipRow = root.querySelector(".gl-chips");
  var cur = 0, shown = -1;
  // The row hugs the active slide (no empty band under a short one); neighbours are capped to it in CSS.
  function fitHeight() {
    if (!car || !slides[cur]) return;
    var h = slides[cur].offsetHeight;
    car.style.setProperty("--car-h", h + "px");
    car.style.height = h + "px";
    car.classList.add("is-sized");
  }
  // Fade whichever chip-row edge still hides chips.
  function chipEdges() {
    if (!chipRow) return;
    var max = chipRow.scrollWidth - chipRow.clientWidth;
    chipRow.classList.toggle("more-l", chipRow.scrollLeft > 2);
    chipRow.classList.toggle("more-r", chipRow.scrollLeft < max - 2);
  }
  // Keep the active project's chip in view (centred) as the slides change.
  function followChip() {
    var chip = chips[cur];
    if (!chipRow || !chip) return;
    var left = chip.offsetLeft - (chipRow.clientWidth - chip.offsetWidth) / 2;
    chipRow.scrollTo({ left: Math.max(0, left), behavior: reduceMotion ? "auto" : "smooth" });
  }
  function nearest() {
    var best = 0, bestD = Infinity;
    for (var i = 0; i < slides.length; i++) {
      var d = Math.abs(slides[i].offsetLeft - car.scrollLeft);
      if (d < bestD) { bestD = d; best = i; }
    }
    // At the far right the last slides can't snap to the left edge: count the end as the last.
    if (car.scrollLeft + car.clientWidth >= car.scrollWidth - 4) best = slides.length - 1;
    return best;
  }
  function sync() {
    cur = nearest();
    for (var i = 0; i < chips.length; i++) chips[i].setAttribute("aria-pressed", i === cur ? "true" : "false");
    for (var k = 0; k < slides.length; k++) slides[k].classList.toggle("is-active", k === cur);
    if (countEl) countEl.textContent = (cur + 1) + " / " + slides.length;
    if (prevBtn) prevBtn.disabled = cur === 0;
    if (nextBtn) nextBtn.disabled = cur === slides.length - 1;
    if (cur !== shown) { shown = cur; fitHeight(); followChip(); }
  }
  function go(i) {
    i = Math.max(0, Math.min(slides.length - 1, i));
    car.scrollTo({ left: slides[i].offsetLeft, behavior: reduceMotion ? "auto" : "smooth" });
  }
  if (car && slides.length) {
    var ticking = false;
    car.addEventListener("scroll", function () {
      if (ticking) return;
      ticking = true;
      requestAnimationFrame(function () { ticking = false; sync(); });
    }, { passive: true });
    for (var c = 0; c < chips.length; c++) {
      chips[c].addEventListener("click", function () { go(+this.getAttribute("data-slide")); });
    }
    if (prevBtn) prevBtn.addEventListener("click", function () { go(cur - 1); });
    if (nextBtn) nextBtn.addEventListener("click", function () { go(cur + 1); });
    window.addEventListener("resize", function () { sync(); fitHeight(); chipEdges(); });
    if (chipRow) chipRow.addEventListener("scroll", chipEdges, { passive: true });
    // Live cards fill in after load and change a slide's height — re-fit when the active one does.
    if (window.ResizeObserver) {
      var ro = new ResizeObserver(function () { fitHeight(); });
      for (var r = 0; r < slides.length; r++) ro.observe(slides[r]);
    }
    sync();
    chipEdges();
  }
  // mdbook's book.js turns ←/→ into "previous/next chapter" — on the homepage
  // that would yank the reader to another page. Swallow them here (capture phase,
  // so book.js never sees them); inside the carousel they move between projects.
  window.addEventListener("keydown", function (e) {
    if (e.key !== "ArrowLeft" && e.key !== "ArrowRight") return;
    if (e.altKey || e.ctrlKey || e.metaKey || e.shiftKey) return;
    e.stopPropagation();
    var t = e.target;
    if (car && t && t.closest && (t.closest("#gl-car") || t.closest(".gl-chips"))) {
      e.preventDefault();
      go(cur + (e.key === "ArrowRight" ? 1 : -1));
    }
  }, true);

  // ---- Social bots slide: a live, auto-scrolling feed of what the bots really posted ----
  // Sources (both public, CORS-open, fetched fail-soft and only once the carousel nears the screen):
  //  - Twitter (X), Threads and Instagram: the bot repo's own dashboard data (its `feed` records the
  //    exact post text + URL + posted time; `records` carries each bill's latest action).
  //  - Bluesky: one account per topic, read from Bluesky's public AppView API (no auth). Its posts
  //    put the dated action line ("Sept. 2, 2026: Interim Study Report…") in the bot's own reply,
  //    so the chip is read from that reply for the posts shown (none found → no chip, never a guess).
  // The newest few per platform are interleaved (every platform shows) and the list is rendered
  // twice so the auto-scroll can wrap seamlessly; the copy is aria-hidden and out of the tab order.
  (function () {
    var list = document.getElementById("gl-bf-list");
    var win = document.getElementById("gl-bf-win");
    if (!list || !win) return;
    var BOTS_DATA = "https://frankies2727.github.io/CHN-SocialMedia-Govbot-Main/data.json";
    var BSKY_API = "https://public.api.bsky.app/xrpc/app.bsky.feed.";
    var PER_PLATFORM = 5;                       // 4 platforms × 5 = the newest 20 posts
    var AVATAR = "dashboard/assets/govbot-mark.png";
    // Topic key → [display name, dot colour]; names match the slide's "Topics tracked" chips.
    var TOPICS = {
      ai_data_centers: ["AI, Data Centers & Crypto", "#818CF8"], criminal_justice: ["Criminal Justice", "#94A3B8"],
      education: ["Education", "#60A5FA"], elections_voting_rights: ["Elections & Voting", "#A78BFA"],
      environment_climate: ["Environment & Climate", "#4ADE80"], healthcare: ["Healthcare", "#2DD4BF"],
      housing: ["Housing", "#FB923C"], immigration: ["Immigration", "#22D3EE"], labor: ["Labor", "#F59E0B"],
      lgbtq: ["LGBTQ", "#E879F9"], reproductive_rights: ["Reproductive Rights", "#F472B6"],
      taxation: ["Taxation", "#FACC15"], transportation: ["Transportation", "#38BDF8"]
    };
    var BSKY = {
      ai_data_centers: "govbotaidatacenter", criminal_justice: "govbotcrimejustice", education: "govboteducation",
      elections_voting_rights: "govbotelections", environment_climate: "govbotclimate", healthcare: "govbothealthcare",
      housing: "govbothousing", immigration: "govbotimmigration", labor: "govbotlaborrights", lgbtq: "govbotlgbtq",
      reproductive_rights: "govbotreproductive", taxation: "govbottaxation", transportation: "govbottransport"
    };
    var PLAT = {
      "x-including-Crypto": { key: "x", name: "Twitter", color: "var(--gb-text)", handle: "@Govbot27" },
      "meta-threads": { key: "threads", name: "Threads", color: "var(--gb-text)", handle: "@legislationtracker.govbot" },
      "instagram": { key: "instagram", name: "Instagram", color: "#E4405F", handle: "@legislationtracker.govbot" },
      "bluesky": { key: "bluesky", name: "Bluesky", color: "#1185FE" }
    };
    var MON = ["Jan", "Feb", "Mar", "Apr", "May", "June", "July", "Aug", "Sept", "Oct", "Nov", "Dec"];

    // "Oct 1, 2026" — the day the post went up, in Central time like the rest of the site.
    function postedDay(iso) {
      var d = new Date(iso);
      if (isNaN(d)) return "";
      try { return d.toLocaleDateString("en-US", { timeZone: "America/Chicago", month: "short", day: "numeric", year: "numeric" }); }
      catch (e) { return d.toDateString().slice(4); }
    }
    // "Sept 27 · Approved by the Governor" from a record's YYYY-MM-DD date + raw action text.
    function actionLine(ymd, action) {
      // Drop the trailing vote/date detail some legislatures append ("…  06/02/2026 (Vote 14-0; RC).").
      var a = String(action || "").split(/\s{2,}/)[0].replace(/\s+\d{1,2}\/\d{1,2}\/\d{4}\b.*$/, "").replace(/[.:;,\s]+$/, "").trim();
      if (!a) return "";
      if (a.length > 72) a = a.slice(0, 72).replace(/\s+\S*$/, "") + "…";
      a = a.charAt(0).toUpperCase() + a.slice(1);
      var m = /^(\d{4})-(\d{2})-(\d{2})/.exec(ymd || "");
      if (!m) return a;
      var when = MON[+m[2] - 1] + " " + (+m[3]) + (+m[1] !== new Date().getFullYear() ? ", " + m[1] : "");
      return when + " · " + a;
    }
    // A bot post's text: optional "<emoji> Topic" line, then "<emoji> ST BILL — Headline", then the
    // summary paragraphs. Keep the headline and the first sentence or two of the summary.
    function parsePost(text) {
      var lines = String(text || "").split("\n");
      var hi = -1;
      for (var i = 0; i < lines.length; i++) { if (lines[i].indexOf(" — ") !== -1) { hi = i; break; } }
      if (hi === -1) return null;
      var headline = lines[hi].replace(/^[^A-Za-z0-9]+/, "").trim();
      var para = "";
      for (var j = hi + 1; j < lines.length; j++) { var l = lines[j].trim(); if (l && l !== "...") { para = l; break; } }
      para = para.replace(/\s*(\.\.\.|…)+\s*$/, "").trim();
      var sentences = para.match(/[^.!?]+[.!?]+["’”')]*\s*/g) || [para];
      var body = "";
      for (var k = 0; k < sentences.length; k++) {
        if (body && (body + sentences[k]).length > 260) break;
        body += sentences[k];
      }
      return { headline: headline, body: body.trim(), cardTitle: headline.replace(/^.*? — /, "") };
    }
    function topicOf(key) { return TOPICS[key] || [key ? String(key).replace(/_/g, " ") : "Legislation", "#A5ADBC"]; }

    function postHtml(p, clone) {
      var t = topicOf(p.topic), pl = PLAT[p.platform];
      var tab = clone ? ' tabindex="-1"' : "";
      var body = p.platform === "instagram"
        ? '<div class="gl-post-ig"><div class="gl-igcard" aria-hidden="true"><span class="gl-igcard-t">' + esc(t[0]) + '</span>' +
          '<span class="gl-igcard-h">' + esc(p.cardTitle) + '</span></div><div class="gl-post-body">' + esc(p.body) + '</div></div>'
        : '<div class="gl-post-body">' + esc(p.body) + '</div>';
      return '<article class="gl-post" style="--tc: ' + t[1] + '; --plc: ' + pl.color + '">' +
        '<img class="gl-post-av" src="' + AVATAR + '" alt="" width="40" height="40" loading="lazy">' +
        '<div class="gl-post-main"><div class="gl-post-top"><span class="gl-post-name">Govbot</span>' +
        '<span class="gl-post-handle">' + esc(p.handle) + '</span>' +
        '<span class="gl-post-when">· Posted: ' + esc(p.when) + '</span>' +
        '<span class="gl-post-plat"><i></i>' + esc(pl.name) + '</span></div>' +
        '<div class="gl-post-h">' + esc(p.headline) + '</div>' + body +
        '<div class="gl-post-foot">' + (p.action ? '<span class="gl-post-act">' + esc(p.action) + '</span>' : "") +
        '<span class="gl-post-topic"><i></i>' + esc(t[0]) + '</span>' +
        '<a class="gl-post-link" href="' + escAttr(p.url) + '" target="_blank" rel="noopener"' + tab +
        ' aria-label="View the ' + escAttr(pl.name) + ' post: ' + escAttr(p.headline) + '">View post ↗</a></div></div></article>';
    }

    function loadDashboard() {
      return fetch(BOTS_DATA).then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); })
        .catch(function () { return null; });
    }
    function loadBluesky() {
      var handles = Object.keys(BSKY);
      return Promise.all(handles.map(function (topic) {
        var actor = BSKY[topic] + ".bsky.social";
        return fetch(BSKY_API + "getAuthorFeed?actor=" + encodeURIComponent(actor) + "&limit=2&filter=posts_no_replies")
          .then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); })
          .then(function (d) {
            return ((d && d.feed) || []).filter(function (it) { return it.post && !it.reason; }).map(function (it) {
              var rec = it.post.record || {};
              return { topic: topic, handle: "@" + actor, text: rec.text, at: rec.createdAt || it.post.indexedAt, uri: it.post.uri,
                url: "https://bsky.app/profile/" + actor + "/post/" + String(it.post.uri).split("/").pop() };
            });
          })
          .catch(function () { return []; });
      })).then(function (all) { return [].concat.apply([], all); });
    }

    // A shown Bluesky post's action line, from the bot's own reply: "Sept. 2, 2026: <action>".
    var MONTH_IX = { jan: 1, feb: 2, mar: 3, apr: 4, may: 5, jun: 6, jul: 7, aug: 8, sep: 9, oct: 10, nov: 11, dec: 12 };
    function bskyAction(p) {
      return fetch(BSKY_API + "getPostThread?depth=1&parentHeight=0&uri=" + encodeURIComponent(p.uri))
        .then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); })
        .then(function (d) {
          var me = p.handle.slice(1), replies = (d && d.thread && d.thread.replies) || [];
          for (var i = 0; i < replies.length; i++) {
            var rp = replies[i].post;
            if (!rp || !rp.author || rp.author.handle !== me) continue;
            var m = /^([A-Za-z]{3})[a-z]*\.?\s+(\d{1,2}),\s+(\d{4}):\s*(.+)$/m.exec((rp.record && rp.record.text) || "");
            var mo = m && MONTH_IX[m[1].toLowerCase()];
            if (mo) {
              p.action = actionLine(m[3] + "-" + (mo < 10 ? "0" : "") + mo + "-" + (+m[2] < 10 ? "0" : "") + (+m[2]), m[4]);
              return;
            }
          }
        })
        .catch(function () { /* no chip */ });
    }

    function build(dash, bsky) {
      var byPlat = { "x-including-Crypto": [], "meta-threads": [], "instagram": [], "bluesky": [] };
      ((dash && dash.feed) || []).forEach(function (r) {
        if (!byPlat[r.platform] || r.platform === "bluesky" || !r.post_url || !r.posted_at) return;
        var x = parsePost(r.posted);
        if (!x) return;
        byPlat[r.platform].push({ platform: r.platform, topic: r.topic, handle: PLAT[r.platform].handle, at: r.posted_at,
          when: postedDay(r.posted_at), url: r.post_url, headline: x.headline, body: x.body, cardTitle: x.cardTitle,
          action: actionLine(r.date, r.action) });
      });
      (bsky || []).forEach(function (b) {
        var x = parsePost(b.text);
        if (!x) return;
        byPlat.bluesky.push({ platform: "bluesky", topic: b.topic, handle: b.handle, at: b.at, when: postedDay(b.at),
          url: b.url, uri: b.uri, headline: x.headline, body: x.body, cardTitle: x.cardTitle, action: "" });
      });
      var lanes = Object.keys(byPlat).map(function (k) {
        var seen = {};
        return byPlat[k].sort(function (a, b) { return String(b.at).localeCompare(String(a.at)); })
          .filter(function (p) { if (seen[p.url]) return false; seen[p.url] = 1; return true; })
          .slice(0, PER_PLATFORM);
      }).filter(function (l) { return l.length; })
        .sort(function (a, b) { return String(b[0].at).localeCompare(String(a[0].at)); });
      var out = [];
      for (var i = 0; i < PER_PLATFORM; i++) lanes.forEach(function (l) { if (l[i]) out.push(l[i]); });
      return out;
    }

    var paused = false, raf = 0, last = 0, pos = 0, looping = false;
    var slide = win.closest(".gl-slide");
    function canRun() {
      return looping && !paused && !document.hidden && (!slide || slide.classList.contains("is-active"));
    }
    function frame(ts) {
      raf = requestAnimationFrame(frame);
      var dt = last ? Math.min(ts - last, 64) : 16;
      last = ts;
      if (!canRun()) { pos = win.scrollTop; return; }
      pos += dt * 0.025;                                   // ~25px a second
      // One loop = the distance from the first post to the first post of the hidden copy.
      var clone = list.lastElementChild, period = clone ? clone.offsetTop - list.firstElementChild.offsetTop : 0;
      if (period > 0 && pos >= period) pos -= period;
      win.scrollTop = pos;
    }
    function pause() { paused = true; }
    function resume() { paused = false; pos = win.scrollTop; }
    win.addEventListener("mouseenter", pause);
    win.addEventListener("mouseleave", resume);
    win.addEventListener("focusin", pause);
    win.addEventListener("focusout", resume);
    // A touch pauses it; it picks up again a few seconds after the finger lifts.
    var touchT = 0;
    win.addEventListener("touchstart", function () { clearTimeout(touchT); pause(); }, { passive: true });
    win.addEventListener("touchend", function () { clearTimeout(touchT); touchT = setTimeout(resume, 3000); }, { passive: true });
    win.addEventListener("wheel", function () { pos = win.scrollTop; }, { passive: true });

    var started = false;
    function start() {
      if (started) return;
      started = true;
      var posts = [];
      Promise.all([loadDashboard(), loadBluesky()]).then(function (res) {
        posts = build(res[0], res[1]);
        return Promise.all(posts.filter(function (p) { return p.uri; }).map(bskyAction));
      }).then(function () {
        if (!posts.length) {
          list.innerHTML = stateHtml("error", "Couldn't load the bots' posts",
            "The social feeds didn't respond. You can still see every post on the bots' own dashboard.",
            "https://frankies2727.github.io/CHN-SocialMedia-Govbot-Main/", "Open the bot dashboard ↗");
          return;
        }
        var html = posts.map(function (p) { return postHtml(p, false); }).join("");
        looping = !reduceMotion && posts.length > 2;
        list.innerHTML = looping
          ? html + '<div class="gl-bf-list" aria-hidden="true">' + posts.map(function (p) { return postHtml(p, true); }).join("") + "</div>"
          : html;
        if (looping) raf = requestAnimationFrame(frame);
      });
    }
    if ("IntersectionObserver" in window) {
      var io = new IntersectionObserver(function (es) {
        if (es.some(function (e) { return e.isIntersecting; })) { io.disconnect(); start(); }
      }, { rootMargin: "600px 0px" });
      io.observe(car || win);
    } else {
      start();
    }
  })();

  // ---- "Built together" band: the project's contributors as live multiplayer cursors ----
  // The people on github.com/chihacknight/govbot/graphs/contributors (bots left out), with avatars
  // vendored in dashboard/assets/contributors/ — refresh this list as new people contribute.
  // Half of them are on screen at once (9 on desktop, 4 on phones); a cursor that pauses may hand
  // over to the next person not shown, so everyone passes through. @sartaj always stays on screen
  // and now and then types "government data as Git" in a cursor-chat bubble.
  // Between wanders the cursors do real work in the workspace, one task of each kind at a time:
  // type a real govbot command into the terminal, rewrite the govbot.yml topic (excerpts of the
  // real scripts/govbot-dashboard.yml descriptions), stick a note on the canvas, or drag a
  // selection box.
  (function () {
    var space = document.getElementById("gl-crew");
    var layer = document.getElementById("gl-crew-cursors");
    var fx = document.getElementById("gl-crew-fx");
    var copy = document.getElementById("gl-crew-copy");
    if (!space || !layer || !copy || !fx) return;
    var hist = document.getElementById("gl-crew-hist");
    var typed = document.getElementById("gl-crew-typed");
    var ymlKey = document.getElementById("gl-crew-key");
    var ymlD1 = document.getElementById("gl-crew-d1");
    var ymlD2 = document.getElementById("gl-crew-d2");
    var PEOPLE = [
      ["sartaj", "#3DDC84"], ["tamara-builds", "#F472B6"], ["frankies2727", "#60A5FA"], ["GrossNate", "#FBBF24"],
      ["kouglas", "#A78BFA"], ["eddiechacha", "#FB923C"], ["adaup1", "#22D3EE"], ["bbgits", "#F87171"],
      ["nate-j5", "#A3E635"], ["18indypeyton18", "#E879F9"], ["syobonaction", "#FACC15"], ["EmilySutter", "#38BDF8"],
      ["fionatagious", "#FDA4AF"], ["jleverenz", "#2DD4BF"], ["rrchow97", "#C084FC"], ["Japapino", "#FDBA74"],
      ["TahaMHusain", "#818CF8"], ["haileyplusplus", "#34D399"]
    ];
    var CMDS = ["govbot clone il", "govbot logs | govbot tag", "govbot load", "govbot build",
      "duckdb --ui govbot_data/govbot.duckdb", "govbot clone all"];
    var TOPICS = [
      ["housing", "Housing affordability, rental", "and tenant protections,"],
      ["education", "Schools, school funding,", "curriculum, teachers,"],
      ["transportation", "Roads and highways, transit", "and rail, bridges,"],
      ["immigration", "Immigration, refugees and", "asylum, citizenship,"],
      ["health care", "Health care, public health,", "insurance coverage,"]
    ];
    var NOTES = ["Review the IL bill synopses", "Write more DuckDB examples", "Test it on a phone", "Ship it!",
      "Pair on a good first issue?", "Add the next state's hearings"];
    var SAY = "government data as Git", CPS = 14, DEL_CPS = 28, HOLD = 2.4;
    var ARROW = '<svg width="22" height="22" viewBox="0 0 24 24" aria-hidden="true"><path d="M3 2.5 L20 11.2 L12.2 13 L8.6 20.5 Z" fill="currentColor" stroke="#FFFFFF" stroke-width="1.6" stroke-linejoin="round"/></svg>';
    var W = 0, H = 0, keep = null, phone = false, cur = [], next = 0, raf = 0, last = 0, visible = false;
    var sayCool = 1.5, taskCool = 1.2, busy = { term: false, yml: false, note: 0, marq: false };
    var cmdI = 0, topicI = 0, noteI = 0;

    function measure() {
      W = space.clientWidth; H = space.clientHeight;
      var s = space.getBoundingClientRect(), c = copy.getBoundingClientRect();
      keep = { x0: c.left - s.left - 30, x1: c.right - s.left + 10, y0: c.top - s.top - 30, y1: c.bottom - s.top + 12 };
      phone = W < 620;
    }
    // Does a cursor (with its name label — and a bubble/note of size big) at x,y cover the copy?
    function overCopy(x, y, big) {
      var lw = big ? (phone ? 210 : 250) : (phone ? 140 : 170), lh = big ? 86 : 44;
      return x + lw > keep.x0 && x - 20 < keep.x1 && y + lh > keep.y0 && y < keep.y1;
    }
    // A spot clear of the copy, preferably one reached without gliding across it.
    // Would a name tag parked at x,y sit on another cursor's tag (where it is, or where it's heading)?
    function crowded(x, y, me) {
      var lw = phone ? 150 : 180;
      for (var i = 0; i < cur.length; i++) {
        var o = cur[i];
        if (o === me) continue;
        if ((Math.abs(x - o.tx) < lw && Math.abs(y - o.ty) < 42) || (Math.abs(x - o.x) < lw && Math.abs(y - o.y) < 42)) return true;
      }
      return false;
    }
    function pick(fx0, fy0, big, me) {
      var best = null;
      for (var t = 0; t < 40; t++) {
        var x = 12 + Math.random() * Math.max(40, W - (big ? (phone ? 220 : 260) : (phone ? 150 : 190)));
        var y = 12 + Math.random() * Math.max(40, H - (big ? 92 : 44));
        if (overCopy(x, y, big) || (t < 30 && crowded(x, y, me))) continue;
        best = best || { x: x, y: y };
        if (fx0 == null) return best;
        var crosses = false;
        for (var k = 1; k < 10 && !crosses; k++) crosses = overCopy(fx0 + (x - fx0) * k / 10, fy0 + (y - fy0) * k / 10, big);
        if (!crosses) return { x: x, y: y };
      }
      return best || { x: 12, y: H - 44 };
    }
    // An open patch of canvas (w×h at x,y) clear of the copy and every visible window, for a
    // sticky note or a selection box; null when the layout leaves no room (then another task runs).
    function freeSpot(w, h) {
      var s = space.getBoundingClientRect(), boxes = [keep];
      var cards = space.querySelectorAll(".gl-crew-card");
      for (var i = 0; i < cards.length; i++) {
        var r = cards[i].getBoundingClientRect();
        if (r.width) boxes.push({ x0: r.left - s.left - 10, x1: r.right - s.left + 10, y0: r.top - s.top - 10, y1: r.bottom - s.top + 10 });
      }
      for (var t = 0; t < 60; t++) {
        var x = 10 + Math.random() * (W - w - 20), y = 10 + Math.random() * (H - h - 20), ok = W - w > 20 && H - h > 20;
        for (var b = 0; ok && b < boxes.length; b++) {
          var q = boxes[b];
          if (x < q.x1 && x + w > q.x0 && y < q.y1 && y + h > q.y0) ok = false;
        }
        if (ok) return { x: x, y: y };
      }
      return null;
    }
    // Where the caret of an element sits, in the workspace's coordinates.
    function endOf(el) {
      var s = space.getBoundingClientRect(), r = el.getBoundingClientRect();
      return { x: r.right - s.left + 2, y: r.top - s.top + r.height * 0.55 };
    }
    function setPerson(c, i) {
      var p = PEOPLE[i];
      c.who = i;
      c.el.style.setProperty("--cc", p[1]);
      c.el.style.color = p[1];
      c.label.innerHTML = '<img src="dashboard/assets/contributors/' + p[0] + '.png" alt="" width="18" height="18"><b>@' + p[0] + "</b>";
    }
    function build() {
      layer.innerHTML = "";
      measure();
      var slots = phone ? 4 : 9;
      cur = [];
      for (var i = 0; i < slots; i++) {
        var el = document.createElement("div");
        el.className = i === 0 ? "gl-cur is-lead" : "gl-cur";   // @sartaj draws on top
        el.innerHTML = '<span class="gl-cur-ring"></span>' + ARROW + '<span class="gl-cur-label"></span>' +
          (i === 0 ? '<span class="gl-cur-chat"></span>' : "");
        layer.appendChild(el);
        var big = i === 0, a = pick(null, null, big), b = pick(a.x, a.y, big);
        var c = { el: el, ring: el.firstChild, label: el.querySelector(".gl-cur-label"), chat: el.querySelector(".gl-cur-chat"),
          big: big, x: a.x, y: a.y, vx: 0, vy: 0, tx: b.x, ty: b.y, pause: Math.random() * 1.5, rv: 0, say: -1, task: null };
        setPerson(c, i);
        cur.push(c);
        place(c);
      }
      next = slots;
    }
    function place(c) {
      c.el.style.transform = "translate(" + c.x.toFixed(1) + "px," + c.y.toFixed(1) + "px)";
      c.el.classList.toggle("flip", c.x > W - (c.big ? (phone ? 220 : 260) : (phone ? 150 : 190)));
      c.ring.style.opacity = c.rv.toFixed(2);
      c.ring.style.transform = "scale(" + (1 + (1 - c.rv) * 1.4).toFixed(2) + ")";
    }

    // ---- tasks ----
    function startTask(c) {
      var kinds = [];
      if (!busy.term && typed) kinds.push("term");
      if (!busy.yml && ymlKey) kinds.push("yml");
      var noteSpot = busy.note < 2 ? freeSpot(190, 128) : null, marqSpot = !busy.marq ? freeSpot(210, 112) : null;
      if (noteSpot) kinds.push("note");
      if (marqSpot) kinds.push("marq");
      if (!kinds.length) return false;
      var k = kinds[Math.floor(Math.random() * kinds.length)], t = { kind: k, phase: "go", t: 0 };
      if (k === "term") { busy.term = true; t.text = CMDS[cmdI++ % CMDS.length]; t.at = function () { return endOf(typed); }; }
      if (k === "yml") {
        busy.yml = true;
        var nt = TOPICS[++topicI % TOPICS.length];
        t.ops = [[ymlKey, nt[0]], [ymlD1, nt[1]], [ymlD2, nt[2]]]; t.op = 0;
        t.at = function () { return endOf(t.ops[Math.min(t.op, 2)][0]); };
      }
      if (k === "note" || k === "marq") {
        var spot = k === "note" ? noteSpot : marqSpot;
        if (k === "note") { busy.note++; t.text = NOTES[noteI++ % NOTES.length]; } else busy.marq = true;
        t.at = function () { return spot; };
      }
      c.task = t;
      return true;
    }
    function endTask(c) {
      var k = c.task.kind;
      if (k === "term") busy.term = false;
      if (k === "yml") busy.yml = false;
      if (k === "marq") busy.marq = false;
      c.task = null;
      c.pause = 0.4 + Math.random();
      var n = pick(c.x, c.y, c.big, c); c.tx = n.x; c.ty = n.y;
    }
    // One frame of a task's work; the cursor keeps its spring toward t.at() while it works.
    function work(c, t, dt) {
      t.t += dt;
      if (t.kind === "term") {
        var n = Math.min(t.text.length, Math.floor(t.t * CPS));
        if (typed.textContent.length !== n || typed.textContent !== t.text.slice(0, n)) typed.textContent = t.text.slice(0, n);
        if (t.t > t.text.length / CPS + 0.7) {             // "enter": the command joins the history
          var line = document.createElement("span");
          line.innerHTML = "<i>$</i> ";
          line.appendChild(document.createTextNode(t.text));
          hist.appendChild(line);
          while (hist.children.length > 5) hist.removeChild(hist.firstChild);
          typed.textContent = "";
          endTask(c);
        }
      } else if (t.kind === "yml") {
        var op = t.ops[t.op], el = op[0], want = op[1];
        if (!t.from) { t.from = el.textContent; t.t = 0; el.classList.add("gl-crew-edit"); el.style.setProperty("--cc", PEOPLE[c.who][1]); }
        var del = t.from.length / DEL_CPS;
        el.textContent = t.t < del ? t.from.slice(0, Math.max(0, t.from.length - Math.floor(t.t * DEL_CPS)))
          : want.slice(0, Math.min(want.length, Math.floor((t.t - del) * CPS)));
        if (t.t > del + want.length / CPS + 0.25) {
          el.textContent = want; el.classList.remove("gl-crew-edit");
          t.from = null; t.op++;
          if (t.op >= t.ops.length) endTask(c);
        }
      } else if (t.kind === "note") {
        if (!t.el) {
          t.el = document.createElement("div");
          t.el.className = "gl-crew-note";
          t.el.style.left = (c.x + 12) + "px"; t.el.style.top = (c.y + 46) + "px";   // under the cursor's name tag
          t.el.innerHTML = '<span></span><small>— @' + PEOPLE[c.who][0] + "</small>";
          fx.appendChild(t.el);
          requestAnimationFrame(function () { t.el.classList.add("is-on"); });
        }
        t.el.firstChild.textContent = t.text.slice(0, Math.floor(t.t * CPS));
        if (t.t > t.text.length / CPS + 0.5) {
          var note = t.el;
          setTimeout(function () { note.classList.add("is-off"); }, 7000);
          setTimeout(function () { if (note.parentNode) note.parentNode.removeChild(note); busy.note = Math.max(0, busy.note - 1); }, 7700);
          endTask(c);
        }
      } else if (t.kind === "marq") {
        if (!t.el) {
          t.x0 = c.x; t.y0 = c.y;
          var d = { x: c.x + (phone ? 100 : 130) + Math.random() * 60, y: c.y + 50 + Math.random() * 40 };
          t.at = function () { return d; };
          t.el = document.createElement("div");
          t.el.className = "gl-crew-marq";
          t.el.style.setProperty("--cc", PEOPLE[c.who][1]);
          fx.appendChild(t.el);
        }
        var x0 = Math.min(t.x0, c.x), y0 = Math.min(t.y0, c.y);
        t.el.style.left = x0 + "px"; t.el.style.top = y0 + "px";
        t.el.style.width = Math.abs(c.x - t.x0) + "px"; t.el.style.height = Math.abs(c.y - t.y0) + "px";
        if (t.t > 1.8) {
          var box = t.el; box.classList.add("is-off");
          setTimeout(function () { if (box.parentNode) box.parentNode.removeChild(box); }, 600);
          endTask(c);
        }
      }
    }

    function step(dt) {
      if (sayCool > 0) sayCool -= dt;
      taskCool -= dt;
      if (taskCool <= 0) {                                   // hand a task to someone idle
        taskCool = 1.2 + Math.random() * 1.8;
        var idle = cur.filter(function (o) { return !o.task && o.say < 0; });
        if (idle.length) startTask(idle[Math.floor(Math.random() * idle.length)]);
      }
      // Gentle separation: two cursors whose name tags overlap drift apart vertically.
      for (var a = 0; a < cur.length; a++) {
        for (var b = a + 1; b < cur.length; b++) {
          var p = cur[a], q = cur[b], ddx = q.x - p.x, ddy = q.y - p.y, lw = phone ? 140 : 165;
          if (Math.abs(ddx) < lw && Math.abs(ddy) < 36) {
            var sgn = ddy >= 0 ? 1 : -1, f = (36 - Math.abs(ddy)) * 26 * dt;
            if (!(p.task && p.task.phase === "work")) p.vy -= sgn * f;
            if (!(q.task && q.task.phase === "work")) q.vy += sgn * f;
          }
        }
      }
      cur.forEach(function (c, i) {
        if (c.rv > 0) c.rv = Math.max(0, c.rv - dt * 1.6);
        if (c.chat && c.say >= 0) {                      // typing, then holding the line
          c.say += dt;
          var n = Math.min(SAY.length, Math.floor(c.say * CPS));
          if (c.chat.textContent.length !== n) c.chat.textContent = SAY.slice(0, n);
          if (c.say > SAY.length / CPS + HOLD) { c.say = -1; c.chat.classList.remove("is-on"); c.el.classList.remove("is-saying"); sayCool = 6 + Math.random() * 6; }
        }
        var t = c.task;
        if (t) { var p = t.at(); c.tx = p.x; c.ty = p.y; }
        else if (c.pause > 0) {                            // parked — but still let a nudge settle it
          c.pause -= dt;
          if (Math.abs(c.vy) > 1) { c.y = Math.max(8, Math.min(H - 40, c.y + c.vy * dt)); c.vy *= 0.85; }
          place(c); return;
        }
        // A soft spring toward the next spot: quick start, gentle arrival, a hint of overshoot.
        var dx = c.tx - c.x, dy = c.ty - c.y;
        var k = t && t.kind === "marq" && t.el ? 2.4 : 5.2;    // dragging a box is slower
        c.vx += (dx * k - c.vx * 4.2) * dt;
        c.vy += (dy * k - c.vy * 4.2) * dt;
        var sp = Math.sqrt(c.vx * c.vx + c.vy * c.vy);
        if (sp > 420) { c.vx *= 420 / sp; c.vy *= 420 / sp; }
        c.x += c.vx * dt; c.y += c.vy * dt;
        var arrived = Math.abs(dx) + Math.abs(dy) < 8 && sp < 40;
        if (t) {
          if (t.phase === "go" && arrived) { t.phase = "work"; t.t = 0; c.rv = 1; }
          if (t.phase === "work") work(c, t, dt);
        } else if (arrived) {
          c.pause = 0.5 + Math.random() * 2.4;
          if (c.chat && sayCool <= 0 && c.say < 0) {      // @sartaj stops to type
            c.say = 0; c.chat.textContent = ""; c.chat.classList.add("is-on"); c.el.classList.add("is-saying");
            c.pause = SAY.length / CPS + HOLD + 0.4;
          } else if (Math.random() < 0.45) c.rv = 1;
          else if (i !== 0 && Math.random() < 0.5) {
            var shown = cur.map(function (o) { return o.who; }), w = next % PEOPLE.length;
            while (shown.indexOf(w) !== -1) { next++; w = next % PEOPLE.length; }
            setPerson(c, w); next++;
          }
          var nn = pick(c.x, c.y, c.big, c); c.tx = nn.x; c.ty = nn.y;
        }
        place(c);
      });
    }
    function frame(ts) {
      raf = requestAnimationFrame(frame);
      var dt = last ? Math.min((ts - last) / 1000, 0.08) : 0.016;
      last = ts;
      step(dt);
    }
    function start() { if (!raf && !reduceMotion) { last = 0; raf = requestAnimationFrame(frame); } }
    function stop() { if (raf) cancelAnimationFrame(raf); raf = 0; }
    build();
    if (reduceMotion) {                            // a still, composed scatter — @sartaj's line shown whole
      if (cur[0] && cur[0].chat) { cur[0].chat.textContent = SAY; cur[0].chat.classList.add("is-on"); }
      return;
    }
    // Web fonts can change the copy's box: re-measure, and move anyone now sitting on it.
    window.addEventListener("load", function () {
      measure();
      cur.forEach(function (c) {
        if (c.task) return;
        if (overCopy(c.x, c.y, c.big)) { var a = pick(null, null, c.big, c); c.x = a.x; c.y = a.y; }
        var n = pick(c.x, c.y, c.big, c); c.tx = n.x; c.ty = n.y; place(c);
      });
    });
    if (typed) typed.textContent = "";                // the live prompt starts empty; cursors type into it
    if ("IntersectionObserver" in window) {
      new IntersectionObserver(function (es) {
        visible = es[0].isIntersecting;
        if (visible && !document.hidden) start(); else stop();
      }).observe(space);
    } else { visible = true; start(); }
    document.addEventListener("visibilitychange", function () {
      if (document.hidden) stop(); else if (visible) start();
    });
    var rt = 0, lastW = space.clientWidth;
    window.addEventListener("resize", function () {
      clearTimeout(rt);
      rt = setTimeout(function () {
        // phone ↔ desktop changes the slot count; otherwise just re-measure and keep moving
        var wasPhone = phone; measure();
        if (wasPhone !== phone) {
          fx.innerHTML = ""; busy = { term: false, yml: false, note: 0, marq: false };
          if (typed) typed.textContent = "";
          build();
        } else if (Math.abs(space.clientWidth - lastW) > 40) cur.forEach(function (c) { if (!c.task) { var n = pick(c.x, c.y, c.big, c); c.tx = n.x; c.ty = n.y; } });
        lastW = space.clientWidth;
      }, 150);
    });
  })();

  // ---- Liberty embers: little green sparks rising off the torch and drifting up
  // past the crown, flickering like embers off a fireplace. Positions are in the
  // statue image's own pixels (520×1000) so they track it at every size.
  (function () {
    var cv = root.querySelector(".gl-embers");
    var img = root.querySelector(".gl-art-img");
    if (!cv || !img || !cv.getContext) return;
    var ctx = cv.getContext("2d");
    var IW = 520, IH = 1000, N = 46;
    var W = 0, H = 0, ox = 0, oy = 0, sc = 1, embers = [], raf = 0, last = 0;
    function rnd(a, b) { return a + Math.random() * (b - a); }
    function layout() {
      var dpr = Math.min(window.devicePixelRatio || 1, 2);
      var cr = cv.getBoundingClientRect(), ir = img.getBoundingClientRect();
      W = cr.width; H = cr.height;
      cv.width = Math.round(W * dpr); cv.height = Math.round(H * dpr);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      sc = ir.height / IH; ox = ir.left - cr.left; oy = ir.top - cr.top;
    }
    // ~35% leap off the torch flame; the rest rise out of the field beside the crown.
    function spawn(e, warm) {
      var torch = Math.random() < 0.35;
      e.x = torch ? rnd(122, 165) : rnd(190, 405);
      e.y = torch ? rnd(40, 80) : rnd(150, 400);
      e.vy = -rnd(16, 38);                     // image px / s, upward
      e.vx = torch ? rnd(4, 16) : rnd(-4, 8);  // a light draught to the right
      e.size = rnd(2.5, 7.5);
      e.life = rnd(2.8, 6);
      e.age = warm ? rnd(0, e.life) : 0;
      e.ph = rnd(0, 6.28); e.fq = rnd(5, 13); e.sw = rnd(0.6, 1.8);
      e.hi = Math.random() < 0.3;
      return e;
    }
    function step(dt) {
      for (var i = 0; i < embers.length; i++) {
        var e = embers[i];
        e.age += dt;
        if (e.age >= e.life) { spawn(e, false); continue; }
        e.x += (e.vx + Math.sin(e.age * e.sw * 2 + e.ph) * 9) * dt;
        e.y += e.vy * dt;
      }
    }
    function draw(t) {
      ctx.clearRect(0, 0, W, H);
      ctx.globalCompositeOperation = "lighter";
      for (var i = 0; i < embers.length; i++) {
        var e = embers[i], k = e.age / e.life;
        var fade = Math.min(1, k / 0.15) * Math.min(1, (1 - k) / 0.4);
        var flick = 0.6 + 0.4 * Math.sin(t * e.fq + e.ph);
        var a = fade * flick;
        if (a <= 0.01) continue;
        var s = e.size * sc * (1 - k * 0.45), x = ox + e.x * sc, y = oy + e.y * sc;
        ctx.fillStyle = "rgba(61,220,132," + (a * 0.22).toFixed(3) + ")";   // soft glow
        ctx.fillRect(x - s * 1.4, y - s * 1.4, s * 2.8, s * 2.8);
        ctx.fillStyle = e.hi ? "rgba(190,255,220," + a.toFixed(3) + ")" : "rgba(124,235,176," + (a * 0.9).toFixed(3) + ")";
        ctx.fillRect(x - s / 2, y - s / 2, s, s);
      }
      ctx.globalCompositeOperation = "source-over";
    }
    function frame(ts) {
      var dt = last ? Math.min(0.05, (ts - last) / 1000) : 0.016;
      last = ts; step(dt); draw(ts / 1000);
      raf = requestAnimationFrame(frame);
    }
    function start() { if (!raf) { last = 0; raf = requestAnimationFrame(frame); } }
    function stop() { if (raf) cancelAnimationFrame(raf); raf = 0; }
    function init() {
      layout();
      if (!W) return;
      embers = [];
      for (var i = 0; i < N; i++) embers.push(spawn({}, true));
      draw(0);
      if (reduceMotion) return;                 // a still scatter, like the original art
      try {
        new IntersectionObserver(function (es) {
          if (es[0].isIntersecting && !document.hidden) start(); else stop();
        }).observe(cv);
      } catch (e) { start(); }
      document.addEventListener("visibilitychange", function () {
        if (document.hidden) stop();
        else { var r = cv.getBoundingClientRect(); if (r.bottom > 0 && r.top < innerHeight) start(); }
      });
    }
    var rt;
    window.addEventListener("resize", function () {
      clearTimeout(rt);
      rt = setTimeout(function () { layout(); if (reduceMotion) draw(0); }, 150);
    });
    if (img.complete) init(); else img.addEventListener("load", init);
  })();

  // ---- Copy buttons (install / clone / AI prompt) ----
  var copyBtns = root.querySelectorAll(".gl-copy");
  for (var b = 0; b < copyBtns.length; b++) {
    copyBtns[b].addEventListener("click", function () {
      var btn = this, src = btn.parentNode.querySelector(".gl-code-t");
      var text = src ? src.innerText.trim() : "";
      function done() {
        btn.textContent = "Copied";
        setTimeout(function () { btn.textContent = "Copy"; }, 1800);
      }
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).then(done, function () {});
      } else {
        // Old browsers: select the text so the reader can copy it themselves.
        var r = document.createRange(); r.selectNodeContents(src);
        var sel = window.getSelection(); sel.removeAllRanges(); sel.addRange(r);
      }
    });
  }

  // ---- "From the firehose to the point." canvas animation ----
  (function () {
    var canvas = document.getElementById("stream-canvas");
    if (!canvas || !canvas.getContext) return;
    var ctx = canvas.getContext("2d");
    var mqReduce = window.matchMedia ? window.matchMedia("(prefers-reduced-motion: reduce)") : { matches: false };

    // Palette read from the live CSS variables, refreshed when the theme flips.
    var pal = {};
    function readPalette() {
      var cs = getComputedStyle(document.documentElement);
      function v(n, d) { var x = cs.getPropertyValue(n).trim(); return x || d; }
      pal.text = v("--gb-text", "#F4F5F7");
      pal.text2 = v("--gb-text-2", "#A5ADBC");
      pal.surface2 = v("--gb-surface-2", "#10151F");
      pal.border = v("--gb-border", "#273042");
      pal.blue = v("--gb-blue", "#2F6BFF");
      pal.gold = v("--gb-gold", "#3DDC84");
      pal.amber = v("--gb-amber", "#E0A83C");
      pal.green = v("--gb-green", "#3FB37F");
      pal.red = v("--gb-red", "#E5484D");
      pal.purple = v("--gb-purple", "#8C78E6");
    }
    readPalette();
    try {
      new MutationObserver(readPalette).observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
      var mqDark = window.matchMedia("(prefers-color-scheme: dark)");
      if (mqDark.addEventListener) mqDark.addEventListener("change", readPalette);
    } catch (e) { /* ignore */ }

    // The orderly topic lanes on the right — colour keyed to the civic palette.
    var TOPICS = [
      { label: "AI + DATA CENTERS", c: function () { return pal.blue; } },
      { label: "EDUCATION",         c: function () { return pal.purple; } },
      { label: "HOUSING",           c: function () { return pal.amber; } },
      { label: "LABOR RIGHTS",      c: function () { return pal.red; } },
      { label: "TRANSPORTATION",    c: function () { return "#22B8CF"; } }
    ];
    // The chaotic raw records that stream in from the left.
    var RAW = ["HB 2431", "SB 88", "Roll call", "Hearing", "Witness slip", "Amendment",
      "Ballot", "Vote 34–21", "Committee", "Filing", "Agenda", "Resolution", "Motion",
      "Docket", "Gov. signs", "Veto", "Open data", "Minutes", "Redistrict", "Subpoena"];

    var W = 0, H = 0, dpr = 1, hub = { x: 0, y: 0 }, botR = 60, buckets = [], labelFont = 12, isMobile = false;
    var botEl = document.querySelector(".stream-bot");
    function layout() {
      var rect = canvas.getBoundingClientRect();
      W = rect.width; H = rect.height;
      if (!W || !H) return;
      dpr = Math.min(window.devicePixelRatio || 1, 2);
      canvas.width = Math.round(W * dpr);
      canvas.height = Math.round(H * dpr);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      var mobile = W < 560;
      isMobile = mobile;
      var bw, bx, laneTop, laneBottom;
      if (mobile) {
        // Same framing as desktop on phones — chaos left, hub middle-left, lanes
        // right — zoomed out, with the lane band stopping higher for the captions.
        hub.x = W * 0.30; hub.y = H * 0.44;
        botR = Math.max(32, Math.min(H * 0.11, 42));
        bw = Math.min(W * 0.48, 188); bx = W - bw - 10; labelFont = 9.5;
        laneTop = H * 0.14; laneBottom = H * 0.70;
      } else {
        hub.x = W * 0.5; hub.y = H * 0.5;
        botR = Math.max(46, Math.min(H * 0.22, 64));
        bw = Math.min(W * 0.28, 196); bx = W - bw - Math.min(W * 0.04, 22); labelFont = 12;
        laneTop = H * 0.13; laneBottom = H * 0.87;
      }
      // Keep the DOM robot centred on the canvas hub (which can move on mobile).
      if (botEl) { botEl.style.left = hub.x + "px"; botEl.style.top = hub.y + "px"; }
      var n = TOPICS.length;
      var gap = (laneBottom - laneTop) / (n - 1);
      buckets = TOPICS.map(function (t, i) {
        return { label: t.label, color: t.c, x: bx, y: laneTop + gap * i,
                 w: bw, h: Math.min(gap * 0.7, 30), glow: 0 };
      });
    }

    var incoming = [], outgoing = [], hubPulse = 0, spawnAcc = 0;
    function rnd(a, b) { return a + Math.random() * (b - a); }

    function spawnIncoming() {
      incoming.push({
        x: -30, y: rnd(H * 0.12, H * 0.88), sx: rnd(115, 205),
        wobP: rnd(0, Math.PI * 2), wobA: rnd(2, 7), wobF: rnd(1.5, 3),
        rot: rnd(-0.28, 0.28), label: RAW[(Math.random() * RAW.length) | 0], t: 0
      });
    }
    function spawnOutgoing() {
      var bi = (Math.random() * buckets.length) | 0;
      outgoing.push({ bi: bi, t: 0, dur: rnd(0.9, 1.5),
        sx: hub.x, sy: hub.y, cx: hub.x + (buckets[bi].x - hub.x) * 0.5, cy: rnd(H * 0.3, H * 0.7) });
    }

    function roundRect(x, y, w, h, r) {
      ctx.beginPath();
      ctx.moveTo(x + r, y); ctx.arcTo(x + w, y, x + w, y + h, r);
      ctx.arcTo(x + w, y + h, x, y + h, r); ctx.arcTo(x, y + h, x, y, r);
      ctx.arcTo(x, y, x + w, y, r); ctx.closePath();
    }
    function withAlpha(hex, a) {
      // #rgb / #rrggbb -> rgba(); pass through non-hex (already rgba) untouched.
      var h = (hex || "").trim();
      if (h.charAt(0) !== "#") return h;
      if (h.length === 4) h = "#" + h[1] + h[1] + h[2] + h[2] + h[3] + h[3];
      var n = parseInt(h.slice(1), 16);
      return "rgba(" + ((n >> 16) & 255) + "," + ((n >> 8) & 255) + "," + (n & 255) + "," + a + ")";
    }

    function drawBuckets() {
      ctx.textBaseline = "middle";
      ctx.font = "600 " + labelFont + "px 'IBM Plex Sans', system-ui, sans-serif";
      for (var i = 0; i < buckets.length; i++) {
        var b = buckets[i], col = b.color();
        var glow = b.glow;
        roundRect(b.x, b.y - b.h / 2, b.w, b.h, b.h / 2);
        ctx.fillStyle = withAlpha(col, 0.10 + glow * 0.22);
        ctx.fill();
        ctx.lineWidth = 1.4 + glow * 1.2;
        ctx.strokeStyle = withAlpha(col, 0.55 + glow * 0.45);
        ctx.stroke();
        ctx.beginPath();
        ctx.arc(b.x + b.h * 0.5, b.y, 3 + glow * 2, 0, Math.PI * 2);
        ctx.fillStyle = col; ctx.fill();
        ctx.textAlign = "left";
        ctx.fillStyle = withAlpha(pal.text, 0.9);
        ctx.fillText(b.label, b.x + b.h * 0.9, b.y + 0.5);
      }
      ctx.textAlign = "left";
      ctx.fillStyle = withAlpha(pal.text2, 0.8);
      ctx.font = "600 11px 'IBM Plex Sans', system-ui, sans-serif";
      var last = buckets[buckets.length - 1];
      if (last) ctx.fillText("…and more", last.x + last.h * 0.9, Math.min(H - 10, last.y + last.h + 14));
    }

    function step(dt) {
      spawnAcc += dt;
      var interval = 0.085;
      var maxIncoming = isMobile ? 24 : 46;   // fewer scraps on phones so the small chaos zone isn't cluttered
      while (spawnAcc >= interval) { spawnAcc -= interval; if (incoming.length < maxIncoming) spawnIncoming(); }

      var ingestX = hub.x - botR - 26;
      for (var i = incoming.length - 1; i >= 0; i--) {
        var p = incoming[i];
        p.t += dt; p.x += p.sx * dt;
        p.wobP += p.wobF * dt;
        if (p.x >= ingestX) {
          // curve toward the hub + fade as it is "ingested"
          var k = Math.min(1, (p.x - ingestX) / (hub.x - ingestX));
          p.yDraw = p.y + Math.sin(p.wobP) * p.wobA * (1 - k) + (hub.y - p.y) * k;
          p.a = 1 - k;
          if (p.x >= hub.x - botR * 0.35 || k >= 1) {
            incoming.splice(i, 1);
            hubPulse = 1;
            if (outgoing.length < 34) spawnOutgoing();
            continue;
          }
        } else {
          p.yDraw = p.y + Math.sin(p.wobP) * p.wobA;
          p.a = Math.min(1, p.t * 2.2);
        }
      }
      for (var j = outgoing.length - 1; j >= 0; j--) {
        var o = outgoing[j];
        o.t += dt / o.dur;
        if (o.t >= 1) { buckets[o.bi].glow = 1; outgoing.splice(j, 1); }
      }
      for (var b = 0; b < buckets.length; b++) buckets[b].glow = Math.max(0, buckets[b].glow - dt * 1.8);
      hubPulse = Math.max(0, hubPulse - dt * 2.4);
    }

    function render() {
      ctx.clearRect(0, 0, W, H);
      // Hub glow behind the DOM robot.
      var hg = ctx.createRadialGradient(hub.x, hub.y, 2, hub.x, hub.y, botR * (1.7 + hubPulse * 0.5));
      hg.addColorStop(0, withAlpha(pal.gold, 0.22 + hubPulse * 0.18));
      hg.addColorStop(1, withAlpha(pal.gold, 0));
      ctx.fillStyle = hg;
      ctx.beginPath(); ctx.arc(hub.x, hub.y, botR * 2.2, 0, Math.PI * 2); ctx.fill();

      drawBuckets();

      // Incoming raw scraps — muted "documents" with a tiny label.
      ctx.textAlign = "left"; ctx.textBaseline = "middle";
      ctx.font = (isMobile ? "9px" : "10px") + " 'IBM Plex Sans', system-ui, sans-serif";
      for (var i = 0; i < incoming.length; i++) {
        var p = incoming[i];
        var y = (p.yDraw == null ? p.y : p.yDraw);
        ctx.save();
        ctx.translate(p.x, y); ctx.rotate(p.rot);
        ctx.globalAlpha = Math.max(0, p.a == null ? 1 : p.a);
        var tw = ctx.measureText(p.label).width + 14;
        roundRect(-tw / 2, -8, tw, 16, 4);
        ctx.fillStyle = withAlpha(pal.surface2, 0.92); ctx.fill();
        ctx.lineWidth = 1; ctx.strokeStyle = withAlpha(pal.text2, 0.5); ctx.stroke();
        ctx.fillStyle = withAlpha(pal.text2, 0.95);
        ctx.fillText(p.label, -tw / 2 + 7, 0.5);
        ctx.restore();
      }
      ctx.globalAlpha = 1;

      // Outgoing packets — clean colour-coded dots gliding into their lane.
      for (var j = 0; j < outgoing.length; j++) {
        var o = outgoing[j], bk = buckets[o.bi], col = bk.color();
        var t = o.t, mt = 1 - t;
        var tx = bk.x + bk.h * 0.5, ty = bk.y;
        var x = mt * mt * o.sx + 2 * mt * t * o.cx + t * t * tx;
        var yy = mt * mt * o.sy + 2 * mt * t * o.cy + t * t * ty;
        var pt = Math.max(0, t - 0.05);
        var px = (1 - pt) * (1 - pt) * o.sx + 2 * (1 - pt) * pt * o.cx + pt * pt * tx;
        var py = (1 - pt) * (1 - pt) * o.sy + 2 * (1 - pt) * pt * o.cy + pt * pt * ty;
        ctx.strokeStyle = withAlpha(col, 0.5); ctx.lineWidth = 2;
        ctx.beginPath(); ctx.moveTo(px, py); ctx.lineTo(x, yy); ctx.stroke();
        ctx.beginPath(); ctx.arc(x, yy, 3.2, 0, Math.PI * 2);
        ctx.fillStyle = col; ctx.fill();
      }
    }

    // Static, motion-free composition for reduced-motion users.
    function renderStatic() {
      layout();
      for (var i = 0; i < 16; i++) {
        incoming.push({ x: rnd(10, hub.x - botR - 30), y: rnd(H * 0.12, H * 0.88),
          rot: rnd(-0.28, 0.28), a: 0.95, label: RAW[i % RAW.length] });
      }
      for (var k = 0; k < buckets.length; k++) {
        outgoing.push({ bi: k, t: rnd(0.3, 0.85), dur: 1,
          sx: hub.x, sy: hub.y, cx: hub.x + (buckets[k].x - hub.x) * 0.5, cy: rnd(H * 0.3, H * 0.7) });
        buckets[k].glow = k === 2 ? 0.8 : 0.1;
      }
      render();
    }

    var raf = 0, last = 0, running = false;
    var SPEED = 0.7;   // <1 slows the whole flow (scraps, packets, pulses) uniformly
    function frame(ts) {
      if (!running) return;
      var dt = Math.min(0.05, (ts - last) / 1000 || 0) * SPEED; last = ts;
      step(dt); render();
      raf = requestAnimationFrame(frame);
    }
    function start() { if (running || !W) return; running = true; last = performance.now(); raf = requestAnimationFrame(frame); }
    function stop() { running = false; if (raf) cancelAnimationFrame(raf); }
    function isInView() {
      var r = canvas.getBoundingClientRect();
      return r.top < (window.innerHeight || 0) && r.bottom > 0;
    }
    function init() {
      layout();
      if (!W) return;
      if (mqReduce.matches) { renderStatic(); return; }
      // Pre-warm a few seconds of flow and paint it, so the figure is already
      // full the moment it scrolls into view (and in a print/screenshot).
      for (var w = 0; w < 120; w++) step(0.035);
      render();
      // Only animate while the section is on screen and the tab is visible.
      try {
        var io = new IntersectionObserver(function (es) {
          if (es[0].isIntersecting && !document.hidden) start(); else stop();
        }, { threshold: 0.05 });
        io.observe(canvas);
      } catch (e) { start(); }
      document.addEventListener("visibilitychange", function () {
        if (document.hidden) stop(); else if (isInView()) start();
      });
    }
    var rt;
    window.addEventListener("resize", function () {
      clearTimeout(rt);
      rt = setTimeout(function () {
        layout();
        if (mqReduce.matches) { incoming = []; outgoing = []; renderStatic(); }
      }, 150);
    });
    if (mqReduce.addEventListener) mqReduce.addEventListener("change", function () {
      stop(); incoming = []; outgoing = []; hubPulse = 0;
      if (mqReduce.matches) renderStatic(); else init();
    });
    if (document.readyState === "complete") init();
    else window.addEventListener("load", init);
  })();
})();
