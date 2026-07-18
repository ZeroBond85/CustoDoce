"""
Collector Service - Coordinates scrapers and processes product matches.
"""

import importlib
import multiprocessing as mp
import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import suppress
from datetime import UTC, date
from datetime import datetime as dt_now
from inspect import signature

import httpx

from services.http_client import get_client
from parsers.brand_extractor import extract_brand
from parsers.matcher import (
    clean_text,
    extract_all_keywords,
    has_excluded_terms,
    has_ingredient_keyword,
    match_ingredient,
    rank_ingredients,
)
from parsers.normalizer import normalize_price
from parsers.semantic_matcher import get_matcher
from scrapers.aggregator_scraper import TiendeoScraper
from scrapers.carrefour_scraper import CarrefourScraper
from scrapers.ecomplus_scraper import EcomplusScraper
from scrapers.extra_flyer_scraper import ExtraFlyerScraper
from scrapers.facebook_flyer_scraper import FacebookFlyerScraper
from scrapers.flyer_scraper import FlyerScraper
from scrapers.giga_flyer_scraper import GigaFlyerScraper
from scrapers.max_api_scraper import MaxApiScraper
from scrapers.pao_flyer_scraper import PaoFlyerScraper
from scrapers.playwright_price_scraper import PlaywrightPriceScraper
from scrapers.roldao_api_scraper import RoldaoApiScraper
from scrapers.roldao_flyer_scraper import RoldaoFlyerScraperSync
from scrapers.tenda_api_scraper import TendaApiScraper
from scrapers.vipcommerce_api_scraper import VipCommerceApiScraper
from scrapers.vtex_scraper import VtexScraper
from scrapers.website_scraper import WebsiteScraper
from services.config_db import get_active_ingredients, get_active_stores
from services.flyer_service import upsert_flyer
from services.logger import logger
from services.price_service import insert_review_item, log_scraper_run, upsert_price
from services.scraper_health import TRANSIENT_ERROR_CLASSES, classify_error_for_alert
from services.supabase_client import get_service_client, get_supabase
from services.types import Ingredient, PriceEntry, Store
from services.url_guard import guard_url

API_SCRAPER_MAP = {
    "tenda_api_scraper": TendaApiScraper,
    "roldao_api_scraper": RoldaoApiScraper,
    "max_api_scraper": MaxApiScraper,
}

# Estatísticas da última coleta por loja (raw extraído vs. casado), populado por
# _scrape_store. Usado por ferramentas de diagnóstico (test_single_store) para
# distinguir "0 extraído" (falha real) de "extraído mas 0 casou" (flyer sem
# ingredientes monitorados). Não persiste; reflete só a última execução no processo.
LAST_RUN_STATS: dict[str, dict[str, int]] = {}


def load_ingredients() -> list[Ingredient]:
    return get_active_ingredients()


def _merge_store_config(store: Store) -> Store:
    """Promove chaves da coluna `config` (jsonb) para o topo do dict da loja.

    Scrapers leem configs específicas (browse_urls, api_base, headers,
    verify_ssl, api_base_fallbacks, image_host_fallbacks, anti_bot, rate_limit,
    vision_timeout_seconds, store_slug, ...) via ``store.get(...)``. Essas chaves
    não são colunas da tabela `stores`; ficam em `config`. Sem promovê-las, o
    scraper em CI perde a configuração (ex: Rede Krill sem browse_urls cai no
    /busca?q= quebrado → 0 produtos). Colunas reais têm precedência sobre config.
    """
    cfg = store.get("config")
    if not isinstance(cfg, dict) or not cfg:
        return store
    merged = {**cfg, **store}
    return merged


def load_stores() -> list[Store]:
    all_stores = get_active_stores()
    if not all_stores:
        return []
    client = get_supabase()
    freq = client.table("scrape_frequencies").select("store_id, enabled").execute()
    freq_by_store = {}
    for f in (freq.data or []):
        sid = f.get("store_id")
        if sid:
            freq_by_store[sid] = f.get("enabled", True)
    # Include store if it has no freq row (use tier default), or if its freq row is enabled.
    # Explicitly disabled rows (enabled=False) still exclude the store.
    active = [s for s in all_stores if s.get("id") not in freq_by_store or freq_by_store.get(s["id"], True)]
    return [_merge_store_config(s) for s in active]


def _extract_validity_from_product(product_text: str) -> str:
    m = re.search(r"(?:valido?\s*(?:ate?|até)?\s*:?\s*[\d]{2}/[\d]{2}(?:/[\d]{2,4})?)", product_text, re.I)
    if m:
        return m.group(0)
    m2 = re.search(r"(?:ate?|até)\s*[\d]{2}/[\d]{2}(?:/[\d]{2,4})?", product_text, re.I)
    if m2:
        return m2.group(0)
    return ""


