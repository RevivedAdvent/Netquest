/* NetQuest shared frontend helpers.
   No frameworks, no external requests. Everything degrades gracefully. */
(function () {
  "use strict";

  // --- mobile sidebar ----------------------------------------------------
  var menuBtn = document.getElementById("menuBtn");
  var sidebar = document.getElementById("sidebar");
  if (menuBtn && sidebar) {
    menuBtn.addEventListener("click", function () {
      sidebar.classList.toggle("open");
    });
    sidebar.addEventListener("click", function (e) {
      if (e.target.closest("a") && window.innerWidth <= 860) {
        sidebar.classList.remove("open");
      }
    });
  }

  // --- copy buttons ------------------------------------------------------
  function attachCopy() {
    document.querySelectorAll(".codeblock").forEach(function (block) {
      if (block.querySelector(".copy")) return;
      var pre = block.querySelector("pre");
      if (!pre) return;
      var btn = document.createElement("button");
      btn.className = "copy";
      btn.type = "button";
      btn.textContent = "copy";
      btn.addEventListener("click", function () {
        var text = pre.innerText.replace(/^\$\s?/gm, "");
        if (navigator.clipboard) {
          navigator.clipboard.writeText(text).then(function () {
            btn.textContent = "copied";
            setTimeout(function () { btn.textContent = "copy"; }, 1200);
          });
        } else {
          var ta = document.createElement("textarea");
          ta.value = text; document.body.appendChild(ta); ta.select();
          document.execCommand("copy"); document.body.removeChild(ta);
          btn.textContent = "copied";
          setTimeout(function () { btn.textContent = "copy"; }, 1200);
        }
      });
      block.appendChild(btn);
    });
  }
  attachCopy();
  window.NetQuestUI = { attachCopy: attachCopy };

  // --- tabs --------------------------------------------------------------
  // Markup uses data-tab="name" on the button and data-pane="name" on the
  // panel. Older pages used data-target + #id, so support both.
  document.querySelectorAll("[data-tabs]").forEach(function (group) {
    var tabs = Array.prototype.slice.call(group.querySelectorAll(".tab"));
    // Panes are siblings of the tab strip, not descendants, so scope the
    // lookup to the wrapping block (fall back to the whole document).
    var scope = group.parentElement || document;
    var panes = Array.prototype.slice.call(scope.querySelectorAll(".tabpane"));
    if (!panes.length) panes = Array.prototype.slice.call(document.querySelectorAll(".tabpane"));

    function paneFor(tab) {
      var name = tab.dataset.pane || tab.dataset.target || tab.dataset.tab;
      if (!name) return null;
      return scope.querySelector('[data-pane="' + name + '"]') ||
        document.querySelector('[data-pane="' + name + '"]') ||
        scope.querySelector("#" + name) || null;
    }

    function activate(tab) {
      var target = paneFor(tab);
      if (!target) return;
      tabs.forEach(function (t) {
        t.classList.toggle("active", t === tab);
        t.setAttribute("aria-selected", t === tab ? "true" : "false");
      });
      panes.forEach(function (p) { p.classList.toggle("active", p === target); });
    }

    tabs.forEach(function (tab) {
      tab.setAttribute("role", "tab");
      tab.addEventListener("click", function () { activate(tab); });
    });

    // Honour a server-rendered .active tab, otherwise open the first one.
    var initial = tabs.filter(function (t) { return t.classList.contains("active"); })[0];
    (initial || tabs[0]) && activate(initial || tabs[0]);
  });

  // --- generic JSON poster ----------------------------------------------
  window.NetQuest = {
    post: function (url, payload) {
      return fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload || {})
      }).then(function (r) {
        if (!r.ok) throw new Error("Request failed: " + r.status);
        return r.json();
      });
    },
    escape: function (s) {
      return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
        return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
      });
    },
    toast: function (msg) {
      var el = document.getElementById("nq-toast");
      if (!el) {
        el = document.createElement("div");
        el.id = "nq-toast";
        el.style.cssText = "position:fixed;bottom:18px;left:50%;transform:translateX(-50%);" +
          "background:#242424;border:1px solid #3d3d3d;color:#eee;padding:9px 16px;" +
          "border-radius:8px;font-size:13px;z-index:100;box-shadow:0 6px 24px rgba(0,0,0,.5)";
        document.body.appendChild(el);
      }
      el.textContent = msg;
      el.style.display = "block";
      clearTimeout(el._t);
      el._t = setTimeout(function () { el.style.display = "none"; }, 2600);
    }
  };
})();
