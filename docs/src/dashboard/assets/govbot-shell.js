/* ==========================================================================
   Govbot shell — shared interactions for every dashboard page.
   Dependency-free. Every hook is optional: a page that lacks an element
   simply skips that behavior. Theme is dark-first; a per-visitor override is
   remembered in localStorage. To avoid a flash, pages also inline the tiny
   pre-paint snippet below in <head>; this file wires the controls.
   ========================================================================== */
(function () {
  "use strict";
  var root = document.documentElement;
  var STORE = "govbot-theme"; // "dark" | "light" | absent (follow OS)

  /* ---- theme -------------------------------------------------------- */
  function save(v) {
    try { v ? localStorage.setItem(STORE, v) : localStorage.removeItem(STORE); } catch (e) {}
  }
  function osDark() {
    return !window.matchMedia || window.matchMedia("(prefers-color-scheme: dark)").matches;
  }
  function isDark() {
    var t = root.getAttribute("data-theme");
    if (t === "dark") return true;
    if (t === "light") return false;
    return osDark();
  }
  function applyToggleState() {
    document.querySelectorAll("[data-gb-theme-toggle]").forEach(function (btn) {
      var dark = isDark();
      btn.setAttribute("aria-pressed", String(dark));
      btn.setAttribute("aria-label", dark ? "Switch to light theme" : "Switch to dark theme");
    });
  }
  function setTheme(mode) {
    if (mode === "dark" || mode === "light") root.setAttribute("data-theme", mode);
    else root.removeAttribute("data-theme");
    save(mode === "dark" || mode === "light" ? mode : null);
    applyToggleState();
  }
  // wire toggle buttons — click flips between explicit dark and light
  document.querySelectorAll("[data-gb-theme-toggle]").forEach(function (btn) {
    btn.addEventListener("click", function () { setTheme(isDark() ? "light" : "dark"); });
  });
  applyToggleState();

  /* ---- mobile nav drawer -------------------------------------------- */
  var menuBtn = document.querySelector("[data-gb-menu]");
  var drawer = document.querySelector("[data-gb-drawer]");
  if (menuBtn && drawer) {
    var setOpen = function (open) {
      drawer.classList.toggle("open", open);
      menuBtn.setAttribute("aria-expanded", String(open));
      document.body.style.overflow = open ? "hidden" : "";
    };
    menuBtn.setAttribute("aria-expanded", "false");
    menuBtn.addEventListener("click", function () { setOpen(!drawer.classList.contains("open")); });
    // Close on any link tap — including the icon/description spans inside a group item.
    drawer.addEventListener("click", function (e) { if (e.target.closest && e.target.closest("a")) setOpen(false); });
    document.addEventListener("keydown", function (e) { if (e.key === "Escape") setOpen(false); });
  }

  /* ---- back to top -------------------------------------------------- */
  var toTop = document.querySelector("[data-gb-to-top]");
  if (toTop) {
    var onScroll = function () { toTop.classList.toggle("show", window.scrollY > 400); };
    window.addEventListener("scroll", onScroll, { passive: true });
    onScroll();
    toTop.addEventListener("click", function () {
      var reduce = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      window.scrollTo({ top: 0, behavior: reduce ? "auto" : "smooth" });
    });
  }

  /* ---- global-nav mega-menu dropdowns ------------------------------- */
  var dropdowns = document.querySelectorAll("[data-gb-dropdown]");
  function closeDropdowns(except) {
    dropdowns.forEach(function (d) {
      if (d === except) return;
      d.classList.remove("open");
      var t = d.querySelector(".gb-nav-trigger");
      if (t) t.setAttribute("aria-expanded", "false");
    });
  }
  var finePointer = window.matchMedia && window.matchMedia("(pointer: fine)").matches;
  dropdowns.forEach(function (item) {
    var trigger = item.querySelector(".gb-nav-trigger");
    if (!trigger) return;
    var setOpen = function (open) {
      if (open) closeDropdowns(item);
      item.classList.toggle("open", open);
      trigger.setAttribute("aria-expanded", String(open));
    };
    trigger.addEventListener("click", function (e) { e.stopPropagation(); setOpen(!item.classList.contains("open")); });
    if (finePointer) {
      item.addEventListener("mouseenter", function () { setOpen(true); });
      item.addEventListener("mouseleave", function () { setOpen(false); });
    }
  });
  if (dropdowns.length) {
    document.addEventListener("click", function () { closeDropdowns(null); });
    document.addEventListener("keydown", function (e) { if (e.key === "Escape") closeDropdowns(null); });
  }

  /* ---- global search (cross-site: bills, sponsors, candidates, races,
     hearings) — routes to the dedicated search page ------------------- */
  document.querySelectorAll("[data-gb-search]").forEach(function (form) {
    form.addEventListener("submit", function (e) {
      e.preventDefault();
      var input = form.querySelector("input");
      var q = input && input.value ? input.value.trim() : "";
      if (!q) return;
      // action="<path>/search.html" comes from the shared header, so it resolves from any page
      window.location.href = (form.getAttribute("action") || "search.html") + "#q=" + encodeURIComponent(q);
    });
  });

  /* ---- a clear (×) button in every search box ------------------------- */
  // Desktop browsers draw their own ×; phones (iOS Safari) don't. So one Govbot × replaces it
  // everywhere (govbot.css hides the native one). It's an absolutely placed sibling of the
  // input — no wrapper, so each page's layout is untouched — placed over the input's right edge
  // each time it's shown. Boxes built later (elections' panel/popup search) join on first focus.
  var CLEAR_SVG = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" ' +
    'stroke-linecap="round" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18"/></svg>';
  function isSearch(el) { return el && el.tagName === "INPUT" && el.type === "search"; }
  function clearBtn(input) {
    var b = input._gbClear;
    if (b && b.isConnected) return b;
    b = document.createElement("button");
    b.type = "button"; b.className = "gb-clear"; b.hidden = true;
    b.setAttribute("aria-label", "Clear search");
    b.innerHTML = CLEAR_SVG;
    b.addEventListener("mousedown", function (e) { e.preventDefault(); }); // keep focus in the box
    b.addEventListener("click", function () {
      input.value = "";
      input.dispatchEvent(new Event("input", { bubbles: true }));
      input.dispatchEvent(new Event("keyup", { bubbles: true })); // mdbook's doc search listens to keyup
      input.focus();
      syncClear(input);
    });
    input.insertAdjacentElement("afterend", b);
    input.classList.add("gb-has-clear");
    input._gbClear = b;
    return b;
  }
  function syncClear(input) {
    var b = clearBtn(input);
    b.hidden = !input.value || input.disabled || !input.offsetParent;
    if (b.hidden) return;
    b.style.left = (input.offsetLeft + input.offsetWidth - b.offsetWidth - 6) + "px";
    b.style.top = (input.offsetTop + (input.offsetHeight - b.offsetHeight) / 2) + "px";
  }
  function syncAllClear() { document.querySelectorAll('input[type="search"]').forEach(syncClear); }
  document.addEventListener("input", function (e) { if (isSearch(e.target)) syncClear(e.target); });
  document.addEventListener("focusin", function (e) { if (isSearch(e.target)) syncClear(e.target); });
  window.addEventListener("resize", syncAllClear);
  window.addEventListener("hashchange", function () { setTimeout(syncAllClear, 0); });
  window.addEventListener("load", syncAllClear);
  syncAllClear();

  /* ---- mark the current page in the shared header + drawer ------------- */
  // The header/drawer are one template on every page (docs/theme/header.html), so the active
  // link is found at runtime: a same-site link whose path matches this page (hash links skipped).
  var here = location.pathname.replace(/index\.html$/, "");
  document.querySelectorAll(".gb-nav a[href], .gb-drawer a[href]").forEach(function (a) {
    if (a.target === "_blank" || a.getAttribute("href").indexOf("#") !== -1 || a.getAttribute("role") === "menuitem") return;
    var u = new URL(a.getAttribute("href"), location.href);
    if (u.origin === location.origin && u.pathname.replace(/index\.html$/, "") === here) {
      a.setAttribute("aria-current", "page");
    }
  });
})();
