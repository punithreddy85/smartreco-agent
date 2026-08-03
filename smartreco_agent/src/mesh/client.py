"""Mesh API client - an OpenAI-compatible gateway, so the official SDK works
with only a base_url change (ARCHITECTURE.md \u00a73.1, Appendix D).

Two defences the doc calls out explicitly, both implemented here:

1. Never call `json.loads` bare on a chat completion - parse through Pydantic
   and treat `ValidationError`/`ParseFailure` as a normal agent failure path.
2. `assert_models_capable()` is a startup smoke test: it sends a two-field
   schema to each configured model and asserts valid JSON comes back, catching
   a bad `MESH_CHAT_MODEL` before a user does.
"""

from __future__ import annotations

import json
from typing import Literal, Sequence, TypeVar

from openai import APIStatusError, AsyncOpenAI
from pydantic import BaseModel, ConfigDict, ValidationError

from smartreco_agent.src.settings import settings
from smartreco_agent.utils.pylogger import get_python_logger

logger = get_python_logger(settings.PYTHON_LOG_LEVEL)

BaseModelT = TypeVar("BaseModelT", bound=BaseModel)

_client: AsyncOpenAI | None = None

# Process-wide counters for the two Mesh call types. Read by
# `scripts/simulate_user.py` to print the total-LLM-calls frugality number;
# incremented here rather than at each call site so every caller is covered.
CALL_COUNTS: dict[str, int] = {"chat": 0, "embeddings": 0}


class MeshError(Exception):
    """Base class for Mesh-related failures."""


class ParseFailure(MeshError):
    """The model returned content that did not validate against the requested schema."""


class BalanceExhausted(MeshError):
    """Mesh returned 402 - the account has no balance / hit a spend limit."""


class ConfigError(MeshError):
    """A configured model ID is missing or lacks a required capability."""


def get_mesh_client() -> AsyncOpenAI:
    """Lazily-initialised, reused across warm invocations (Vercel cold-start note, \u00a712.1)."""
    global _client
    if _client is None:
        _client = AsyncOpenAI(
            base_url=settings.MESH_BASE_URL,
            api_key=settings.MESH_API_KEY,
            timeout=30.0,
            max_retries=2,
        )
    return _client


class Usage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


def _schema_name(schema: type[BaseModel]) -> str:
    return schema.__name__.lower()


async def complete_json(
    *,
    model: str,
    system: str,
    user: str,
    schema: type[BaseModelT],
    max_tokens: int = 1200,
    temperature: float = 0.0,
    _retry: bool = True,
) -> tuple[BaseModelT, Usage]:
    """Chat completion constrained to `schema`. Raises ParseFailure on invalid JSON.

    The JSON payload always arrives as a *string* in `choices[0].message.content`
    and is never pre-parsed by Mesh - see Appendix D.3.
    """
    client = get_mesh_client()
    json_schema = schema.model_json_schema()
    json_schema.setdefault("additionalProperties", False)

    CALL_COUNTS["chat"] += 1
    try:
        resp = await client.chat.completions.create(
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            response_format={
                "type": "json_schema",
                "json_schema": {"name": _schema_name(schema), "schema": json_schema},
            },
        )
    except APIStatusError as e:
        if e.status_code == 402:
            raise BalanceExhausted("Mesh balance/spend-limit exhausted") from e
        raise MeshError(f"Mesh chat completion failed: {e.status_code} {e.message}") from e

    choice = resp.choices[0]
    usage = Usage(**(resp.usage.model_dump() if resp.usage else {}))

    if choice.finish_reason not in ("stop", None):
        logger.warning("mesh_truncated_response", finish_reason=choice.finish_reason, model=model)
        if _retry:
            return await complete_json(
                model=model, system=system, user=user, schema=schema,
                max_tokens=max_tokens * 2, temperature=temperature, _retry=False,
            )
        raise ParseFailure(f"Response truncated (finish_reason={choice.finish_reason})")

    raw = choice.message.content or ""
    try:
        parsed_dict = json.loads(raw)
        parsed = schema.model_validate(parsed_dict)
    except (json.JSONDecodeError, ValidationError) as e:
        logger.warning("mesh_parse_failure", model=model, error=str(e), raw=raw[:500])
        if _retry:
            return await complete_json(
                model=model, system=system,
                user=f"{user}\n\nYour previous response was not valid JSON matching the schema. "
                     f"Return only valid JSON matching the schema, nothing else.",
                schema=schema, max_tokens=max_tokens, temperature=temperature, _retry=False,
            )
        raise ParseFailure(f"Could not parse Mesh response into {schema.__name__}: {e}") from e

    return parsed, usage


async def embed(
    texts: Sequence[str], *, input_type: Literal["document", "query"]
) -> list[list[float]]:
    """Batched embeddings at `settings.MESH_EMBED_DIMENSIONS` width.

    `dimensions` is passed explicitly on every call - Qwen v4's default width is
    not 1536, and omitting it would silently break the `vector(1536)` column the
    moment a provider default changed (Appendix D.4).
    """
    if not texts:
        return []
    client = get_mesh_client()
    CALL_COUNTS["embeddings"] += 1
    try:
        resp = await client.embeddings.create(
            model=settings.MESH_EMBED_MODEL,
            input=list(texts),
            dimensions=settings.MESH_EMBED_DIMENSIONS,
            extra_body={"input_type": input_type},
        )
    except APIStatusError as e:
        if e.status_code == 402:
            raise BalanceExhausted("Mesh balance/spend-limit exhausted") from e
        raise MeshError(f"Mesh embeddings call failed: {e.status_code} {e.message}") from e

    return [d.embedding for d in resp.data]


_query_embed_cache: dict[str, list[float]] = {}


async def embed_query_cached(text: str) -> list[float]:
    """Query embeddings are cached by normalised text - repeated searches cost nothing (\u00a77)."""
    key = text.strip().lower()
    if key in _query_embed_cache:
        return _query_embed_cache[key]
    [vector] = await embed([text], input_type="query")
    _query_embed_cache[key] = vector
    return vector


async def assert_models_capable() -> None:
    """Startup capability check (Appendix D.5). Run from lifespan locally; run
    from `/api/cron/reconcile` on Vercel so a cold start never pays for it."""
    client = get_mesh_client()
    models_resp = await client.models.list()
    models = {m.id: m for m in models_resp.data}

    for key in {settings.MESH_CHAT_MODEL, settings.MESH_CHEAP_MODEL}:
        m = models.get(key)
        if m is None:
            raise ConfigError(f"{key} is not in the Mesh registry")
        if not getattr(m, "supports_structured_output", True):
            raise ConfigError(f"{key} will not enforce response_format")

    emb = models.get(settings.MESH_EMBED_MODEL)
    if emb is None:
        raise ConfigError(f"{settings.MESH_EMBED_MODEL} is not in the Mesh registry")
    if not getattr(emb, "supports_embeddings", True):
        raise ConfigError(f"{settings.MESH_EMBED_MODEL} cannot produce embeddings")

    class _Probe(BaseModel):
        model_config = ConfigDict(extra="forbid")

        ok: bool
        echo: str

    for key in {settings.MESH_CHAT_MODEL, settings.MESH_CHEAP_MODEL}:
        await complete_json(
            model=key,
            system="Reply with ok=true and echo the word 'ping'.",
            user="ping",
            schema=_Probe,
            max_tokens=50,
        )
    logger.info("mesh_capability_check_passed", chat=settings.MESH_CHAT_MODEL, embed=settings.MESH_EMBED_MODEL)
