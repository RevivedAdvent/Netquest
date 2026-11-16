/* Layer 2 switching simulator: MAC learning, flooding, filtering, VLANs. */
(function () {
  "use strict";
  var U = window.NetQuestSim;
  var data = window.NETQUEST_DATA;
  if (!data) return;

  var macTable = {};        /* mac -> {port, vlan} */
  var learnCount = {};      /* mac -> frames seen */
  var frameIndex = 0;
  var logNo = 0;
  var pendingFrame = null;
  var steps = [];

  var stage = U.el("simStage");
  var log = U.el("simLog");
  var detail = U.el("simDetail");
  var tableHost = U.el("macTable");

  function hostById(id) {
    return data.hosts.filter(function (h) { return h.id === id; })[0];
  }

  function renderTopology(activeHostId) {
    var html = '<div class="node-wrap">';
    data.hosts.forEach(function (h) {
      var cls = "node";
      if (activeHostId && h.id === activeHostId) cls += " active";
      html += '<div class="' + cls + '"><div class="nname">' + U.esc(h.name) +
        "</div><div class=\"naddr\">" + U.esc(h.mac) + "</div>" +
        '<div class="naddr">port ' + h.port + " &middot; VLAN " + h.vlan + "</div>" +
        '<div class="naddr">' + U.esc(h.ip) + "</div></div>";
    });
    html += "</div>";
    html += '<div class="mt16 small" style="text-align:center">' +
      '<div class="muted small">switch ' + U.esc(data.switch.name) + " &middot; ports 1-" +
      data.switch.ports + " &middot; VLANs " + data.switch.vlans.join(", ") + "</div></div>";
    var grid = '<div class="port-grid mt16">';
    for (var p = 1; p <= data.switch.ports; p++) {
      var owner = data.hosts.filter(function (h) { return h.port === p; })[0];
      grid += '<div class="port ' + (owner ? "used" : "") + '">port ' + p +
        (owner ? "<br>" + U.esc(owner.name) + "<br>VLAN " + owner.vlan : "") + "</div>";
    }
    grid += "</div>";
    stage.innerHTML = html + grid;
  }

  function renderTable() {
    var rows = Object.keys(macTable).sort();
    var html = '<table class="mac-table"><tr><th>MAC address</th><th>Port</th><th>VLAN</th></tr>';
    if (!rows.length) {
      html += '<tr><td colspan="3" class="muted">empty &mdash; the switch has learned nothing yet</td></tr>';
    }
    rows.forEach(function (mac) {
      var e = macTable[mac];
      html += "<tr><td>" + U.esc(mac) + "</td><td>" + e.port + "</td><td>" + e.vlan + "</td></tr>";
    });
    html += "</table>";
    tableHost.innerHTML = html;
  }

  function nextStep() {
    if (pendingFrame && steps.length) {
      var st = steps.shift();
      applyStep(st);
      return;
    }
    if (frameIndex >= data.frames.length) {
      detail.innerHTML = '<h4>All predefined frames processed</h4><p class="small">' +
        "Reset to run again, or add your own frame below to test a specific case.</p>";
      return;
    }
    var f = data.frames[frameIndex++];
    pendingFrame = f;
    planFrame(f);
    var st = steps.shift();
    applyStep(st);
  }

  function planFrame(f) {
    steps = [];
    var src = hostById(f.src);
    if (!src) return;
    var srcName = src.name;
    var dst = f.kind === "broadcast" ? null : hostById(f.dst);
    var dstMac = f.kind === "broadcast" ? "FF:FF:FF:FF:FF:FF" : (dst ? dst.mac : null);
    var ingress = src.port;

    steps.push({
      title: "1-3. Learn from the source",
      text: srcName + " sends from port " + ingress + " with source MAC " + src.mac +
        ". The switch records " + src.mac + " -> port " + ingress + " (VLAN " + src.vlan + ").",
      apply: function () {
        macTable[src.mac] = { port: ingress, vlan: src.vlan };
        learnCount[src.mac] = (learnCount[src.mac] || 0) + 1;
        renderTable();
        renderTopology(src.id);
      }
    });

    if (f.kind === "broadcast") {
      steps.push({
        title: "4-5. Destination is broadcast",
        text: "Destination MAC FF:FF:FF:FF:FF:FF is the broadcast address, so the switch floods it to every port in VLAN " +
          src.vlan + " except the ingress port. Other VLANs never see it.",
        apply: function () {
          var targets = data.hosts.filter(function (h) {
            return h.vlan === src.vlan && h.port !== ingress;
          }).map(function (h) { return h.name; });
          U.log(log, ++logNo, "FLOOD " + srcName + " -> broadcast, VLAN " + src.vlan +
            " (ports of: " + (targets.join(", ") || "none") + ")");
          detail.innerHTML = '<h4>Flooded (broadcast)</h4><p>' +
            "Broadcast and unknown unicast frames are flooded inside the VLAN. This is exactly how ARP reaches the gateway.</p>";
        }
      });
      return;
    }

    if (dst && dst.vlan !== src.vlan) {
      steps.push({
        title: "4-5. Destination is in a different VLAN",
        text: "The destination " + dst.name + " is in VLAN " + dst.vlan + ", but the frame arrived in VLAN " +
          src.vlan + ". VLANs are separate broadcast domains, so the frame is never forwarded there.",
        apply: function () {
          U.log(log, ++logNo, "DROP " + srcName + " -> " + dst.name +
            ": cross-VLAN at Layer 2 is impossible (VLAN " + src.vlan + " vs " + dst.vlan + ")");
          detail.innerHTML = '<h4>Never crosses the VLAN boundary</h4>' +
            "<p>This is not a switch bug. Traffic between VLANs requires a router or Layer 3 switch with an interface in each VLAN, and the hosts must be in different subnets.</p>";
        }
      });
      return;
    }

    if (dst.mac === src.mac) {
      steps.push({
        title: "4-5. Destination is the sender itself",
        text: "The destination MAC equals the source MAC, so this frame is addressed to the sending host. " +
          "A switch never sends a frame back out the port it arrived on, so it is filtered.",
        apply: function () {
          U.log(log, ++logNo, "FILTER " + srcName + " -> itself (destination MAC equals source MAC)");
          detail.innerHTML = "<h4>Filtered</h4><p>This case appears when a host ARPs for its own address " +
            "(duplicate-address detection) or has a broken ARP table.</p>";
        }
      });
      return;
    }

    var entry = macTable[dst.mac];
    if (entry && entry.port === ingress) {
      steps.push({
        title: "4-5. Destination is on the ingress port",
        text: "The destination MAC " + dst.mac + " is already known to be on port " + ingress +
          ", which is where the frame came from. The switch filters (drops) it.",
        apply: function () {
          U.log(log, ++logNo, "FILTER " + srcName + " -> " + dst.name +
            " (destination already on the ingress port)");
          detail.innerHTML = "<h4>Filtered</h4><p>A switch has no reason to send a frame back out the port it arrived on.</p>";
        }
      });
      return;
    }

    if (entry) {
      steps.push({
        title: "4-5. Destination is known",
        text: "The destination MAC " + dst.mac + " is mapped to port " + entry.port +
          ", so the switch forwards the frame out exactly that port and nowhere else.",
        apply: function () {
          U.log(log, ++logNo, "FORWARD " + srcName + " -> " + dst.name +
            " out port " + entry.port + " (known destination)");
          detail.innerHTML = "<h4>Forwarded to one port</h4><p>This is the payoff of learning: subsequent frames are unicast, not flooded.</p>";
        }
      });
      return;
    }

    steps.push({
      title: "4-5. Destination is unknown",
      text: "The switch has no entry for " + dst.mac + ", so it floods the frame to every port in VLAN " +
        src.vlan + " except port " + ingress + ". When " + dst.name +
        " replies, the switch learns where it is.",
      apply: function () {
        var targets = data.hosts.filter(function (h) {
          return h.vlan === src.vlan && h.port !== ingress;
        }).map(function (h) { return h.name; });
        U.log(log, ++logNo, "FLOOD " + srcName + " -> " + dst.name +
          " (unknown unicast, VLAN " + src.vlan + "; ports of: " + (targets.join(", ") || "none") + ")");
        detail.innerHTML = "<h4>Flooded (unknown unicast)</h4>" +
          "<p>Unknown unicast flooding is normal and self-limiting: the reply teaches the switch the destination's port.</p>";
      }
    });
  }

  function applyStep(st) {
    if (st.apply) st.apply();
    var n = log.children.length + 1;
    detail.innerHTML = "<h4>" + U.esc(st.title) + "</h4><p>" + U.esc(st.text) + "</p>";
  }

  function reset() {
    macTable = {};
    logNo = 0;
    learnCount = {};
    frameIndex = 0;
    pendingFrame = null;
    steps = [];
    U.clear(log);
    renderTopology(null);
    renderTable();
    detail.innerHTML = '<h4>Ready</h4><p>Press <b>Next step</b> to send the first frame and watch the MAC table build up. ' +
      "Every decision is explained in this panel.</p>";
  }

  function addCustomFrame() {
    var s = U.el("customSrc").value;
    var d = U.el("customDst").value;
    if (!s || !d) return;
    var f = { id: "custom" + Date.now(), src: s, dst: d, kind: d === "__broadcast" ? "broadcast" : "unicast",
              label: "custom" };
    pendingFrame = f;
    planFrame(f);
    applyStep(steps.shift());
  }

  /* ---- wiring ---- */
  U.el("simNext").addEventListener("click", nextStep);
  U.el("simReset").addEventListener("click", reset);

  var srcSel = U.el("customSrc"), dstSel = U.el("customDst");
  if (srcSel && dstSel) {
    data.hosts.forEach(function (h) {
      srcSel.insertAdjacentHTML("beforeend", '<option value="' + h.id + '">' + U.esc(h.name) +
        " (VLAN " + h.vlan + ")</option>");
      dstSel.insertAdjacentHTML("beforeend", '<option value="' + h.id + '">' + U.esc(h.name) +
        " (VLAN " + h.vlan + ")</option>");
    });
    dstSel.insertAdjacentHTML("beforeend", '<option value="__broadcast">Broadcast (ff:ff:ff:ff:ff:ff)</option>');
    U.el("customSend").addEventListener("click", addCustomFrame);
  }

  U.renderAssessment(window.NETQUEST_SIM, U.el("simAssessment"));
  reset();
})();
