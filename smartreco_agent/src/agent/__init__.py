"""The LangGraph recommendation agent.

Graph: load_signals -> analyze_intent -> retrieve -> grade -> [refine ->]
rerank -> generate_and_verify -> persist (ARCHITECTURE.md \u00a79.1). Runs only
when `tracking.gate.should_generate` returns a reason - never inline in a
request a user is waiting on.
"""
