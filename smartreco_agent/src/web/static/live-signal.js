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
  if (!feedEl || !recEl) return;

  var timer = null;

  function clearChildren(el) {
    while (el.firstChild) el.removeChild(el.firstChild);
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
      var chip = document.createElement("div");
      chip.className = "signal-chip" + (item.is_latest ? " latest" : "");

      var label = document.createElement("strong");
      label.textContent = item.label;
      chip.appendChild(label);
      chip.appendChild(document.createTextNode(" \u00b7 " + item.detail));

      feedEl.appendChild(chip);
    });
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
