/**
 * Live "Your Signal" panel (product page only).
 *
 * Polls GET /api/live-signal every few seconds and re-renders the activity
 * feed + inline recommendation card in place - no page reload, no manual
 * "Refresh now" click. Kept separate from tracker.js, which is write-path
 * only (ARCHITECTURE.md \u00a76.1); this file is purely a read-path poller.
 *
 * Pauses while the tab is hidden so a backgrounded tab doesn't keep polling.
 */
(function () {
  "use strict";

  if (!window.SMARTRECO_USER_ID) return;

  var ENDPOINT = "/api/live-signal";
  var POLL_MS = 4000;

  var feedEl = document.getElementById("signal-feed");
  var recEl = document.getElementById("signal-recommendation");
  var interestsEl = document.getElementById("signal-interests");
  var strengthFillEl = document.getElementById("signal-strength-fill");
  var strengthLabelEl = document.getElementById("signal-strength-label");
  if (!feedEl || !recEl) return;

  var timer = null;

  // Small inline icon set (P3.4) - a symbolic name per event type rather
  // than an icon-font dependency. Paths are hard-coded constants, never
  // built from server data, so this stays injection-safe despite innerHTML.
  var ICON_PATHS = {
    eye: '<path d="M2 12s4-7 10-7 10 7 10 7-4 7-10 7-10-7-10-7Z"></path><circle cx="12" cy="12" r="3"></circle>',
    pointer: '<path d="M5 3l14 8-6 2-2 6-6-16Z"></path>',
    search: '<circle cx="11" cy="11" r="7"></circle><path d="m21 21-4.3-4.3"></path>',
    clock: '<circle cx="12" cy="12" r="9"></circle><path d="M12 7v5l3 2"></path>',
    cart: '<circle cx="9" cy="20" r="1"></circle><circle cx="18" cy="20" r="1"></circle><path d="M3 4h2l2.4 12.4a2 2 0 0 0 2 1.6h7.6a2 2 0 0 0 2-1.6L21 8H6"></path>',
    dismiss: '<path d="M6 6l12 12M18 6 6 18"></path>',
    dot: '<circle cx="12" cy="12" r="4"></circle>',
  };

  var TRIGGER_LABELS = {
    count: "count threshold",
    drift: "interest drift",
    category_shift: "category shift",
    manual: "manual refresh",
    scheduled: "scheduled digest",
  };

  function clearChildren(el) {
    while (el.firstChild) el.removeChild(el.firstChild);
  }

  function makeIcon(name) {
    var svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("viewBox", "0 0 24 24");
    svg.setAttribute("class", "signal-icon");
    svg.setAttribute("aria-hidden", "true");
    svg.innerHTML = ICON_PATHS[name] || ICON_PATHS.dot;
    return svg;
  }

  function renderFeed(items) {
    clearChildren(feedEl);
    if (!items || items.length === 0) {
      var empty = document.createElement("p");
      empty.className = "muted small";
      empty.textContent = "Browse a few courses and your activity will show up here.";
      feedEl.appendChild(empty);
      return;
    }
    items.forEach(function (item) {
      var row = document.createElement("div");
      row.className = "signal-row" + (item.is_latest ? " latest" : "");
      row.appendChild(makeIcon(item.icon));

      var text = document.createElement("div");
      text.className = "signal-row-text";
      var label = document.createElement("strong");
      label.textContent = item.label;
      text.appendChild(label);
      text.appendChild(document.createTextNode(" \u00b7 " + item.detail));
      row.appendChild(text);

      var time = document.createElement("span");
      time.className = "signal-row-time";
      time.textContent = item.occurred_at || "";
      row.appendChild(time);

      feedEl.appendChild(row);
    });
  }

  function renderInterests(interests) {
    if (!interestsEl) return;
    if (!interests || interests.length === 0) {
      interestsEl.textContent = "";
      return;
    }
    interestsEl.textContent = interests
      .map(function (i) {
        return i.label + " " + i.pct + "%";
      })
      .join(" \u00b7 ");
  }

  function renderSignalStrength(count, threshold) {
    if (!strengthFillEl || !strengthLabelEl) return;
    var safeCount = count || 0;
    var safeThreshold = threshold || 3;
    var pct = Math.max(0, Math.min(100, Math.round((safeCount / safeThreshold) * 100)));
    strengthFillEl.style.width = pct + "%";
    // At capacity the count has already done its job (a generation was
    // requested); the agent run itself is a couple of sequential LLM calls
    // that can take real seconds, so "3 / 3 to next refresh" would sit there
    // looking stale/stuck for that whole window. Say what's actually
    // happening instead of restating a threshold that's already been hit.
    strengthLabelEl.textContent =
      safeCount >= safeThreshold
        ? "Refreshing your recommendations\u2026"
        : safeCount + " / " + safeThreshold + " to next refresh";
  }

  function renderRecommendation(rec) {
    clearChildren(recEl);
    if (!rec) {
      var empty = document.createElement("p");
      empty.className = "muted small";
      empty.textContent =
        "Still learning your interests \u2014 recommendations will appear here soon.";
      recEl.appendChild(empty);
      return;
    }

    var heading = document.createElement("div");
    heading.className = "agent-rec-heading";
    heading.textContent = "Agent \u00b7 Recommendation";
    recEl.appendChild(heading);

    if (rec.refreshed_at || rec.trigger_reason) {
      var meta = document.createElement("p");
      meta.className = "agent-rec-meta";
      var bits = [];
      if (rec.refreshed_at) bits.push("refreshed " + rec.refreshed_at + " ago");
      if (rec.trigger_reason) {
        bits.push(TRIGGER_LABELS[rec.trigger_reason] || rec.trigger_reason);
      }
      meta.textContent = bits.join(" \u00b7 ");
      recEl.appendChild(meta);
    }

    var narrative = document.createElement("p");
    narrative.className = "agent-rec-narrative";
    narrative.textContent = rec.narrative;
    recEl.appendChild(narrative);

    var grid = document.createElement("div");
    grid.className = "agent-rec-items";
    (rec.items || []).forEach(function (item) {
      var link = document.createElement("a");
      link.className = "agent-rec-mini-card";
      link.href = "/products/" + item.product_id;

      var title = document.createElement("div");
      title.className = "title";
      title.textContent = item.title;
      link.appendChild(title);

      var category = document.createElement("div");
      category.className = "muted small";
      category.textContent = item.category;
      link.appendChild(category);

      if (item.reason) {
        var reason = document.createElement("div");
        reason.className = "reason";
        reason.textContent = item.reason;
        link.appendChild(reason);
      }

      var price = document.createElement("div");
      price.className = "price";
      price.textContent = "$" + (item.price_cents / 100).toFixed(2);
      link.appendChild(price);

      grid.appendChild(link);
    });
    recEl.appendChild(grid);
  }

  function poll() {
    fetch(ENDPOINT, { credentials: "same-origin" })
      .then(function (res) {
        if (!res.ok) return null;
        return res.json();
      })
      .then(function (data) {
        if (!data) return;
        renderFeed(data.feed);
        renderRecommendation(data.recommendation);
        renderInterests(data.top_interests);
        renderSignalStrength(data.events_since_gen, data.trigger_threshold);
      })
      .catch(function () {
        /* best-effort: a missed poll tick just tries again next interval */
      });
  }

  function start() {
    if (timer) return;
    poll();
    timer = window.setInterval(poll, POLL_MS);
  }

  function stop() {
    if (!timer) return;
    window.clearInterval(timer);
    timer = null;
  }

  document.addEventListener("visibilitychange", function () {
    if (document.visibilityState === "hidden") {
      stop();
    } else {
      start();
    }
  });

  start();
})();
