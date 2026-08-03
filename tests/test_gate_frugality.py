"""test_trigger_policy_is_frugal (ARCHITECTURE.md \u00a715, evidence item #1).

Drives `tracking.gate.should_generate` - the deterministic Tier-1 policy -
through 200 synthetic events spanning roughly an hour of active browsing and
asserts the number of "fire" decisions stays in the frugal single-digit band
the architecture claims. `catalog.get_profile` / `get_current_recommendation`
are monkeypatched with an in-memory state machine so this test needs no
database; `gate`'s clock is frozen so cooldown maths are deterministic.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import numpy as np
import pytest

from smartreco_agent.src.tracking import gate

USER_ID = "11111111-1111-1111-1111-111111111111"


def _unit_vector(seed: int, dim: int = 8) -> list[float]:
    rng = np.random.default_rng(seed)
    v = rng.normal(size=dim)
    return (v / np.linalg.norm(v)).tolist()


async def _should_generate_at(now: datetime, *, force: bool = False):
    """`should_generate` reads the wall clock internally; freeze it for one call
    so a 200-iteration simulated timeline does not need to sleep in real time."""
    import smartreco_agent.src.tracking.gate as gate_module

    real_datetime = gate_module.datetime

    class _FrozenDatetime(real_datetime):
        @classmethod
        def now(cls, tz=None):
            return now

    gate_module.datetime = _FrozenDatetime
    try:
        return await gate.should_generate(USER_ID, force=force)
    finally:
        gate_module.datetime = real_datetime


@pytest.mark.asyncio
async def test_trigger_policy_is_frugal(monkeypatch):
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    interval = timedelta(seconds=20)  # 200 events ~= 66 minutes of active browsing

    state = {
        "last_generated_at": None,
        "events_since_gen": 0,
        "profile_hash": "h-init",
        "interest_vector": _unit_vector(0),
        "gen_vector": None,
        "weights": {"category:Agentic AI": 1.0},
    }
    ctx = {"last_fired_hash": None}

    async def fake_get_profile(_uid):
        return dict(state)

    async def fake_get_current_recommendation(_uid):
        if ctx["last_fired_hash"] is None:
            return None
        return {"profile_hash": ctx["last_fired_hash"], "items": [{"category": "Agentic AI"}]}

    monkeypatch.setattr(gate.catalog, "get_profile", AsyncMock(side_effect=fake_get_profile))
    monkeypatch.setattr(
        gate.catalog, "get_current_recommendation", AsyncMock(side_effect=fake_get_current_recommendation)
    )

    fired = 0
    now = start
    for i in range(200):
        now += interval
        state["events_since_gen"] += 1
        key = next(iter(state["weights"]), "category:Agentic AI")
        state["weights"][key] = state["weights"].get(key, 0.0) + 0.05  # every event nudges the interest weight

        if i == 60:
            state["interest_vector"] = _unit_vector(1)  # a real behavioural drift
        if i == 130:
            state["weights"] = {"category:Data Engineering": 5.0}  # a category pivot

        state["profile_hash"] = f"h-{i}"  # a distinct hash every batch, like a live weight update

        reason = await _should_generate_at(now)
        if reason:
            fired += 1
            ctx["last_fired_hash"] = state["profile_hash"]
            state["gen_vector"] = state["interest_vector"]
            state["last_generated_at"] = now
            state["events_since_gen"] = 0

    assert 4 <= fired <= 8, f"expected a frugal 4-8 generations across 200 events, got {fired}"


@pytest.mark.asyncio
async def test_cooldown_blocks_even_a_forced_refresh(monkeypatch):
    """The cooldown is absolute - `force=True` (a manual "Refresh now" click)
    must not bypass it (ARCHITECTURE.md \u00a78)."""
    now = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    profile = {
        "last_generated_at": now - timedelta(minutes=2),
        "events_since_gen": 99,
        "profile_hash": "same",
        "interest_vector": _unit_vector(0),
        "gen_vector": _unit_vector(5),
        "weights": {},
    }
    monkeypatch.setattr(gate.catalog, "get_profile", AsyncMock(return_value=profile))
    monkeypatch.setattr(gate.catalog, "get_current_recommendation", AsyncMock(return_value=None))

    reason = await _should_generate_at(now, force=True)

    assert reason is None


@pytest.mark.asyncio
async def test_unchanged_profile_hash_skips_generation(monkeypatch):
    """Nothing moved since the last generation -> no Mesh call, even past cooldown
    and past the event-count threshold."""
    now = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    profile = {
        "last_generated_at": now - timedelta(hours=1),
        "events_since_gen": 50,
        "profile_hash": "stable",
        "interest_vector": _unit_vector(0),
        "gen_vector": _unit_vector(0),
        "weights": {},
    }
    monkeypatch.setattr(gate.catalog, "get_profile", AsyncMock(return_value=profile))
    monkeypatch.setattr(
        gate.catalog,
        "get_current_recommendation",
        AsyncMock(return_value={"profile_hash": "stable", "items": []}),
    )

    reason = await _should_generate_at(now)

    assert reason is None
