"""Enriquece preços com Isolation Forest, tags e anomalias."""

import json
from pathlib import Path

from services.price_intelligence import PriceIntelligence


def main():
    pi = PriceIntelligence()
    prices_path = Path("data/prices_latest.json")
    if prices_path.exists():
        with open(prices_path) as f:
            prices = json.load(f)
    else:
        print(f"{prices_path} não encontrado — nada a enriquecer")
        return

    enriched = pi.enrich_prices(prices)
    with open(prices_path, "w") as f:
        json.dump(enriched, f, ensure_ascii=False, default=str, indent=2)
    print(f"Enriched {len(enriched)} prices → {prices_path}")
    anomalies = [p for p in enriched if p.get("ai_anomaly", {}).get("is_anomaly")]
    if anomalies:
        print(f"{len(anomalies)} anomalias detectadas")


if __name__ == "__main__":
    main()