def build_product_entry(
    store: Store,
    ingredient: Ingredient,
    raw_product: str,
    raw_price: float,
    raw_unit: str,
    confidence: float,
    validity_raw: str = "",
    brand: str = "",
) -> PriceEntry:
    from services.price_service import _detect_promotion, _weekday_pt

    normalized = normalize_price(raw_price, raw_unit)
    validity = validity_raw or _extract_validity_from_product(raw_product)
    brand = brand or extract_brand(raw_product, ingredient)
    return {
        "ingredient_id": ingredient["canonical_name"],
        "store_id": store.get("id") or store["name"].lower().replace(" ", "_"),
        "source": store.get("type", "automated"),
        "store_name": store["name"],
        "raw_product": raw_product,
        "raw_price": raw_price,
        "raw_unit": raw_unit,
        "validity_raw": validity,
        "collected_weekday": _weekday_pt(dt_now.now()),
        "is_promotion": _detect_promotion(raw_product, raw_unit),
        "tier": store.get("tier", 3),
        "confidence": confidence,
        "normalized": normalized.to_dict() if normalized else None,
        "city": store.get("cities", [""])[0] if isinstance(store.get("cities"), list) else store.get("city", ""),
        "logistics": store.get("logistics", "pickup_local"),
        "brand": brand,
    }


_keyword_cache: tuple[int, set] | None = None


def _get_ingredient_keywords(ingredients: list[Ingredient]) -> set:
    global _keyword_cache
    ing_id = id(ingredients)
    if _keyword_cache is not None and _keyword_cache[0] == ing_id:
        return _keyword_cache[1]
    keywords = extract_all_keywords(ingredients)
    _keyword_cache = (ing_id, keywords)
    return keywords


def process_price_match(
    store: Store,
    product_text: str,
    raw_price: float,
    raw_unit: str,
    ingredients: list[Ingredient],
    validity_raw: str = "",
    brand: str = "",
    image_url: str = "",
    source_url: str = "",
) -> PriceEntry | None:
    keywords = _get_ingredient_keywords(ingredients)
    if not has_ingredient_keyword(product_text, keywords):
        return None

    for ing in ingredients:
        if has_excluded_terms(product_text, ing):
            return None

    ingredient, score, match_type = match_ingredient(product_text, ingredients)

    if ingredient and score >= 80.0:
        entry = build_product_entry(
            store,
            ingredient,
            product_text,
            raw_price,
            raw_unit,
            score / 100.0,
            validity_raw=validity_raw,
            brand=brand,
        )
        try:
            upsert_price(entry)
        except Exception as e_upsert:
            logger.warning("[%s] upsert_price failed for product, skipping: %s", store.get("name", "?"), e_upsert)
            return None
        return entry

    semantic_score = 0.0
    combined = score / 100.0
    from services.config import get_feature

    ai_enabled = get_feature(
        "features.ai.enabled", ingredient=ingredient["canonical_name"] if ingredient else None, default=True
    )
    if ai_enabled:
        if ingredient and score >= 55.0:
            sm = get_matcher()
            semantic_score = sm.get_similarity(product_text, ingredient)
            combined = sm.combined_score(score, semantic_score)
        elif ingredient:
            combined = score / 100.0

        if ingredient and combined >= 0.80:
            entry = build_product_entry(
                store,
                ingredient,
                product_text,
                raw_price,
                raw_unit,
                combined,
                validity_raw=validity_raw,
                brand=brand,
            )
            try:
                upsert_price(entry)
            except Exception as e_upsert:
                logger.warning("[%s] upsert_price failed for product (combined>=0.80), skipping: %s", store.get("name", "?"), e_upsert)
                return None
            return entry

        if 0.65 <= combined < 0.80 and os.environ.get("GROQ_API_KEY"):
            from parsers.llm_classifier import classify as _llm_classify

            candidates = rank_ingredients(product_text, ingredients, top_n=3)
            # Usa a instância singleton do classifier para que o circuit breaker
            # do LLM persista entre produtos: após o Groq abrir (429), ele é
            # pulado de fato e a cadeia cede ao OpenRouter/HF (backoff agressivo
            # evita martelar o free-tier esgotado a cada produto).
            llm_result = _llm_classify(product_text, [c[0] for c in candidates])
            if llm_result and llm_result.get("confidence", 0) >= 0.85:
                chosen = next((c for c in candidates if c[0]["canonical_name"] == llm_result["ingredient"]), None)
                if chosen:
                    entry = build_product_entry(
                        store,
                        chosen[0],
                        product_text,
                        raw_price,
                        raw_unit,
                        llm_result["confidence"],
                        validity_raw=validity_raw,
                        brand=brand,
                    )
                    try:
                        upsert_price(entry)
                    except Exception as e_upsert:
                        logger.warning("[%s] upsert_price failed for product (llm), skipping: %s", store.get("name", "?"), e_upsert)
                        return None
                    return entry

    from services.config import get_feature

    threshold = get_feature(
        "features.review_threshold", ingredient=ingredient["canonical_name"] if ingredient else None, default=0.55
    )
    if combined >= threshold:
        candidates = rank_ingredients(product_text, ingredients, top_n=3)
        suggestions = [c[0]["canonical_name"] for c in candidates if c[1] >= 55.0]
        validity = validity_raw or _extract_validity_from_product(product_text)

        match_type = ""
        match_reason = ""
        if candidates:
            top = candidates[0]
            top_ing, top_score, top_type, top_term = top
            match_type = top_type
            type_labels = {
                "proximo_nome": "semelhante ao nome do ingrediente",
                "proximo_apelido": "semelhante a um apelido do ingrediente",
                "exato": "exato",
                "contido": "nome do ingrediente contido no produto",
            }
            type_label = type_labels.get(top_type, top_type)
            product_words = set(clean_text(product_text).split())
            canonical_words = set(clean_text(top_ing["canonical_name"]).split())
            unmatched_words = product_words - canonical_words
            match_reason = (
                f"Tipo: {type_label} | "
                f"Score: {top_score:.0f}% | "
                f"Candidato: '{top_ing['canonical_name']}' | "
                f"Termo match: '{top_term}'"
            )
            if unmatched_words:
                match_reason += f" | Palavras não matcheadas: {', '.join(sorted(unmatched_words))}"
        else:
            match_reason = f"Score {score:.0f}% - nenhum candidato acima de 55%"

        top3_summary = []
        for c in candidates:
            top3_summary.append(
                {
                    "canonical_name": c[0]["canonical_name"],
                    "score": c[1],
                    "match_type": c[2],
                    "matched_term": c[3],
                }
            )

        if not brand and candidates:
            brand = extract_brand(product_text, candidates[0][0])

        if candidates:
            combined_pct = int(combined * 100)
            match_reason = (
                f"Tipo: {type_label} | Score: {combined_pct}% "
                f"(RF: {score:.0f}%, Semântico: {int(semantic_score * 100)}%) "
                f"| Candidato: '{top_ing['canonical_name']}' | Termo: '{top_term}'"
            )
            if unmatched_words:
                match_reason += f" | Palavras não matcheadas: {', '.join(sorted(unmatched_words))}"

        review_item = {
            "raw_product": product_text,
            "raw_price": raw_price,
            "raw_unit": raw_unit,
            "store_name": store["name"],
            "source": store.get("type", "automated"),
            "confidence": combined,
            "suggestions": suggestions,
            "validity_raw": validity,
            "brand": brand,
            "image_url": image_url,
            "source_url": source_url,
            "match_reason": match_reason,
            "match_type": match_type,
            "top3": top3_summary,
        }
        try:
            insert_review_item(review_item)
        except Exception as e:
            logger.warning("Review queue error: %s", e)

    return None


