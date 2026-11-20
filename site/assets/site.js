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

  // ---------- tables: give every cell its column name (shown above the value when tables become cards on phones)
  document.querySelectorAll("table.list").forEach(function (t) {
    var head = null;
    Array.prototype.forEach.call(t.rows, function (tr) {
      var th = tr.querySelectorAll("th"), td = tr.querySelectorAll("td");
      if (!td.length && th.length > 1) { tr.classList.add("hdr"); head = Array.prototype.map.call(th, function (x) { return x.textContent.trim(); }); return; }
      if (!td.length && th.length === 1 && th[0].colSpan > 1) { tr.classList.add("grp"); return; }
      if (head) Array.prototype.forEach.call(td, function (c, i) { if (head[i]) c.setAttribute("data-label", head[i]); });
    });
  });

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

  // ---------- term popups: any element with data-t="key" (words in keys, diagram hotspots, chips)
  // Mouse: shows on hover. Keyboard: on focus. Touch: first tap shows the popup, a second tap follows the link.
  var siteBase = (function () {
    var s = document.querySelector('script[src$="assets/site.js"]');
    return s ? s.getAttribute("src").replace(/assets\/site\.js$/, "") : "";
  })();
  var lastPointer = "mouse";
  document.addEventListener("pointerdown", function (e) { lastPointer = e.pointerType || "mouse"; }, true);
  (function () {
    var T = window.SF_TERMS;
    if (!T) return;
    var pop = document.createElement("div");
    pop.id = "gpop"; pop.setAttribute("role", "tooltip"); pop.hidden = true;
    document.body.appendChild(pop);
    var cur = null, hideT = null;
    var SEX = { female: "♀ female", male: "♂ male", both: "♀♂ both sexes" };
    function content(k) {
      var e = T[k];
      return '<div class="gp-h"><b>' + e.t + "</b>" + (e.f ? '<span class="gp-f">' + e.f + "</span>" : "") +
        (e.x && SEX[e.x] ? '<span class="gp-x">' + SEX[e.x] + "</span>" : "") + "</div>" +
        '<p class="gp-d">' + e.d + "</p>" +
        (e.s ? '<p class="gp-s">Also called: ' + e.s + "</p>" : "") +
        '<a class="gp-a" href="' + siteBase + e.g + '">' + (e.l ? "Glossary: " + e.l : "Open in glossary") + " ›</a>";
    }
    function place(el) {
      var r = el.getBoundingClientRect();
      pop.style.left = "0px"; pop.style.top = "0px";
      var pw = pop.offsetWidth, ph = pop.offsetHeight;
      var x = Math.min(Math.max(8, r.left + r.width / 2 - pw / 2), window.innerWidth - pw - 8);
      var y = r.bottom + 8;
      if (y + ph > window.innerHeight - 8 && r.top - ph - 8 > 8) y = r.top - ph - 8;
      pop.style.left = (x + window.scrollX) + "px"; pop.style.top = (y + window.scrollY) + "px";
    }
    function show(el) {
      var k = el.getAttribute("data-t");
      if (!T[k]) return;
      clearTimeout(hideT);
      if (cur === el && !pop.hidden) return;
      if (cur) cur.classList.remove("gt-on");
      cur = el; el.classList.add("gt-on");
      pop.innerHTML = content(k); pop.hidden = false; place(el);
    }
    function hideNow() { pop.hidden = true; if (cur) cur.classList.remove("gt-on"); cur = null; }
    function hide() { clearTimeout(hideT); hideT = setTimeout(hideNow, 220); }
    document.addEventListener("mouseover", function (e) {
      if (lastPointer === "touch") return;
      var el = e.target.closest("[data-t]");
      if (el) show(el);
      else if (cur && !e.target.closest("#gpop")) hide();
    });
    pop.addEventListener("mouseenter", function () { clearTimeout(hideT); });
    pop.addEventListener("mouseleave", hide);
    document.addEventListener("focusin", function (e) { var el = e.target.closest && e.target.closest("[data-t]"); if (el) show(el); });
    document.addEventListener("focusout", function (e) { if (e.target.closest && e.target.closest("[data-t]")) hide(); });
    document.addEventListener("keydown", function (e) { if (e.key === "Escape") hideNow(); });
    window.addEventListener("resize", function () { if (cur && !pop.hidden) place(cur); });
    document.addEventListener("click", function (e) {
      var el = e.target.closest("[data-t]");
      if (el && lastPointer !== "mouse" && (cur !== el || pop.hidden)) {  // touch / pen: first tap only shows
        e.preventDefault(); e.stopPropagation(); show(el); return;
      }
      if (!el && !e.target.closest("#gpop")) hideNow();
    }, true);
  })();

  // ---------- glossary page: diagram tabs, hotspot highlighting, filters
  (function () {
    var ex = document.getElementById("explorer");
    if (ex) {
      var tabs = ex.querySelectorAll(".dtabs button"), panels = ex.querySelectorAll(".dpanel");
      var showD = function (d) {
        tabs.forEach(function (b) { var on = b.getAttribute("data-d") === d; b.classList.toggle("on", on); b.setAttribute("aria-selected", on); });
        panels.forEach(function (p) { p.classList.toggle("on", p.getAttribute("data-d") === d); });
      };
      tabs.forEach(function (b) { b.addEventListener("click", function () { showD(b.getAttribute("data-d")); }); });
      var flash = function (sel) {
        ex.querySelectorAll(".hs.flash").forEach(function (h) { h.classList.remove("flash"); });
        ex.querySelectorAll(sel).forEach(function (h) { h.classList.add("flash"); });
      };
      // chips in the side list highlight their hotspots
      ex.querySelectorAll(".chip").forEach(function (c) {
        c.addEventListener("mouseenter", function () { flash('.dpanel.on .hs[data-t="' + c.getAttribute("data-hs") + '"]'); });
        c.addEventListener("mouseleave", function () { flash("none"); });
      });
      ex.querySelectorAll(".showall input").forEach(function (cb) {
        cb.addEventListener("change", function () { ex.classList.toggle("outline", cb.checked);
          ex.querySelectorAll(".showall input").forEach(function (o) { o.checked = cb.checked; }); });
      });
      // glossary cards: hovering highlights the part on the visible diagram; "Show on diagram" switches to it
      document.querySelectorAll(".gcard").forEach(function (card) {
        card.addEventListener("mouseenter", function () { flash('.dpanel.on .hs[data-g="' + card.id + '"]'); });
        card.addEventListener("mouseleave", function () { flash("none"); });
      });
      document.querySelectorAll(".locate").forEach(function (b) {
        b.addEventListener("click", function () {
          showD(b.getAttribute("data-d"));
          ex.scrollIntoView({ behavior: "smooth", block: "start" });
          var g = b.getAttribute("data-g");
          flash('.dpanel.on .hs[data-g="' + g + '"]');
          setTimeout(function () { flash("none"); }, 3500);
        });
      });
    }
    var gs = document.getElementById("gsearch");
    if (gs) {
      var sex = "", part = "";
      var segs = document.querySelectorAll(".gfilter .seg button"), pcs = document.querySelectorAll(".gfilter .partchips button");
      var count = document.querySelector(".gcount");
      var apply = function () {
        var v = gs.value.trim().toLowerCase(), n = 0;
        document.querySelectorAll(".gcard").forEach(function (c) {
          var cs = c.getAttribute("data-sex");
          var ok = (!v || c.getAttribute("data-text").indexOf(v) >= 0) && (!sex || cs === sex || cs === "both") &&
            (!part || c.getAttribute("data-part") === part);
          c.classList.toggle("hidden", !ok); if (ok) n++;
        });
        document.querySelectorAll(".gsec").forEach(function (s) { s.classList.toggle("hidden", !s.querySelector(".gcard:not(.hidden)")); });
        count.textContent = (v || sex || part) ? n + " term" + (n === 1 ? "" : "s") + " shown" : "";
      };
      segs.forEach(function (b) { b.addEventListener("click", function () {
        sex = b.getAttribute("data-sex"); segs.forEach(function (o) { o.classList.toggle("on", o === b); }); apply(); }); });
      pcs.forEach(function (b) { b.addEventListener("click", function () {
        part = part === b.getAttribute("data-part") ? "" : b.getAttribute("data-part");
        pcs.forEach(function (o) { o.classList.toggle("on", o.getAttribute("data-part") === part); }); apply(); }); });
      gs.addEventListener("input", apply);
      // a link to glossary.html#term highlights that card
      var hl = function () { var t = location.hash && document.getElementById(location.hash.slice(1));
        if (t && t.classList.contains("gcard")) { t.classList.remove("pulse"); void t.offsetWidth; t.classList.add("pulse"); } };
      window.addEventListener("hashchange", hl); hl();
    }
  })();

  // ---------- offline use: service worker (saves the whole site), progress label, install button, update notice
  (function () {
    if (!("serviceWorker" in navigator) || !/^https?:$/.test(location.protocol)) return;  // not for file:// copies
    var s = document.querySelector('script[src$="assets/site.js"]');
    var base = s ? s.getAttribute("src").replace(/assets\/site\.js$/, "") : "";
    var label = document.getElementById("offline"), inst = document.getElementById("installbtn");
    var hadController = !!navigator.serviceWorker.controller;
    function show(st) {
      if (!label || !st || st.type !== "sf-offline" || st.state === "idle") return;
      label.hidden = false;
      label.className = "offline " + st.state;
      if (st.state === "ready") { label.textContent = "✓ Available offline"; label.title = "The whole site is saved on this device and works without internet."; }
      else if (st.state === "saving") { label.textContent = "⤓ Saving for offline " + Math.round(100 * st.done / Math.max(1, st.total)) + "%"; label.title = "Keep this page open with internet until it says Available offline."; }
      else if (st.state === "partial") { label.textContent = "⚠ Partly saved offline"; label.title = "Some files could not be saved. Reload with internet to finish."; }
      else label.hidden = true;
    }
    navigator.serviceWorker.addEventListener("message", function (e) { show(e.data); });
    navigator.serviceWorker.register(base + "sw.js").then(function (reg) {
      if (navigator.serviceWorker.controller) navigator.serviceWorker.controller.postMessage("sf-status");
      else if (reg.installing || reg.waiting) show({ type: "sf-offline", state: "saving", done: 0, total: 1 });
    }).catch(function () {});
    navigator.serviceWorker.addEventListener("controllerchange", function () {
      if (!hadController) { hadController = true; return; }  // first install: nothing to reload
      var bar = document.createElement("div");
      bar.className = "updbar";
      bar.innerHTML = 'A new version of the site has been saved. <button type="button">Reload</button>';
      bar.querySelector("button").addEventListener("click", function () { location.reload(); });
      document.body.appendChild(bar);
    });
    var deferred = null;
    window.addEventListener("beforeinstallprompt", function (e) { e.preventDefault(); deferred = e; if (inst) inst.hidden = false; });
    if (inst) inst.addEventListener("click", function () {
      if (!deferred) return;
      deferred.prompt();
      deferred.userChoice.then(function () { deferred = null; inst.hidden = true; });
    });
    window.addEventListener("appinstalled", function () { if (inst) inst.hidden = true; });
  })();

  // ---------- figure viewer (all pages): figures open in an overlay instead of leaving the page (zoom, ← → between
  // figures). The phone/browser Back button closes it, so the installed app (which has no Back button of its own)
  // never gets stuck on a bare image.
  (function () {
    var SEL = "a.thumb, .gallery figure > a, .gthumbs a";
    var isImg = function (a) { return /\.(jpe?g|png|gif|webp|svg)$/i.test(a.getAttribute("href") || ""); };
    var box = null, list = [], idx = 0;
    function caption(a) {
      var fig = a.closest("figure"), fc = fig && fig.querySelector("figcaption");
      return fc ? fc.innerHTML : (a.getAttribute("title") || "");
    }
    function build() {
      box = document.createElement("div");
      box.id = "lbox"; box.setAttribute("role", "dialog"); box.setAttribute("aria-modal", "true"); box.setAttribute("aria-label", "Figure viewer");
      box.innerHTML = '<button type="button" class="lb-x" aria-label="Close">✕</button>' +
        '<button type="button" class="lb-p" aria-label="Previous figure">‹</button><button type="button" class="lb-n" aria-label="Next figure">›</button>' +
        '<div class="lb-stage"><img alt=""></div><div class="lb-cap"></div>';
      document.body.appendChild(box);
      box.querySelector(".lb-x").addEventListener("click", close);
      box.querySelector(".lb-p").addEventListener("click", function () { open(idx - 1); });
      box.querySelector(".lb-n").addEventListener("click", function () { open(idx + 1); });
      box.querySelector(".lb-stage").addEventListener("click", function (e) {
        if (e.target.tagName === "IMG") box.classList.toggle("zoom"); else close();
      });
    }
    function open(i) {
      if (!box) build();
      idx = (i + list.length) % list.length;
      var a = list[idx];
      box.classList.remove("zoom");
      box.querySelector("img").src = a.getAttribute("href");
      box.querySelector(".lb-cap").innerHTML = caption(a) +
        ' <span class="lb-hint">' + (list.length > 1 ? (idx + 1) + " / " + list.length + " · " : "") + "tap the image to zoom · ✕ or Back to close</span>";
      box.classList.toggle("single", list.length < 2);
      if (!box.classList.contains("on")) { try { window.history.pushState({ sfViewer: 1 }, ""); } catch (e) {} }  // Back = close
      box.classList.add("on"); document.documentElement.classList.add("lb-open");
      box.querySelector(".lb-x").focus();
    }
    function hide() { if (box) { box.classList.remove("on"); document.documentElement.classList.remove("lb-open"); } }
    function close() {  // ✕, Esc, tap outside: undo the history entry added on open (popstate then hides)
      if (!box || !box.classList.contains("on")) return;
      if (window.history.state && window.history.state.sfViewer) window.history.back(); else hide();
    }
    window.addEventListener("popstate", function () { if (box && box.classList.contains("on")) hide(); });
    document.addEventListener("click", function (e) {
      if (e.defaultPrevented || e.button !== 0 || e.ctrlKey || e.metaKey || e.shiftKey) return;
      var a = e.target.closest(SEL);
      if (!a || !isImg(a)) return;
      e.preventDefault();
      var scope = a.closest(".lead, .gcard, .gallery, tr") || document;
      list = Array.prototype.filter.call(scope.querySelectorAll(SEL), isImg);
      open(list.indexOf(a));
    });
    document.addEventListener("keydown", function (e) {
      if (!box || !box.classList.contains("on")) return;
      if (e.key === "Escape") close();
      else if (e.key === "ArrowLeft") open(idx - 1);
      else if (e.key === "ArrowRight") open(idx + 1);
    });
  })();
})();
