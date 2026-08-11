"""Table-driven tests for `tracking.signal_feed` - the pure formatters behind
the live "Your Signal" panel. No DB, no LLM: this only shapes data the caller
already fetched (ARCHITECTURE.md \u00a76.1, \u00a715)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from smartreco_agent.src.tracking.signal_feed import humanize_events, top_interests

NOW = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

PRODUCT = {
    "id": "p1",
    "title": "Tool-Calling and Function Execution for Agents",
    "category": "Agentic AI",
}
PRODUCTS_BY_ID = {"p1": PRODUCT}


def _ago(seconds: int) -> datetime:
    return NOW - timedelta(seconds=seconds)


def test_product_view_resolves_title():
    events = [
        {"type": "product_view", "product_id": "p1", "payload": {}, "occurred_at": NOW}
    ]

    feed = humanize_events(events, PRODUCTS_BY_ID, now=NOW)

    assert feed == [
        {
            "label": "Viewed",
            "detail": PRODUCT["title"],
            "icon": "eye",
            "is_latest": True,
            "occurred_at": "now",
        }
    ]


def test_add_to_cart_and_click_and_dismiss_resolve_title():
    for event_type, label, icon in [
        ("add_to_cart", "Added", "cart"),
        ("click", "Clicked", "pointer"),
        ("dismiss", "Dismissed", "dismiss"),
    ]:
        events = [
            {
                "type": event_type,
                "product_id": "p1",
                "payload": {},
                "occurred_at": NOW,
            }
        ]
        feed = humanize_events(events, PRODUCTS_BY_ID, now=NOW)
        assert feed == [
            {
                "label": label,
                "detail": PRODUCT["title"],
                "icon": icon,
                "is_latest": True,
                "occurred_at": "now",
            }
        ]


def test_search_uses_quoted_query():
    events = [
        {
            "type": "search",
            "product_id": None,
            "payload": {"query": "agentic ai"},
            "occurred_at": NOW,
        }
    ]

    feed = humanize_events(events, {}, now=NOW)

    assert feed == [
        {
            "label": "Searched",
            "detail": '"agentic ai"',
            "icon": "search",
            "is_latest": True,
            "occurred_at": "now",
        }
    ]


def test_search_with_blank_query_is_dropped():
    events = [
        {
            "type": "search",
            "product_id": None,
            "payload": {"query": "   "},
            "occurred_at": NOW,
        }
    ]

    assert humanize_events(events, {}, now=NOW) == []


def test_dwell_formats_seconds_and_title():
    events = [
        {"type": "dwell", "product_id": "p1", "payload": {"seconds": 12}, "occurred_at": NOW},
    ]

    feed = humanize_events(events, PRODUCTS_BY_ID, now=NOW)

    assert feed == [
        {
            "label": "Dwell",
            "detail": f"12s on {PRODUCT['title']}",
            "icon": "clock",
            "is_latest": True,
            "occurred_at": "now",
        }
    ]


def test_dwell_without_product_or_path_is_dropped():
    events = [
        {"type": "dwell", "product_id": None, "payload": {"seconds": 12}, "occurred_at": NOW}
    ]

    assert humanize_events(events, {}, now=NOW) == []


def test_dwell_without_product_falls_back_to_friendly_path():
    events = [
        {
            "type": "dwell",
            "product_id": None,
            "payload": {"seconds": 9, "path": "/catalog"},
            "occurred_at": NOW,
        }
    ]

    feed = humanize_events(events, {}, now=NOW)

    assert feed[0]["detail"] == "9s on the catalog"


def test_dwell_on_a_product_path_never_leaks_the_raw_id(monkeypatch=None):
    """P0.2 regression: a dwell recorded with no resolvable product (e.g. the
    product was deleted, or the id raced the page's inline script) must never
    render the raw UUID from the URL path."""
    events = [
        {
            "type": "dwell",
            "product_id": None,
            "payload": {
                "seconds": 54,
                "path": "/products/9702a0a9-38cc-4145-9443-6a1649ae1e72",
            },
            "occurred_at": NOW,
        }
    ]

    feed = humanize_events(events, {}, now=NOW)

    assert feed[0]["detail"] == "54s on a course page"
    assert "9702a0a9" not in feed[0]["detail"]


def test_scroll_events_are_always_hidden():
    events = [
        {"type": "scroll", "product_id": None, "payload": {"depth_pct": 50}, "occurred_at": NOW},
        {"type": "product_view", "product_id": "p1", "payload": {}, "occurred_at": NOW},
    ]

    feed = humanize_events(events, PRODUCTS_BY_ID, now=NOW)

    assert len(feed) == 1
    assert feed[0]["label"] == "Viewed"


def test_only_the_first_surviving_entry_is_flagged_latest():
    events = [
        {"type": "product_view", "product_id": "p1", "payload": {}, "occurred_at": NOW},
        {"type": "scroll", "product_id": None, "payload": {}, "occurred_at": NOW},  # dropped
        {"type": "click", "product_id": "p1", "payload": {}, "occurred_at": _ago(120)},
    ]

    feed = humanize_events(events, PRODUCTS_BY_ID, now=NOW)

    assert [item["is_latest"] for item in feed] == [True, False]


def test_event_with_unresolvable_product_is_dropped():
    events = [
        {"type": "product_view", "product_id": "unknown", "payload": {}, "occurred_at": NOW}
    ]

    assert humanize_events(events, PRODUCTS_BY_ID, now=NOW) == []


def test_empty_input_returns_empty_feed():
    assert humanize_events([], {}, now=NOW) == []


# --- P0.3: collapsing consecutive duplicates ---------------------------------


def test_repeated_identical_clicks_collapse_with_a_count_suffix():
    events = [
        {"type": "click", "product_id": "p1", "payload": {}, "occurred_at": NOW},
        {"type": "click", "product_id": "p1", "payload": {}, "occurred_at": _ago(10)},
        {"type": "click", "product_id": "p1", "payload": {}, "occurred_at": _ago(20)},
    ]

    feed = humanize_events(events, PRODUCTS_BY_ID, now=NOW)

    assert len(feed) == 1
    assert feed[0]["detail"] == f"{PRODUCT['title']} \u00d73"
    assert feed[0]["occurred_at"] == "now"  # keeps the most recent timestamp


def test_duplicate_collapse_respects_the_five_minute_window():
    events = [
        {"type": "click", "product_id": "p1", "payload": {}, "occurred_at": NOW},
        {"type": "click", "product_id": "p1", "payload": {}, "occurred_at": _ago(400)},
    ]

    feed = humanize_events(events, PRODUCTS_BY_ID, now=NOW)

    assert len(feed) == 2


def test_dwells_with_different_durations_are_not_collapsed():
    events = [
        {"type": "dwell", "product_id": "p1", "payload": {"seconds": 30}, "occurred_at": NOW},
        {"type": "dwell", "product_id": "p1", "payload": {"seconds": 8}, "occurred_at": _ago(5)},
    ]

    feed = humanize_events(events, PRODUCTS_BY_ID, now=NOW)

    assert len(feed) == 2


def test_different_search_queries_are_not_collapsed():
    events = [
        {
            "type": "search",
            "product_id": None,
            "payload": {"query": "agentic ai"},
            "occurred_at": NOW,
        },
        {
            "type": "search",
            "product_id": None,
            "payload": {"query": "rag"},
            "occurred_at": _ago(5),
        },
    ]

    feed = humanize_events(events, {}, now=NOW)

    assert len(feed) == 2


# --- P1.5: relative timestamps -----------------------------------------------


def test_relative_timestamps_bucket_correctly():
    events = [
        {"type": "click", "product_id": "p1", "payload": {}, "occurred_at": _ago(3)},
        {"type": "click", "product_id": "p1", "payload": {}, "occurred_at": _ago(400)},
        {"type": "click", "product_id": "p1", "payload": {}, "occurred_at": _ago(4000)},
    ]

    # Each is its own row (outside the 5-minute collapse window of the last).
    feed = humanize_events([events[0]], PRODUCTS_BY_ID, now=NOW)
    assert feed[0]["occurred_at"] == "now"

    feed = humanize_events([events[1]], PRODUCTS_BY_ID, now=NOW)
    assert feed[0]["occurred_at"] == "6m"

    feed = humanize_events([events[2]], PRODUCTS_BY_ID, now=NOW)
    assert feed[0]["occurred_at"] == "1h"


# --- P1.4: top interest weights -----------------------------------------------


def test_top_interests_normalises_to_percentages_of_category_mass():
    weights = {
        "category:Security": 0.62,
        "category:Cloud & DevOps": 0.24,
        "category:Machine Learning": 0.14,
        "tag:appsec": 0.9,  # tags are excluded - only categories are shown
    }

    result = top_interests(weights, limit=2)

    assert result == [
        {"label": "Security", "pct": 62},
        {"label": "Cloud & DevOps", "pct": 24},
    ]


def test_top_interests_with_no_weights_is_empty():
    assert top_interests(None) == []
    assert top_interests({}) == []
    assert top_interests({"category:Security": 0.0}) == []
