"""Seeds the catalog with courses across categories that deliberately overlap
semantically (e.g. "Agentic AI" and "LLM Engineering" share vocabulary), so
retrieval and reranking have something real to discriminate between
(ARCHITECTURE.md §16). Also creates one admin and one demo user.

Idempotent: re-running upserts every product by title (backfilling new
columns on existing rows) and skips creating users that already exist.

Usage (from the app container or a host venv with DATABASE_URL configured):
    python scripts/seed_catalog.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from smartreco_agent.src.auth.security import hash_password  # noqa: E402
from smartreco_agent.src.cron.outbox_drainer import drain_outbox  # noqa: E402
from smartreco_agent.src.db import catalog, outbox  # noqa: E402
from smartreco_agent.src.db.pool import (  # noqa: E402
    close_pool,
    get_connection,
    open_pool,
    transaction,
)
from smartreco_agent.src.settings import settings  # noqa: E402

# Read from env (see .env.example / settings.py) rather than hard-coding: this
# script is committed to a public repo, so the seeded admin/demo credentials
# must be overridable before seeding a publicly reachable (e.g. deployed)
# database. The defaults below are only safe for local/Docker Compose use.
ADMIN_EMAIL = settings.SEED_ADMIN_EMAIL
ADMIN_PASSWORD = settings.SEED_ADMIN_PASSWORD
DEMO_EMAIL = settings.SEED_DEMO_EMAIL
DEMO_PASSWORD = settings.SEED_DEMO_PASSWORD

_USING_DEFAULT_CREDS = (
    ADMIN_PASSWORD == "adminpass123" or DEMO_PASSWORD == "demopass123"
)

# 8 categories, deliberately overlapping in vocabulary (agentic AI <-> LLM
# engineering <-> data engineering) so the retrieval/rerank story is real.
#
# Each course is (title, level, description, tags, learning_outcomes) - the
# last is "What you'll learn" on the product detail page (BUGFIX.md P2.4),
# also folded into the embedded text so it improves retrieval, not just layout.
CATALOG: dict[str, list[tuple[str, str, str, list[str], list[str]]]] = {
    "Agentic AI": [
        (
            "Agentic AI Foundations",
            "beginner",
            "Learn what makes an AI system 'agentic': planning, tool use, and memory. "
            "Build your first LangGraph-style agent that reasons over a task and calls tools.",
            ["langgraph", "agents", "llm"],
            [
                "Explain what separates an agentic system from a plain LLM call: planning, tool use, and memory.",
                "Build a first LangGraph-style agent that reasons over a task before acting.",
                "Wire a tool into an agent and have it decide when to call it.",
            ],
        ),
        (
            "Building Multi-Agent Systems",
            "intermediate",
            "Design agent teams that collaborate: a planner, a retriever, and a critic working "
            "together on complex tasks. Covers state machines and message passing between agents.",
            ["multi-agent", "langgraph", "orchestration"],
            [
                "Design a planner/retriever/critic team that collaborates on a single task.",
                "Model agent coordination as a state machine instead of ad-hoc control flow.",
                "Pass messages between agents without losing context across hops.",
            ],
        ),
        (
            "Advanced Agentic Workflows with LangGraph",
            "advanced",
            "Deep dive into conditional graphs, human-in-the-loop checkpoints, and self-correcting "
            "agents that grade their own retrieval quality before generating a final answer.",
            ["langgraph", "agents", "rag"],
            [
                "Build conditional graphs that branch based on an agent's own intermediate output.",
                "Add human-in-the-loop checkpoints to a running graph.",
                "Have an agent grade its own retrieval quality before it answers.",
            ],
        ),
        (
            "Tool-Calling and Function Execution for Agents",
            "intermediate",
            "Give your agents real capabilities: structured tool schemas, safe execution sandboxes, "
            "and retry strategies when a tool call fails or returns malformed output.",
            ["agents", "tool-use", "llm"],
            [
                "Design structured tool schemas an LLM can call reliably.",
                "Sandbox tool execution so a bad call can't damage production systems.",
                "Handle a failed or malformed tool call with a retry strategy.",
            ],
        ),
        (
            "Agent Observability and Evaluation",
            "advanced",
            "Instrument agentic pipelines end-to-end: tracing, token accounting, and building an "
            "eval harness that catches regressions before they reach production.",
            ["agents", "observability", "evals"],
            [
                "Instrument an agentic pipeline end-to-end with tracing.",
                "Track token spend per node so cost regressions are visible.",
                "Build an eval harness that catches quality regressions before production.",
            ],
        ),
        (
            "Autonomous Research Agents",
            "advanced",
            "Build an agent that plans a multi-step research task, retrieves sources, and "
            "synthesizes a cited report - the same pattern behind deep-research products.",
            ["agents", "rag", "research"],
            [
                "Plan a multi-step research task the way a deep-research product does.",
                "Retrieve and cite sources instead of asserting facts from memory.",
                "Synthesize a structured, cited report from many retrieved documents.",
            ],
        ),
    ],
    "LLM Engineering": [
        (
            "Prompt Engineering for Production Systems",
            "beginner",
            "Move beyond ad-hoc prompting: structured outputs, few-shot design, and prompts that "
            "stay reliable across model upgrades.",
            ["llm", "prompting"],
            [
                "Move from ad-hoc prompting to structured, versioned prompts.",
                "Design few-shot examples that generalize instead of overfitting.",
                "Write prompts that stay reliable across a model upgrade.",
            ],
        ),
        (
            "Fine-Tuning Open-Source LLMs",
            "advanced",
            "Fine-tune a small open-weight model on domain data using LoRA, then evaluate it "
            "against the base model on your own benchmark.",
            ["llm", "fine-tuning"],
            [
                "Fine-tune an open-weight model on domain data with LoRA.",
                "Build a benchmark that fairly compares a fine-tune against its base model.",
                "Decide when fine-tuning beats prompting or RAG for a given task.",
            ],
        ),
        (
            "Structured Output and JSON-Schema Constrained Generation",
            "intermediate",
            "Force an LLM to always return valid, schema-conformant JSON - the backbone of any "
            "agent node that hands its output to code instead of a human.",
            ["llm", "structured-output"],
            [
                "Force an LLM to return schema-conformant JSON on every call.",
                "Design a schema an agent node can hand straight to code, no parsing hacks.",
                "Handle schema-violation failures without breaking a downstream pipeline.",
            ],
        ),
        (
            "LLM Cost and Latency Optimization",
            "intermediate",
            "Cut LLM spend without hurting quality: caching, model routing, batching, and "
            "choosing cheap models for cheap sub-tasks.",
            ["llm", "cost-optimization"],
            [
                "Cut LLM spend with caching and prompt/response reuse.",
                "Route requests to a cheaper model for cheap sub-tasks.",
                "Batch calls to cut latency without hurting output quality.",
            ],
        ),
        (
            "Building an LLM Gateway",
            "advanced",
            "Build a provider-agnostic gateway (the same idea behind Mesh API) that fronts "
            "multiple model providers behind one OpenAI-compatible interface.",
            ["llm", "gateway", "infrastructure"],
            [
                "Build a provider-agnostic gateway that fronts multiple LLM vendors.",
                "Expose one OpenAI-compatible interface regardless of the backing model.",
                "Add failover and rate-limit handling across providers.",
            ],
        ),
        (
            "Evaluating LLM Outputs at Scale",
            "intermediate",
            "Automated eval pipelines: LLM-as-judge, golden datasets, and regression testing for "
            "non-deterministic systems.",
            ["llm", "evals"],
            [
                "Build an LLM-as-judge pipeline for non-deterministic outputs.",
                "Curate a golden dataset that catches real regressions, not noise.",
                "Run regression tests on every prompt or model change.",
            ],
        ),
    ],
    "RAG & Retrieval": [
        (
            "Retrieval-Augmented Generation from Scratch",
            "beginner",
            "Build a RAG pipeline end-to-end: chunking, embeddings, a vector store, and grounding "
            "an LLM's answer in retrieved passages so it stops making things up.",
            ["rag", "embeddings", "vector-db"],
            [
                "Chunk documents and embed them for retrieval.",
                "Stand up a vector store and query it end-to-end.",
                "Ground an LLM's answer in retrieved passages instead of memory.",
            ],
        ),
        (
            "Vector Databases in Depth",
            "intermediate",
            "Compare HNSW, IVF, and exact search; tune index parameters for recall vs. latency; "
            "and design a schema that supports metadata filtering at scale.",
            ["vector-db", "rag", "pgvector"],
            [
                "Compare HNSW, IVF, and exact search for a given recall/latency budget.",
                "Tune index parameters instead of accepting defaults.",
                "Design a schema that supports metadata filtering at scale.",
            ],
        ),
        (
            "Advanced Retrieval: Reranking and Query Expansion",
            "advanced",
            "Go beyond top-k cosine similarity: cross-encoder reranking, maximal marginal "
            "relevance for diversity, and multi-query retrieval for ambiguous questions.",
            ["rag", "reranking", "mmr"],
            [
                "Add cross-encoder reranking on top of vector similarity.",
                "Use maximal marginal relevance to diversify retrieved results.",
                "Expand an ambiguous query into multiple retrieval queries.",
            ],
        ),
        (
            "Hybrid Search: Combining Keyword and Semantic Retrieval",
            "intermediate",
            "Blend BM25 keyword search with dense vector search using score fusion, and know "
            "when each one wins.",
            ["rag", "hybrid-search"],
            [
                "Blend BM25 keyword search with dense vector search.",
                "Fuse two ranked result sets into one score.",
                "Know which query types favor keyword search over semantic search.",
            ],
        ),
        (
            "Grounding and Hallucination Prevention",
            "advanced",
            "Techniques to guarantee an LLM only cites real, retrieved content - the same "
            "grounding guarantee a production recommendation agent needs.",
            ["rag", "grounding"],
            [
                "Guarantee an LLM only cites content that was actually retrieved.",
                "Detect when a generated claim isn't supported by any source.",
                "Design grounding as a security boundary, not just a quality nicety.",
            ],
        ),
    ],
    "Data Engineering": [
        (
            "Data Engineering Fundamentals",
            "beginner",
            "ETL vs. ELT, batch vs. streaming, and how to design a data pipeline that survives "
            "contact with messy real-world data.",
            ["data-engineering", "etl"],
            [
                "Compare ETL and ELT and know when to reach for each.",
                "Design a pipeline that survives messy, real-world data.",
                "Choose between batch and streaming for a given workload.",
            ],
        ),
        (
            "Building Data Pipelines with Airflow",
            "intermediate",
            "Orchestrate multi-step pipelines with DAGs, retries, and SLAs using Apache Airflow.",
            ["airflow", "data-engineering", "orchestration"],
            [
                "Model a multi-step pipeline as a DAG.",
                "Add retries and SLAs so failures don't go unnoticed.",
                "Orchestrate dependent tasks across a schedule.",
            ],
        ),
        (
            "Streaming Data with Kafka",
            "advanced",
            "Design event-driven pipelines with Kafka: partitioning, exactly-once semantics, and "
            "consumer group scaling.",
            ["kafka", "streaming", "data-engineering"],
            [
                "Design an event-driven pipeline around Kafka topics.",
                "Partition data for throughput without breaking ordering guarantees.",
                "Implement exactly-once semantics across consumer groups.",
            ],
        ),
        (
            "Data Modeling for Analytics Warehouses",
            "intermediate",
            "Star schemas, slowly changing dimensions, and modeling patterns that keep a "
            "warehouse fast as it grows.",
            ["data-modeling", "warehouse"],
            [
                "Design a star schema for a real analytics workload.",
                "Model slowly changing dimensions correctly.",
                "Keep a warehouse fast as it grows, not just on day one.",
            ],
        ),
        (
            "The Transactional Outbox Pattern",
            "advanced",
            "Keep two data stores in sync reliably - the exact pattern this platform uses to keep "
            "its SQL catalog and vector store consistent.",
            ["data-engineering", "outbox", "distributed-systems"],
            [
                "Keep two data stores in sync without two-phase commit.",
                "Implement an outbox table and a drain process.",
                "Reason about at-least-once delivery and idempotent consumers.",
            ],
        ),
    ],
    "Machine Learning": [
        (
            "Machine Learning Foundations",
            "beginner",
            "Supervised vs. unsupervised learning, train/test splits, and the bias-variance "
            "tradeoff, taught through hands-on scikit-learn exercises.",
            ["machine-learning", "python"],
            [
                "Distinguish supervised from unsupervised learning with real examples.",
                "Build proper train/test splits that don't leak information.",
                "Reason about the bias-variance tradeoff when a model underperforms.",
            ],
        ),
        (
            "Deep Learning with PyTorch",
            "intermediate",
            "Build and train neural networks from scratch in PyTorch: backprop, optimizers, and "
            "regularization.",
            ["deep-learning", "pytorch"],
            [
                "Build a neural network from scratch in PyTorch.",
                "Implement backpropagation instead of treating it as a black box.",
                "Apply regularization to fix an overfitting model.",
            ],
        ),
        (
            "Recommendation Systems in Practice",
            "advanced",
            "Collaborative filtering, matrix factorization, and the behavioral-signal-driven "
            "recommendation architecture used by real product platforms.",
            ["recommendation-systems", "machine-learning"],
            [
                "Implement collaborative filtering and matrix factorization.",
                "Design a behavioral-signal-driven recommendation architecture.",
                "Evaluate a recommender with more than just accuracy.",
            ],
        ),
        (
            "Feature Engineering for Tabular Data",
            "intermediate",
            "Turn raw events and logs into model-ready features, including decayed time-series "
            "features similar to an interest-decay model.",
            ["feature-engineering", "machine-learning"],
            [
                "Turn raw events and logs into model-ready features.",
                "Build decayed time-series features, the same idea behind an interest-decay model.",
                "Avoid target leakage when engineering features from history.",
            ],
        ),
        (
            "MLOps: Deploying Models to Production",
            "advanced",
            "Model registries, canary rollouts, and monitoring for drift once a model is live.",
            ["mlops", "deployment"],
            [
                "Stand up a model registry with versioned artifacts.",
                "Ship a canary rollout instead of an all-at-once deploy.",
                "Monitor a live model for drift before it silently degrades.",
            ],
        ),
    ],
    "Cloud & DevOps": [
        (
            "Cloud Fundamentals: AWS, GCP, and Azure",
            "beginner",
            "Core cloud concepts - compute, storage, networking - taught across all three major "
            "providers so you can read any cloud's docs afterward.",
            ["cloud", "aws", "gcp"],
            [
                "Map core cloud concepts - compute, storage, networking - across three providers.",
                "Read any provider's docs after learning the shared vocabulary.",
                "Choose the right compute primitive for a given workload.",
            ],
        ),
        (
            "Container Orchestration with Kubernetes",
            "intermediate",
            "Deployments, services, and autoscaling for containerized workloads on Kubernetes.",
            ["kubernetes", "containers", "devops"],
            [
                "Deploy a containerized workload with Kubernetes Deployments and Services.",
                "Configure autoscaling for variable load.",
                "Debug a pod that won't schedule or won't come up healthy.",
            ],
        ),
        (
            "CI/CD Pipelines That Don't Break",
            "intermediate",
            "Design pipelines with fast feedback loops, proper caching, and deployment gates that "
            "catch regressions before production.",
            ["cicd", "devops"],
            [
                "Design a pipeline with a fast feedback loop.",
                "Cache dependencies without caching stale bugs.",
                "Add deployment gates that catch regressions before production.",
            ],
        ),
        (
            "Serverless Architecture Patterns",
            "advanced",
            "Design for cold starts, connection pooling, and stateless functions - the same "
            "constraints a serverless-deployed agent backend has to handle.",
            ["serverless", "cloud-architecture"],
            [
                "Design around cold starts instead of fighting them.",
                "Manage connection pooling for stateless functions.",
                "Apply the same constraints a serverless-deployed agent backend faces.",
            ],
        ),
        (
            "Infrastructure as Code with Terraform",
            "intermediate",
            "Manage cloud infrastructure declaratively, with state management and module reuse.",
            ["terraform", "iac", "devops"],
            [
                "Manage cloud infrastructure declaratively instead of by hand.",
                "Structure reusable modules instead of copy-pasted config.",
                "Manage Terraform state safely across a team.",
            ],
        ),
    ],
    "Product & Design": [
        (
            "Product Management Foundations",
            "beginner",
            "Discovery, prioritization frameworks, and writing requirements that engineers can "
            "actually build from.",
            ["product-management"],
            [
                "Run a discovery process before committing to a solution.",
                "Apply a prioritization framework to an actual backlog.",
                "Write requirements an engineer can build from without guessing.",
            ],
        ),
        (
            "UX Research Methods",
            "intermediate",
            "Run usability tests, synthesize findings, and turn qualitative signal into design "
            "decisions.",
            ["ux", "research"],
            [
                "Run a usability test that surfaces real friction, not opinions.",
                "Synthesize qualitative findings into an actionable pattern.",
                "Turn research signal into a concrete design decision.",
            ],
        ),
        (
            "Designing Persuasive User Experiences",
            "intermediate",
            "The ethics and mechanics of persuasive design - directly relevant to writing "
            "recommendation copy that motivates without manipulating.",
            ["ux", "persuasion", "design"],
            [
                "Apply the mechanics of persuasive design ethically.",
                "Write copy that motivates action without manipulating the user.",
                "Recognize the line between persuasion and a dark pattern.",
            ],
        ),
        (
            "Data-Informed Product Decisions",
            "advanced",
            "Instrument a product with meaningful behavioral events and turn that data into "
            "decisions - the tracking half of this very platform.",
            ["product-management", "analytics"],
            [
                "Instrument a product with behavioral events that matter.",
                "Turn raw event data into a product decision, not just a dashboard.",
                "Apply the tracking half of the architecture this platform runs on.",
            ],
        ),
    ],
    "Security": [
        (
            "Application Security Fundamentals",
            "beginner",
            "OWASP Top 10, secure authentication patterns, and how to think like an attacker "
            "before you ship a feature.",
            ["security", "appsec"],
            [
                "Recognize each OWASP Top 10 vulnerability in real code.",
                "Implement a secure authentication pattern end-to-end.",
                "Think like an attacker before a feature ships, not after.",
            ],
        ),
        (
            "Securing LLM and Agent Applications",
            "advanced",
            "Prompt injection, tool-call sandboxing, and grounding as a security boundary, not "
            "just a quality feature.",
            ["security", "llm", "agents"],
            [
                "Defend against prompt injection in an agentic pipeline.",
                "Sandbox tool calls so an agent can't take unsafe actions.",
                "Treat grounding as a security boundary, not just a quality feature.",
            ],
        ),
        (
            "Cloud Security Best Practices",
            "intermediate",
            "IAM least-privilege, secrets management, and network segmentation in cloud "
            "environments.",
            ["security", "cloud"],
            [
                "Apply least-privilege IAM instead of broad roles.",
                "Manage secrets without hard-coding them into config.",
                "Segment a cloud network to limit blast radius.",
            ],
        ),
    ],
}


def _price_for(level: str) -> int:
    return {"beginner": 4900, "intermediate": 8900, "advanced": 14900}[level]


def _shape_for(level: str) -> tuple[int, int]:
    """(duration_minutes, module_count) - deliberately correlated with level
    so a longer, more advanced course also looks more substantial."""
    return {
        "beginner": (240, 6),
        "intermediate": (360, 8),
        "advanced": (480, 10),
    }[level]


async def _seed_users() -> None:
    if not await catalog.get_user_by_email(ADMIN_EMAIL):
        await catalog.create_user(
            ADMIN_EMAIL, hash_password(ADMIN_PASSWORD), role="admin"
        )
        print(f"created admin user: {ADMIN_EMAIL} / {ADMIN_PASSWORD}")
    else:
        print(f"admin user already exists: {ADMIN_EMAIL}")

    if not await catalog.get_user_by_email(DEMO_EMAIL):
        await catalog.create_user(DEMO_EMAIL, hash_password(DEMO_PASSWORD), role="user")
        print(f"created demo user: {DEMO_EMAIL} / {DEMO_PASSWORD}")
    else:
        print(f"demo user already exists: {DEMO_EMAIL}")


async def _existing_product_ids_by_title() -> dict[str, str]:
    async with get_connection() as conn, conn.cursor() as cur:
        await cur.execute("select id, title from catalog.products")
        return {r["title"]: str(r["id"]) for r in await cur.fetchall()}


async def _seed_products() -> tuple[int, int]:
    """Upserts every product by title: inserts new ones, and backfills
    existing ones with any new columns (e.g. `learning_outcomes`) so a
    schema change never requires dropping and re-seeding the catalog."""
    existing_ids = await _existing_product_ids_by_title()
    created = 0
    updated = 0

    for category, courses in CATALOG.items():
        for title, level, description, tags, learning_outcomes in courses:
            duration_minutes, module_count = _shape_for(level)
            product_id = existing_ids.get(title)
            async with transaction() as conn:
                product = await catalog.upsert_product(
                    product_id=product_id,
                    title=title,
                    description=description,
                    category=category,
                    level=level,
                    price_cents=_price_for(level),
                    tags=tags,
                    is_active=True,
                    learning_outcomes=learning_outcomes,
                    duration_minutes=duration_minutes,
                    module_count=module_count,
                    conn=conn,
                )
                await outbox.enqueue(product["id"], op="upsert", conn=conn)
            if product_id is None:
                created += 1
            else:
                updated += 1

    return created, updated


async def main() -> None:
    if _USING_DEFAULT_CREDS and settings.use_transaction_pooler:
        print(
            "WARNING: seeding with the default admin/demo passwords against what "
            "looks like a remote (Supabase pooler) DATABASE_URL. These defaults are "
            "committed to a public repo - set SEED_ADMIN_PASSWORD / SEED_DEMO_PASSWORD "
            "in your .env before seeding a publicly reachable database.",
            file=sys.stderr,
        )

    await open_pool()
    try:
        await _seed_users()
        created, updated = await _seed_products()
        print(f"created {created} new products, updated {updated} existing products")

        print("embedding new/changed products into the vector store...")
        report = await drain_outbox(limit=200)
        print(
            f"embedded={report.embedded} skipped_unchanged={report.skipped_unchanged} "
            f"failed={report.failed}"
        )
        print("seed complete.")
    finally:
        await close_pool()


if __name__ == "__main__":
    asyncio.run(main())
