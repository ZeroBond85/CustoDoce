
import hashlib
import logging

import httpx
from scrapers.base_web_scraper import BaseWebScraper

logger = logging.getLogger(__name__)


class RoldaoApiScraper(BaseWebScraper):

    def __init__(self, store_config: dict):
        # Roldão's blog has SSL certificate issues, force verify_ssl=False
        store_config = {**store_config, "verify_ssl": False}
        super().__init__(store_config)
        self.api_base = store_config.get("api_base", "https://blog.roldao.com.br/wp-json/wp/v2")
        self.endpoints = store_config.get("api_endpoints", {})

    def get_posts(self, per_page: int = 10) -> list[dict]:
        url = f"{self.api_base}{self.endpoints.get('posts', '/posts?per_page=10&categories=10')}"
        data = self.fetch_json(url)
        return data if isinstance(data, list) else []

    def get_media(self, media_id: int) -> dict | None:
        url = f"{self.api_base}{self.endpoints.get('media', '/media/{media_id}')}"
        url = url.replace("{media_id}", str(media_id))
        try:
            resp = self._http.get(url, timeout=10.0)
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as e:
            logger.warning("[%s] Media %d: HTTP %s (pulando)", self.name, media_id, e.response.status_code)
            return None
        except Exception as e:
            logger.warning("[%s] Media %d: %s (pulando)", self.name, media_id, e)
            return None

    def parse_post(self, post: dict) -> list[dict]:
        entries = []
        media_id = post.get("featured_media")
        if not media_id:
            return entries

        media = self.get_media(media_id)
        if not media:
            return entries

        image_url = media.get("guid", {}).get("rendered", "")
        if not image_url:
            return entries

        title = post.get("title", {}).get("rendered", "Encarte Roldão")
        date = post.get("date", "")
        excerpt = post.get("excerpt", {}).get("rendered", "")

        entries.append({
            "product": f"Encarte Roldão - {title}",
            "price": 0.0,
            "unit": "encarte",
            "image_url": image_url,
            "image_hash": hashlib.md5(image_url.encode(), usedforsecurity=False).hexdigest(),
            "post_date": date,
            "excerpt": excerpt,
        })
        return entries

    def parse_products(self, raw_data) -> list[dict]:
        return []

    def run(self, ingredients: list[dict]) -> list[dict]:
        all_entries = []
        posts = self.get_posts()
        for post in posts:
            parsed = self.parse_post(post)
            all_entries.extend(parsed)
        return all_entries
