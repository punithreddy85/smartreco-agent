"""Prompt builder for `generate_and_verify` - the only node whose output the
user actually reads."""

from __future__ import annotations

from typing import Any


def build_narrative_prompt(
    *,
    themes: list[str],
    journey_stage: str,
    candidates: list[dict[str, Any]],
    violation_note: str | None = None,
) -> tuple[str, str]:
    system = (
        "You write short, persuasive, second-person recommendation copy for an online "
        "course marketplace. You may ONLY recommend courses from the candidate list below "
        "- you may never invent a course or reference a product_id that is not listed. "
        "Ground every reason in this specific learner's behaviour (their themes and "
        "journey stage), not generic marketing language. Keep the narrative to 2-4 "
        "sentences, written directly to the learner."
    )

    candidate_lines = []
    for c in candidates:
        candidate_lines.append(
            f"- id={c['id']} | {c['title']} | category={c['category']} | level={c['level']} | "
            f"price=${c['price_cents'] / 100:.2f}\n  {c['description'][:280]}"
        )

    user = (
        f"Learner themes: {', '.join(themes)}\n"
        f"Journey stage: {journey_stage}\n\n"
        f"Candidate courses (choose up to 4, ranked best first):\n"
        + "\n".join(candidate_lines)
        + "\n\n"
        "Write the narrative, then list the chosen courses as items with a one-sentence "
        "reason each, referencing this learner's behaviour."
    )

    if violation_note:
        user += f"\n\nIMPORTANT: {violation_note} Only use product_id values from the candidate list above."

    return system, user
