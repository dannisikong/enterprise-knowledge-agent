from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any

from app.services.observability_service import _connect, initialize_traces


def _since(days: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=max(1, min(days, 90)))).isoformat()


def admin_dashboard(days: int = 7) -> dict[str, Any]:
    initialize_traces()
    since = _since(days)
    with _connect() as connection:
        totals = connection.execute("""
            SELECT COUNT(*) AS total,
                   SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) AS success,
                   SUM(CASE WHEN status = 'error' THEN 1 ELSE 0 END) AS errors,
                   SUM(CASE WHEN status = 'no_answer' THEN 1 ELSE 0 END) AS no_answer,
                   AVG(total_duration_ms) AS avg_total_ms,
                   AVG(retrieval_duration_ms) AS avg_retrieval_ms,
                   AVG(model_duration_ms) AS avg_model_ms
            FROM request_traces WHERE created_at >= ?
        """, (since,)).fetchone()
        statuses = connection.execute("""
            SELECT status, COUNT(*) AS count FROM request_traces
            WHERE created_at >= ? GROUP BY status ORDER BY status
        """, (since,)).fetchall()
        daily = connection.execute("""
            SELECT substr(created_at, 1, 10) AS day, COUNT(*) AS total,
                   SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) AS success,
                   SUM(CASE WHEN status = 'error' THEN 1 ELSE 0 END) AS errors,
                   SUM(CASE WHEN status = 'no_answer' THEN 1 ELSE 0 END) AS no_answer,
                   AVG(total_duration_ms) AS avg_total_ms
            FROM request_traces WHERE created_at >= ?
            GROUP BY substr(created_at, 1, 10) ORDER BY day
        """, (since,)).fetchall()
        feedback = connection.execute("""
            SELECT f.rating, COUNT(*) AS count FROM trace_feedback f
            JOIN request_traces t ON t.trace_id = f.trace_id
            WHERE t.created_at >= ? GROUP BY f.rating ORDER BY f.rating
        """, (since,)).fetchall()
    total = int(totals["total"] or 0)
    return {
        "period_days": max(1, min(days, 90)),
        "total_requests": total,
        "success_rate": round((totals["success"] or 0) / total, 4) if total else 0,
        "error_rate": round((totals["errors"] or 0) / total, 4) if total else 0,
        "no_answer_rate": round((totals["no_answer"] or 0) / total, 4) if total else 0,
        "avg_total_ms": round(totals["avg_total_ms"], 2) if totals["avg_total_ms"] is not None else None,
        "avg_retrieval_ms": round(totals["avg_retrieval_ms"], 2) if totals["avg_retrieval_ms"] is not None else None,
        "avg_model_ms": round(totals["avg_model_ms"], 2) if totals["avg_model_ms"] is not None else None,
        "status_breakdown": [dict(row) for row in statuses],
        "daily_trend": [dict(row) for row in daily],
        "feedback_breakdown": [dict(row) for row in feedback],
    }


def admin_list_traces(*, limit: int = 50, offset: int = 0, status: str | None = None,
                      query: str | None = None, start_date: str | None = None,
                      end_date: str | None = None) -> dict[str, Any]:
    initialize_traces()
    limit = max(1, min(int(limit), 100))
    offset = max(0, int(offset))
    clauses: list[str] = []
    params: list[Any] = []
    if status:
        clauses.append("t.status = ?")
        params.append(status)
    if query:
        clauses.append("t.question LIKE ?")
        params.append("%" + query[:100] + "%")
    if start_date:
        clauses.append("t.created_at >= ?")
        params.append(start_date[:30])
    if end_date:
        clauses.append("t.created_at <= ?")
        params.append(end_date[:30])
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    with _connect() as connection:
        total = connection.execute("SELECT COUNT(*) FROM request_traces t" + where, params).fetchone()[0]
        rows = connection.execute("""
            SELECT t.trace_id, t.session_id, t.conversation_id, t.endpoint, t.status,
                   t.question, t.effective_mode, t.result_count, t.model_name,
                   t.retrieval_duration_ms, t.model_duration_ms, t.first_token_ms,
                   t.total_duration_ms, t.error_type, t.created_at,
                   f.rating AS feedback_rating
            FROM request_traces t LEFT JOIN trace_feedback f
              ON f.trace_id = t.trace_id AND f.session_id = t.session_id
        """ + where + " ORDER BY t.created_at DESC LIMIT ? OFFSET ?",
            [*params, limit, offset]).fetchall()
    return {"items": [dict(row) for row in rows], "total": total, "limit": limit, "offset": offset}


def admin_get_trace(trace_id: str) -> dict | None:
    initialize_traces()
    with _connect() as connection:
        row = connection.execute("SELECT * FROM request_traces WHERE trace_id = ?", (trace_id,)).fetchone()
        if row is None:
            return None
        item = dict(row)
        for field, target in (("retrieved_chunks_json", "retrieved_chunks"),
                              ("sources_json", "sources"),
                              ("diagnostic_chunks_json", "diagnostic_chunks")):
            try:
                item[target] = __import__("json").loads(item.pop(field) or "[]")
            except (TypeError, ValueError):
                item[target] = []
        feedback = connection.execute(
            "SELECT rating, comment, created_at FROM trace_feedback WHERE trace_id = ? ORDER BY created_at DESC",
            (trace_id,),
        ).fetchall()
    item["feedback"] = [dict(value) for value in feedback]
    return item


def admin_audit_logs(limit: int = 50) -> list[dict]:
    with _connect() as connection:
        # The table is created by the authentication service during login/startup.
        try:
            rows = connection.execute(
                "SELECT action, client_ip, created_at FROM admin_audit_logs ORDER BY created_at DESC LIMIT ?",
                (max(1, min(int(limit), 100)),),
            ).fetchall()
        except sqlite3.OperationalError:
            return []
    return [dict(row) for row in rows]
