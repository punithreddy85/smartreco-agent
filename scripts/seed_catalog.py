"""Seeds the catalog with courses across categories that deliberately overlap
semantically (e.g. "Agentic AI" and "LLM Engineering" share vocabulary), so
retrieval and reranking have something real to discriminate between
(ARCHITECTURE.md §16). Also creates one admin and one demo user.

Idempotent: re-running skips products/users that already exist by title/email.

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

ADMIN_EMAIL = "admin@smartreco.dev"
ADMIN_PASSWORD = "adminpass123"
DEMO_EMAIL = "demo@smartreco.dev"
DEMO_PASSWORD = "demopass123"

# 8 categories, deliberately overlapping in vocabulary (agentic AI <-> LLM
# engineering <-> data engineering) so the retrieval/rerank story is real.
CATALOG: dict[str, list[tuple[str, str, str, list[str]]]] = {
    "Agentic AI": [
        (
            "Agentic AI Foundations",
            "beginner",
            "Learn what makes an AI system 'agentic': planning, tool use, and memory. "
            "Build your first LangGraph-style agent that reasons over a task and calls tools.",
            ["langgraph", "agents", "llm"],
        ),
        (
            "Building Multi-Agent Systems",
            "intermediate",
            "Design agent teams that collaborate: a planner, a retriever, and a critic working "
            "together on complex tasks. Covers state machines and message passing between agents.",
            ["multi-agent", "langgraph", "orchestration"],
        ),
        (
            "Advanced Agentic Workflows with LangGraph",
            "advanced",
            "Deep dive into conditional graphs, human-in-the-loop checkpoints, and self-correcting "
            "agents that grade their own retrieval quality before generating a final answer.",
            ["langgraph", "agents", "rag"],
        ),
        (
            "Tool-Calling and Function Execution for Agents",
            "intermediate",
            "Give your agents real capabilities: structured tool schemas, safe execution sandboxes, "
            "and retry strategies when a tool call fails or returns malformed output.",
            ["agents", "tool-use", "llm"],
        ),
        (
            "Agent Observability and Evaluation",
            "advanced",
            "Instrument agentic pipelines end-to-end: tracing, token accounting, and building an "
            "eval harness that catches regressions before they reach production.",
            ["agents", "observability", "evals"],
        ),
        (
            "Autonomous Research Agents",
            "advanced",
            "Build an agent that plans a multi-step research task, retrieves sources, and "
            "synthesizes a cited report - the same pattern behind deep-research products.",
            ["agents", "rag", "research"],
        ),
    ],
    "LLM Engineering": [
        (
            "Prompt Engineering for Production Systems",
            "beginner",
            "Move beyond ad-hoc prompting: structured outputs, few-shot design, and prompts that "
            "stay reliable across model upgrades.",
            ["llm", "prompting"],
        ),
        (
            "Fine-Tuning Open-Source LLMs",
            "advanced",
            "Fine-tune a small open-weight model on domain data using LoRA, then evaluate it "
            "against the base model on your own benchmark.",
            ["llm", "fine-tuning"],
        ),
        (
            "Structured Output and JSON-Schema Constrained Generation",
            "intermediate",
            "Force an LLM to always return valid, schema-conformant JSON - the backbone of any "
            "agent node that hands its output to code instead of a human.",
            ["llm", "structured-output"],
        ),
        (
            "LLM Cost and Latency Optimization",
            "intermediate",
            "Cut LLM spend without hurting quality: caching, model routing, batching, and "
            "choosing cheap models for cheap sub-tasks.",
            ["llm", "cost-optimization"],
        ),
        (
            "Building an LLM Gateway",
            "advanced",
            "Build a provider-agnostic gateway (the same idea behind Mesh API) that fronts "
            "multiple model providers behind one OpenAI-compatible interface.",
            ["llm", "gateway", "infrastructure"],
        ),
        (
            "Evaluating LLM Outputs at Scale",
            "intermediate",
            "Automated eval pipelines: LLM-as-judge, golden datasets, and regression testing for "
            "non-deterministic systems.",
            ["llm", "evals"],
        ),
    ],
    "RAG & Retrieval": [
        (
            "Retrieval-Augmented Generation from Scratch",
            "beginner",
            "Build a RAG pipeline end-to-end: chunking, embeddings, a vector store, and grounding "
            "an LLM's answer in retrieved passages so it stops making things up.",
            ["rag", "embeddings", "vector-db"],
        ),
        (
            "Vector Databases in Depth",
            "intermediate",
            "Compare HNSW, IVF, and exact search; tune index parameters for recall vs. latency; "
            "and design a schema that supports metadata filtering at scale.",
            ["vector-db", "rag", "pgvector"],
        ),
        (
            "Advanced Retrieval: Reranking and Query Expansion",
            "advanced",
            "Go beyond top-k cosine similarity: cross-encoder reranking, maximal marginal "
            "relevance for diversity, and multi-query retrieval for ambiguous questions.",
            ["rag", "reranking", "mmr"],
        ),
        (
            "Hybrid Search: Combining Keyword and Semantic Retrieval",
            "intermediate",
            "Blend BM25 keyword search with dense vector search using score fusion, and know "
            "when each one wins.",
            ["rag", "hybrid-search"],
        ),
        (
            "Grounding and Hallucination Prevention",
            "advanced",
            "Techniques to guarantee an LLM only cites real, retrieved content - the same "
            "grounding guarantee a production recommendation agent needs.",
            ["rag", "grounding"],
        ),
    ],
    "Data Engineering": [
        (
            "Data Engineering Fundamentals",
            "beginner",
            "ETL vs. ELT, batch vs. streaming, and how to design a data pipeline that survives "
            "contact with messy real-world data.",
            ["data-engineering", "etl"],
        ),
        (
            "Building Data Pipelines with Airflow",
            "intermediate",
            "Orchestrate multi-step pipelines with DAGs, retries, and SLAs using Apache Airflow.",
            ["airflow", "data-engineering", "orchestration"],
        ),
        (
            "Streaming Data with Kafka",
            "advanced",
            "Design event-driven pipelines with Kafka: partitioning, exactly-once semantics, and "
            "consumer group scaling.",
            ["kafka", "streaming", "data-engineering"],
        ),
        (
            "Data Modeling for Analytics Warehouses",
            "intermediate",
            "Star schemas, slowly changing dimensions, and modeling patterns that keep a "
            "warehouse fast as it grows.",
            ["data-modeling", "warehouse"],
        ),
        (
            "The Transactional Outbox Pattern",
            "advanced",
            "Keep two data stores in sync reliably - the exact pattern this platform uses to keep "
            "its SQL catalog and vector store consistent.",
            ["data-engineering", "outbox", "distributed-systems"],
        ),
    ],
    "Machine Learning": [
        (
            "Machine Learning Foundations",
            "beginner",
            "Supervised vs. unsupervised learning, train/test splits, and the bias-variance "
            "tradeoff, taught through hands-on scikit-learn exercises.",
            ["machine-learning", "python"],
        ),
        (
            "Deep Learning with PyTorch",
            "intermediate",
            "Build and train neural networks from scratch in PyTorch: backprop, optimizers, and "
            "regularization.",
            ["deep-learning", "pytorch"],
        ),
        (
            "Recommendation Systems in Practice",
            "advanced",
            "Collaborative filtering, matrix factorization, and the behavioral-signal-driven "
            "recommendation architecture used by real product platforms.",
            ["recommendation-systems", "machine-learning"],
        ),
        (
            "Feature Engineering for Tabular Data",
            "intermediate",
            "Turn raw events and logs into model-ready features, including decayed time-series "
            "features similar to an interest-decay model.",
            ["feature-engineering", "machine-learning"],
        ),
        (
            "MLOps: Deploying Models to Production",
            "advanced",
            "Model registries, canary rollouts, and monitoring for drift once a model is live.",
            ["mlops", "deployment"],
        ),
    ],
    "Cloud & DevOps": [
        (
            "Cloud Fundamentals: AWS, GCP, and Azure",
            "beginner",
            "Core cloud concepts - compute, storage, networking - taught across all three major "
            "providers so you can read any cloud's docs afterward.",
            ["cloud", "aws", "gcp"],
        ),
        (
            "Container Orchestration with Kubernetes",
            "intermediate",
            "Deployments, services, and autoscaling for containerized workloads on Kubernetes.",
            ["kubernetes", "containers", "devops"],
        ),
        (
            "CI/CD Pipelines That Don't Break",
            "intermediate",
            "Design pipelines with fast feedback loops, proper caching, and deployment gates that "
            "catch regressions before production.",
            ["cicd", "devops"],
        ),
        (
            "Serverless Architecture Patterns",
            "advanced",
            "Design for cold starts, connection pooling, and stateless functions - the same "
            "constraints a serverless-deployed agent backend has to handle.",
            ["serverless", "cloud-architecture"],
        ),
        (
            "Infrastructure as Code with Terraform",
            "intermediate",
            "Manage cloud infrastructure declaratively, with state management and module reuse.",
            ["terraform", "iac", "devops"],
        ),
    ],
    "Product & Design": [
        (
            "Product Management Foundations",
            "beginner",
            "Discovery, prioritization frameworks, and writing requirements that engineers can "
            "actually build from.",
            ["product-management"],
        ),
        (
            "UX Research Methods",
            "intermediate",
            "Run usability tests, synthesize findings, and turn qualitative signal into design "
            "decisions.",
            ["ux", "research"],
        ),
        (
            "Designing Persuasive User Experiences",
            "intermediate",
            "The ethics and mechanics of persuasive design - directly relevant to writing "
            "recommendation copy that motivates without manipulating.",
            ["ux", "persuasion", "design"],
        ),
        (
            "Data-Informed Product Decisions",
            "advanced",
            "Instrument a product with meaningful behavioral events and turn that data into "
            "decisions - the tracking half of this very platform.",
            ["product-management", "analytics"],
        ),
    ],
    "Security": [
        (
            "Application Security Fundamentals",
            "beginner",
            "OWASP Top 10, secure authentication patterns, and how to think like an attacker "
            "before you ship a feature.",
            ["security", "appsec"],
        ),
        (
            "Securing LLM and Agent Applications",
            "advanced",
            "Prompt injection, tool-call sandboxing, and grounding as a security boundary, not "
            "just a quality feature.",
            ["security", "llm", "agents"],
        ),
        (
            "Cloud Security Best Practices",
            "intermediate",
            "IAM least-privilege, secrets management, and network segmentation in cloud "
            "environments.",
            ["security", "cloud"],
        ),
    ],
}


def _price_for(level: str) -> int:
    return {"beginner": 4900, "intermediate": 8900, "advanced": 14900}[level]


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


async def _existing_titles() -> set[str]:
    async with get_connection() as conn, conn.cursor() as cur:
        await cur.execute("select title from catalog.products")
        return {r["title"] for r in await cur.fetchall()}


async def _seed_products() -> int:
    existing = await _existing_titles()
    created = 0

    for category, courses in CATALOG.items():
        for title, level, description, tags in courses:
            if title in existing:
                continue
            async with transaction() as conn:
                product = await catalog.upsert_product(
                    product_id=None,
                    title=title,
                    description=description,
                    category=category,
                    level=level,
                    price_cents=_price_for(level),
                    tags=tags,
                    is_active=True,
                    conn=conn,
                )
                await outbox.enqueue(product["id"], op="upsert", conn=conn)
            created += 1

    return created


async def main() -> None:
    await open_pool()
    try:
        await _seed_users()
        created = await _seed_products()
        print(f"created {created} new products")

        if created:
            print("embedding new products into the vector store...")
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
