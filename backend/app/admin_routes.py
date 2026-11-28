from __future__ import annotations

import ipaddress
import os
from typing import Literal

from fastapi import APIRouter, Cookie, Header, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field

from app.services.admin_auth_service import (
    authenticate_admin, validate_admin_session, revoke_admin_session, record_admin_access,
)
from app.services.admin_observability_service import (
    admin_dashboard, admin_list_traces, admin_get_trace, admin_audit_logs,
)

router = APIRouter(prefix="/admin", tags=["admin-observability"])


class AdminLoginRequest(BaseModel):
    password: str = Field(min_length=1, max_length=256)


def _client_ip(request: Request) -> str:
    if request.client is None:
        return "unknown"
    try:
        return ipaddress.ip_address(request.client.host).compressed
    except ValueError:
        return "unknown"


def _require_admin(request: Request, token: str | None, csrf: str | None) -> None:
    if not validate_admin_session(token, csrf):
        record_admin_access("access_denied", _client_ip(request))
        raise HTTPException(status_code=401, detail="Admin authentication required.")


@router.post("/auth/login")
async def admin_login(payload: AdminLoginRequest, request: Request, response: Response) -> dict:
    result = authenticate_admin(payload.password, _client_ip(request))
    if result is None:
        raise HTTPException(status_code=401, detail="Invalid admin credentials or login temporarily limited.")
    response.set_cookie(
        key="admin_session",
        value=result["token"],
        httponly=True,
        secure=os.getenv("ADMIN_COOKIE_SECURE", "true").lower() in {"1", "true", "yes", "on"},
        samesite="lax",
        path="/",
        max_age=8 * 60 * 60,
    )
    return {"authenticated": True, "csrf_token": result["csrf_token"], "expires_at": result["expires_at"]}


@router.get("/auth/me")
async def admin_me(request: Request, admin_session: str | None = Cookie(default=None),
                   x_admin_csrf: str | None = Header(default=None)) -> dict:
    _require_admin(request, admin_session, x_admin_csrf)
    return {"authenticated": True}


@router.post("/auth/logout")
async def admin_logout(request: Request, response: Response,
                       admin_session: str | None = Cookie(default=None),
                       x_admin_csrf: str | None = Header(default=None)) -> dict:
    _require_admin(request, admin_session, x_admin_csrf)
    revoke_admin_session(admin_session, _client_ip(request))
    response.delete_cookie("admin_session", path="/", httponly=True,
                           secure=os.getenv("ADMIN_COOKIE_SECURE", "true").lower() in {"1", "true", "yes", "on"},
                           samesite="lax")
    return {"logged_out": True}


@router.get("/observability/dashboard")
async def dashboard(request: Request, days: int = Query(default=7, ge=1, le=90),
                    admin_session: str | None = Cookie(default=None),
                    x_admin_csrf: str | None = Header(default=None)) -> dict:
    _require_admin(request, admin_session, x_admin_csrf)
    record_admin_access("dashboard_viewed", _client_ip(request))
    return admin_dashboard(days)


@router.get("/observability/traces")
async def traces(request: Request, limit: int = Query(default=50, ge=1, le=100),
                 offset: int = Query(default=0, ge=0),
                 status: Literal["success", "no_answer", "error", "cancelled"] | None = None,
                 query: str | None = Query(default=None, max_length=100),
                 start_date: str | None = Query(default=None, max_length=30),
                 end_date: str | None = Query(default=None, max_length=30),
                 admin_session: str | None = Cookie(default=None),
                 x_admin_csrf: str | None = Header(default=None)) -> dict:
    _require_admin(request, admin_session, x_admin_csrf)
    record_admin_access("trace_list_viewed", _client_ip(request))
    return admin_list_traces(limit=limit, offset=offset, status=status, query=query,
                             start_date=start_date, end_date=end_date)


@router.get("/observability/traces/{trace_id}")
async def trace_detail(request: Request, trace_id: str,
                       admin_session: str | None = Cookie(default=None),
                       x_admin_csrf: str | None = Header(default=None)) -> dict:
    _require_admin(request, admin_session, x_admin_csrf)
    record_admin_access("trace_detail_viewed", _client_ip(request))
    trace = admin_get_trace(trace_id)
    if trace is None:
        raise HTTPException(status_code=404, detail="Trace not found.")
    return trace


@router.get("/observability/audit-logs")
async def audit_logs(request: Request, limit: int = Query(default=50, ge=1, le=100),
                     admin_session: str | None = Cookie(default=None),
                     x_admin_csrf: str | None = Header(default=None)) -> list[dict]:
    _require_admin(request, admin_session, x_admin_csrf)
    record_admin_access("audit_logs_viewed", _client_ip(request))
    return admin_audit_logs(limit)
