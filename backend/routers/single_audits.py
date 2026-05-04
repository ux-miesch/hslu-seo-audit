from __future__ import annotations
import json
import secrets
from datetime import datetime, timedelta

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.single_audits import get_single_audits_db

router = APIRouter(prefix="/single-audits", tags=["single-audits"])


def _gen_id(n: int = 8) -> str:
    return secrets.token_urlsafe(n)[:n]


class SingleAuditCreate(BaseModel):
    url: str
    result: dict


@router.get("/")
def list_single_audits():
    conn = get_single_audits_db()
    try:
        rows = conn.execute(
            "SELECT id, url, result, created_at, expires_at FROM single_audits ORDER BY created_at DESC"
        ).fetchall()
        result = []
        for row in rows:
            r = dict(row)
            raw = r.pop("result", "{}")
            try:
                data = json.loads(raw)
                checks = data.get("checks", {})
                scores = [c["score"] for c in checks.values() if isinstance(c.get("score"), (int, float))]
                avg_score = round(sum(scores) / len(scores), 1) if scores else None
                lang = ((checks.get("spelling") or {}).get("data") or {}).get("language_detected") or "—"
            except Exception:
                avg_score = None
                lang = "—"
            r["score"] = avg_score
            r["language"] = lang
            result.append(r)
        return result
    finally:
        conn.close()


@router.post("/", status_code=201)
def create_single_audit(body: SingleAuditCreate):
    audit_id = _gen_id()
    now = datetime.utcnow()
    expires = now + timedelta(days=30)
    conn = get_single_audits_db()
    try:
        conn.execute(
            "INSERT INTO single_audits (id, url, result, created_at, expires_at) VALUES (?, ?, ?, ?, ?)",
            (audit_id, body.url, json.dumps(body.result), now.isoformat(), expires.isoformat()),
        )
        conn.commit()
    finally:
        conn.close()
    return {"id": audit_id}


@router.get("/{audit_id}")
def get_single_audit(audit_id: str):
    conn = get_single_audits_db()
    try:
        row = conn.execute(
            "SELECT * FROM single_audits WHERE id = ?", (audit_id,)
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        raise HTTPException(status_code=404, detail="Nicht gefunden")
    if row["expires_at"] < datetime.utcnow().isoformat():
        return {"error": "expired"}
    return {
        "id": row["id"],
        "url": row["url"],
        "result": json.loads(row["result"]),
        "created_at": row["created_at"],
        "expires_at": row["expires_at"],
    }


@router.delete("/{audit_id}", status_code=204)
def delete_single_audit(audit_id: str):
    conn = get_single_audits_db()
    try:
        conn.execute("DELETE FROM single_audits WHERE id = ?", (audit_id,))
        conn.commit()
    finally:
        conn.close()
