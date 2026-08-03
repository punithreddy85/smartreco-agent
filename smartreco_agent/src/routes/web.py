"""Server-rendered pages: catalog, product detail, recommendations panel."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, Request
from fastapi.responses import RedirectResponse

from smartreco_agent.src.agent.graph import run_agent
from smartreco_agent.src.auth.dependencies import (
    CurrentUser,
    get_current_user,
    require_user,
)
from smartreco_agent.src.db import catalog
from smartreco_agent.src.tracking.gate import should_generate
from smartreco_agent.src.web.templating import templates

router = APIRouter()


@router.get("/")
async def index(user: Optional[CurrentUser] = Depends(get_current_user)):
    return RedirectResponse(url="/catalog" if user else "/login")


@router.get("/catalog")
async def catalog_page(
    request: Request,
    q: Optional[str] = None,
    category: Optional[str] = None,
    user: CurrentUser = Depends(require_user),
):
    products = await catalog.list_products(active_only=True, category=category)
    if q:
        needle = q.lower()
        products = [
            p for p in products
            if needle in p["title"].lower() or needle in p["description"].lower()
        ]
    categories = sorted({p["category"] for p in await catalog.list_products(active_only=True)})
    return templates.TemplateResponse(
        request, "catalog.html",
        {"products": products, "categories": categories, "q": q or "", "active_category": category or ""},
    )


@router.get("/products/{product_id}")
async def product_detail(request: Request, product_id: str, user: CurrentUser = Depends(require_user)):
    product = await catalog.get_product(product_id)
    if not product:
        return RedirectResponse(url="/catalog")
    already_added = await catalog.has_added_to_cart(user.id, product_id)
    return templates.TemplateResponse(
        request, "product.html", {"product": product, "already_added": already_added}
    )


@router.get("/recommendations")
async def recommendations_page(request: Request, user: CurrentUser = Depends(require_user)):
    rec = await catalog.get_current_recommendation(user.id)
    return templates.TemplateResponse(request, "recommendations.html", {"rec": rec})


@router.post("/recommendations/refresh")
async def refresh_recommendations(
    background_tasks: BackgroundTasks, user: CurrentUser = Depends(require_user)
):
    """Enqueues a manual regeneration. Never calls Mesh inline - the cooldown
    still applies even to an explicit refresh (ARCHITECTURE.md \u00a78)."""

    async def _run():
        reason = await should_generate(user.id, force=True)
        if reason:
            await run_agent(user.id, trigger_reason=reason)

    background_tasks.add_task(_run)
    return RedirectResponse(url="/recommendations?refreshing=1", status_code=303)
