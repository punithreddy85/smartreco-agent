"""Shared Jinja2Templates instance for every route module that renders HTML."""

from pathlib import Path

from fastapi.templating import Jinja2Templates

TEMPLATES_DIR = Path(__file__).parent / "templates"
STATIC_DIR = Path(__file__).parent / "static"

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# Rows from psycopg come back with native uuid.UUID (and datetime) values, which
# the stdlib `json` module used by Jinja's `tojson` filter can't serialize.
# Falling back to `str()` lets `{{ some_uuid | tojson }}` in templates just work.
templates.env.policies["json.dumps_kwargs"] = {"default": str}
