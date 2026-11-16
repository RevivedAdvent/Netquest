/* Routing: longest prefix match, hop-by-hop path, loop detection. */
(function () {
  "use strict";
  var U = window.NetQuestSim;
  var data = window.NETQUEST_DATA;
  if (!data) return;

  var stage = U.el("simStage");
  var log = U.el("simLog");
  var detail = U.el("simDetail");
  var stepNo = 0;

  function byId(id) {
    return data.routers.filter(function (r) { return r.id === id; })[0];
  }

  function cloneTables() {
    var out = {};
    data.routers.forEach(function (r) {
      out[r.id] = r.table.map(function (row) { return Object.assign({}, row); });
    });
    return out;
  }

  var tables = cloneTables();
  var activeFault = null;

  function applyFault(faultId) {
    tables = cloneTables();
    activeFault = faultId;
    var f = data.faults.filter(function (x) { return x.id === faultId; })[0];
    if (!f) return;
    f.apply.forEach(function (op) {
      var t = tables[op.router];
      if (!t) return;
      if (op.remove) {
        tables[op.router] = t.filter(function (row) { return row.prefix !== op.remove; });
      }
      if (op.replace) {
        t.forEach(function (row) {
          if (row.prefix === op.replace.from) {
            if (op.replace.prefix) row.prefix = op.replace.prefix;
            if (op.replace.via !== undefined) row.via = op.replace.via;
          }
        });
      }
      if (op.add) t.push(Object.assign({}, op.add));
    });
  }

  function renderStage(activeRouter, highlight) {
    var html = '<div class="node-wrap">';
    data.routers.forEach(function (r) {
      html += '<div class="node ' + (r.id === activeRouter ? "active" : "") + '">' +
        '<div class="nname">' + U.esc(r.name) + "</div>" +
        r.interfaces.map(function (i) {
          return '<div class="naddr">' + U.esc(i.iface + " " + i.ip) + "</div>";
        }).join("") + "</div>";
    });
    html += "</div>";
    if (highlight) {
      html += '<div class="mt16 mono small">hop ' + highlight.hop + ": " + U.esc(highlight.text) + "</div>";
    }
    stage.innerHTML = html;
    renderTables(activeRouter);
  }

  function renderTables(activeRouter) {
    var html = "";
    data.routers.forEach(function (r) {
      if (activeRouter && r.id !== activeRouter) return;
      html += '<h4 class="mt16">' + U.esc(r.name) + " routing table</h4>";
      html += '<table class="mac-table"><tr><th>Prefix</th><th>Via</th><th>Interface</th><th>Metric</th><th>Proto</th></tr>';
      tables[r.id].forEach(function (row) {
        html += "<tr><td>" + U.esc(row.prefix) + "</td><td>" +
          (row.via ? U.esc(row.via) : '<span class="muted">on-link</span>') + "</td><td>" +
          U.esc(row.iface) + "</td><td>" + row.metric + "</td><td class=\"muted\">" +
          U.esc(row.proto) + "</td></tr>";
      });
      html += "</table>";
    });
    var host = U.el("tables"); if (host) host.innerHTML = html;
  }

  function reset(text) {
    stepNo = 0;
    U.clear(log);
    applyFault(U.el("faultSelect") ? U.el("faultSelect").value : "none");
    detail.innerHTML = text || '<h4>Ready</h4><p>Choose a destination and press <b>Trace</b>. ' +
      "Each hop shows the table and the winning route, with the longest prefix match highlighted.</p>";
    renderStage(null, null);
  }

  function trace() {
    var dest = U.el("destSelect").value;
    reset('<h4>Trace to ' + U.esc(dest) + "</h4>");
    stepNo = 0;

    /* local host decision */
    var host = data.hosts[0];
    var hostRouter = byId(host.router);
    var localNet = host.gateway.replace(/\.\d+$/, ".0") + "/24";
    var isLocal = U.lpm([{ prefix: localNet, via: null, iface: "eth0", metric: 0 }], dest) !== null;
    if (isLocal) {
      stepNo += 1; U.log(log, stepNo, "HOST: " + dest + " is on-link (" + localNet + "), ARP and send directly");
      detail.innerHTML += "<h4>Host: on-link</h4><p>The destination falls inside the host's own connected subnet, so it ARPs for " +
        U.esc(dest) + " directly and never uses the gateway.</p>";
      detail.innerHTML += '<div class="feedback ok"><h4>REACHED</h4><div>Delivered on the local segment in one hop.</div></div>';
      renderStage(null, null);
      return;
    }
    stepNo += 1;
    U.log(log, stepNo, "HOST: " + dest + " is off-link, use default gateway " + host.gateway + " (" + hostRouter.name + ")");
    detail.innerHTML += "<h4>Host: off-link</h4><p>" + U.esc(dest) + " is outside " + U.esc(localNet) +
      ", so the host sends to its default gateway " + U.esc(host.gateway) + ". The destination IP stays the same; only the destination MAC changes.</p>";

    var current = hostRouter;
    var visited = [];
    var hop = 0;
    var limit = 12;

    while (hop < limit) {
      hop += 1;
      if (visited.indexOf(current.id) !== -1) {
        stepNo += 1; U.log(log, stepNo, "LOOP detected at " + current.name);
        detail.innerHTML += '<div class="feedback bad"><h4>ROUTING LOOP</h4><div>' + U.esc(current.name) +
          " already handled this packet. TTL expires, the router returns ICMP time-exceeded, and the destination is unreachable.</div></div>";
        renderStage(current.id, { hop: hop, text: current.name + " repeats — loop" });
        return;
      }
      visited.push(current.id);

      var table = tables[current.id];
      var best = U.lpm(table, dest);
      renderStage(current.id, null);
      if (!best) {
        stepNo += 1; U.log(log, stepNo, current.name + ": no route to " + dest);
        detail.innerHTML += '<div class="feedback bad"><h4>NO ROUTE</h4><div>' + U.esc(current.name) +
          " has no entry matching " + U.esc(dest) + ", so it returns ICMP network unreachable.</div></div>";
        return;
      }

      stepNo += 1;
      U.log(log, stepNo, current.name + ": " + best.prefix + (best.via ? " via " + best.via : " on-link") +
        " (" + best.proto + ")");

      detail.innerHTML += '<h4>Hop ' + hop + ": " + U.esc(current.name) + "</h4><p>Longest prefix match selects <b>" +
        U.esc(best.prefix) + "</b>" + (best.via ? " via " + U.esc(best.via) : " as directly connected") +
        " out " + U.esc(best.iface) + ". Prefix length " + U.maskBits(best.prefix) +
        " beats every shorter candidate" + (best.via ? "" : ", and no next hop is needed because the destination is on-link") + ".</p>";

      if (!best.via) {
       /* The ISP edge holds the last default route: once the packet leaves
           wan0 it is outside the lab, which is the honest end of the trace. */
        if (best.iface === "wan0" || best.proto === "isp") {
          stepNo += 1;
          U.log(log, stepNo, "EXIT " + dest + " towards the internet via " + best.iface + " on " + current.name);
          detail.innerHTML += '<div class="feedback ok"><h4>LEFT THE LAB</h4><div>' + U.esc(dest) +
            " is handed to the provider out " + U.esc(best.iface) + " (" +
            U.esc(best.prefix) + "). Anything the lab does not have a route for still leaves — " +
            "which is why a mistyped internal subnet can silently head for the internet." +
            "</div></div>";
          renderStage(current.id, { hop: hop, text: "exits towards the ISP via " + best.iface });
          return;
        }
        var owner = data.routers.filter(function (r) {
          return r.interfaces.some(function (i) { return i.ip.split("/")[0] === dest; });
        })[0];
        if (owner && U.lpm([{ prefix: best.prefix }], dest)) {
          stepNo += 1;
          U.log(log, stepNo, "DELIVER " + dest + " on " + best.iface + " of " + current.name);
          detail.innerHTML += '<div class="feedback ok"><h4>REACHED</h4><div>' + U.esc(dest) +
            " is directly connected to " + U.esc(current.name) + " on " + U.esc(best.iface) +
            ". The router ARPs for it and delivers.</div></div>";
          renderStage(current.id, { hop: hop, text: "delivered on " + best.iface });
          return;
        }
        stepNo += 1;
        U.log(log, stepNo, "DELIVER " + dest + " on-link at " + current.name + " (" + best.prefix + ")");
        detail.innerHTML += '<div class="feedback ok"><h4>REACHED</h4><div>' + U.esc(dest) +
          " is inside " + U.esc(best.prefix) + ", which is directly connected to " +
          U.esc(current.name) + ", so the router ARPs for the host and delivers it out " +
          U.esc(best.iface) + ".</div></div>";
        renderStage(current.id, { hop: hop, text: "delivered on-link" });
        return;
      }

      /* find the router that owns the next hop address */
      var nhop = best.via;
      var nextRouter = null;
      data.routers.forEach(function (r) {
        r.interfaces.forEach(function (i) {
          if (i.ip.split("/")[0] === nhop) nextRouter = r;
        });
      });
      if (!nextRouter) {
        stepNo += 1; U.log(log, stepNo, "next hop " + nhop + " is not a neighbour on any link");
        detail.innerHTML += '<div class="feedback bad"><h4>NEXT HOP UNREACHABLE</h4><div>' +
          U.esc(current.name) + " cannot reach " + U.esc(nhop) +
          ". The static route points at an address that is not on any connected subnet, so ARP fails and packets are dropped.</div></div>";
        return;
      }
      var adjacency = current.interfaces.some(function (i) {
        return i.ip.split("/")[0].replace(/\.\d+$/, "") === nhop.replace(/\.\d+$/, "");
      });
      if (!adjacency) {
        stepNo += 1; U.log(log, stepNo, current.name + ": next hop " + nhop + " is not on a connected subnet");
        detail.innerHTML += '<div class="feedback bad"><h4>NEXT HOP NOT ON-LINK</h4><div>' +
          U.esc(nhop) + " is not in any subnet attached to " + U.esc(current.name) +
          ", so the route is unusable: a gateway must be reachable directly.</div></div>";
        return;
      }
      detail.innerHTML += '<p class="small">Forwarding to ' + U.esc(nextRouter.name) + " at " + U.esc(nhop) +
        ": a new Layer 2 frame is built for that link (TTL decremented).</p>";
      current = nextRouter;
    }
    stepNo += 1; U.log(log, stepNo, "TTL exhausted after " + limit + " hops");
    detail.innerHTML += '<div class="feedback bad"><h4>TTL EXHAUSTED</h4><div>The packet never reached its destination within the hop limit.</div></div>';
  }

  /* wiring */
  data.destinations.forEach(function (d) {
    U.el("destSelect").insertAdjacentHTML("beforeend", '<option value="' + U.esc(d.ip) + '">' +
      U.esc(d.ip) + " &mdash; " + U.esc(d.label) + "</option>");
  });
  data.faults.forEach(function (f) {
    U.el("faultSelect").insertAdjacentHTML("beforeend", '<option value="' + f.id + '">' +
      U.esc(f.label) + "</option>");
  });
  U.el("simNext").textContent = "Trace";
  U.el("simNext").addEventListener("click", trace);
  U.el("simReset").addEventListener("click", function () { reset(); });
  U.el("faultSelect").addEventListener("change", function () {
    var id = U.el("faultSelect").value;
    applyFault(id);
    var f = data.faults.filter(function (x) { return x.id === id; })[0];
    reset('<h4>' + U.esc(f.label) + "</h4><p>" + U.esc(f.detail) + "</p>" +
      (f.symptom ? '<div class="note"><b>Expected symptom:</b> ' + U.esc(f.symptom) + "</div>" : ""));
  });

  U.renderAssessment(window.NETQUEST_SIM, U.el("simAssessment"));
  reset();
})();
