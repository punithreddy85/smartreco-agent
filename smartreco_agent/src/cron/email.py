"""Digest email composition + delivery via Resend.

Composed from the same recommendation record the site renders, so the digest
and the on-site panel can never disagree (ARCHITECTURE.md \u00a710)."""

from __future__ import annotations

import resend

from smartreco_agent.src.settings import settings
from smartreco_agent.utils.pylogger import get_python_logger

logger = get_python_logger(settings.PYTHON_LOG_LEVEL)


def _render_html(email: str, narrative: str, items: list[dict]) -> str:
    item_html = "".join(
        f"<li><strong>{item['title']}</strong> "
        f"(${item['price_cents'] / 100:.2f}, {item['level']}) &mdash; {item['reason']}</li>"
        for item in items
    )
    return f"""
    <div style="font-family: -apple-system, Helvetica, Arial, sans-serif; max-width: 560px; margin: 0 auto;">
      <h2 style="color:#1a1a2e;">Your SmartReco digest</h2>
      <p>{narrative}</p>
      <ul>{item_html}</ul>
      <p style="color:#888; font-size: 12px;">
        Sent to {email} based on today's activity on SmartReco.
        <a href="{settings.APP_BASE_URL}/recommendations">View on the site</a>.
      </p>
    </div>
    """


async def send_digest_email(*, to_email: str, narrative: str, items: list[dict]) -> bool:
    if not settings.RESEND_API_KEY:
        logger.warning("resend_not_configured_skipping_email", to_email=to_email)
        return False

    resend.api_key = settings.RESEND_API_KEY
    try:
        resend.Emails.send(
            {
                "from": settings.RESEND_FROM_EMAIL,
                "to": [to_email],
                "subject": "Your SmartReco recommendations for today",
                "html": _render_html(to_email, narrative, items),
            }
        )
        return True
    except Exception as e:  # noqa: BLE001 - email delivery must never break the worker loop
        logger.error("digest_email_failed", to_email=to_email, error=str(e))
        return False
