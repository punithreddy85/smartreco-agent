/**
 * SmartReco behavioral event tracker (ARCHITECTURE.md \u00a76.1).
 *
 * Design constraints:
 *  - Never blocks rendering or user interaction: all sends are async
 *    (`fetch(..., {keepalive:true})` or `navigator.sendBeacon`), never sync XHR.
 *  - Batches events client-side; flushes on whichever comes first: buffer of 10,
 *    a 5s timer, or the page being hidden/unloaded.
 *  - Signal-specific throttling/debouncing keeps high-frequency signals
 *    (scroll, search keystrokes) from flooding the interest model with noise.
 *  - Every event carries a client-generated UUID so retried/duplicate beacons
 *    are idempotent against the server's unique index.
 */
(function () {
  "use strict";

  if (!window.SMARTRECO_USER_ID) return;

  var ENDPOINT = "/api/events";
  var MAX_BUFFER = 10;
  var FLUSH_INTERVAL_MS = 5000;
  var SCROLL_THROTTLE_MS = 250;
  var SEARCH_DEBOUNCE_MS = 800;

  function uuid() {
    if (window.crypto && window.crypto.randomUUID) return window.crypto.randomUUID();
    return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, function (c) {
      var r = (Math.random() * 16) | 0;
      var v = c === "x" ? r : (r & 0x3) | 0x8;
      return v.toString(16);
    });
  }

  function sessionId() {
    var key = "smartreco_session_id";
    var existing = window.sessionStorage.getItem(key);
    if (existing) return existing;
    var fresh = uuid();
    window.sessionStorage.setItem(key, fresh);
    return fresh;
  }

  var SESSION_ID = sessionId();
  var buffer = [];
  var flushTimer = null;

  function makeEvent(type, productId, payload) {
    return {
      event_id: uuid(),
      type: type,
      product_id: productId || null,
      payload: payload || {},
      occurred_at: new Date().toISOString(),
    };
  }

  function scheduleFlush() {
    if (flushTimer) return;
    flushTimer = window.setTimeout(function () {
      flushTimer = null;
      flush(false);
    }, FLUSH_INTERVAL_MS);
  }

  function flush(useBeacon) {
    if (buffer.length === 0) return;
    var events = buffer.splice(0, buffer.length);
    var body = JSON.stringify({ session_id: SESSION_ID, events: events });

    if (useBeacon && navigator.sendBeacon) {
      var blob = new Blob([body], { type: "application/json" });
      var ok = navigator.sendBeacon(ENDPOINT, blob);
      if (ok) return;
      // fall through to fetch keepalive if the beacon queue rejected it
    }

    fetch(ENDPOINT, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "same-origin",
      keepalive: true,
      body: body,
    }).catch(function () {
      /* best-effort: dropped events do not degrade the page */
    });
  }

  function push(event) {
    buffer.push(event);
    if (buffer.length >= MAX_BUFFER) {
      flush(false);
    } else {
      scheduleFlush();
    }
  }

  // --- Public, low-frequency, high-signal events: sent immediately into the buffer ---

  function trackProductView(productId) {
    push(makeEvent("product_view", productId));
  }

  function trackAddToCart(productId) {
    push(makeEvent("add_to_cart", productId));
  }

  function trackClick(productId) {
    push(makeEvent("click", productId));
  }

  function trackDismiss(productId) {
    push(makeEvent("dismiss", productId));
  }

  var searchTimer = null;
  function trackSearch(query, opts) {
    query = (query || "").trim();
    if (!query) return;
    var immediate = opts && opts.immediate;
    if (searchTimer) {
      window.clearTimeout(searchTimer);
      searchTimer = null;
    }
    if (immediate) {
      push(makeEvent("search", null, { query: query }));
      return;
    }
    searchTimer = window.setTimeout(function () {
      push(makeEvent("search", null, { query: query }));
      searchTimer = null;
    }, SEARCH_DEBOUNCE_MS);
  }

  // --- Delegated click tracking so we don't attach N listeners ---

  document.addEventListener(
    "click",
    function (e) {
      var el = e.target.closest("[data-product-id]");
      if (el && el.dataset.productId) {
        trackClick(el.dataset.productId);
      }
    },
    true
  );

  // --- Scroll depth: throttled, emitted only at new 25% milestones ---

  var lastScrollEmit = 0;
  var seenMilestones = {};
  window.addEventListener(
    "scroll",
    function () {
      var now = Date.now();
      if (now - lastScrollEmit < SCROLL_THROTTLE_MS) return;
      lastScrollEmit = now;

      var doc = document.documentElement;
      var scrollable = doc.scrollHeight - doc.clientHeight;
      if (scrollable <= 0) return;
      var pct = Math.min(100, Math.round((window.scrollY / scrollable) * 100));
      var milestone = Math.floor(pct / 25) * 25;
      if (milestone > 0 && !seenMilestones[milestone]) {
        seenMilestones[milestone] = true;
        push(makeEvent("scroll", null, { depth_pct: milestone, path: location.pathname }));
      }
    },
    { passive: true }
  );

  // --- Dwell time: accumulated via the Page Visibility API, flushed on hide ---

  var dwellStart = document.visibilityState === "visible" ? Date.now() : null;

  function flushDwell() {
    if (dwellStart == null) return;
    var seconds = Math.round((Date.now() - dwellStart) / 1000);
    dwellStart = null; // clear before the transport call so a second
    // visibilitychange/pagehide firing for the same navigation is a no-op
    if (seconds < 2) return; // ignore drive-by loads
    // Read the product id lazily, at flush time: tracker.js loads before
    // product.html's inline script sets this global, so capturing it once
    // at parse time always sees `null` on product pages.
    push(
      makeEvent("dwell", window.SMARTRECO_CURRENT_PRODUCT_ID || null, {
        seconds: seconds,
        path: location.pathname,
      })
    );
  }

  document.addEventListener("visibilitychange", function () {
    if (document.visibilityState === "hidden") {
      flushDwell();
      flush(true);
    } else {
      dwellStart = Date.now();
    }
  });

  window.addEventListener("pagehide", function () {
    flushDwell();
    flush(true);
  });

  window.smartreco = {
    trackProductView: trackProductView,
    trackAddToCart: trackAddToCart,
    trackClick: trackClick,
    trackDismiss: trackDismiss,
    trackSearch: trackSearch,
  };
})();
