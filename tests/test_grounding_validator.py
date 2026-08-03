"""test_grounding_validator_rejects_hallucination (ARCHITECTURE.md \u00a715, evidence
item #4). Stubs `complete_json` to return a recommendation citing a product_id
that is not in the retrieved candidate set, on both the first attempt and the
one allowed retry, and asserts `generate_and_verify` fails closed: no
recommendation is returned and the previous one stays current."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from smartreco_agent.src.agent.nodes import generate as generate_module
from smartreco_agent.src.agent.schemas import (
    IntentAnalysis,
    Recommendation,
    RecommendedItem,
)
from smartreco_agent.src.mesh.client import Usage

REAL_ID = "aaaaaaaa-1111-1111-1111-111111111111"
HALLUCINATED_ID = "bbbbbbbb-2222-2222-2222-222222222222"

CANDIDATES = [
    {
        "id": REAL_ID,
        "title": "Agentic AI Foundations",
        "category": "Agentic AI",
        "level": "beginner",
        "price_cents": 4900,
        "description": "Learn what makes an AI system agentic.",
    }
]

INTENT = IntentAnalysis(
    themes=["agentic ai"],
    level="beginner",
    journey_stage="exploring",
    retrieval_queries=["agentic ai", "langgraph"],
)


def _hallucinated_response() -> tuple[Recommendation, Usage]:
    rec = Recommendation(
        narrative="You'll love this course.",
        items=[RecommendedItem(product_id=HALLUCINATED_ID, reason="great fit")],
    )
    return rec, Usage(prompt_tokens=100, completion_tokens=50, total_tokens=150)


@pytest.mark.asyncio
async def test_grounding_validator_rejects_hallucination_after_retry(monkeypatch):
    mock_complete = AsyncMock(
        side_effect=[_hallucinated_response(), _hallucinated_response()]
    )
    monkeypatch.setattr(generate_module, "complete_json", mock_complete)

    state = {
        "reranked": CANDIDATES,
        "intent": INTENT,
        "prompt_tokens": 0,
        "completion_tokens": 0,
    }
    result = await generate_module.generate_and_verify(state)

    assert result["recommendation"] is None
    assert "grounding" in result["error"]
    assert mock_complete.call_count == 2  # one retry allowed, then fail closed
    assert result["prompt_tokens"] == 200
    assert result["completion_tokens"] == 100


@pytest.mark.asyncio
async def test_grounding_validator_accepts_grounded_response(monkeypatch):
    rec = Recommendation(
        narrative="You'll love this course.",
        items=[RecommendedItem(product_id=REAL_ID, reason="great fit")],
    )
    mock_complete = AsyncMock(
        return_value=(
            rec,
            Usage(prompt_tokens=80, completion_tokens=40, total_tokens=120),
        )
    )
    monkeypatch.setattr(generate_module, "complete_json", mock_complete)

    state = {
        "reranked": CANDIDATES,
        "intent": INTENT,
        "prompt_tokens": 0,
        "completion_tokens": 0,
    }
    result = await generate_module.generate_and_verify(state)

    assert result["recommendation"] is rec
    assert mock_complete.call_count == 1  # grounded on the first try - no retry spent
    assert result.get("error") is None


@pytest.mark.asyncio
async def test_grounding_validator_recovers_on_retry(monkeypatch):
    """If the retry corrects itself and cites only real products, it is accepted."""
    good_rec = Recommendation(
        narrative="Corrected.",
        items=[RecommendedItem(product_id=REAL_ID, reason="great fit")],
    )
    mock_complete = AsyncMock(
        side_effect=[
            _hallucinated_response(),
            (good_rec, Usage(prompt_tokens=90, completion_tokens=45, total_tokens=135)),
        ]
    )
    monkeypatch.setattr(generate_module, "complete_json", mock_complete)

    state = {
        "reranked": CANDIDATES,
        "intent": INTENT,
        "prompt_tokens": 0,
        "completion_tokens": 0,
    }
    result = await generate_module.generate_and_verify(state)

    assert result["recommendation"] is good_rec
    assert mock_complete.call_count == 2