def _get_default_frequency_minutes(store: Store) -> int:
    """Default scrape frequency by tier if not in scrape_frequencies table."""
    tier = store.get("tier", 3)
    return {1: 10080, 2: 1440, 3: 1440, 4: 43200}.get(tier, 1440)


def _should_skip_store(store: Store) -> tuple[bool, str]:
    """Check if this store was recently scraped. Returns (skip, reason)."""
    if os.environ.get("CUSTODOCE_FORCE_SCRAPE") == "1":
        return False, ""
    store_id = store.get("id") or store["name"].lower().replace(" ", "_")
    try:
        client = get_supabase()
        # Get frequency
        freq = (
            client.table("scrape_frequencies")
            .select("frequency_minutes")
            .eq("store_id", store_id)
            .limit(1)
            .execute()
        )
        frequency_minutes = (
            freq.data[0]["frequency_minutes"]
            if freq.data and freq.data[0].get("frequency_minutes")
            else _get_default_frequency_minutes(store)
        )
        # Get last successful run
        last = (
            client.table("scraping_logs")
            .select("started_at")
            .eq("store_name", store["name"])
            .eq("status", "completed")
            .order("started_at", desc=True)
            .limit(1)
            .execute()
        )
        if not last.data:
            return False, ""  # Never scraped before
        last_run = dt_now.fromisoformat(last.data[0]["started_at"].replace("Z", "+00:00"))
        elapsed = (dt_now.now(UTC) - last_run).total_seconds() / 60
        if elapsed < frequency_minutes * 0.8:
            remaining = int(frequency_minutes * 0.8 - elapsed)
            return True, (
                f"skip: last run {int(elapsed)}m ago (freq={frequency_minutes}m), "
                f"{remaining}m remaining until threshold"
            )
        return False, ""
    except Exception as e:
        logger.debug("[should_skip] %s: %s", store.get("name", "unknown"), e)
        return False, ""


def _auto_disable_if_needed(store_name: str, threshold: int = 3):
    try:
        client = get_service_client()
        logs = (
            client.table("scraping_logs")
            .select("status")
            .eq("store_name", store_name)
            .order("started_at", desc=True)
            .limit(threshold)
            .execute()
        )
        if not logs.data or len(logs.data) < threshold:
            return
        if all(log["status"] in ("error", "failed") for log in logs.data):
            store = client.table("stores").select("id, is_active").eq("name", store_name).single().execute()
            if store.data and store.data.get("is_active") is not False:
                client.table("stores").update({"is_active": False}).eq("id", store.data["id"]).execute()
                logger.warning("[AUTO-DISABLE] %s desativada apos %d falhas consecutivas", store_name, threshold)
    except Exception as e:
        logger.debug("auto-disable check failed for %s: %s", store_name, e)


