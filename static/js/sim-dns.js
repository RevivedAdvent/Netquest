/* DNS resolution laboratory: hosts file, cache, hierarchy, faults. */
(function () {
  "use strict";
  var U = window.NetQuestSim;
  var data = window.NETQUEST_DATA;
  if (!data) return;

  var stage = U.el("simStage");
  var log = U.el("simLog");
  var detail = U.el("simDetail");
  var stepNo = 0;

  /* ---------- resolution engine ---------- */
  function recordsFor(name) {
    var out = [];
    Object.keys(data.zones).forEach(function (z) {
      data.zones[z].records.forEach(function (r) {
        if (r.name === name) out.push({ rec: r, zone: z, auth: data.zones[z].authoritative });
      });
    });
    return out;
  }

  function zoneOf(name) {
    var keys = Object.keys(data.zones).sort(function (a, b) { return b.length - a.length; });
    for (var i = 0; i < keys.length; i++) {
      var z = keys[i].replace(/\.$/, "");
      if (name === z || name.slice(-(z.length + 1)) === "." + z) return keys[i];
    }
    return null;
  }

  function isInternal(zone) { return zone && zone.indexOf("corp.") === 0; }

  function hostsEntry(name) {
    return data.hosts_file.filter(function (h) { return h.name === name; })[0];
  }

  function step(title, text, cls) {
    stepNo += 1;
    U.log(log, stepNo, title);
    detail.innerHTML += "<h4>" + U.esc(title) + "</h4><p>" + U.esc(text) + "</p>";
  }

  function verdict(kind, text) {
    detail.innerHTML += '<div class="feedback ' + (kind === "ok" ? "ok" : "bad") + '"><h4>' +
      (kind === "ok" ? "ANSWER" : kind.toUpperCase()) + "</h4><div>" + U.esc(text) + "</div></div>";
  }

  function reset(detailText) {
    stepNo = 0;
    U.clear(log);
    detail.innerHTML = detailText ||
      '<h4>Ready</h4><p>Choose a query, a scenario and press <b>Resolve</b>. The panel will explain each lookup stage in order.</p>';
    stage.innerHTML = '<div class="node-wrap">' + data.resolvers.map(function (r) {
      return '<div class="node"><div class="nname">' + U.esc(r.name) + '</div><div class="naddr">' +
        U.esc(r.ip) + "</div></div>";
    }).join("") + "</div>";
  }

  function scenarioById(id) {
    return data.scenarios.filter(function (s) { return s.id === id; })[0] || data.scenarios[0];
  }

  function selectedQuery() {
    var raw = U.el("queryName").value;
    var idx = parseInt(raw, 10);
    if (!isNaN(idx) && data.queries[idx]) return data.queries[idx];
    return data.queries.filter(function (q) { return q.name === raw; })[0] || null;
  }

  function resolve() {
    var picked = selectedQuery();
    var qname = (picked ? picked.name : U.el("queryName").value).trim().replace(/\.$/, "");
    var qtype = U.el("queryType").value;
    var sc = scenarioById(U.el("scenarioSelect").value);
    var resolver = data.resolvers.filter(function (r) { return r.id === sc.resolver; })[0];

    reset('<h4>Resolving ' + U.esc(qname) + " " + qtype + "</h4><p>Scenario: " +
      U.esc(sc.label) + ". Resolver: " + U.esc(resolver.name) + " (" + resolver.ip + ").</p>");

    /* 1. NSS / hosts file */
    var h = hostsEntry(qname);
    if (h) {
      step("1. NSS: hosts file", "/etc/nsswitch.conf lists files first (hosts: files dns ...). " +
        qname + " is present with address " + h.ip + ", so no DNS query is sent at all.");
      verdict("ok", qname + " " + qtype + " = " + h.ip + " (source: files)");
      return;
    }
    step("1. NSS: hosts file", "No entry for " + qname + " in /etc/hosts. NSS moves on to dns and asks the configured resolver with a recursive query.");

    /* 2. resolver + cache */
    step("2. Query the resolver", "The stub resolver sends a recursive query to " + resolver.ip +
      " (from /etc/resolv.conf or resolvectl). A recursive resolver answers on the client's behalf.");

    if (sc.cache === "warm" || sc.cache === "stale") {
      var any = recordsFor(qname).filter(function (x) { return x.rec.type === qtype; });
      if (any.length) {
        var rec = any[0].rec;
        if (sc.cache === "stale") {
          step("3. Cache hit (stale)", "The cache holds an older entry for " + qname +
            " that has not expired yet. The cached value is returned, not the current authoritative one.");
          var stale = sc.stale_value || rec.value;
          verdict("ok", qname + " " + qtype + " = " + stale + " (cached, remaining TTL " +
            Math.max(1, Math.round(rec.ttl / 3)) + "s) — the authoritative record is now " +
            rec.value + ", but nobody asks until the TTL expires");
          return;
        }
        step("3. Cache hit", "The resolver already holds " + qname + " " + qtype +
          " with a live TTL, so the hierarchy is never consulted.");
        verdict("ok", qname + " " + qtype + " = " + rec.value + " (cached, remaining TTL " +
          Math.max(1, Math.round(rec.ttl / 2)) + "s)");
        return;
      }
    }
    step("3. Cache miss", "Nothing usable in the cache for " + qname + " " + qtype + ", so the resolver must walk the hierarchy.");

    /* 4. faults that happen upstream */
    if (sc.fault === "timeout") {
      step("4. Referral to authoritative", "The resolver sends its query to the authoritative server and waits.");
      verdict("timeout", "No response at all. The client's dig reports 'no servers could be reached' after the timeout " +
        "(default 5s, 3 tries). Nothing is cached, because there is no answer to cache.");
      detail.innerHTML += '<div class="note"><b>Interpretation:</b> a timeout means silence — a filtered path, wrong address or dead server. ' +
        "Compare with refused (server said no) and servfail (server tried and failed).</div>";
      return;
    }
    if (sc.fault === "servfail") {
      step("4. Authoritative lookup", "The authoritative server is contacted but returns a server failure.");
      verdict("servfail", "SERVFAIL. The name may well exist; the server could not complete the lookup. " +
        "Common causes: DNSSEC validation failure, an unreachable upstream, a broken zone transfer or a lame delegation.");
      return;
    }

    var zone = zoneOf(qname);
    if (!zone) {
      step("4. Hierarchy walk", "Root refers to the TLD, the TLD refers to the authoritative server, but no zone matches " +
        qname + ".");
      verdict("nxdomain", "NXDOMAIN: the name does not exist in any zone the resolver can see.");
      return;
    }
    if (isInternal(zone) && resolver.id === "public") {
      step("4. Hierarchy walk (public resolver)", "The public resolver follows root, then the TLD, but corp.example is " +
        "served only by the internal nameserver ns1.corp.example (10.10.0.53), which is not reachable from outside.");
      verdict("nxdomain", "NXDOMAIN. split-horizon DNS: the internal name simply does not exist in the public view. " +
        "The fix is to point internal clients at the internal resolver.");
      return;
    }

    var auth = data.zones[zone].authoritative;
    var parts = qname.split(".");
    var tld = parts[parts.length - 1] + ".";
    step("4. Root referral", "The resolver asks a root server for " + qname +
      ". The root does not know the answer; it returns a referral (delegation) for " + tld);
    step("5. TLD referral", "The " + tld + " servers hold the delegation for " + zone +
      " and return the authoritative nameserver: " + auth + ".");
    step("6. Authoritative query", "The resolver asks " + auth + " for " + qname + " " + qtype +
      ". Authoritative servers answer with authority (AA flag) or with an explicit negative answer.");

    var matches = recordsFor(qname);
    var exact = matches.filter(function (x) { return x.rec.type === qtype; });
    var cname = matches.filter(function (x) { return x.rec.type === "CNAME"; })[0];

    if (sc.fault === "bad_record") {
      verdict("ok", qname + " " + qtype + " = 203.0.113.99 (AA) — the record exists but points at the wrong host. " +
        "A wrong answer looks identical to a right one; only comparing with the intended value reveals it.");
      return;
    }

    if (!matches.length) {
      verdict("nxdomain", "NXDOMAIN with an SOA in the authority section, which also supplies the negative-cache TTL " +
        "(the SOA minimum). The client will not ask again for that period.");
      return;
    }

    if (cname && !exact.length) {
      var target = cname.rec.value;
      step("7. CNAME chain", qname + " is an alias. The resolver restarts its lookup for the target " + target +
        ", which costs an extra query but no extra client work.");
      var t = recordsFor(target).filter(function (x) { return x.rec.type === qtype; })[0];
      if (t) {
        verdict("ok", qname + " CNAME " + target + "; " + target + " " + qtype + " = " + t.rec.value +
          "  (TTL " + t.rec.ttl + "s)");
      } else {
        verdict("bad", "CNAME points at " + target + ", which has no " + qtype + " record. The chain is broken.");
      }
      return;
    }

    if (!exact.length) {
      verdict("nodata", "NODATA: the name exists but has no " + qtype + " record. This is not NXDOMAIN — " +
        "the resolver returns NOERROR with an empty answer and the SOA for negative caching.");
      return;
    }

    var r = exact[0].rec;
    verdict("ok", qname + " " + qtype + " = " + r.value + "  (TTL " + r.ttl +
      "s, authoritative answer from " + auth + ")");
    detail.innerHTML += '<div class="note">Cached now for ' + r.ttl +
      "s. A record change will not be visible to this resolver until that TTL expires.</div>";
  }

  /* ---------- wiring ---------- */
  data.queries.forEach(function (q, i) {
    U.el("queryName").insertAdjacentHTML("beforeend", '<option value="' + i + '">' +
      U.esc(q.name) + " (" + q.type + ")</option>");
  });
  data.scenarios.forEach(function (s) {
    U.el("scenarioSelect").insertAdjacentHTML("beforeend", '<option value="' + s.id + '">' +
      U.esc(s.label) + "</option>");
  });

  function applyQuery(q) {
    if (!q) return;
    U.el("queryType").value = q.type;
    U.el("queryNote").textContent = q.note || "";
  }

  U.el("queryName").addEventListener("change", function () {
    applyQuery(selectedQuery());
  });

  U.el("scenarioSelect").addEventListener("change", function () {
    var sc = scenarioById(U.el("scenarioSelect").value);
    if (!sc.query) return;
    var idx = data.queries.findIndex(function (q) {
      return q.name === sc.query.name && q.type === sc.query.type;
    });
    if (idx === -1) return;
    U.el("queryName").value = String(idx);
    applyQuery(data.queries[idx]);
    U.el("queryNote").textContent = (sc.note || data.queries[idx].note || "");
  });
  U.el("simNext").textContent = "Resolve";
  U.el("simNext").addEventListener("click", resolve);
  U.el("simReset").addEventListener("click", function () { reset(); });

  U.renderAssessment(window.NETQUEST_SIM, U.el("simAssessment"));
  reset('<h4>Ready</h4><p>Pick a name, choose a scenario, then press <b>Resolve</b>. ' +
    "The log shows each stage: NSS, cache, hierarchy, answer.</p>");
})();
