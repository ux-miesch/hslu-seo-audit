import os
import secrets
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from backend.database import get_global_db

router = APIRouter(prefix="/admin", tags=["admin"])

ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")


def _check_auth(x_admin_password: Optional[str]) -> None:
    if not ADMIN_PASSWORD:
        raise HTTPException(status_code=503, detail="ADMIN_PASSWORD nicht konfiguriert.")
    if x_admin_password != ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="Ungültiges Passwort.")


class TokenCreate(BaseModel):
    label: str = ""
    token: str = ""  # Frontend generiert Token, sonst Backend


@router.post("/login")
def login(x_admin_password: Optional[str] = Header(default=None)):
    _check_auth(x_admin_password)
    return {"ok": True}


@router.get("/tokens")
def list_tokens(x_admin_password: Optional[str] = Header(default=None)):
    _check_auth(x_admin_password)
    db = get_global_db()
    try:
        rows = db.execute(
            "SELECT id, token, label, created_at, usage_count, last_used FROM tokens ORDER BY created_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        db.close()


@router.post("/tokens", status_code=201)
def create_token(body: TokenCreate, x_admin_password: Optional[str] = Header(default=None)):
    _check_auth(x_admin_password)
    token = body.token if body.token else secrets.token_urlsafe(24)
    db = get_global_db()
    try:
        db.execute(
            "INSERT INTO tokens (token, label) VALUES (?, ?)",
            (token, body.label.strip()),
        )
        db.commit()
        row = db.execute("SELECT * FROM tokens WHERE token = ?", (token,)).fetchone()
        return dict(row)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        db.close()


@router.delete("/tokens/{token_id}", status_code=204)
def delete_token(token_id: int, x_admin_password: Optional[str] = Header(default=None)):
    _check_auth(x_admin_password)
    db = get_global_db()
    try:
        db.execute("DELETE FROM tokens WHERE id = ?", (token_id,))
        db.commit()
    finally:
        db.close()


@router.get("/validate/{token}")
def validate_token(token: str):
    """Öffentlicher Endpunkt – prüft Token und zählt Usage."""
    db = get_global_db()
    try:
        row = db.execute("SELECT id FROM tokens WHERE token = ?", (token,)).fetchone()
        if not row:
            return {"valid": False}
        db.execute(
            "UPDATE tokens SET usage_count = usage_count + 1, last_used = ? WHERE id = ?",
            (datetime.utcnow().isoformat(), row["id"]),
        )
        db.commit()
        return {"valid": True}
    finally:
        db.close()
