"""Admin: product CRUD with the transactional dual-write, plus a minimal
observability page over `agent_runs` (ARCHITECTURE.md \u00a71.2, \u00a711).

Every route here is gated by `require_admin`, checked server-side on every
request - hiding a nav link is not access control (\u00a713)."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, Form, Request
from fastapi.responses import RedirectResponse

from smartreco_agent.src.auth.dependencies import CurrentUser, require_admin
from smartreco_agent.src.cron.outbox_drainer import drain_outbox
from smartreco_agent.src.cron.reconcile import reconcile
from smartreco_agent.src.db import catalog, outbox
from smartreco_agent.src.db.pool import transaction
from smartreco_agent.src.web.templating import templates

router = APIRouter(prefix="/admin")


@router.get("/")
async def admin_home(admin: CurrentUser = Depends(require_admin)):
    return RedirectResponse(url="/admin/products")


@router.get("/products")
async def list_products(request: Request, admin: CurrentUser = Depends(require_admin)):
    products = await catalog.list_products(active_only=False)
    return templates.TemplateResponse(
        request, "admin/products.html", {"products": products}
    )


@router.get("/products/new")
async def new_product_form(
    request: Request, admin: CurrentUser = Depends(require_admin)
):
    return templates.TemplateResponse(
        request, "admin/product_form.html", {"product": None, "error": None}
    )


@router.post("/products/new")
async def create_product(
    request: Request,
    background_tasks: BackgroundTasks,
    admin: CurrentUser = Depends(require_admin),
    title: str = Form(...),
    description: str = Form(...),
    category: str = Form(...),
    level: str = Form(...),
    price_cents: int = Form(...),
    tags: str = Form(""),
    is_active: Optional[str] = Form(None),
    learning_outcomes: str = Form(""),
    duration_minutes: Optional[int] = Form(None),
    module_count: Optional[int] = Form(None),
):
    tag_list = [t.strip() for t in tags.split(",") if t.strip()]
    outcome_list = [line.strip() for line in learning_outcomes.splitlines() if line.strip()]
    async with transaction() as conn:
        product = await catalog.upsert_product(
            product_id=None,
            title=title,
            description=description,
            category=category,
            level=level,
            price_cents=price_cents,
            tags=tag_list,
            is_active=is_active is not None,
            learning_outcomes=outcome_list,
            duration_minutes=duration_minutes,
            module_count=module_count,
            conn=conn,
        )
        await outbox.enqueue(product["id"], op="upsert", conn=conn)

    background_tasks.add_task(drain_outbox)
    return RedirectResponse(url="/admin/products", status_code=303)


@router.get("/products/{product_id}/edit")
async def edit_product_form(
    request: Request, product_id: str, admin: CurrentUser = Depends(require_admin)
):
    product = await catalog.get_product(product_id)
    return templates.TemplateResponse(
        request, "admin/product_form.html", {"product": product, "error": None}
    )


@router.post("/products/{product_id}/edit")
async def update_product(
    request: Request,
    product_id: str,
    background_tasks: BackgroundTasks,
    admin: CurrentUser = Depends(require_admin),
    title: str = Form(...),
    description: str = Form(...),
    category: str = Form(...),
    level: str = Form(...),
    price_cents: int = Form(...),
    tags: str = Form(""),
    is_active: Optional[str] = Form(None),
    learning_outcomes: str = Form(""),
    duration_minutes: Optional[int] = Form(None),
    module_count: Optional[int] = Form(None),
):
    tag_list = [t.strip() for t in tags.split(",") if t.strip()]
    outcome_list = [line.strip() for line in learning_outcomes.splitlines() if line.strip()]
    async with transaction() as conn:
        product = await catalog.upsert_product(
            product_id=product_id,
            title=title,
            description=description,
            category=category,
            level=level,
            price_cents=price_cents,
            tags=tag_list,
            is_active=is_active is not None,
            learning_outcomes=outcome_list,
            duration_minutes=duration_minutes,
            module_count=module_count,
            conn=conn,
        )
        await outbox.enqueue(product["id"], op="upsert", conn=conn)

    background_tasks.add_task(drain_outbox)
    return RedirectResponse(url="/admin/products", status_code=303)


@router.post("/products/{product_id}/delete")
async def remove_product(
    product_id: str,
    background_tasks: BackgroundTasks,
    admin: CurrentUser = Depends(require_admin),
):
    async with transaction() as conn:
        await outbox.enqueue(product_id, op="delete", conn=conn)
        await catalog.delete_product(product_id, conn=conn)

    background_tasks.add_task(drain_outbox)
    return RedirectResponse(url="/admin/products", status_code=303)


@router.get("/observability")
async def observability(request: Request, admin: CurrentUser = Depends(require_admin)):
    runs = await catalog.recent_agent_runs(limit=50)
    total = len(runs)
    generations = sum(1 for r in runs if not r["cache_hit"] and not r["error"])
    cache_hits = sum(1 for r in runs if r["cache_hit"])
    errors = sum(1 for r in runs if r["error"])
    total_prompt_tokens = sum(r["prompt_tokens"] or 0 for r in runs)
    total_completion_tokens = sum(r["completion_tokens"] or 0 for r in runs)
    return templates.TemplateResponse(
        request,
        "admin/observability.html",
        {
            "runs": runs,
            "total": total,
            "generations": generations,
            "cache_hits": cache_hits,
            "errors": errors,
            "total_prompt_tokens": total_prompt_tokens,
            "total_completion_tokens": total_completion_tokens,
        },
    )


@router.post("/reconcile")
async def run_reconcile_now(admin: CurrentUser = Depends(require_admin)):
    report = await reconcile()
    await drain_outbox(limit=200)
    return RedirectResponse(
        url=f"/admin/observability?missing={report.missing}&stale={report.stale}&orphans={report.orphans}",
        status_code=303,
    )