def _check_zero_products_alert(store_name: str, threshold: int = 3):
    try:
        client = get_service_client()
        logs = (
            client.table("scraping_logs")
            .select("status, items_found")
            .eq("store_name", store_name)
            .order("started_at", desc=True)
            .limit(threshold)
            .execute()
        )
        if not logs.data or len(logs.data) < threshold:
            return
        if all(log["status"] == "completed" and log.get("items_found", 0) == 0 for log in logs.data):
            logger.warning(
                "[ZERO-PRODUCTS ALERT] %s retornou 0 produtos por %d coletas consecutivas", store_name, threshold
            )
    except Exception as e:
        logger.debug("zero-products check failed for %s: %s", store_name, e)


def _verify_scrape_results(all_products: list[PriceEntry], store_count: int, skipped_count: int) -> None:
    """Post-scrape verification checklist (Phase 3a)."""
    if store_count == 0:
        return
    attempted = store_count - skipped_count
    if attempted == 0:
        logger.info("[VERIFY] all %d stores skipped (freshness); 0 attempted", store_count)
        return
    if not all_products:
        logger.warning("[VERIFY] 0 products collected across %d stores (%d skipped)", store_count, skipped_count)
        return
    matched_stores = len({p.get("store_name") for p in all_products if p.get("store_name")})
    if matched_stores < attempted:
        logger.info(
            "[VERIFY] %d/%d stores produced matches (%d skipped)",
            matched_stores, attempted, skipped_count,
        )


def _mp_worker(q, kind, target_mod, target_name, store, extra):
    """Roda alvo isolado em processo filho e devolve resultado via queue.

    Rodar em processo (e nao thread) garante que, em caso de travamento
    (ex.: launch do browser preso), o processo inteiro — incluindo o Chrome
    filho — possa ser terminado sem deixar zumbi que trava as lojas seguintes.
    """
    try:
        mod = importlib.import_module(target_mod)
        target = getattr(mod, target_name)
        if kind == "scraper":
            ingredients, needs = extra
            with target(store) as scraper:
                sig = signature(scraper.run)
                raw = scraper.run(ingredients) if needs and "ingredients" in sig.parameters else scraper.run()
                thumb = getattr(scraper, "_thumbnail", None)
            q.put(("ok", (raw if raw is not None else [], thumb)))
        else:  # callable (ex.: run_fn de agregador)
            result = target(store)
            q.put(("ok", result if result is not None else []))
    except Exception as exc:  # noqa: BLE001 - relata falha ao pai
        q.put(("err", str(exc)))


def _spawn_isolated(kind, target_mod, target_name, store, store_name, timeout_seconds, extra=None):
    """Spawn de processo filho com timeout hard; termina o processo no expiry."""
    mp_q = mp.get_context("spawn").Queue()
    p = mp.get_context("spawn").Process(
        target=_mp_worker,
        args=(mp_q, kind, target_mod, target_name, store, extra),
        daemon=True,
    )
    p.start()
    p.join(timeout=timeout_seconds)
    if p.is_alive():
        scraper_type = target_mod.replace("scrapers.", "")
        logger.error(
            "[%s] TIMEOUT after %ds — encerrando processo (scraper=%s, store=%s)",
            store_name, timeout_seconds, scraper_type, store.get("name", store_name),
        )
        p.terminate()
        with suppress(Exception):
            p.join(timeout=10)
        return None
    try:
        status, payload = mp_q.get(timeout=15)
    except Exception:  # noqa: BLE001
        return None
    if status == "err":
        raise RuntimeError(f"falha no scraper: {payload}")
    return payload


def _run_scraper_isolated(scraper_cls, store, ingredients, needs_ingredients, store_name, timeout_seconds=300):
    """Executa o scraper em processo filho com timeout hard.

    O launch do browser (``cls(store)``) e o ``scraper.run()`` ficam DENTRO do
    processo filho, entao um travamento em qualquer ponto e coberto pelo timeout:
    ao estourar, o processo e terminado (junto com o Chrome), liberando recursos
    para as lojas seguintes. Retorna ``(raw_products, thumbnail)``.
    """
    res = _spawn_isolated("scraper", scraper_cls.__module__, scraper_cls.__name__, store, store_name, timeout_seconds, extra=(ingredients, needs_ingredients))
    if res is None:
        return [], None
    return res


def _run_callable_isolated(func, store, store_name, timeout_seconds=300):
    """Executa ``func(store)`` em processo filho com timeout hard (agregadores)."""
    res = _spawn_isolated("callable", func.__module__, func.__name__, store, store_name, timeout_seconds)
    if res is None:
        return []
    return res[0] if isinstance(res, tuple) else res


