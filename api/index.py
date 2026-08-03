"""Vercel entrypoint. Vercel's Python runtime discovers an ASGI `app` object in
`api/*.py` and wraps it as a serverless function; every request is routed here
by the catch-all rewrite in `vercel.json` (ARCHITECTURE.md \u00a712.1).

Nothing else belongs in this file - the entire application lives in
`smartreco_agent/`, so local Docker and Vercel run identical code.
"""

from smartreco_agent.src.api import app

__all__ = ["app"]
