#!/usr/bin/env python3
"""
Testa TODAS as lojas ativas em sequência, coleta métricas completas.
Uso: python scripts/test_all_stores.py [--force] [--output results.json] [--max-stores N]
"""

import json
import subprocess
import sys
import time
import argparse
from pathlib import Path

# Adiciona o diretório raiz ao path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.config_db import get_active_stores
from services.scraper_health import compute_health_score
from services.supabase_client import get_service_client


def test_store(store_name: str, timeout: int = 600) -> dict:
    """Roda test_single_store.py e parseia JSON output."""
    result = subprocess.run(
        [sys.executable, "scripts/test_single_store.py", store_name, str(timeout)],
        capture_output=True, text=True, timeout=timeout + 60
    )
    try:
        # A última linha do stdout é o JSON
        lines = result.stdout.strip().split('\n')
        for line in reversed(lines):
            line = line.strip()
            if line.startswith('{'):
                return json.loads(line)
        return {"store": store_name, "ok": False, "error": "no_json_output", "stdout": result.stdout[-500:], "stderr": result.stderr[-500:]}
    except Exception as e:
        return {"store": store_name, "ok": False, "error": f"parse_failed: {e}", "stdout": result.stdout[-500:], "stderr": result.stderr[-500:]}


def get_health_score(store_name: str) -> int:
    """Busca health score do scraper_health_log."""
    try:
        client = get_service_client()
        logs = client.table("scraper_health_log").select("*").eq("scraper_name", store_name).order("created_at", desc=True).limit(20).execute()
        rows = logs.data or []
        if not rows:
            return 0
        # Calcula métricas para compute_health_score
        total = len(rows)
        successes = sum(1 for r in rows if r.get("event_type") == "success")
        failures = sum(1 for r in rows if r.get("event_type") in ("failure", "auto_disabled"))
        transient = sum(1 for r in rows if r.get("event_type") == "transient_failure")
        items_found = [r.get("items_found", 0) for r in rows if r.get("items_found") is not None]
        avg_items = sum(items_found) / len(items_found) if items_found else 0
        last_run = rows[0].get("created_at") if rows else None

        data = {
            "success_rate": successes / total if total > 0 else 0,
            "failures_count": failures,
            "avg_items_per_run": avg_items,
            "latency_p95_ms": 0,  # Não disponível no log simples
            "last_run": last_run,
        }
        return compute_health_score(data)
    except Exception:
        return 0


def count_review_queue(store_name: str) -> int:
    """Conta itens na review_queue para esta loja."""
    try:
        client = get_service_client()
        r = client.table("review_queue").select("id", count="exact").eq("store_name", store_name).execute()
        return r.count or 0
    except Exception:
        return 0