def _scrape_store(
    store: Store,
    scraper_cls: type,
    ingredients: list[Ingredient],
    label: str,
    needs_ingredients_param: bool,
    post_process,
    store_timeout: int,
) -> tuple[str, list[PriceEntry]]:
    """Coleta UMA loja (thread-safe). Retorna (nome, produtos)."""
    store_name = store.get("name", "unknown")
    started_at = dt_now.now(UTC)
    scraper_name = {
        "FlyerScraper": "pdf_flyers",
        "AggregatorScraper": "aggregators",
        "VtexScraper": "vtex",
    }.get(scraper_cls.__name__, scraper_cls.__name__.lower().replace("scraper", ""))

    logger.info("[%s] >>> INICIANDO coleta (timeout=%ds)", store_name, store_timeout)
    try:
        from services.config import get_feature

        filtered_ingredients = [
            ing
            for ing in ingredients
            if get_feature(f"features.scrapers.{scraper_name}", ingredient=ing["canonical_name"], default=True)
        ]

        # Scrapers puramente HTTP (sem browser) com timeouts delimitados são
        # seguros para rodar no processo pai: evita o overhead/instabilidade do
        # spawn de subprocesso no Windows (que degrada ~50x requisições HTTP).
        # Scrapers com browser (Playwright) continuam isolados para não travar
        # o pipeline se o Chrome pendulum.
        if getattr(scraper_cls, "safe_in_parent", False):
            try:
                scraper = scraper_cls(store)
                raw_products = scraper.run(filtered_ingredients) if needs_ingredients_param else scraper.run()
                thumbnail = None
            except Exception as exc:  # noqa: BLE001
                logger.error("[%s] erro no scraper (safe_in_parent): %s", store_name, exc)
                with suppress(Exception):
                    from services.scraper_health import record_failure

                    record_failure(store_name, reason=str(exc), attempted_by="collector")
                raw_products = []
            raw_products = raw_products or []
        else:
            raw_products, thumbnail = _run_scraper_isolated(
                scraper_cls, store, filtered_ingredients, needs_ingredients_param, store_name, timeout_seconds=store_timeout
            )

        elapsed = int((dt_now.now(UTC) - started_at).total_seconds())
        cache_status = "hit" if not raw_products else "miss"
        logger.info("[%s] <<< FIM coleta (%ds) — Cache %s: %d raw products found", store_name, elapsed, cache_status, len(raw_products))

        if thumbnail:
            try:
                from services.flyer_service import _upload_flyer_thumbnail

                thumb_url = _upload_flyer_thumbnail(store_name, thumbnail)
                if thumb_url:
                    upsert_flyer(
                        {
                            "store_name": store_name,
                            "region": store.get("region", ""),
                            "city": store.get("city", ""),
                            "flyer_title": f"Panfleto {date.today().strftime('%d/%m/%Y')}",
                            "image_url": thumb_url,
                            "source": "pdf_scrape",
                        }
                    )
            except Exception as e:
                logger.debug("[%s] Flyer record save failed: %s", store_name, e)

        if not raw_products:
            logger.info("[%s] No products found", store_name)
            LAST_RUN_STATS[store_name] = {"extracted": 0, "matched": 0}
            log_scraper_run(store_name, "completed", 0, 0, started_at=started_at)
            _check_zero_products_alert(store_name)
            with suppress(Exception):
                from services.scraper_health import record_success

                record_success(
                    store_name, items_found=0, products_matched=0, flyer_count=0, attempted_by="collector"
                )
            return store_name, []

        matched = 0
        entries: list[PriceEntry] = []
        for prod in raw_products:
            if post_process:
                entry = post_process(store, prod, ingredients)
            else:
                entry = process_price_match(
                    store,
                    prod.get("product", ""),
                    prod.get("price", 0),
                    prod.get("unit", ""),
                    ingredients,
                    validity_raw=prod.get("validity_raw", ""),
                    brand=prod.get("brand", ""),
                    source_url=prod.get("source_url", ""),
                )
            if entry:
                matched += 1
                entries.append(entry)

        logger.info("[%s] %d products, %d matched", store_name, len(raw_products), matched)
        LAST_RUN_STATS[store_name] = {"extracted": len(raw_products), "matched": matched}
        log_scraper_run(store_name, "completed", len(raw_products), matched, started_at=started_at)
        _check_zero_products_alert(store_name)
        with suppress(Exception):
            from services.scraper_health import record_success

            record_success(
                store_name,
                items_found=len(raw_products),
                products_matched=matched,
                flyer_count=0,
                attempted_by="collector",
            )
        return store_name, entries

    except Exception as e:
        error_class = classify_error_for_alert(str(e))
        if error_class in TRANSIENT_ERROR_CLASSES:
            # Falha contornável (rede/timeout/rate-limit/recurso): a loja permanece
            # ativa e retenta na próxima janela. Não desativa, não alerta por email.
            logger.warning(
                "[%s] erro TRANSITÓRIO (%s): %s — loja mantida ativa, retenta próxima janela",
                store_name, error_class, e,
            )
            log_scraper_run(store_name, "transient", 0, 0, str(e), started_at=started_at)
            with suppress(Exception):
                from services.scraper_health import record_transient_failure

                record_transient_failure(
                    store_name,
                    error_class=error_class,
                    reason=str(e),
                    attempted_by="collector",
                )
            return store_name, []
        logger.error("[%s] %s: %s", label, store_name, e)
        log_scraper_run(store_name, "error", 0, 0, str(e), started_at=started_at)
        with suppress(Exception):
            from services.email_service import send_scraper_error

            send_scraper_error(store_name, str(e))
        _auto_disable_if_needed(store_name)
        with suppress(Exception):
            from services.scraper_health import record_failure

            record_failure(
                store_name,
                reason=str(e),
                items_found=0,
                products_matched=0,
                flyer_count=0,
                attempted_by="collector",
            )
        return store_name, []


