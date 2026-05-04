import os
import secrets
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel

from backend.database import get_global_db

router = APIRouter(prefix="/admin", tags=["admin"])

ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")
FIXED_ADMIN_TOKEN = os.environ.get("ADMIN_TOKEN", "")


def _check_auth(x_admin_password: Optional[str]) -> None:
    if not ADMIN_PASSWORD:
        raise HTTPException(status_code=503, detail="ADMIN_PASSWORD nicht konfiguriert.")
    if not secrets.compare_digest(x_admin_password or "", ADMIN_PASSWORD):
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


# ── Admin-Token (single shared access token) ──────────────────────────────

def _get_admin_token() -> Optional[str]:
    if FIXED_ADMIN_TOKEN:
        return FIXED_ADMIN_TOKEN
    db = get_global_db()
    try:
        row = db.execute("SELECT value FROM config WHERE key = 'admin_token'").fetchone()
        return row["value"] if row else None
    finally:
        db.close()


def _set_admin_token(token: str) -> None:
    if FIXED_ADMIN_TOKEN:
        return
    db = get_global_db()
    try:
        db.execute(
            "INSERT OR REPLACE INTO config (key, value) VALUES ('admin_token', ?)", (token,)
        )
        db.commit()
    finally:
        db.close()


@router.get("/token")
def get_admin_token_endpoint(x_admin_password: Optional[str] = Header(default=None)):
    _check_auth(x_admin_password)
    token = _get_admin_token()
    if not token:
        return {"token": None, "masked": None}
    masked = token[:4] + "••••" + token[-4:] if len(token) >= 8 else "••••"
    return {"token": token, "masked": masked}


@router.post("/token")
def generate_admin_token(x_admin_password: Optional[str] = Header(default=None)):
    _check_auth(x_admin_password)
    if FIXED_ADMIN_TOKEN:
        masked = FIXED_ADMIN_TOKEN[:4] + "••••" + FIXED_ADMIN_TOKEN[-4:]
        return {"token": FIXED_ADMIN_TOKEN, "masked": masked}
    token = secrets.token_urlsafe(24)
    _set_admin_token(token)
    masked = token[:4] + "••••" + token[-4:]
    return {"token": token, "masked": masked}


@router.get("/token/verify")
def verify_admin_token(token: str = Query(...)):
    stored = _get_admin_token()
    if not stored or token != stored:
        return {"valid": False}
    return {"valid": True}


class PasswordVerifyRequest(BaseModel):
    password: str


@router.post("/password/verify")
def verify_admin_password(body: PasswordVerifyRequest):
    """Öffentlicher Endpunkt – prüft ADMIN_PASSWORD."""
    if not ADMIN_PASSWORD:
        return {"valid": False}
    return {"valid": secrets.compare_digest(body.password, ADMIN_PASSWORD)}
