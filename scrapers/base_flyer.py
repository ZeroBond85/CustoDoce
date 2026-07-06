import hashlib
import io
from abc import ABC, abstractmethod
from datetime import date
from pathlib import Path

import httpx

from services.logger import logger


class BaseFlyerScraper(ABC):
    def __init__(self, store_config: dict, cache_dir: str = "data/cache"):
        self.store = store_config
        self.name = store_config["name"]
        self.url_pattern = store_config.get("url_pattern", "")
        self.publish_day = store_config.get("publish_day", "wednesday")
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._http = httpx.Client(
            timeout=30.0,
            follow_redirects=True,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
                "Accept": "application/pdf, */*",
            },
        )

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self._http.close()

    def close(self):
        self._http.close()

    # ─── Sprint 4: Self-Healing Hooks (Licao #15) ────────────────────
    # Symmetric with BaseWebScraper.report_failure / report_success.
    # Subclasses MUST call these helpers from their failure / success paths.

    @property
    def store_name(self) -> str:
        """Public accessor used by self-healing hooks."""
        return self.name

    def report_failure(self, reason: str, items_found: int = 0, flyer_count: int = 0) -> dict:
        """Record a failure to services.scraper_health.

        Flyer scrapers care mostly about flyer_count / items_found (0 in
        most flyer-only paths). Errors swallowing is intentional.
        """
        from contextlib import suppress

        from services.scraper_health import record_failure

        with suppress(Exception):
            return record_failure(
                self.store_name,
                reason=reason,
                items_found=items_found,
                products_matched=0,
                flyer_count=flyer_count,
                attempted_by="flyer_runner",
            )
        return {"recorded": False}

    def report_success(self, items_found: int, flyer_count: int, products_matched: int = 0) -> dict:
        """Record a successful execution (resets failure counter)."""
        from contextlib import suppress

        from services.scraper_health import record_success

        with suppress(Exception):
            return record_success(
                self.store_name,
                items_found=items_found,
                products_matched=products_matched,
                flyer_count=flyer_count,
                attempted_by="flyer_runner",
            )
        return {"recorded": False}

    def _md5_path(self) -> Path:
        return self.cache_dir / f"{self.name.lower().replace(' ', '_')}_md5.txt"

    def _etag_path(self) -> Path:
        return self.cache_dir / f"{self.name.lower().replace(' ', '_')}_etag.txt"

    def build_url(self, target_date: date | None = None) -> str:
        if target_date is None:
            target_date = date.today()
        week = target_date.isocalendar().week
        year = target_date.year
        city_part = self.store.get("cities", ["santos"])[0].lower().replace(" ", "_")
        state = self.store.get("state", "sp")
        store_slug = self.store.get("store_slug", city_part)
        try:
            url = self.url_pattern.format(week=week, year=year, city=city_part, state=state, store_slug=store_slug)
        except KeyError:
            url = self.url_pattern.replace("{week}", str(week)).replace("{city}", city_part)
        return url

    def _compute_md5(self, content: bytes) -> str:
        return hashlib.md5(content, usedforsecurity=False).hexdigest()  # nosec B324

    def download(self, target_date: date | None = None) -> tuple[bytes | None, bool]:
        url = self.build_url(target_date)
        md5_path = self._md5_path()
        etag_path = self._etag_path()
        cached_md5 = md5_path.read_text().strip() if md5_path.exists() else ""
        cached_etag = etag_path.read_text().strip() if etag_path.exists() else ""

        try:
            head = self._http.head(url)
            etag = head.headers.get("etag", "")
            if etag and etag == cached_etag:
                logger.info("[%s] ETag unchanged, skipping download", self.name)
                return None, False
            head_md5 = head.headers.get("content-md5", "")
            if head_md5 and head_md5 == cached_md5:
                logger.info("[%s] Content-MD5 unchanged, skipping download", self.name)
                return None, False
        except Exception:
            logger.debug("[%s] HEAD check failed, proceeding with GET", self.name)

        try:
            resp = self._http.get(url)
            resp.raise_for_status()
        except httpx.HTTPError as e:
            logger.error("[%s] HTTP error for %s: %s", self.name, url, e)
            return None, False
        except Exception as e:
            logger.error("[%s] Download error: %s", self.name, e)
            return None, False

        content = resp.content
        current_md5 = self._compute_md5(content)
        if current_md5 == cached_md5:
            logger.info("[%s] MD5 unchanged, skipping", self.name)
            return None, False

        md5_path.write_text(current_md5)
        etag = resp.headers.get("etag", "")
        if etag:
            etag_path.write_text(etag)
        return content, True

    def extract_text(self, pdf_bytes: bytes) -> str:
        import pdfplumber

        text_parts = []
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    text_parts.append(text)
                tables = page.extract_tables()
                for table in tables:
                    for row in table:
                        if row:
                            text_parts.append(" | ".join(str(c) for c in row if c))
        return "\n".join(text_parts)

    def _render_first_page(self, pdf_bytes: bytes) -> bytes | None:
        """Render the first page of a PDF to a PNG thumbnail. Returns None on failure."""
        try:
            import pdfplumber

            with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
                if not pdf.pages:
                    return None
                img = pdf.pages[0].to_image(resolution=150)
                buf = io.BytesIO()
                img.save(buf, format="PNG")
                return buf.getvalue()
        except Exception as e:
            logger.debug("[%s] Thumbnail generation failed: %s", self.name, e)
            return None

    def run(self, target_date: date | None = None) -> list[dict]:
        content, is_new = self.download(target_date)
        if not is_new or content is None:
            return []
        raw_text = self.extract_text(content)

        if not raw_text or not raw_text.strip():
            logger.info("[%s] pdfplumber returned empty, trying OCR...", self.name)
            try:
                from scrapers.ocr import ocr_pdf

                raw_text = ocr_pdf(content)
                if raw_text.strip():
                    logger.info("[%s] OCR extracted %d chars", self.name, len(raw_text))
                else:
                    logger.info("[%s] OCR also returned empty", self.name)
            except ImportError as e:
                logger.warning("[%s] OCR not available: %s", self.name, e)
            except Exception as e:
                logger.warning("[%s] OCR error: %s", self.name, e)

        self._thumbnail = self._render_first_page(content)
        return self.parse_products(raw_text)

    @abstractmethod
    def parse_products(self, text: str) -> list[dict]: ...
