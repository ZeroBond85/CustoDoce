"""
services/scraper_health.py

Centralized self-healing coordinator for scrapers. Provides:

- record_failure(scraper_name, reason=None, items_found=0, products_matched=0, flyer_count=0, attempted_by="auto")
    Log a failure event in scraper_health_log; auto-disable the store after
    `threshold` (= 3 by default) consecutive failures. Idempotent re-disabling
    is safe.

- record_success(scraper_name, items_found=0, products_matched=0, flyer_count=0, attempted_by="auto")
    Mark a successful execution; resets the auto-disable counter.

- attempt_heal(scraper_name=None, dry_run=False)
    For every currently-disabled scraper older than `min_idle_days` (= 15 by default),
    attempt a lightweight heal: re-fetch the latest few scraping_logs and decide
    whether to reactivate. Pure heuristic — does NOT trigger an actual re-scrape.
    Returns a summary dict.

- classify_error_for_alert(reason)
    Map a free-form error string into a coarse category for alerting.

This is the **mandatory** entry point referenced by AGENTS.md Licao #15:
'Self-healing obrigatorio em todos os scrapers'. New scrapers must call
record_failure / record_success from their failure / success branches.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta

from services.logger import logger
from services.supabase_client import get_service_client

# Caller can override via env or features.yaml reading later.
THRESHOLD_FAILURES = int(os.environ.get("SCRAPER_HEALTH_THRESHOLD", "3"))
RECOVERY_MIN_ITEMS = int(os.environ.get("SCRAPER_HEALTH_RECOVERY_ITEMS", "1"))
MIN_IDLE_DAYS_BEFORE_HEAL = int(os.environ.get("SCRAPER_HEALTH_HEAL_DAYS", "15"))


# ─── Helpers ──────────────────────────────────────────────────────────────────


def _utcnow_iso() -> str:
    return datetime.now(tz=UTC).isoformat()


def _count_consecutive_failures(client, scraper_name: str) -> int:
    """Returns how many of the most-recent successive logs are failures
    (limited to THRESHOLD_FAILURES rows; if any early row is non-failure, returns 0).
    """
    res = (
        client.table("scraping_logs")
        .select("status")
        .eq("store_name", scraper_name)
        .order("started_at", desc=True)
        .limit(THRESHOLD_FAILURES)
        .execute()
    )
    rows = res.data or []
    count = 0
    for r in rows:
        if r.get("status") in ("error", "failed"):
            count += 1
        else:
            break
    return count


def classify_error_for_alert(reason: str | None) -> str:
    """Coarse 1-line classifier used in alerting + scraper_health_log.error_class."""
    if not reason:
        return "Unknown"
    s = reason.lower()
    if "timeout" in s or "timed out" in s:
        return "Timeout"
    if "ssl" in s or "tls" in s or "certificate" in s:
        return "SSLError"
    if "proxy" in s:
        return "ProxyConfigError"
    if "connect" in s or "connection" in s:
        return "ConnectError"
    if "404" in s or "not found" in s:
        return "LayoutChanged"
    if "parse" in s or "selector" in s or "no element" in s:
        return "LayoutChanged"
    if "captcha" in s or "robot" in s:
        return "AntiBot"
    if "rate" in s or "429" in s or "too many" in s:
        return "RateLimit"
    return "Other"


# ─── Core API ──────────────────────────────────────────────────────────────────


def record_failure(
    scraper_name: str,
    reason: str | None = None,
    items_found: int = 0,
    products_matched: int = 0,
    flyer_count: int = 0,
    attempted_by: str = "auto",
) -> dict:
    """Record a failure and auto-disable the scraper if THRESHOLD_FAILURES hit.

    Returns a small summary of what happened (used by scripts/heal_scrapers.py).
    """
    try:
        client = get_service_client()
    except Exception as exc:
        logger.warning("scraper_health.record_failure: no supabase client (%s)", exc)
        return {"recorded": False, "reason": "no-client"}

    error_class = classify_error_for_alert(reason)
    failures_count = _count_consecutive_failures(client, scraper_name)
    regressions = []

    # Insert into scraper_health_log
    try:
        client.table("scraper_health_log").insert(
            {
                "scraper_name": scraper_name,
                "event_type": "failure",
                "failures_count": failures_count,
                "is_active": True,
                "reason": (reason or "")[:512],
                "items_found": items_found,
                "products_matched": products_matched,
                "flyer_count": flyer_count,
                "error_class": error_class,
                "attempted_by": attempted_by,
            }
        ).execute()
        regressions.append("log_inserted")
    except Exception as exc:
        logger.debug("scraper_health_log insert failed for %s: %s", scraper_name, exc)

    # Auto-disable if threshold reached
    if failures_count >= THRESHOLD_FAILURES:
        try:
            store = client.table("stores").select("id, is_active").eq("name", scraper_name).single().execute()
            if store.data and store.data.get("is_active") is not False:
                client.table("stores").update({"is_active": False}).eq("id", store.data["id"]).execute()
                logger.warning(
                    "[AUTO-DISABLE] %s desativada apos %d falhas consecutivas",
                    scraper_name,
                    failures_count,
                )
                regressions.append("auto_disabled")
                # Log the auto-disable event
                try:
                    client.table("scraper_health_log").insert(
                        {
                            "scraper_name": scraper_name,
                            "event_type": "auto_disabled",
                            "failures_count": failures_count,
                            "is_active": False,
                            "reason": f"threshold {THRESHOLD_FAILURES} failures hit",
                            "error_class": error_class,
                            "attempted_by": attempted_by,
                        }
                    ).execute()
                except Exception as exc:
                    logger.debug(
                        "auto_disabled log insert failed for %s: %s",
                        scraper_name,
                        exc,
                    )
        except Exception as exc:
            logger.warning("auto-disable update failed for %s: %s", scraper_name, exc)

    return {
        "recorded": True,
        "scraper": scraper_name,
        "failures_count": failures_count,
        "auto_disabled": "auto_disabled" in regressions,
        "error_class": error_class,
    }


def record_success(
    scraper_name: str,
    items_found: int = 0,
    products_matched: int = 0,
    flyer_count: int = 0,
    attempted_by: str = "auto",
) -> dict:
    """Record a successful run; resets failure counter."""
    try:
        client = get_service_client()
    except Exception as exc:
        logger.warning("scraper_health.record_success: no supabase client (%s)", exc)
        return {"recorded": False}

    try:
        client.table("scraper_health_log").insert(
            {
                "scraper_name": scraper_name,
                "event_type": "success",
                "failures_count": 0,
                "is_active": True,
                "items_found": items_found,
                "products_matched": products_matched,
                "flyer_count": flyer_count,
                "attempted_by": attempted_by,
            }
        ).execute()
        return {"recorded": True, "scraper": scraper_name}
    except Exception as exc:
        logger.debug(
            "scraper_health_log success insert failed for %s: %s",
            scraper_name,
            exc,
        )
        return {"recorded": False}


def attempt_heal(scraper_name: str | None = None, dry_run: bool = False) -> dict:
    """For every currently-disabled scraper older than MIN_IDLE_DAYS_BEFORE_HEAL
    days, evaluate the latest scraping_logs and decide whether to reactivate.

    Returns a summary dict {candidates, reactivated, skipped, missing_facts}.
    Lightweight heuristic only: real re-scrape is NOT performed here. That is
    delegated to scripts/heal_scrapers.py (which can be invoked manually).
    """
    try:
        client = get_service_client()
    except Exception as exc:
        logger.warning("scraper_health.attempt_heal: no db (%s)", exc)
        return {"error": "no-client"}

    summary: dict = {
        "candidates": [],
        "reactivated": [],
        "skipped": [],
        "missing_facts": [],
    }

    # 1. List currently-inactive stores
    q = client.table("stores").select("id, name, is_active").eq("is_active", False)
    if scraper_name:
        q = q.eq("name", scraper_name)
    inactive = q.execute().data or []

    if not inactive:
        return summary

    # 2. For each, evaluate recent logs
    cutoff = (datetime.now(tz=UTC) - timedelta(days=MIN_IDLE_DAYS_BEFORE_HEAL)).isoformat()

    for s in inactive:
        # Has ANY log entry more recent than the cutoff?
        logs = (
            client.table("scraping_logs")
            .select("status, items_found, started_at")
            .eq("store_name", s["name"])
            .order("started_at", desc=True)
            .limit(THRESHOLD_FAILURES)
            .execute()
        )
        rows = logs.data or []
        if not rows:
            summary["missing_facts"].append(s["name"])
            continue

        # If last log is recent, check whether scheduler/collector has been
        # hammering it (i.e. we'd see failures again quickly). If quiet, candidate.
        summary["candidates"].append(s["name"])

        # Heuristic: reactivate ONLY if scraper_health_log has a recent
        # 'auto_disabled' event older than MIN_IDLE_DAYS, AND no recent failures
        log_done = (
            client.table("scraper_health_log")
            .select("event_type, created_at")
            .eq("scraper_name", s["name"])
            .eq("event_type", "auto_disabled")
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        last_disabled = (log_done.data or [None])[0]
        if not last_disabled or last_disabled["created_at"] > cutoff:
            summary["skipped"].append({"scraper": s["name"], "reason": "disbled_recently"})
            continue

        # Has scraper accumulated recent SUCCESS logs in last 24h? (unlikely,
        # but could happen if other workflow re-scraped despite inactive flag)
        recent_success = any(
            r.get("status") == "completed"
            and r.get("items_found", 0) >= RECOVERY_MIN_ITEMS
            and (r.get("started_at", "") > cutoff)
            for r in rows
        )
        if not recent_success:
            summary["skipped"].append({"scraper": s["name"], "reason": "no_recent_success_log"})
            continue

        # Decision: reactivate (still subject to dry_run)
        if dry_run:
            summary["reactivated"].append({"scraper": s["name"], "dry_run": True})
        else:
            try:
                client.table("stores").update({"is_active": True}).eq("id", s["id"]).execute()
                client.table("scraper_health_log").insert(
                    {
                        "scraper_name": s["name"],
                        "event_type": "auto_reactivated",
                        "failures_count": 0,
                        "is_active": True,
                        "reason": "heal attempt succeeded",
                        "attempted_by": "auto",
                    }
                ).execute()
                summary["reactivated"].append({"scraper": s["name"]})
                logger.info("[AUTO-REACTIVATE] %s reactivated", s["name"])
            except Exception as exc:
                logger.warning("reactivate failed for %s: %s", s["name"], exc)
                summary["skipped"].append({"scraper": s["name"], "reason": "reactivate_db_error"})

    return summary
