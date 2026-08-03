"""Prompt builders for `analyze_intent` and `refine`."""

from __future__ import annotations

from typing import Any


def top_weight_summary(weights: dict[str, float], top_k: int = 8) -> str:
    ranked = sorted(weights.items(), key=lambda kv: kv[1], reverse=True)[:top_k]
    if not ranked:
        return "(no interest signal yet)"
    return "\n".join(f"- {key}: {value:.2f}" for key, value in ranked)


def build_intent_prompt(
    *,
    weights: dict[str, float],
    recent_events: list[dict[str, Any]],
    recent_search_queries: list[str],
) -> tuple[str, str]:
    system = (
        "You analyze a learner's behavioural signals on an online course marketplace "
        "and extract structured intent. Be concrete and specific - vague themes like "
        "'technology' are useless for retrieval. Prefer themes phrased the way a course "
        "title or search query would be phrased."
    )
    events_summary = "\n".join(
        f"- {e['type']}" + (f" (product {e['product_id']})" if e.get("product_id") else "")
        for e in recent_events[:20]
    ) or "(no recent events)"
    searches = "\n".join(f"- {q}" for q in recent_search_queries) or "(no recent searches)"

    user = (
        f"Decayed interest weights (higher = more current interest):\n"
        f"{top_weight_summary(weights)}\n\n"
        f"Recent activity:\n{events_summary}\n\n"
        f"Recent searches:\n{searches}\n\n"
        "Return 2-5 themes, an inferred skill level, a one-phrase journey stage "
        "(e.g. 'just starting to explore', 'comparing advanced options'), and 2-4 "
        "short semantic search queries that would retrieve courses matching this "
        "learner's current interest."
    )
    return system, user


def build_refine_prompt(*, previous_queries: list[str], grade_reasons: list[str]) -> tuple[str, str]:
    system = (
        "Your previous set of search queries did not retrieve enough relevant, diverse "
        "results from the course catalog. Broaden or re-angle them - do not repeat the "
        "same phrasing."
    )
    user = (
        "Previous queries:\n" + "\n".join(f"- {q}" for q in previous_queries) + "\n\n"
        "Why they fell short:\n" + "\n".join(f"- {r}" for r in grade_reasons) + "\n\n"
        "Return 2-4 new search queries, broader or differently angled, plus a one-sentence "
        "explanation of the change."
    )
    return system, user
