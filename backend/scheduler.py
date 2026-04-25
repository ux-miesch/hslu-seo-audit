from __future__ import annotations
import asyncio
from typing import Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

scheduler = AsyncIOScheduler()

SLOTS_PER_DAY = 8  # Stunden 00–07, 1 Slot pro Stunde


def _calc_slot(schedule_type: str, slug: str) -> tuple[int, int]:
    """Berechnet Tag-Offset und Stunde für einen Projekt-Job.

    Wöchentlich: Tag-Offset 0–4 → Mo–Fr, Stunde 0–7
    Monatlich:   Tag-Offset 0–4 → 1.–5. des Monats, Stunde 0–7
    """
    from backend.database import list_all_projects
    projects = list_all_projects()
    scheduled = [
        p for p in sorted(projects, key=lambda x: x.get("created_at", ""))
        if p.get("schedule") == schedule_type and p["slug"] != slug
    ]
    idx = len(scheduled)
    day_offset = idx // SLOTS_PER_DAY
    hour = idx % SLOTS_PER_DAY
    return day_offset, hour


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

    WEEKDAYS = ["mon", "tue", "wed", "thu", "fri"]

    if schedule == "weekly":
        day_offset, hour = _calc_slot("weekly", slug)
        day_offset = min(day_offset, len(WEEKDAYS) - 1)
        day_name = WEEKDAYS[day_offset]
        print(f"[SCHEDULER] {slug}: wöchentlich {day_name} {hour:02d}:00", flush=True)
        scheduler.add_job(
            _run_project_audit,
            CronTrigger(day_of_week=day_name, hour=hour, minute=0),
            args=[slug],
            id=job_id,
            replace_existing=True,
        )
    elif schedule == "monthly":
        day_offset, hour = _calc_slot("monthly", slug)
        day = min(day_offset + 1, 5)  # 1.–5. des Monats
        print(f"[SCHEDULER] {slug}: monatlich {day}. {hour:02d}:00", flush=True)
        scheduler.add_job(
            _run_project_audit,
            CronTrigger(day=day, hour=hour, minute=0),
            args=[slug],
            id=job_id,
            replace_existing=True,
        )


def register_all_scheduled_jobs() -> None:
    """Registriert alle geplanten Jobs in einem Pass – kein N+1.

    Berechnet Slots inkrementell, ohne pro Job list_all_projects() aufzurufen.
    """
    from backend.database import list_all_projects
    WEEKDAYS = ["mon", "tue", "wed", "thu", "fri"]

    projects = list_all_projects()
    projects_sorted = sorted(projects, key=lambda x: x.get("created_at", ""))

    weekly_idx = 0
    monthly_idx = 0

    for p in projects_sorted:
        sched = p.get("schedule")
        slug = p["slug"]
        job_id = f"audit_{slug}"

        if sched == "weekly":
            day_offset = weekly_idx // SLOTS_PER_DAY
            hour = weekly_idx % SLOTS_PER_DAY
            day_offset = min(day_offset, len(WEEKDAYS) - 1)
            day_name = WEEKDAYS[day_offset]
            print(f"[SCHEDULER] {slug}: wöchentlich {day_name} {hour:02d}:00", flush=True)
            scheduler.add_job(
                _run_project_audit,
                CronTrigger(day_of_week=day_name, hour=hour, minute=0),
                args=[slug],
                id=job_id,
                replace_existing=True,
            )
            weekly_idx += 1
        elif sched == "monthly":
            day_offset = monthly_idx // SLOTS_PER_DAY
            hour = monthly_idx % SLOTS_PER_DAY
            day = min(day_offset + 1, 5)
            print(f"[SCHEDULER] {slug}: monatlich {day}. {hour:02d}:00", flush=True)
            scheduler.add_job(
                _run_project_audit,
                CronTrigger(day=day, hour=hour, minute=0),
                args=[slug],
                id=job_id,
                replace_existing=True,
            )
            monthly_idx += 1


def init_scheduler() -> None:
    """Startet den Scheduler – Jobs werden separat via register_all_scheduled_jobs() geladen."""
    scheduler.start()


def shutdown_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown()
