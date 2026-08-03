"""test_profile_decay (ARCHITECTURE.md \u00a715, evidence item #6).

Asserts the exponential decay in `tracking.profile` behaves as specified: a
7-day-old interest ranks below a 1-hour-old one of equal original weight, and
`_decay_factor` matches the documented `exp(-hours/tau)` formula with
tau=72h.
"""

from __future__ import annotations

import math

import pytest

from smartreco_agent.src.tracking import profile


def test_decay_factor_matches_formula():
    assert profile._decay_factor(0) == pytest.approx(1.0)
    assert profile._decay_factor(profile.TAU_HOURS) == pytest.approx(
        math.exp(-1), rel=1e-9
    )
    assert profile._decay_factor(1000) < 0.001  # effectively fully decayed


def test_a_week_old_interest_ranks_below_an_hour_old_one():
    original_weight = 10.0

    week_old_hours = 7 * 24
    hour_old_hours = 1

    week_old_now = profile._decay_all({"category:X": original_weight}, week_old_hours)[
        "category:X"
    ]
    hour_old_now = profile._decay_all({"category:X": original_weight}, hour_old_hours)[
        "category:X"
    ]

    assert week_old_now < hour_old_now
    # A week is ~2.33x tau (72h), so the week-old weight should have decayed
    # to a small fraction of its original value while the hour-old one has
    # barely moved.
    assert week_old_now < original_weight * 0.1
    assert hour_old_now > original_weight * 0.95


def test_decay_never_produces_negative_or_growing_weights():
    weights = {"category:A": 5.0, "category:B": -2.0}  # dismiss events can go negative
    decayed = profile._decay_all(weights, hours_elapsed=24)

    assert abs(decayed["category:A"]) < abs(weights["category:A"])
    assert abs(decayed["category:B"]) < abs(weights["category:B"])
    assert decayed["category:B"] < 0  # sign is preserved, only magnitude decays


def test_dwell_below_threshold_contributes_zero_weight():
    # Matches the real payload shape sent by static/tracker.js's flushDwell().
    short_dwell = {"type": "dwell", "payload": {"seconds": 10}}
    long_dwell = {"type": "dwell", "payload": {"seconds": 45}}

    assert profile._event_weight(short_dwell) == 0.0
    assert profile._event_weight(long_dwell) == profile.EVENT_WEIGHT["dwell"]


def test_dismiss_weight_is_negative():
    assert profile.EVENT_WEIGHT["dismiss"] < 0