def _collect_generic(
    stores: list[Store],
    scraper_cls: type,
    ingredients: list[Ingredient],
    label: str,
    needs_ingredients_param: bool = True,
    post_process=None,
    store_timeout: int = 300,
    max_workers: int = 2,
) -> list[PriceEntry]:
    all_products: list[PriceEntry] = []
    skipped_count = 0

    # Freshness check (sequencial, barato) — define quais lojas vao rodar.
    pending: list[Store] = []
    for store in stores:
        store_name = store.get("name", "unknown")
        started_at = dt_now.now(UTC)
        skip, skip_reason = _should_skip_store(store)
        if skip:
            logger.info("[%s] %s", store_name, skip_reason)
            log_scraper_run(store_name, "skipped", 0, 0, errors=[skip_reason], started_at=started_at)
            skipped_count += 1
            continue
        pending.append(store)

    logger.info("[%s] %d lojas pendentes para coleta (parallel max_workers=%d)", label, len(pending), max_workers)
    if not pending:
        _verify_scrape_results(all_products, len(stores), skipped_count)
        return all_products

    with ThreadPoolExecutor(max_workers=min(max_workers, max(1, len(pending)))) as ex:
        futures = {
            ex.submit(
                _scrape_store,
                store,
                scraper_cls,
                ingredients,
                label,
                needs_ingredients_param,
                post_process,
                store_timeout,
            ): store.get("name", "unknown")
            for store in pending
        }
        for fut in as_completed(futures):
            store_name = futures[fut]
            _name, prods = fut.result()
            if prods:
                logger.info("[%s] coleta OK: %d produtos", store_name, len(prods))
            else:
                logger.warning("[%s] coleta vazia: 0 produtos", store_name)
            all_products.extend(prods)

    _verify_scrape_results(all_products, len(stores), skipped_count)
    return all_products


def _collect_prices(
    stores: list[Store],
    scraper_cls: type,
    ingredients: list[Ingredient],
    label: str,
    store_timeout: int = 300,
) -> list[PriceEntry]:
    return _collect_generic(stores, scraper_cls, ingredients, label, store_timeout=store_timeout)


def _collect_flyers(
    stores: list[Store],
    scraper_cls: type | None,
    label: str,
    run_fn=None,
) -> list[dict]:
    all_flyers: list[dict] = []
    for store in stores:
        store_name = store.get("name", "unknown")
        try:
            if scraper_cls:
                entries, _thumb = _run_scraper_isolated(scraper_cls, store, [], False, store_name, timeout_seconds=300)
            elif run_fn:
                entries = _run_callable_isolated(run_fn, store, store_name, timeout_seconds=300)
            else:
                continue

            if not entries:
                logger.info("[%s] No flyer entries found", store_name)
                continue

            saved = 0
            for entry in entries:
                try:
                    if "store_name" not in entry:
                        entry["store_name"] = store_name
                    if "region" not in entry:
                        entry["region"] = store.get("city", store.get("zone", ""))
                    if not entry.get("image_url") and not entry.get("flyer_url"):
                        continue
                    upsert_flyer(entry)
                    saved += 1
                except Exception as e:
                    logger.warning("Flyer save error: %s", e)

            logger.info("[%s] %d flyer entries, %d saved", store_name, len(entries), saved)

        except Exception as e:
            error_class = classify_error_for_alert(str(e))
            if error_class in TRANSIENT_ERROR_CLASSES:
                logger.warning(
                    "[%s] erro TRANSITÓRIO (%s): %s — flyer mantido ativo, retenta próxima janela",
                    store_name, error_class, e,
                )
                log_scraper_run(store_name, "transient", 0, 0, str(e))
                with suppress(Exception):
                    from services.scraper_health import record_transient_failure

                    record_transient_failure(
                        store_name, error_class=error_class, reason=str(e), attempted_by="collector"
                    )
            else:
                logger.error("[%s] %s: %s", label, store_name, e)
                with suppress(Exception):
                    from services.email_service import send_scraper_error

                    send_scraper_error(store_name, str(e))
                with suppress(Exception):
                    from services.scraper_health import record_failure

                    record_failure(store_name, reason=str(e), attempted_by="collector")

    return all_flyers


