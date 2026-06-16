import hashlib
from datetime import date
from pathlib import Path
from typing import Optional

import httpx


class CacheEntry:
    def __init__(self, store_name: str, week: int, url: str, md5: str):
        self.store_name = store_name
        self.week = week
        self.url = url
        self.md5 = md5

    def to_dict(self):
        return {"store": self.store_name, "week": self.week, "url": self.url, "md5": self.md5}


class BaseFlyerScraper:
    def __init__(self, store_config: dict, cache_dir: str = "data/cache"):
        self.store = store_config
        self.name = store_config["name"]
        self.url_pattern = store_config.get("url_pattern", "")
        self.publish_day = store_config.get("publish_day", "wednesday")
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.session = httpx.Client(
            timeout=30.0,
            follow_redirects=True,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                              "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
                "Accept": "application/pdf, */*",
            },
        )

    def build_url(self, target_date: Optional[date] = None) -> str:
        if target_date is None:
            target_date = date.today()
        week = target_date.isocalendar().week
        year = target_date.year
        city_part = self.store.get("cities", ["santos"])[0].lower().replace(" ", "_")
        try:
            url = self.url_pattern.format(week=week, year=year, city=city_part)
        except KeyError:
            url = self.url_pattern.replace("{week}", str(week)).replace("{city}", city_part)
        return url

    def compute_md5(self, content: bytes) -> str:
        return hashlib.md5(content).hexdigest()

    def is_cached(self, md5: str) -> bool:
        cache_file = self.cache_dir / f"{self.name.lower().replace(' ', '_')}_md5.txt"
        if cache_file.exists():
            with open(cache_file) as f:
                return f.read().strip() == md5
        return False

    def save_cache(self, md5: str):
        cache_file = self.cache_dir / f"{self.name.lower().replace(' ', '_')}_md5.txt"
        with open(cache_file, "w") as f:
            f.write(md5)

    def download(self, target_date: Optional[date] = None) -> tuple[Optional[bytes], bool]:
        url = self.build_url(target_date)
        try:
            resp = self.session.get(url)
            resp.raise_for_status()
            content = resp.content
            md5 = self.compute_md5(content)

            if self.is_cached(md5):
                return None, False  # unchanged

            self.save_cache(md5)
            return content, True  # new content

        except httpx.HTTPError as e:
            print(f"[BaseFlyer] HTTP error for {self.name} ({url}): {e}")
            return None, False
        except Exception as e:
            print(f"[BaseFlyer] Error for {self.name}: {e}")
            return None, False

    def extract_text(self, pdf_bytes: bytes) -> str:
        import pdfplumber
        text_parts = []
        with pdfplumber.open(pdf_bytes) as pdf:
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

    def run(self, target_date: Optional[date] = None) -> list[dict]:
        content, is_new = self.download(target_date)
        if not is_new or content is None:
            return []
        raw_text = self.extract_text(content)

        if not raw_text or not raw_text.strip():
            print(f"[BaseFlyer/{self.name}] pdfplumber returned empty, trying OCR...")
            try:
                from scrapers.ocr import ocr_pdf
                raw_text = ocr_pdf(content)
                if raw_text.strip():
                    print(f"[BaseFlyer/{self.name}] OCR extracted {len(raw_text)} chars")
                else:
                    print(f"[BaseFlyer/{self.name}] OCR also returned empty")
            except ImportError as e:
                print(f"[BaseFlyer/{self.name}] OCR not available: {e}")
            except Exception as e:
                print(f"[BaseFlyer/{self.name}] OCR error: {e}")

        products = self.parse_products(raw_text)
        return products

    def parse_products(self, text: str) -> list[dict]:
        raise NotImplementedError("Subclasses must implement parse_products")
