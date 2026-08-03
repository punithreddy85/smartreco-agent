"""Pure formatting for the live "Your Signal" panel on the product page.

Turns raw `catalog.events` rows into short, human-readable feed entries (e.g.
"Viewed - Tool-Calling and Function Execution for Agents"). No DB access and
no LLM calls happen here - this only shapes data already fetched by the
caller, which is what makes it independently testable and keeps
`routes/signal.py` (ARCHITECTURE.md \u00a76.1, \u00a715) free of Mesh calls.
"""

from __future__ import annotations

from typing import Any

# `scroll` is intentionally excluded: it already carries zero weight in the
# interest model (tracking/profile.py) and is too noisy to be meaningful
# "signal" for a human watching this panel.
_LABELS: dict[str, str] = {
    "page_view": "Viewed",
    "product_view": "Viewed",
    "search": "Searched",
    "click": "Clicked",
    "dwell": "Dwell",
    "add_to_cart": "Added",
    "dismiss": "Dismissed",
}

_HIDDEN_TYPES = {"scroll"}

_PATH_LABELS: dict[str, str] = {
    "/catalog": "the catalog",
    "/recommendations": "your recommendations",
}


def _friendly_path(path: str | None) -> str | None:
    if not path:
        return None
    if path in _PATH_LABELS:
        return _PATH_LABELS[path]
    return path.strip("/").replace("-", " ") or "the site"


def _detail(event: dict[str, Any], product: dict[str, Any] | None) -> str | None:
    event_type = event["type"]
    payload = event.get("payload") or {}

    if event_type == "search":
        query = (payload.get("query") or "").strip()
        return f'"{query}"' if query else None

    if event_type == "dwell":
        seconds = payload.get("seconds")
        target = product["title"] if product else _friendly_path(payload.get("path"))
        if not seconds or not target:
            return None
        return f"{int(seconds)}s on {target}"

    if event_type == "page_view":
        return product["title"] if product else None

    # click / product_view / add_to_cart / dismiss all key off the product.
    return product["title"] if product else None


def humanize_events(
    events: list[dict[str, Any]], products_by_id: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    """Formats recent events (newest first, as returned by
    `catalog.recent_events`) into feed entries for the live signal panel.

    Skips event types with no meaningful display (`scroll`, or any event
    whose detail could not be resolved, e.g. a `dwell` with no product/path).
    Flags the first surviving entry as `is_latest` for the highlighted-chip
    treatment in the UI.
    """
    feed: list[dict[str, Any]] = []
    for event in events:
        event_type = event["type"]
        if event_type in _HIDDEN_TYPES:
            continue
        label = _LABELS.get(event_type)
        if label is None:
            continue

        product_id = event.get("product_id")
        product = products_by_id.get(str(product_id)) if product_id else None
        detail = _detail(event, product)
        if not detail:
            continue

        feed.append(
            {
                "label": label,
                "detail": detail,
                "is_latest": len(feed) == 0,
            }
        )

    return feed
