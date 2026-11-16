/* DHCP DORA simulator with fault injection. */
(function () {
  "use strict";
  var U = window.NetQuestSim;
  var data = window.NETQUEST_DATA;
  if (!data) return;

  var index = 0;
  var fault = null;
  var finished = false;

  var stage = U.el("simStage");
  var log = U.el("simLog");
  var detail = U.el("simDetail");

  function renderTopology(activeId) {
    var nodes = [
      { id: "client", name: data.client.name, addr: data.client.mac, sub: "VLAN " + data.client.vlan + " &middot; no address yet" },
      { id: "relay", name: data.relay.name, addr: data.relay.ip, sub: "relay agent" },
      { id: "server", name: data.server.name, addr: data.server.ip, sub: "scope " + data.scope.network }
    ];
    var html = '<div class="node-wrap">';
    nodes.forEach(function (n, i) {
      html += '<div class="node ' + (activeId === n.id ? "active" : "") + '">' +
        '<div class="nname">' + U.esc(n.name) + '</div><div class="naddr">' + n.addr +
        '</div><div class="naddr">' + n.sub + "</div></div>";
      if (i < nodes.length - 1) html += '<div class="arrow">' + (i === 0 ? "-->" : "-->") + "</div>";
    });
    html += "</div>";
    html += '<div class="mt16 small muted">Lease pool: ' + data.scope.pool +
      " &middot; free addresses: " + data.scope.free + "</div>";
    stage.innerHTML = html;
  }

  var READY = '<h4>Ready</h4><p>The client has a link but no address. Press <b>Next message</b> to walk the DORA exchange, ' +
    "or inject a fault first to see how the exchange changes.</p>";

  function reset(keepFault) {
    index = 0;
    if (!keepFault) fault = null;
    finished = false;
    U.clear(log);
    renderTopology(null);
    detail.innerHTML = READY;
    updateButtons();
  }

  function updateButtons() {
    U.el("simNext").disabled = finished;
  }

  function currentFault() {
    if (!fault || fault === "none") return null;
    return data.faults.filter(function (f) { return f.id === fault; })[0] || null;
  }

  function showFault(f) {
    detail.innerHTML = "<h4>Fault injected: " + U.esc(f.label) + "</h4><p>" + U.esc(f.detail) +
      '</p><div class="note"><b>Symptom:</b> ' + U.esc(f.symptom) + "</div>" +
      '<p class="small"><b>Diagnose it:</b> ' + U.esc(f.diagnosis) + "</p>";
  }

  function next() {
    if (finished) return;
    var f = currentFault();

    var step = data.steps[index];
    if (!step) return;

    /* does the fault break the exchange at this step? */
    if (f && (f.breaks_at === step.id ||
        (f.breaks_at === "after_ack" && step.id === "ack" && index === data.steps.length - 1))) {
      U.log(log, index + 1, "[" + step.label + "] affected by fault: " + f.label);
      showFault(f);
      finished = true;
      updateButtons();
      return;
    }

    if (f && f.breaks_at === "offer" && index >= 1) {
      /* no OFFER arrives: the exchange stalls here */
      U.log(log, index + 1, "STALL: no " + step.label + " received");
      showFault(f);
      finished = true;
      updateButtons();
      return;
    }

    renderTopology(step.direction === "client-server" ? "client" : "server");
    U.log(log, index + 1, step.label + " :: " + step.from + " -> " + step.to);
    var fields = step.fields.map(function (x) { return "<li>" + U.esc(x) + "</li>"; }).join("");
    detail.innerHTML = "<h4>" + U.esc(step.label) + "</h4>" +
      '<table><tr><th>From</th><td>' + U.esc(step.from) + "</td></tr>" +
      "<tr><th>To</th><td>" + U.esc(step.to) + "</td></tr>" +
      "<tr><th>Src</th><td class='mono'>" + U.esc(step.src) + "</td></tr>" +
      "<tr><th>Dst</th><td class='mono'>" + U.esc(step.dst) + "</td></tr>" +
      "<tr><th>L2</th><td>" + U.esc(step.l2) + "</td></tr></table>" +
      "<p>" + U.esc(step.summary) + "</p><p>" + U.esc(step.detail) + "</p>" +
      '<p class="small muted">Fields: </p><ul class="small">' + fields + "</ul>";

    index += 1;
    if (index >= data.steps.length) {
      finished = true;
      U.log(log, index, "Configuration applied: 10.30.0.100/24 via 10.30.0.1, DNS 10.10.0.53");
      detail.innerHTML += '<div class="feedback ok"><h4>Lease complete</h4><p>The client installs the address, a connected route, ' +
        "a default route via option 3 and the resolver from option 6. Renewal happens at T1 (50% of the lease) and rebinding at T2 (87.5%).</p></div>";
      updateButtons();
    }
  }

  U.el("simNext").addEventListener("click", next);
  U.el("simReset").addEventListener("click", function () {
    U.el("faultSelect").value = "none";
    reset(false);
  });
  U.el("faultSelect").addEventListener("change", function (e) {
    fault = e.target.value;          // read BEFORE resetting the walk
    reset(true);                     // keep the chosen fault, restart at DISCOVER
    var f = currentFault();
    if (f) {
      showFault(f);
      U.log(log, 0, "Fault armed: " + f.label);
    }
  });

  U.el("faultSelect").insertAdjacentHTML("beforeend",
    '<option value="none">No fault (normal DORA)</option>');
  data.faults.forEach(function (f) {
    U.el("faultSelect").insertAdjacentHTML("beforeend",
      '<option value="' + f.id + '">' + U.esc(f.label) + "</option>");
  });
  U.el("faultSelect").value = "none";

  U.renderAssessment(window.NETQUEST_SIM, U.el("simAssessment"));
  reset();
})();
