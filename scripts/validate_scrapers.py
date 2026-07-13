#!/usr/bin/env python3
"""
validate_scrapers.py — Iterates all active stores via dispatch map and validates
the collection pipeline WITHOUT writing to Supabase (dry-run by default).

Usage:
    python scripts/validate_scrapers.py                     # dry-run: count stores per scraper type
    python scripts/validate_scrapers.py --validate           # full: calls each collector, logs items
    python scripts/validate_scrapers.py --validate --write   # full + allow upserts to DB
"""

import logging
import sys
import time
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("validate_scrapers")


def _dry_run():
    """Count active stores per scraper type without connecting to anything."""
    import yaml

    stores_path = Path(__file__).resolve().parent.parent / "config" / "stores.yaml"
    with open(stores_path, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    stores = data.get("stores", [])
    by_scraper: dict[str, list[str]] = defaultdict(list)
    for s in stores:
        if s.get("is_active", True):
            scraper = s.get("scraper", "none")
            by_scraper[scraper].append(s["name"])

    total = sum(len(v) for v in by_scraper.values())
    print(f"\n{'='*60}")
    print(f"VALIDATE SCRAPERS — DRY RUN")
    print(f"{'='*60}")
    print(f"\nTotal active stores in YAML: {total}")
    print(f"\n{'Scraper Type':<35} {'Count':<6}  Stores")
    print(f"{'-'*35:<35} {'-'*6:<6}  {'-'*30}")
    for scraper in sorted(by_scraper.keys()):
        names = by_scraper[scraper]
        print(f"{scraper:<35} {len(names):<6}  {', '.join(names[:5])}{'...' if len(names) > 5 else ''}")
    print()

    # Cross-ref with collector.py load_stores() logic
    print(f"{'='*60}")
    print(f"NOTE: load_stores() also requires Supabase (scrape_frequencies).")
    print(f"Stores without a freq row OR with enabled=True pass through.")
    print(f"Stores with enabled=False in freq row are excluded.")
    print(f"{'='*60}\n")


def _do_validate(allow_write: bool = False):
    """Run each collector and log results."""
    from services.collector import (
        collect_aggregators_js,
        collect_aggregators_ssr,
        collect_carrefour,
        collect_extra_flyers,
        collect_facebook_flyers,
        collect_pao_flyers,
        collect_roldao_flyer,
        collect_tier1_api_flyers,
        collect_tier1_pdfs,
        collect_tier2_js,
        collect_tier2_vtex,
        collect_tier3_websites,
        load_ingredients,
    )
    from services.config_db import get_active_stores

    if not allow_write:
        # Monkey-patch upsert functions to no-op during validation
        import services.price_service as ps
        import services.flyer_service as fs

        _orig_upsert = ps.upsert_price
        _orig_review = ps.insert_review_item
        _orig_flyer = fs.upsert_flyer

        def _noop(*args, **kwargs):
            return None

        ps.upsert_price = _noop
        ps.insert_review_item = _noop
        fs.upsert_flyer = _noop

    phases = [
        ("Tier-1 PDFs", lambda ing: collect_tier1_pdfs(ing)),
        ("Extra Flyers", lambda ing: collect_extra_flyers(ing)),
        ("Pao Flyers", lambda ing: collect_pao_flyers(ing)),
        ("Tier-1 API Flyers", lambda ing: collect_tier1_api_flyers(ing)),
        ("Tier-2 VTEX", lambda ing: collect_tier2_vtex(ing)),
        ("Tier-3 Websites", lambda ing: collect_tier3_websites(ing)),
        ("Carrefour", lambda ing: collect_carrefour(ing)),
        ("Tier-2 JS (Playwright)", lambda ing: collect_tier2_js(ing)),
        ("Roldao Flyer", lambda ing: collect_roldao_flyer(ing)),
        ("Facebook Flyers", lambda ing: collect_facebook_flyers(ing)),
        ("Aggregators SSR (Tiendeo)", lambda ing: collect_aggregators_ssr()),
        ("Aggregators JS (Kimbino/Porta/Promotons)", lambda ing: collect_aggregators_js()),
    ]

    print(f"\n{'='*60}")
    print(f"VALIDATE SCRAPERS — {'LIVE (no-write)' if not allow_write else 'LIVE (WRITE ENABLED)'}")
    print(f"{'='*60}\n")

    # Check Supabase connectivity first
    try:
        stores = get_active_stores()
        logger.info("Supabase reachable — %d active stores in DB", len(stores))
    except Exception as e:
        logger.error("Cannot reach Supabase: %s", e)
        logger.info("Aborting validation — no Supabase connection")
        return

    ingredients = load_ingredients()
    logger.info("Loaded %d active ingredients\n", len(ingredients))

    results = {}
    all_ok = True

    for label, fn in phases:
        logger.info("─── %s ───", label)
        try:
            t0 = time.time()
            items = fn(ingredients)
            elapsed = time.time() - t0
            count = len(items)
            results[label] = {"items": count, "time": elapsed, "error": None}
            status = "OK" if count > 0 or "Aggregator" in label else "WARN"
            if count == 0:
                status = "ZERO"
                all_ok = False
            logger.info("  → %d items in %.1fs [%s]", count, elapsed, status)
        except Exception as e:
            elapsed = time.time() - t0 if 't0' in dir() else 0
            results[label] = {"items": -1, "time": elapsed, "error": str(e)}
            logger.error("  → FAILED: %s", e)
            all_ok = False

    print(f"\n{'='*60}")
    print(f"SUMMARY")
    print(f"{'='*60}")
    print(f"{'Phase':<40} {'Items':<8} {'Time':<8} Status")
    print(f"{'-'*40:<40} {'-'*8:<8} {'-'*8:<8} {'-'*10}")
    for label, r in results.items():
        status = "OK" if r["error"] is None and r["items"] >= 0 else "FAIL" if r["error"] else "ZERO"
        items = str(r["items"]) if r["items"] >= 0 else "ERR"
        elapsed_s = f"{r['time']:.1f}s"
        print(f"{label:<40} {items:<8} {elapsed_s:<8} {status}")
    print(f"\n{'TOTAL OK' if all_ok else 'SOME FAILURES'}")
    print(f"{'='*60}\n")

    if not allow_write:
        ps.upsert_price = _orig_upsert
        ps.insert_review_item = _orig_review
        fs.upsert_flyer = _orig_flyer

    sys.exit(0 if all_ok else 1)


def _check_fks():
    """Scan migration SQL files for REFERENCES stores(id) with wrong types."""
    import re

    migration_dirs = [
        Path(__file__).resolve().parent.parent / "supabase",
        Path(__file__).resolve().parent.parent / "supabase" / "migrations",
    ]
    wrong_types = re.compile(
        r"(?:store_id|matched_store_id)\s+(INTEGER|BIGINT|SMALLINT|UUID)\s+REFERENCES\s+stores",
        re.I,
    )

    errors = []
    for d in migration_dirs:
        if not d.exists():
            continue
        for f in sorted(d.glob("*.sql")):
            text = f.read_text(encoding="utf-8", errors="replace")
            for m in wrong_types.finditer(text):
                lineno = text[: m.start()].count("\n") + 1
                errors.append((f.name, lineno, m.group()))

    if errors:
        print(f"\n{'='*60}")
        print(f"FK TYPE DRIFT DETECTED")
        print(f"{'='*60}")
        for fname, lineno, match in errors:
            print(f"  {fname}:{lineno}: {match}")
        print(f"\n  Fix: change INTEGER/UUID to TEXT in REFERENCES stores(id)\n")
        sys.exit(1)
    else:
        print(f"\n{'='*60}")
        print("FK TYPE CHECK: All REFERENCES stores(id) use TEXT [OK]")
        print(f"{'='*60}\n")


def main():
    args = [a.lower() for a in sys.argv[1:]]
    is_validate = "--validate" in args
    allow_write = "--write" in args
    check_fks = "--check-fks" in args

    if check_fks:
        _check_fks()
    elif is_validate:
        _do_validate(allow_write=allow_write)
    else:
        _dry_run()


if __name__ == "__main__":
    main()
