"""Pure formatting for the live "Your Signal" panel on the product page.

Turns raw `catalog.events` rows into short, human-readable feed entries (e.g.
"Viewed - Tool-Calling and Function Execution for Agents"). No DB access and
no LLM calls happen here - this only shapes data already fetched by the
caller, which is what makes it independently testable and keeps
`routes/signal.py` (ARCHITECTURE.md \u00a76.1, \u00a715) free of Mesh calls.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
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

# Event-type icon key rendered client-side (P3.4) - kept as a short symbolic
# name rather than markup so this module stays free of presentation detail.
_ICONS: dict[str, str] = {
    "page_view": "eye",
    "product_view": "eye",
    "search": "search",
    "click": "pointer",
    "dwell": "clock",
    "add_to_cart": "cart",
    "dismiss": "dismiss",
}

_HIDDEN_TYPES = {"scroll"}

_TRIGGER_LABELS: dict[str, str] = {
    "count": "count threshold",
    "drift": "interest drift",
    "category_shift": "category shift",
    "manual": "manual refresh",
    "scheduled": "scheduled digest",
}


def trigger_reason_label(trigger_reason: str | None) -> str | None:
    """Friendly copy for `recommendations.trigger_reason` (P1.3) - shown so a
    viewer can see the agent decided to run rather than running on a fixed
    schedule."""
    if not trigger_reason:
        return None
    return _TRIGGER_LABELS.get(trigger_reason, trigger_reason)

# Runs of the same (label, detail) within this window collapse into one row
# with a `xN` suffix (P0.3). Grouping on the *rendered* text rather than the
# raw (type, product_id) pair means a dwell with a different duration, or a
# search with a different query, is correctly treated as a distinct signal.
_COLLAPSE_WINDOW_SECONDS = 300

_PATH_LABELS: dict[str, str] = {
    "/catalog": "the catalog",
    "/recommendations": "your recommendations",
}

# First path segment -> a friendly generic noun, used when the next segment
# is an opaque ID we must never render (e.g. /products/<uuid> -> "a course
# page"). Falls back to a singularized version of the segment itself.
_SEGMENT_LABELS: dict[str, str] = {
    "products": "course",
}

# Matches a bare UUID and, defensively, any long hex run - a formatter bug
# must never let an identifier reach the page, even one this regex wasn't
# written with in mind (ARCHITECTURE.md guard for P0.2).
_ID_LIKE_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
    r"|^[0-9a-fA-F]{16,}$"
)


def _friendly_path(path: str | None) -> str | None:
    """Never returns a raw ID. Known static paths get a friendly name;
    detail paths whose final segment looks like an identifier collapse to a
    generic page-type label instead (P0.2)."""
    if not path:
        return None
    if path in _PATH_LABELS:
        return _PATH_LABELS[path]

    segments = [s for s in path.split("/") if s]
    if not segments:
        return "the site"

    if len(segments) > 1 and _ID_LIKE_RE.match(segments[-1]):
        head = segments[0]
        noun = _SEGMENT_LABELS.get(head, head.rstrip("s") or "site")
        return f"a {noun} page"

    if any(_ID_LIKE_RE.match(s) for s in segments):
        return "the site"

    return " ".join(segments).replace("-", " ")


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


def relative_time(occurred_at: datetime, now: datetime) -> str:
    """`now` / `14s` / `2m` / `1h` / `3d` - server-computed so the client never
    needs its own clock-skew-prone "time ago" logic (P1.5)."""
    delta = (now - occurred_at).total_seconds()
    if delta < 5:
        return "now"
    if delta < 60:
        return f"{int(delta)}s"
    if delta < 3600:
        return f"{int(delta // 60)}m"
    if delta < 86400:
        return f"{int(delta // 3600)}h"
    return f"{int(delta // 86400)}d"


def humanize_events(
    events: list[dict[str, Any]],
    products_by_id: dict[str, dict[str, Any]],
    *,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    """Formats recent events (newest first, as returned by
    `catalog.recent_events`) into feed entries for the live signal panel.

    Skips event types with no meaningful display (`scroll`, or any event
    whose detail could not be resolved, e.g. a `dwell` with no product/path).
    Consecutive rows with identical rendered text within a five-minute
    window collapse into one `xN` row (P0.3). Flags the first surviving
    entry as `is_latest` for the highlighted-row treatment in the UI.
    """
    now = now or datetime.now(timezone.utc)
    feed: list[dict[str, Any]] = []
    groups: list[dict[str, Any]] = []  # parallel list carrying collapse bookkeeping

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

        occurred_at = event["occurred_at"]

        if groups:
            group = groups[-1]
            gap = (group["newest_at"] - occurred_at).total_seconds()
            if (
                group["label"] == label
                and group["detail"] == detail
                and gap <= _COLLAPSE_WINDOW_SECONDS
            ):
                group["count"] += 1
                feed[-1]["detail"] = f"{detail} \u00d7{group['count']}"
                continue

        groups.append({"label": label, "detail": detail, "newest_at": occurred_at, "count": 1})
        feed.append(
            {
                "label": label,
                "detail": detail,
                "icon": _ICONS.get(event_type, "dot"),
                "is_latest": len(feed) == 0,
                "occurred_at": relative_time(occurred_at, now),
            }
        )

    return feed


def top_interests(
    weights: dict[str, float] | None, *, limit: int = 3
) -> list[dict[str, Any]]:
    """Top category weights from `user_profiles.weights`, normalised to
    percentages of the category weight mass at render time (P1.4) - the
    stored value stays a raw decayed weight, never a percentage."""
    categories = {
        key[len("category:") :]: value
        for key, value in (weights or {}).items()
        if key.startswith("category:") and value > 0
    }
    total = sum(categories.values())
    if total <= 0:
        return []

    ranked = sorted(categories.items(), key=lambda kv: kv[1], reverse=True)[:limit]
    return [
        {"label": label, "pct": round(weight / total * 100)} for label, weight in ranked
    ]
