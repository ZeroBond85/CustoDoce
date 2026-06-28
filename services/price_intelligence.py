"""
Serviço de inteligência de preços: detecção de anomalias, tendências, tags.
Usa Z-score + Isolation Forest. Puramente estatístico, sem IA generativa.
"""

from services.logger import logger
import numpy as np
import joblib
from pathlib import Path
from datetime import datetime, timedelta
from sklearn.ensemble import IsolationForest
from services.price_service import get_price_history

_IF_CACHE_DIR = Path("data/if_cache")
_IF_CACHE_DIR.mkdir(parents=True, exist_ok=True)
_IF_TTL_DAYS = 7


class PriceIntelligence:
    def __init__(self, zscore_threshold: float = 2.0, history_days: int = 90):
        self.zscore_threshold = zscore_threshold
        self.history_days = history_days
        self._if_models: dict[str, IsolationForest] = {}

    def _get_cache_path(self, ingredient_id: str, store_id: str) -> Path:
        safe_ing = ingredient_id.replace("/", "_").replace(" ", "_")
        safe_store = store_id.replace("/", "_").replace(" ", "_") or "global"
        return _IF_CACHE_DIR / f"if_{safe_ing}_{safe_store}.json"

    def _load_if_model(self, ingredient_id: str, store_id: str) -> IsolationForest | None:
        """Load cached IF model if not expired."""
        cache_path = self._get_cache_path(ingredient_id, store_id).with_suffix(".joblib")
        if not cache_path.exists():
            return None
        try:
            model = joblib.load(cache_path)
            cached_at = model.cached_at if hasattr(model, "cached_at") else None
            if cached_at and (datetime.now() - cached_at > timedelta(days=_IF_TTL_DAYS)):
                return None
            return model
        except Exception:
            return None

    def _save_if_model(self, ingredient_id: str, store_id: str, model: IsolationForest, X_train: np.ndarray):
        """Save IF model to cache using joblib."""
        cache_path = self._get_cache_path(ingredient_id, store_id).with_suffix(".joblib")
        try:
            model.cached_at = datetime.now()
            joblib.dump(model, cache_path)
        except Exception as e:
            logger.debug("Failed to save IF model cache: %s", e)

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

    def _get_if_model(self, ingredient_id: str, store_id: str, values: list[float]) -> IsolationForest:
        """Get or train Isolation Forest model with caching."""
        cache_key = f"{ingredient_id}|{store_id or 'global'}"
        if cache_key in self._if_models:
            return self._if_models[cache_key]

        # Try load from disk cache
        model = self._load_if_model(ingredient_id, store_id)
        if model is not None:
            self._if_models[cache_key] = model
            return model

        # Train new model
        X = np.array(values).reshape(-1, 1)
        model = IsolationForest(contamination=0.1, random_state=42, n_estimators=50)
        model.fit(X)
        self._if_models[cache_key] = model
        self._save_if_model(ingredient_id, store_id, model, X)
        return model

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

        # Z-score check
        if abs(zscore) > self.zscore_threshold:
            tag = "PRECO_SUSPEITO" if zscore < 0 else "PRECO_ELEVADO"
            return {
                "is_anomaly": True,
                "severity": "high" if abs(zscore) > 3.0 else "medium",
                "tag": tag,
                "zscore": round(zscore, 2),
                "expected_range": f"R$ {stats['mean'] - 2 * stats['std']:.2f} ~ R$ {stats['mean'] + 2 * stats['std']:.2f}",
                "historical_mean": round(mean, 2),
            }
        if zscore < -1.0:
            return {
                "is_anomaly": False,
                "severity": "low",
                "tag": "OFERTA_REAL",
                "zscore": round(zscore, 2),
                "expected_range": f"R$ {stats['mean'] - 2 * stats['std']:.2f} ~ R$ {stats['mean'] + 2 * stats['std']:.2f}",
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
        # Group by ingredient+store for batch IF scoring
        from collections import defaultdict

        groups = defaultdict(list)
        for p in prices:
            norm = p.get("normalized") or {}
            ppk = norm.get("price_per_kg")
            if ppk:
                key = (p.get("ingredient_id", ""), p.get("store_id", ""))
                groups[key].append((p, ppk))

        for (ing_id, store_id), items in groups.items():
            values = [ppk for _, ppk in items]
            # Get historical values for training
            hist_prices = get_price_history(ing_id, days=self.history_days)
            if store_id:
                hist_prices = [p for p in hist_prices if p.get("store_id") == store_id]
            hist_values = []
            for hp in hist_prices:
                hn = hp.get("normalized") or {}
                hppk = hn.get("price_per_kg")
                if hppk and hppk > 0:
                    hist_values.append(hppk)

            if len(hist_values) >= 10:  # Need enough data for IF
                model = self._get_if_model(ing_id, store_id, hist_values)
                try:
                    scores = model.decision_function(np.array(values).reshape(-1, 1))
                    # Lower score = more anomalous
                    for (p, ppk), score in zip(items, scores, strict=False):
                        anomaly = self.detect_anomaly(ing_id, store_id, ppk)
                        # Combine Z-score with IF score
                        if score < -0.5 and anomaly["tag"] == "NORMAL":
                            anomaly["tag"] = "PRECO_SUSPEITO"
                            anomaly["is_anomaly"] = True
                            anomaly["severity"] = "medium"
                        p["ai_tags"] = [anomaly["tag"]] if anomaly.get("tag") else []
                        p["ai_anomaly"] = anomaly
                except Exception:
                    for p, ppk in items:
                        anomaly = self.detect_anomaly(ing_id, store_id, ppk)
                        p["ai_tags"] = [anomaly["tag"]] if anomaly.get("tag") else []
                        p["ai_anomaly"] = anomaly
            else:
                for p, ppk in items:
                    anomaly = self.detect_anomaly(ing_id, store_id, ppk)
                    p["ai_tags"] = [anomaly["tag"]] if anomaly.get("tag") else []
                    p["ai_anomaly"] = anomaly
            enriched.extend([p for p, _ in items])

        # Add non-matching prices
        for p in prices:
            if p not in enriched:
                enriched.append(p)
        return enriched
