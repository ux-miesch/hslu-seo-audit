import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(tags=["feedback"])

SMTP_HOST = os.environ.get("SMTP_HOST", "")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "465"))
SMTP_USER = os.environ.get("SMTP_USER", "")
SMTP_PASS = os.environ.get("SMTP_PASS", "")
FEEDBACK_TO = "dms@hslu.ch"


class FeedbackBody(BaseModel):
    message: str
    page: str = ""


@router.post("/feedback")
async def send_feedback(body: FeedbackBody):
    if not body.message.strip():
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="Nachricht darf nicht leer sein.")
    if not SMTP_USER or not SMTP_PASS:
        print(f"[FEEDBACK] SMTP nicht konfiguriert – Feedback: {body.message}", flush=True)
        return {"ok": True}
    msg = MIMEMultipart("alternative")
    msg["From"] = SMTP_USER
    msg["To"] = FEEDBACK_TO
    msg["Subject"] = "SEO-Tool Feedback"
    page_info = f"\n\nSeite: {body.page}" if body.page else ""
    msg.attach(MIMEText(f"{body.message}{page_info}", "plain"))
    try:
        with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT) as smtp:
            smtp.login(SMTP_USER, SMTP_PASS)
            smtp.sendmail(SMTP_USER, FEEDBACK_TO, msg.as_string())
        print(f"[FEEDBACK] Gesendet von {body.page}", flush=True)
    except Exception as exc:
        print(f"[FEEDBACK] Fehler: {exc}", flush=True)
    return {"ok": True}
