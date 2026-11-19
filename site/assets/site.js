// Key-builder site: key stepper, key chooser, display settings and species filter. The site works without JavaScript
// (the full key uses plain anchor links); this only adds the one-couplet-at-a-time view.
(function () {
  var root = document.documentElement;
  root.classList.add("js");

  // ---------- text size and Microscope mode (remembered per browser)
  function store(k, v) { try { localStorage.setItem(k, v); } catch (e) {} }
  function syncCtl() {
    document.querySelectorAll(".viewctl [data-size]").forEach(function (b) {
      b.classList.toggle("on", b.getAttribute("data-size") === (root.dataset.size || "m"));
      b.setAttribute("aria-pressed", b.classList.contains("on"));
    });
    var sc = document.querySelector(".viewctl .scope");
    if (sc) { var on = root.dataset.view === "scope"; sc.classList.toggle("on", on); sc.setAttribute("aria-pressed", on); }
  }
  document.querySelectorAll(".viewctl [data-size]").forEach(function (b) {
    b.addEventListener("click", function () { root.dataset.size = b.getAttribute("data-size"); store("sf-size", root.dataset.size); syncCtl(); });
  });
  var scopeBtn = document.querySelector(".viewctl .scope");
  if (scopeBtn) scopeBtn.addEventListener("click", function () {
    root.dataset.view = root.dataset.view === "scope" ? "normal" : "scope"; store("sf-view", root.dataset.view); syncCtl();
  });
  syncCtl();

  // ---------- home page photo slideshow (pauses on hover/focus and when the tab is hidden)
  (function () {
    var show_ = document.querySelector(".slideshow");
    if (!show_) return;
    var slides = show_.querySelectorAll(".slide"), dots = show_.querySelectorAll(".dots button");
    var cur = 0, timer = null, paused = false, secs = (+show_.getAttribute("data-seconds") || 10) * 1000;
    var go = function (i) {
      slides[cur].classList.remove("on"); if (dots[cur]) dots[cur].classList.remove("on");
      cur = (i + slides.length) % slides.length;
      slides[cur].classList.add("on"); if (dots[cur]) dots[cur].classList.add("on");
    };
    var start = function () { clearInterval(timer); if (slides.length > 1) timer = setInterval(function () { if (!paused && !document.hidden) go(cur + 1); }, secs); };
    dots.forEach(function (d, i) { d.addEventListener("click", function () { go(i); start(); }); });
    show_.addEventListener("mouseenter", function () { paused = true; });
    show_.addEventListener("mouseleave", function () { paused = false; });
    show_.addEventListener("focusin", function () { paused = true; });
    show_.addEventListener("focusout", function () { paused = false; });
    start();
  })();

  // ---------- keys.html: choose which embedded key is shown
  var sel = document.getElementById("keyselect");
  if (sel && sel.options.length) {
    var dkeys = document.querySelectorAll(".dkey");
    function show(kid, scrollTo) {
      var found = false;
      dkeys.forEach(function (d) { var on = d.getAttribute("data-key") === kid; d.classList.toggle("shown", on); found = found || on; });
      if (!found) return false;
      sel.value = kid;
      try { sessionStorage.setItem("sf-key", kid); } catch (e) {}
      if (scrollTo) { var t = document.getElementById(scrollTo); if (t) t.scrollIntoView(); }
      return true;
    }
    function fromHash() {
      var h = decodeURIComponent(location.hash.slice(1));
      if (!h) return false;
      if (h.indexOf("key-") === 0) return show(h.slice(4), h);
      var kid = null;
      dkeys.forEach(function (d) { var k = d.getAttribute("data-key"); if (h.indexOf(k + "-") === 0 && (!kid || k.length > kid.length)) kid = k; });
      return kid ? show(kid, h) : false;
    }
    sel.addEventListener("change", function () { show(sel.value); window.history.replaceState(null, "", "#key-" + sel.value); document.querySelector(".keybar").scrollIntoView(); });
    document.querySelectorAll("[data-show]").forEach(function (a) {
      a.addEventListener("click", function () { show(a.getAttribute("data-show")); });
    });
    document.getElementById("keytop").addEventListener("click", function () {
      var d = document.querySelector(".dkey.shown .couplet"); if (d) d.scrollIntoView();
    });
    window.addEventListener("hashchange", fromHash);
    var saved = null; try { saved = sessionStorage.getItem("sf-key"); } catch (e) {}
    if (!fromHash()) show(saved && document.querySelector('.dkey[data-key="' + saved + '"]') ? saved : sel.options[0].value);
  }

  // ---------- species list: highlight the species a key result pointed to
  if (location.hash && document.querySelector("ul.taxlist")) {
    var li = document.getElementById(decodeURIComponent(location.hash.slice(1)));
    if (li) li.scrollIntoView({ block: "center" });
  }

  // ---------- key pages
  var full = document.getElementById("fullkey");
  var stepper = document.getElementById("stepper");
  if (full && stepper) {
    var cur = stepper.querySelector(".current");
    var trailEl = stepper.querySelector(".trail");
    var start = stepper.getAttribute("data-start");
    var history = [];

    function couplet(id) { return full.querySelector('.couplet[data-c="' + CSS.escape(id) + '"]'); }

    function render() {
      var id = history[history.length - 1];
      cur.innerHTML = "";
      var c = couplet(id);
      if (!c) { cur.textContent = "Couplet " + id + " not found."; return; }
      var clone = c.cloneNode(true);
      clone.removeAttribute("id");
      clone.querySelectorAll("[id]").forEach(function (e) { e.removeAttribute("id"); });
      clone.querySelectorAll(".lead").forEach(function (lead) {
        var go = lead.querySelector("a.goto");
        lead.addEventListener("click", function (ev) {
          if (ev.target.closest("a.thumb")) return;           // let figure links open
          if (ev.target.closest("details.note, details.update")) return;  // open/close a note without choosing the lead
          if (go) { ev.preventDefault(); history.push(go.getAttribute("data-goto")); render(); save(); window.scrollTo({top: stepper.offsetTop - 10}); }
          else if (!ev.target.closest("a.taxon")) {
            var t = lead.querySelector(".res").cloneNode(true);
            var box = document.createElement("div"); box.className = "result";
            box.innerHTML = "<b>Result:</b> ";
            box.appendChild(t);
            box.insertAdjacentHTML("beforeend", '<p class="muted">Check the ⚠ notes on the leads you passed, then open the species page to compare diagnostic notes.</p>');
            var old = cur.querySelector(".result"); if (old) old.remove();
            cur.appendChild(box);
          }
        });
      });
      cur.appendChild(clone);
      trailEl.innerHTML = "Path: " + history.map(function (h, i) {
        return '<a data-i="' + i + '">' + h + "</a>";
      }).join(" › ");
      trailEl.querySelectorAll("a").forEach(function (a) {
        a.addEventListener("click", function () { history = history.slice(0, +a.getAttribute("data-i") + 1); render(); save(); });
      });
    }
    function save() { try { sessionStorage.setItem("path:" + location.pathname, JSON.stringify(history)); } catch (e) {} }
    function load() {
      try { var h = JSON.parse(sessionStorage.getItem("path:" + location.pathname) || "null"); if (h && h.length) return h; } catch (e) {}
      return [start];
    }
    stepper.querySelector(".back").addEventListener("click", function () { if (history.length > 1) { history.pop(); render(); save(); } });
    stepper.querySelector(".restart").addEventListener("click", function () { history = [start]; render(); save(); });

    var buttons = document.querySelectorAll(".modes button");
    function mode(m) {
      buttons.forEach(function (b) { b.classList.toggle("on", b.getAttribute("data-mode") === m); });
      stepper.classList.toggle("hidden", m !== "step");
      full.classList.toggle("hidden", m !== "full");
    }
    buttons.forEach(function (b) { b.addEventListener("click", function () { mode(b.getAttribute("data-mode")); }); });

    history = load();
    render();
    // a link like keys/x.html#l27a or #c27 opens the full key at that place
    if (location.hash) { mode("full"); var t = document.querySelector(location.hash); if (t) t.scrollIntoView(); }
    else mode("step");
  }

  // ---------- species list filter
  var f = document.getElementById("taxfilter");
  if (f) {
    var th = document.getElementById("thonly");
    var q = new URLSearchParams(location.search).get("q");
    if (q) f.value = q;
    function apply() {
      var v = f.value.trim().toLowerCase();
      document.querySelectorAll("ul.taxlist li").forEach(function (li) {
        var ok = (!v || li.getAttribute("data-name").indexOf(v) >= 0) && (!th.checked || li.querySelector(".th"));
        li.classList.toggle("hidden", !ok);
      });
      document.querySelectorAll("ul.taxlist").forEach(function (ul) {
        var any = ul.querySelector("li:not(.hidden)");
        ul.classList.toggle("hidden", !any);
        ul.previousElementSibling.classList.toggle("hidden", !any);
      });
    }
    f.addEventListener("input", apply); th.addEventListener("change", apply); apply();
  }
})();
