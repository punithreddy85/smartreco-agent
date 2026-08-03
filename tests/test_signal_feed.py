"""Table-driven tests for `tracking.signal_feed.humanize_events` - the pure
formatter behind the live "Your Signal" panel. No DB, no LLM: this only
shapes data the caller already fetched (ARCHITECTURE.md \u00a76.1, \u00a715)."""

from __future__ import annotations

from smartreco_agent.src.tracking.signal_feed import humanize_events

PRODUCT = {
    "id": "p1",
    "title": "Tool-Calling and Function Execution for Agents",
    "category": "Agentic AI",
}
PRODUCTS_BY_ID = {"p1": PRODUCT}


def test_product_view_resolves_title():
    events = [{"type": "product_view", "product_id": "p1", "payload": {}}]

    feed = humanize_events(events, PRODUCTS_BY_ID)

    assert feed == [{"label": "Viewed", "detail": PRODUCT["title"], "is_latest": True}]


def test_add_to_cart_and_click_and_dismiss_resolve_title():
    for event_type, label in [
        ("add_to_cart", "Added"),
        ("click", "Clicked"),
        ("dismiss", "Dismissed"),
    ]:
        events = [{"type": event_type, "product_id": "p1", "payload": {}}]
        feed = humanize_events(events, PRODUCTS_BY_ID)
        assert feed == [{"label": label, "detail": PRODUCT["title"], "is_latest": True}]


def test_search_uses_quoted_query():
    events = [
        {"type": "search", "product_id": None, "payload": {"query": "agentic ai"}}
    ]

    feed = humanize_events(events, {})

    assert feed == [{"label": "Searched", "detail": '"agentic ai"', "is_latest": True}]


def test_search_with_blank_query_is_dropped():
    events = [{"type": "search", "product_id": None, "payload": {"query": "   "}}]

    assert humanize_events(events, {}) == []


def test_dwell_formats_seconds_and_title():
    events = [
        {"type": "dwell", "product_id": "p1", "payload": {"seconds": 12}},
    ]

    feed = humanize_events(events, PRODUCTS_BY_ID)

    assert feed == [
        {"label": "Dwell", "detail": f"12s on {PRODUCT['title']}", "is_latest": True}
    ]


def test_dwell_without_product_or_path_is_dropped():
    events = [{"type": "dwell", "product_id": None, "payload": {"seconds": 12}}]

    assert humanize_events(events, {}) == []


def test_dwell_without_product_falls_back_to_friendly_path():
    events = [
        {
            "type": "dwell",
            "product_id": None,
            "payload": {"seconds": 9, "path": "/catalog"},
        }
    ]

    feed = humanize_events(events, {})

    assert feed == [
        {"label": "Dwell", "detail": "9s on the catalog", "is_latest": True}
    ]


def test_scroll_events_are_always_hidden():
    events = [
        {"type": "scroll", "product_id": None, "payload": {"depth_pct": 50}},
        {"type": "product_view", "product_id": "p1", "payload": {}},
    ]

    feed = humanize_events(events, PRODUCTS_BY_ID)

    assert len(feed) == 1
    assert feed[0]["label"] == "Viewed"


def test_only_the_first_surviving_entry_is_flagged_latest():
    events = [
        {"type": "product_view", "product_id": "p1", "payload": {}},
        {"type": "scroll", "product_id": None, "payload": {}},  # dropped, doesn't count
        {"type": "click", "product_id": "p1", "payload": {}},
    ]

    feed = humanize_events(events, PRODUCTS_BY_ID)

    assert [item["is_latest"] for item in feed] == [True, False]


def test_event_with_unresolvable_product_is_dropped():
    events = [{"type": "product_view", "product_id": "unknown", "payload": {}}]

    assert humanize_events(events, PRODUCTS_BY_ID) == []


def test_empty_input_returns_empty_feed():
    assert humanize_events([], {}) == []
