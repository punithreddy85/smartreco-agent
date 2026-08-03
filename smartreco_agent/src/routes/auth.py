"""Registration, login, logout - classic HTML form posts, signed session cookie."""

from __future__ import annotations

from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse
from psycopg.errors import UniqueViolation

from smartreco_agent.src.auth.security import hash_password, verify_password
from smartreco_agent.src.auth.session import clear_session_cookie, set_session_cookie
from smartreco_agent.src.db import catalog
from smartreco_agent.src.settings import settings
from smartreco_agent.src.web.templating import templates
from smartreco_agent.utils.pylogger import get_python_logger

router = APIRouter()
logger = get_python_logger(settings.PYTHON_LOG_LEVEL)


@router.get("/register")
async def register_page(request: Request):
    return templates.TemplateResponse(request, "register.html", {"error": None})


@router.post("/register")
async def register_submit(
    request: Request, email: str = Form(...), password: str = Form(...)
):
    if len(password) < 8:
        return templates.TemplateResponse(
            request,
            "register.html",
            {"error": "Password must be at least 8 characters."},
        )
    try:
        user = await catalog.create_user(
            email=email, password_hash=hash_password(password)
        )
    except UniqueViolation:
        return templates.TemplateResponse(
            request,
            "register.html",
            {"error": "An account with that email already exists."},
        )
    except Exception as e:
        logger.error("registration_failed", error=str(e))
        return templates.TemplateResponse(
            request,
            "register.html",
            {"error": "Could not create account. Please try again."},
        )

    response = RedirectResponse(url="/", status_code=303)
    set_session_cookie(response, user_id=str(user["id"]), role=user["role"])
    return response


@router.get("/login")
async def login_page(request: Request):
    return templates.TemplateResponse(request, "login.html", {"error": None})


@router.post("/login")
async def login_submit(
    request: Request, email: str = Form(...), password: str = Form(...)
):
    user = await catalog.get_user_by_email(email)
    if not user or not verify_password(password, user["password_hash"]):
        return templates.TemplateResponse(
            request, "login.html", {"error": "Invalid email or password."}
        )

    response = RedirectResponse(url="/", status_code=303)
    set_session_cookie(response, user_id=str(user["id"]), role=user["role"])
    return response


@router.post("/logout")
async def logout(request: Request):
    response = RedirectResponse(url="/login", status_code=303)
    clear_session_cookie(response)
    return response