def collect_tier1_pdfs(ingredients: list[Ingredient]) -> list[PriceEntry]:
    today = date.today()
    weekday = today.strftime("%A").lower()
    stores = []
    for s in [x for x in load_stores() if x.get("tier") == 1 and x.get("type") == "pdf_flyer"]:
        pd = s.get("publish_day") or "wednesday"
        if weekday in (pd if isinstance(pd, str) else [pd]) or weekday == "thursday":
            stores.append(s)
    return _collect_prices(stores, FlyerScraper, ingredients, "PDF")


def collect_extra_flyers(ingredients: list[Ingredient]) -> list[PriceEntry]:
    stores = [s for s in load_stores() if s.get("scraper") == "extra_flyer_scraper" and s.get("type") == "extra_flyer"]
    return _collect_prices(stores, ExtraFlyerScraper, ingredients, "ExtraFlyer")


def collect_pao_flyers(ingredients: list[Ingredient]) -> list[PriceEntry]:
    stores = [s for s in load_stores() if s.get("scraper") == "pao_flyer_scraper" and s.get("type") == "pao_flyer"]
    return _collect_prices(stores, PaoFlyerScraper, ingredients, "PaoFlyer")


def collect_tier1_api_flyers(ingredients: list[dict]) -> list[dict]:
    """Coleta lojas api_flyer (Max/Roldão/Tenda) pelo pipeline de PREÇOS.

    Estes scrapers extraem produtos (name+price) via vision-LLM a partir dos
    encartes da API. Antes iam pelo pipeline de flyer-IMAGE (_collect_flyers),
    que descarta silenciosamente qualquer entry sem ``image_url`` — perdendo
    todos os produtos extraídos (ver regressão scrape 29582782313: Roldão
    extraiu 120 produtos → 0 coletados). Agora cada loja roda via _collect_prices
    (match + upsert), como Giga/Roldão flyer, garantindo que os produtos virem
    preços persistidos.
    """
    stores = [s for s in load_stores() if s.get("tier") == 1 and s.get("type") == "api_flyer"]
    if not stores:
        return []
    # Agrupa por classe de scraper resolvida (cada loja pode usar Max/Roldão/Tenda).
    by_cls: dict[type, list[Store]] = {}
    for s in stores:
        scraper_name = (s.get("scraper") or "").strip().lower()
        cls = API_SCRAPER_MAP.get(scraper_name)
        if cls is None:
            logger.warning("[%s] No API scraper class found for '%s'", s.get("name", "unknown"), scraper_name)
            continue
        by_cls.setdefault(cls, []).append(s)

    all_products: list[dict] = []
    for cls, cls_stores in by_cls.items():
        timeout = int(cls_stores[0].get("vision_timeout_seconds", 300))
        all_products.extend(_collect_prices(cls_stores, cls, ingredients, "API-Flyer", store_timeout=timeout))
    return all_products


def collect_tier2_vtex(ingredients: list[Ingredient]) -> list[PriceEntry]:
    stores = [s for s in load_stores() if s.get("scraper") == "vtex_scraper" and s.get("type") == "vtex_api"]
    return _collect_prices(stores, VtexScraper, ingredients, "VTEX", store_timeout=300)


def collect_tier3_websites(ingredients: list[Ingredient]) -> list[PriceEntry]:
    stores = [s for s in load_stores() if s.get("scraper") == "website_scraper" and s.get("type") == "website_catalog"]
    return _collect_prices(stores, WebsiteScraper, ingredients, "Website")


def collect_vipcommerce(ingredients: list[Ingredient]) -> list[PriceEntry]:
    stores = [
        s for s in load_stores()
        if s.get("scraper") == "vipcommerce_api_scraper" and s.get("type") == "vipcommerce_api"
    ]
    return _collect_prices(stores, VipCommerceApiScraper, ingredients, "VipCommerce", store_timeout=300)


def collect_carrefour(ingredients: list[Ingredient]) -> list[PriceEntry]:
    stores = [
        s for s in load_stores() if s.get("scraper") == "carrefour_scraper" and s.get("type") == "website_catalog"
    ]
    return _collect_prices(stores, CarrefourScraper, ingredients, "Carrefour")


def collect_tier2_js(ingredients: list[Ingredient]) -> list[PriceEntry]:
    stores = [
        s
        for s in load_stores()
        if s.get("type") == "website_js" and s.get("scraper") in ("playwright_price_scraper", "ecomplus_scraper")
    ]
    all_products: list[PriceEntry] = []
    for store in stores:
        scraper_cls = (
            PlaywrightPriceScraper
            if store.get("scraper") == "playwright_price_scraper"
            else EcomplusScraper
        )
        # Playwright stores need more time: browser launch + page rendering.
        # Cada loja pode sobrepor playwright_timeout (default 600 p/ Playwright, 300 ecomplus).
        default_pw = 600 if store.get("scraper") == "playwright_price_scraper" else 300
        store_timeout = int(store.get("playwright_timeout", default_pw))
        all_products += _collect_prices([store], scraper_cls, ingredients, "WebJS", store_timeout=store_timeout)
    return all_products


def collect_aggregators_ssr() -> list[dict]:
    stores = [s for s in load_stores() if s.get("scraper") == "aggregator_scraper" and s.get("type") == "aggregator"]
    return _collect_flyers(stores, None, "SSR", run_fn=_run_ssr_scraper)


