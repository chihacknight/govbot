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
