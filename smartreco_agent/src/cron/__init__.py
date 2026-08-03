"""Background/cron-triggered work: outbox drain, reconciliation, digest delivery.

Scheduled in production by `pg_cron` + `pg_net` (ARCHITECTURE.md \u00a710); every
routine here is also invokable as a plain authenticated HTTP endpoint
(`smartreco_agent/src/routes/cron.py`) so `docker compose` reviewers without
`pg_cron` can drive it manually via the Makefile.
"""
