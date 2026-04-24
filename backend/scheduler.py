from __future__ import annotations
import asyncio
from typing import Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

scheduler = AsyncIOScheduler()

SCHEDULE_OFFSET_MINUTES = 30  # Versatz pro Projekt


def _calc_slot(schedule_type: str, slug: str) -> tuple[int, int]:
    """Berechnet Stunde/Minute für einen Projekt-Job basierend auf Anzahl bereits geplanter Projekte."""
    from backend.database import list_all_projects
    projects = list_all_projects()
    # Alle anderen Projekte mit gleichem Schedule-Typ, sortiert nach Erstellungsdatum
    scheduled = [
        p for p in sorted(projects, key=lambda x: x.get("created_at", ""))
        if p.get("schedule") == schedule_type and p["slug"] != slug
    ]
    idx = len(scheduled)  # 0-basierter Index für dieses Projekt
    total_minutes = idx * SCHEDULE_OFFSET_MINUTES
    return total_minutes // 60, total_minutes % 60


async def _run_project_audit(slug: str) -> None:
    from backend.routers.projects import _crawl, _audit
    from backend.database import get_db

    db = get_db(slug)
    try:
        row = db.execute(
            "SELECT id, root_url, language, max_pages, project_type FROM projects WHERE slug = ?", (slug,)
        ).fetchone()
        if row is None:
            return
        project_id = row["id"]
        root_url = row["root_url"]
        language = row["language"]
        max_pages = row["max_pages"] or None  # 0/NULL → keine Begrenzung
        project_type = row["project_type"] or "website"
    finally:
        db.close()

    # Seiten löschen und neu crawlen
    db = get_db(slug)
    try:
        db.execute(
            "DELETE FROM audit_results WHERE page_id IN (SELECT id FROM pages WHERE project_id = ?)",
            (project_id,),
        )
        db.execute("DELETE FROM pages WHERE project_id = ?", (project_id,))
        db.commit()
    finally:
        db.close()

    await _crawl(project_id, root_url, slug, max_pages)
    from backend.routers.projects import _mode_weights_for
    mode_weights = _mode_weights_for(project_type)
    await _audit(project_id, language, mode_weights, slug)


def update_project_schedule(slug: str, schedule: Optional[str]) -> None:
    job_id = f"audit_{slug}"
    if scheduler.get_job(job_id):
        scheduler.remove_job(job_id)

    if schedule == "weekly":
        hour, minute = _calc_slot("weekly", slug)
        print(f"[SCHEDULER] {slug}: wöchentlich Mo {hour:02d}:{minute:02d}", flush=True)
        scheduler.add_job(
            _run_project_audit,
            CronTrigger(day_of_week="mon", hour=hour, minute=minute),
            args=[slug],
            id=job_id,
            replace_existing=True,
        )
    elif schedule == "monthly":
        hour, minute = _calc_slot("monthly", slug)
        print(f"[SCHEDULER] {slug}: monatlich 1. {hour:02d}:{minute:02d}", flush=True)
        scheduler.add_job(
            _run_project_audit,
            CronTrigger(day=1, hour=hour, minute=minute),
            args=[slug],
            id=job_id,
            replace_existing=True,
        )


def init_scheduler() -> None:
    from backend.database import list_all_projects
    projects = list_all_projects()
    # Sortiert nach Erstellungsdatum für konsistente Slot-Zuweisung
    projects_sorted = sorted(projects, key=lambda x: x.get("created_at", ""))
    for p in projects_sorted:
        sched = p.get("schedule")
        if sched in ("weekly", "monthly"):
            update_project_schedule(p["slug"], sched)
    scheduler.start()


def shutdown_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown()
