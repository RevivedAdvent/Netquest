/* NetQuest simulator shared helpers. No frameworks, no network access. */
(function () {
  "use strict";

  var U = {};

  U.el = function (id) { return document.getElementById(id); };

  U.esc = function (s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  };

  U.log = function (container, stepNo, text) {
    if (!container) return;
    var row = document.createElement("div");
    row.className = "entry";
    row.innerHTML = '<span class="step-no">' + String(stepNo).padStart(2, "0") +
      "</span>" + U.esc(text);
    container.appendChild(row);
    container.scrollTop = container.scrollHeight;
  };

  U.clear = function (node) { while (node && node.firstChild) node.removeChild(node.firstChild); };

  U.ipToInt = function (ip) {
    var p = String(ip).split(".");
    return ((+p[0] << 24) >>> 0) + (+p[1] << 16) + (+p[2] << 8) + (+p[3]);
  };

  U.maskBits = function (prefix) { return parseInt(String(prefix).split("/")[1], 10); };

  /* Longest prefix match over a table of {prefix, via, iface, metric}. */
  U.lpm = function (table, destIp) {
    var best = null, bestBits = -1;
    var d = U.ipToInt(destIp);
    table.forEach(function (row) {
      var bits = U.maskBits(row.prefix);
      var mask = bits === 0 ? 0 : (0xFFFFFFFF << (32 - bits)) >>> 0;
      var net = (U.ipToInt(row.prefix.split("/")[0]) & mask) >>> 0;
      if (((d & mask) >>> 0) === net && bits > bestBits) {
        best = row; bestBits = bits;
      }
    });
    return best;
  };

  /* Returns [{name, value}] describing the checking of one question set. */
  U.simAssessment = function (simId, questions, answers, mount) {
    NetQuest.post("/api/simulation/" + simId + "/complete", { answers: answers })
      .then(function (data) {
        mount.innerHTML = renderResults(questions, data.results, data.summary);
      })
      .catch(function (err) {
        mount.innerHTML = '<div class="feedback bad">Could not save: ' + U.esc(err.message) + "</div>";
      });
  };

  function renderResults(questions, results, summary) {
    var byId = {};
    results.forEach(function (r) { byId[r.id] = r; });
    var html = '<div class="feedback ' + (summary.percent >= 70 ? "ok" : "bad") + '">' +
      "<h4>" + summary.percent + "% (" + summary.score + "/" + summary.max_score +
      " points)</h4><div>" +
      (summary.percent >= 70
        ? "Solid understanding of this simulation. Move on, or reset and try the fault scenarios."
        : "Below the 70% bar. Re-read the panel explanations and run the simulation again.") +
      "</div></div>";
    questions.forEach(function (q) {
      var r = byId[q.id];
      if (!r) return;
      var ok = (r.percent || 0) >= 70;
      html += '<div class="feedback ' + (ok ? "ok" : "bad") + '"><h4>' +
        U.esc(q.prompt) + "</h4><div>" +
        (r.percent !== undefined ? r.percent + "% — " : "") +
        U.esc(r.feedback || "") + "</div></div>";
    });
    html += '<p class="small mt16">Mastery and XP updated. <a href="/learn/' +
      (window.NETQUEST_SIM.module_id || "m3") + '">Back to the module</a></p>';
    return html;
  }

  U.renderAssessment = function (sim, mount) {
    var html = "";
    sim.assessment.forEach(function (q, i) {
      html += '<div class="check-block" data-qid="' + q.id + '" data-type="' + q.type + '">' +
        '<div class="qhead"><span class="small">Question ' + (i + 1) + " of " +
        sim.assessment.length + "</span></div>" +
        '<div class="qtext">' + U.esc(q.prompt) + "</div>";
      if (q.type === "mcq") {
        q.options.forEach(function (opt, idx) {
          html += '<label class="option"><input type="radio" name="' + q.id + '" value="' +
            idx + '"><span>' + U.esc(opt) + "</span></label>";
        });
      } else {
        q.checklist.forEach(function (item, idx) {
          html += '<label class="checkitem"><input type="checkbox" name="' + q.id +
            '" value="' + U.esc(item.text) + '"><span>' + U.esc(item.text) + "</span></label>";
        });
      }
      html += "</div>";
    });
    html += '<div class="btn-row mt16"><button class="btn primary" id="simSubmit">' +
      "Submit simulation assessment</button></div><div id=\"simResults\" class=\"mt16\"></div>";
    mount.innerHTML = html;

    U.el("simSubmit").addEventListener("click", function () {
      var answers = {};
      sim.assessment.forEach(function (q) {
        var nodes = document.getElementsByName(q.id);
        if (q.type === "mcq") {
          answers[q.id] = -1;
          nodes.forEach(function (n) { if (n.checked) answers[q.id] = +n.value; });
        } else {
          answers[q.id] = [];
          nodes.forEach(function (n) { if (n.checked) answers[q.id].push(n.value); });
        }
      });
      U.simAssessment(sim.id, sim.assessment, answers, U.el("simResults"));
    });
  };

  window.NetQuestSim = U;
})();
