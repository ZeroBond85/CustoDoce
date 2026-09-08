"""
scripts/scraper_trend_watch.py

Fase C — Watch de degradação temporal de scrapers (cron 30min).
Roda em CI/standalone: analisa todas as lojas, aplica cooldown e envia alerta
Telegram (fallback email) para lojas diagnosticadas critical/degraded.

Uso:
  python scripts/scraper_trend_watch.py [--dry-run]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.logger import logger  # noqa: E402
from services.scraper_trend_detector import (  # noqa: E402
    COOLDOWN_HOURS,
    analyze_all_stores,
    should_alert,
    update_alert_state,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Watch de degradação temporal de scrapers")
    parser.add_argument("--dry-run", action="store_true", help="Não envia alertas, só reporta")
    args = parser.parse_args()

    results = analyze_all_stores()
    logger.info("scraper_trend_watch: %d lojas analisadas", len(results))

    actionable = [r for r in results if r["status"] in ("critical", "degraded")]
    logger.info("scraper_trend_watch: %d lojas com anomalia", len(actionable))

    if args.dry_run:
        for r in actionable:
            logger.info("scraper_trend_watch(dry): %s=%s score=%s", r["store_name"], r["status"], r["trend_score"])
        return

    sent = 0
    for r in actionable:
        store = r["store_name"]
        if not should_alert(store, cooldown_hours=COOLDOWN_HOURS):
            logger.debug("scraper_trend_watch: %s em cooldown, skip", store)
            continue
        try:
            from services.scraper_alert import send_trend_alert

            if send_trend_alert(store, r):
                update_alert_state(store, r["trend_score"], r["status"], active=True)
                sent += 1
                logger.info("scraper_trend_watch: alerta enviado para %s (%s)", store, r["status"])
        except Exception as e:
            logger.warning("scraper_trend_watch: falha ao alertar %s: %s", store, e)

    logger.info("scraper_trend_watch: %d alertas enviados", sent)


if __name__ == "__main__":
    main()