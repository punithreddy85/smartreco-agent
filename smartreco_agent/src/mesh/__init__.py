"""Single owner of all Mesh API access (chat completions + embeddings).

Mesh is mandatory for every LLM/embedding call in this project. No other file
constructs an OpenAI client - see ARCHITECTURE.md Appendix D.
"""