def _run_ssr_scraper(store: dict) -> list[dict]:
    scraper = TiendeoScraper(store)
    return scraper.run()


def collect_aggregators_js() -> list[dict]:
    stores = [s for s in load_stores() if s.get("scraper") == "playwright_scraper" and s.get("type") == "aggregator_js"]
    return _collect_flyers(stores, None, "JS", run_fn=_run_js_scraper)


def _run_js_scraper(store: dict) -> list[dict]:
    from scrapers.playwright_scraper import PlaywrightAggregatorScraper

    scraper = PlaywrightAggregatorScraper(store)
    return scraper.run()


def collect_roldao_flyer(ingredients: list[Ingredient]) -> list[PriceEntry]:
    stores = [
        s for s in load_stores() if s.get("scraper") == "roldao_flyer_scraper" and s.get("type") == "aggregator_js"
    ]
    return _collect_prices(stores, RoldaoFlyerScraperSync, ingredients, "RoldaoFlyer")


def collect_giga_flyer(ingredients: list[Ingredient]) -> list[PriceEntry]:
    stores = [
        s for s in load_stores() if s.get("scraper") == "giga_flyer_scraper" and s.get("type") == "aggregator_js"
    ]
    # Vision-LLM (OCR + LLM) é lento: cada loja pode sobrepor vision_timeout_seconds
    # (default 300). O download do encarte em si é rápido; o gargalo é o LLM.
    timeout = 300
    if stores:
        timeout = int(stores[0].get("vision_timeout_seconds", 300))
    return _collect_prices(stores, GigaFlyerScraper, ingredients, "GigaFlyer", store_timeout=timeout)


def collect_facebook_flyers(ingredients: list[Ingredient]) -> list[PriceEntry]:
    stores = [
        s for s in load_stores()
        if s.get("scraper") == "facebook_flyer_scraper"
        and s.get("type") == "facebook_flyer"
        and s.get("is_active", True)
    ]
    return _collect_prices(stores, FacebookFlyerScraper, ingredients, "FacebookFlyer")


def _resolve_flyer_image(http: httpx.Client, flyer: dict) -> dict:
    """Resolve flyer_url → real image_url by downloading the catalog page (SSR)."""
    flyer_url = flyer.get("flyer_url", "")
    if not flyer_url or flyer.get("image_url", ""):
        return flyer
    safe_url = guard_url(flyer_url)
    if not safe_url:
        logger.warning("[resolver] skipping disallowed flyer_url: %s", flyer_url)
        return flyer
    try:
        from selectolax.parser import HTMLParser
        resp = http.get(safe_url, timeout=30.0, follow_redirects=True)
        resp.raise_for_status()
        tree = HTMLParser(resp.text)
        img = tree.css_first('img[class*="object-contain"]:not([class*="blur"])')
        if img:
            src = img.attributes.get("src", "")
            if src:
                if src.startswith("//"):
                    src = "https:" + src
                safe_img = guard_url(src)
                if safe_img:
                    flyer["image_url"] = safe_img
                else:
                    logger.warning("[resolver] disallowed image src: %s", src)
    except Exception as e:
        logger.warning("[resolver] Failed to resolve %s: %s", flyer_url, e)
    return flyer


def process_ocr_queue() -> int:
    from services.flyer_service import get_pending_flyers, mark_failed, mark_processed
    from scrapers.flyer_ocr import extract_flyer_products

    pending = get_pending_flyers(limit=10)
    if not pending:
        return 0

    http = get_client()
    ingredients = load_ingredients()
    processed = 0
    for flyer in pending:
        try:
            flyer = _resolve_flyer_image(http, flyer)
            if not flyer.get("image_url"):
                logger.warning("[OCR] No image_url for flyer %s, marking failed", flyer.get("id"))
                mark_failed(flyer["id"])
                continue

            store_name = flyer.get("store_name", "")
            image_entries = [flyer]
            products = extract_flyer_products(
                http, image_entries, store_name, source=flyer.get("source", "tiendeo"),
            )

            if not products:
                logger.warning("[OCR] No products extracted from %s", flyer.get("id"))
                mark_failed(flyer["id"])
                continue

            matched = 0
            for prod in products:
                entry = process_price_match(
                    store={"name": store_name, "type": "aggregator", "tier": 3},
                    product_text=prod.get("product", ""),
                    raw_price=prod.get("price", 0),
                    raw_unit=prod.get("unit", ""),
                    ingredients=ingredients,
                    validity_raw=prod.get("validity_raw", ""),
                    image_url=flyer.get("image_url", ""),
                    source_url=flyer.get("flyer_url", ""),
                )
                if entry:
                    matched += 1

            mark_processed(flyer["id"], products_count=matched)
            processed += 1

        except Exception as e:
            logger.warning("[OCR] Error processing flyer %s: %s — marking as failed", flyer.get("id"), e)
            with suppress(Exception):
                mark_failed(flyer["id"])

    return processed
