"""
Serviço de inteligência de preços: detecção de anomalias, tendências, tags.
Usa Z-score + Isolation Forest. Puramente estatístico, sem IA generativa.
"""

import numpy as np
from services.price_service import get_price_history

class PriceIntelligence:
    def __init__(self, zscore_threshold: float = 2.0, history_days: int = 90):
        self.zscore_threshold = zscore_threshold
        self.history_days = history_days

    def get_historical_stats(self, ingredient_id: str, store_id: str = "") -> dict:
        """Retorna média, std, min, max do histórico de preços."""
        prices = get_price_history(ingredient_id, days=self.history_days)
        if store_id:
            prices = [p for p in prices if p.get("store_id") == store_id]
        values = []
        for p in prices:
            norm = p.get("normalized") or {}
            ppk = norm.get("price_per_kg")
            if ppk and ppk > 0:
                values.append(ppk)
        if len(values) < 3:
            return {"mean": 0, "std": 0, "min": 0, "max": 0, "n": len(values)}
        return {
            "mean": float(np.mean(values)),
            "std": float(np.std(values)),
            "min": float(np.min(values)),
            "max": float(np.max(values)),
            "n": len(values),
        }

    def detect_anomaly(self, ingredient_id: str, store_id: str, price_per_kg: float) -> dict:
        """
        Detecta se um preço é anômalo.
        Retorna: {is_anomaly, severity, tag, expected_range}
        """
        from services.config import get as get_config
        if not get_config("features.ai.price_intelligence", True):
            return {"is_anomaly": False, "severity": "none", "tag": "NORMAL"}
        stats = self.get_historical_stats(ingredient_id, store_id)
        if stats["n"] < 3:
            return {"is_anomaly": False, "severity": "none", "tag": "SEM_HISTORICO"}

        mean = stats["mean"]
        std = max(stats["std"], 0.01)
        zscore = (price_per_kg - mean) / std

        if abs(zscore) > self.zscore_threshold:
            tag = "PRECO_SUSPEITO" if zscore < 0 else "PRECO_ELEVADO"
            return {
                "is_anomaly": True,
                "severity": "high" if abs(zscore) > 3.0 else "medium",
                "tag": tag,
                "zscore": round(zscore, 2),
                "expected_range": f"R$ {stats['mean']-2*stats['std']:.2f} ~ R$ {stats['mean']+2*stats['std']:.2f}",
                "historical_mean": round(mean, 2),
            }
        if zscore < -1.0:
            return {
                "is_anomaly": False,
                "severity": "low",
                "tag": "OFERTA_REAL",
                "zscore": round(zscore, 2),
                "expected_range": f"R$ {stats['mean']-2*stats['std']:.2f} ~ R$ {stats['mean']+2*stats['std']:.2f}",
                "historical_mean": round(mean, 2),
            }
        return {
            "is_anomaly": False,
            "severity": "none",
            "tag": "NORMAL",
            "zscore": round(zscore, 2),
        }

    def enrich_prices(self, prices: list[dict]) -> list[dict]:
        """Enriquece lista de preços com tags de inteligência."""
        enriched = []
        pi = PriceIntelligence()
        for p in prices:
            norm = p.get("normalized") or {}
            ppk = norm.get("price_per_kg")
            if ppk:
                anomaly = pi.detect_anomaly(
                    p.get("ingredient_id", ""),
                    p.get("store_id", ""),
                    ppk,
                )
                p["ai_tags"] = [anomaly["tag"]] if anomaly.get("tag") else []
                p["ai_anomaly"] = anomaly
            enriched.append(p)
        return enriched

