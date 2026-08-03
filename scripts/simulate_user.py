"""The demo surface (ARCHITECTURE.md \u00a712.4, \u00a716): replays a behavioural trace for
one user, prints the generated recommendation, replays a second trace skewed
toward a different category, and prints how the recommendation moved -
alongside the total Mesh call count for the whole run.

This is the fastest way to see the agent and the trigger policy working
without reading a line of code:

    make seed
    make demo

Requires the catalog to already be seeded (`make seed`) and MESH_API_KEY set.
"""

from __future__ import annotations

import asyncio
import random
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from smartreco_agent.src.agent.graph import run_agent  # noqa: E402
from smartreco_agent.src.db import catalog  # noqa: E402
from smartreco_agent.src.db.pool import (  # noqa: E402
    close_pool,
    get_connection,
    open_pool,
)
from smartreco_agent.src.mesh.client import CALL_COUNTS  # noqa: E402
from smartreco_agent.src.tracking import gate, profile  # noqa: E402

DEMO_EMAIL = "demo@smartreco.dev"


def _event(type_: str, product_id: str | None = None, payload: dict | None = None, when=None) -> dict:
    return {
        "event_id": str(uuid.uuid4()),
        "type": type_,
        "product_id": product_id,
        "payload": payload or {},
        "occurred_at": when or datetime.now(timezone.utc),
    }


def _build_trace(products: list[dict], queries: list[str], noise_products: list[dict]) -> list[dict]:
    """~35 events skewed toward `products`, with a couple of searches and a
    handful of unrelated `noise_products` so the skew is realistic, not exclusive."""
    now = datetime.now(timezone.utc)
    events: list[dict] = []
    t = now - timedelta(minutes=30)

    def tick(seconds: float = 8.0) -> datetime:
        nonlocal t
        t += timedelta(seconds=seconds)
        return t

    for q in queries:
        events.append(_event("search", payload={"query": q}, when=tick()))

    for p in products:
        events.append(_event("product_view", p["id"], when=tick()))
        if random.random() < 0.6:
            events.append(_event("click", p["id"], when=tick(3)))
        if p["level"] == "advanced" and random.random() < 0.7:
            events.append(_event("dwell", p["id"], payload={"duration_seconds": random.randint(45, 180)}, when=tick(60)))

    for p in noise_products:
        events.append(_event("product_view", p["id"], when=tick()))

    return events


async def _ensure_demo_user() -> str:
    user = await catalog.get_user_by_email(DEMO_EMAIL)
    if not user:
        raise SystemExit(f"Demo user not found - run `make seed` first (expects {DEMO_EMAIL}).")
    return str(user["id"])


async def _expire_cooldown(user_id: str) -> None:
    """Simulates time passing between the two phases of the demo. In production
    the 10-minute cooldown (ARCHITECTURE.md \u00a78) is absolute and not bypassable -
    this is a demo-only shortcut so a reviewer does not have to wait 10 minutes
    to see the second recommendation, not a change to the trigger policy itself."""
    async with get_connection() as conn, conn.cursor() as cur:
        await cur.execute(
            "update catalog.user_profiles set last_generated_at = now() - interval '1 hour' "
            "where user_id = %s",
            (user_id,),
        )


async def _run_phase(user_id: str, label: str, events: list[dict]) -> None:
    print(f"\n--- {label}: replaying {len(events)} events ---")
    await profile.apply(user_id, events)
    reason = await gate.should_generate(user_id)
    if not reason:
        print("gate: no trigger fired (cooldown, or interests have not moved enough yet)")
        return
    print(f"gate fired: trigger_reason={reason!r} -- calling the agent")
    rec = await run_agent(user_id, trigger_reason=reason)
    if not rec:
        print("agent produced no recommendation (see catalog.agent_runs.error)")
        return

    print(f"\nRecommendation ({rec['trigger_reason']}):\n")
    print(rec["narrative"])
    print()
    for item in rec["items"]:
        print(f"  - {item['title']} [{item['category']}/{item['level']}] - {item['reason']}")


async def main() -> None:
    await open_pool()
    try:
        user_id = await _ensure_demo_user()

        agentic = await catalog.list_products(category="Agentic AI")
        data_eng = await catalog.list_products(category="Data Engineering")
        if not agentic or not data_eng:
            raise SystemExit("Catalog looks empty - run `make seed` first.")

        print("=" * 70)
        print("Phase 1: user keeps landing on agentic-AI content, searches for it twice")
        print("=" * 70)
        phase_1_events = _build_trace(
            products=agentic,
            queries=["agentic ai", "langgraph agents"],
            noise_products=data_eng[:2],
        )
        await _run_phase(user_id, "Phase 1 (Agentic AI)", phase_1_events)

        await _expire_cooldown(user_id)

        print("\n" + "=" * 70)
        print("Phase 2: same user pivots hard toward data engineering")
        print("=" * 70)
        phase_2_events = _build_trace(
            products=data_eng,
            queries=["data pipelines", "airflow orchestration"],
            noise_products=agentic[:2],
        )
        await _run_phase(user_id, "Phase 2 (Data Engineering)", phase_2_events)

        print("\n" + "=" * 70)
        print("Mesh call count for this run (frugality check):")
        print(f"  chat completions: {CALL_COUNTS['chat']}")
        print(f"  embeddings calls: {CALL_COUNTS['embeddings']}")
        print(
            f"  -> {len(phase_1_events) + len(phase_2_events)} behavioural events produced "
            f"only {CALL_COUNTS['chat'] + CALL_COUNTS['embeddings']} total Mesh API calls."
        )
        print("=" * 70)
    finally:
        await close_pool()


if __name__ == "__main__":
    asyncio.run(main())