def truncate_prices_and_review():
    """Trunca prices e review_queue para simular first-run real."""
    try:
        client = get_service_client()
        # Trunca prices
        client.table("prices").delete().neq("id", "00000000-0000-0000-0000-000000000000").execute()
        # Trunca review_queue
        client.table("review_queue").delete().neq("id", "00000000-0000-0000-0000-000000000000").execute()
        # Trunca scraping_logs (opcional, mantém histórico de health)
        # client.table("scraping_logs").delete().neq("id", "00000000-0000-0000-0000-000000000000").execute()
        print("✅ Truncated prices and review_queue")
        return True
    except Exception as e:
        print(f"❌ Failed to truncate: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Test all active stores")
    parser.add_argument("--force", action="store_true", help="Force full scrape (ignore freshness)")
    parser.add_argument("--output", default="results_local.json", help="Output JSON file")
    parser.add_argument("--max-stores", type=int, default=0, help="Max stores to test (0 = all)")
    parser.add_argument("--truncate", action="store_true", help="Truncate prices + review_queue before testing")
    parser.add_argument("--tier", type=str, default=None, help="Filter by tier (1, 2a, 3)")
    args = parser.parse_args()

    if args.truncate:
        print("🔄 Truncating prices + review_queue for true first-run simulation...")
        if not truncate_prices_and_review():
            return 1
        print("✅ Ready for first-run simulation")

    # Carrega lojas ativas
    stores = [s for s in get_active_stores() if s.get("is_active", True)]

    if args.tier:
        stores = [s for s in stores if str(s.get("tier")) == args.tier]
        print(f"Filtered to tier {args.tier}: {len(stores)} stores")

    if args.max_stores > 0:
        stores = stores[:args.max_stores]
        print(f"Limited to {args.max_stores} stores")

    print(f"Testing {len(stores)} active stores...")
    print("=" * 80)

    results = []
    start_total = time.time()

    for i, store in enumerate(stores, 1):
        name = store["name"]
        scraper = store.get("scraper", "")
        stype = store.get("type", "")
        tier = store.get("tier", "?")

        # Timeout adaptativo por tipo
        if scraper in ("giga_flyer_scraper", "playwright_price_scraper"):
            timeout = 900
        elif "api_flyer" in stype:
            timeout = 600
        elif scraper in ("playwright_scraper", "aggregator_scraper"):
            timeout = 300
        else:
            timeout = 300

        print(f"[{i}/{len(stores)}] {name} | tier={tier} | scraper={scraper} | type={stype} | timeout={timeout}s")

        t0 = time.time()
        r = test_store(name, timeout)
        elapsed = time.time() - t0

        # Enriquece com métricas
        r["elapsed"] = round(elapsed, 1)
        r["tier"] = tier
        r["scraper"] = scraper
        r["type"] = stype
        r["health_score"] = get_health_score(name)
        r["review_queue_count"] = count_review_queue(name)

        results.append(r)

        status = "✅" if r.get("ok") else "❌"
        extracted = r.get("extracted", 0)
        matched = r.get("collected", 0)
        match_rate = f"{(matched/extracted*100):.1f}%" if extracted > 0 else "N/A"
        health = r.get("health_score", 0)
        rq = r.get("review_queue_count", 0)

        print(f"  {status} extracted={extracted} matched={matched} ({match_rate}) | elapsed={elapsed:.1f}s | health={health} | review_queue={rq}")
        if not r.get("ok"):
            print(f"    ERROR: {r.get('error', 'unknown')}")

    total_elapsed = time.time() - start_total

    # Salva resultados
    output_path = Path(args.output)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump({
            "timestamp": time.time(),
            "total_stores": len(stores),
            "total_elapsed_seconds": round(total_elapsed, 1),
            "results": results
        }, f, indent=2, ensure_ascii=False)

    # Summary
    ok = sum(1 for r in results if r.get("ok"))
    total_extracted = sum(r.get("extracted", 0) for r in results)
    total_matched = sum(r.get("collected", 0) for r in results)
    avg_health = sum(r.get("health_score", 0) for r in results) / len(results) if results else 0
    total_rq = sum(r.get("review_queue_count", 0) for r in results)

    print("\n" + "=" * 80)
    print("=== SUMMARY ===")
    print(f"Stores tested: {len(stores)}")
    print(f"Stores OK: {ok}/{len(stores)} ({ok/len(stores)*100:.1f}%)")
    print(f"Total extracted: {total_extracted}")
    print(f"Total matched: {total_matched}")
    print(f"Global match rate: {(total_matched/total_extracted*100):.1f}%" if total_extracted > 0 else "N/A")
    print(f"Avg health score: {avg_health:.1f}")
    print(f"Total review queue items: {total_rq}")
    print(f"Total time: {total_elapsed:.1f}s")
    print(f"Results saved to: {output_path}")

    failed = [r for r in results if not r.get("ok")]
    if failed:
        print(f"\n❌ FAILED STORES ({len(failed)}):")
        for r in failed:
            print(f"  - {r['store']}: {r.get('error', 'unknown')}")

    # Quality gate
    print("\n=== QUALITY GATES ===")
    gates = {
        "min_ok_rate": (ok / len(stores) >= 0.8, f"{ok}/{len(stores)} = {ok/len(stores)*100:.1f}%"),
        "min_total_matched": (total_matched >= 50, f"{total_matched}"),
        "max_failed_stores": (len(failed) <= 5, f"{len(failed)} failed"),
        "avg_health_ok": (avg_health >= 50, f"{avg_health:.1f}"),
    }
    all_pass = True
    for gate, (passed, detail) in gates.items():
        status = "✅" if passed else "❌"
        print(f"  {status} {gate}: {detail}")
        if not passed:
            all_pass = False

    print(f"\n{'ALL GATES PASSED' if all_pass else 'SOME GATES FAILED'}")

    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())