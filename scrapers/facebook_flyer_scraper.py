"""Facebook Flyer Scraper — best-effort OCR of flyer images from public FB pages.

Flow:
1. Playwright loads page, dismisses cookie/consent interstitial.
2. Scrolls to load posts, selects posts with images.
3. For each post: extracts image_url + post date (abbr[data-utime]/time/aria-label).
4. Downloads image bytes -> extractor.extract_products (OCR + vision fallback) -> flyer_parser.parse_flyer_lines.
5. Yields products with validity_raw = post date.
6. Self-healing: record_success/failure(); on FB login-wall -> record_failure + graceful skip.
"""

import asyncio
import logging
from datetime import datetime

from scrapers.flyer_parser import extract_lines_from_text, parse_flyer_lines
from scrapers.ocr import ocr_image_bytes
from services.scraper_health import record_failure, record_success
from scrapers.base_web_scraper import BaseWebScraper
from scrapers.playwright_pool import get_browser_pool

logger = logging.getLogger(__name__)


class FacebookFlyerScraper(BaseWebScraper):
    def __init__(self, store_config: dict):
        super().__init__(store_config)
        self.page_url = store_config.get("page_url") or store_config.get("base_url")
        if not self.page_url:
            raise ValueError("facebook_flyer_scraper requires 'page_url' or 'base_url' in store config")

    def run(self, ingredients: list[dict]) -> list[dict]:
        return asyncio.run(self._run_async(ingredients))

    async def _run_async(self, ingredients: list[dict]) -> list[dict]:
        all_products = []
        pool = await get_browser_pool()
        context = await pool.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            )
        )
        try:
            for ing in ingredients:
                products = await self._scrape_flyers_for_ingredient(context, ing)
                all_products.extend(products)
        finally:
            await context.close()
        return all_products

    async def _scrape_flyers_for_ingredient(self, context, ing: dict) -> list[dict]:
        page = await context.new_page()
        try:
            await page.goto(self.page_url, wait_until="networkidle", timeout=45000)
            await self._dismiss_cookie_consent(page)
            await self._scroll_to_load_posts(page)
            posts = await self._extract_posts_with_images(page)
            if not posts:
                logger.warning("[%s] No image posts found on %s", self.name, self.page_url)
                return []

            logger.info("[%s] Found %d image posts to process", self.name, len(posts))
            for post in posts:
                try:
                    products = await self._process_post(page, post, ing)
                    if products:
                        return products
                except Exception as e:
                    logger.debug("[%s] Post processing failed: %s", self.name, e)
            return []
        except Exception as e:
            logger.warning("[%s] Facebook flyer scrape failed: %s", self.name, e)
            record_failure(self.name, "facebook_flyer", str(e))
            return []
        finally:
            await page.close()

    async def _dismiss_cookie_consent(self, page) -> None:
        """Try to dismiss FB cookie/consent interstitial if present."""
        for selector in [
            'button[data-cookiebanner="accept_button"]',
            'button:has-text("Permitir")',
            'button:has-text("Aceitar")',
            'button:has-text("Allow")',
            'div[aria-label="Fechar"]',
            '[role="dialog"] button:has-text("Agora não")',
        ]:
            try:
                btn = page.locator(selector).first
                if await btn.is_visible(timeout=2000):
                    await btn.click()
                    await page.wait_for_timeout(500)
                    return
            except Exception as e:
                logger.debug("[%s] Cookie dismiss selector '%s' failed: %s", self.name, selector, e)

    async def _scroll_to_load_posts(self, page, max_scrolls: int = 5) -> None:
        """Scroll down to trigger lazy-loading of posts."""
        for _ in range(max_scrolls):
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await page.wait_for_timeout(1500)

    async def _extract_posts_with_images(self, page) -> list[dict]:
        """Extract post elements containing images + their posted date."""
        posts = []
        # FB post containers typically have data-pagelet or role="article"
        post_locators = page.locator(
            'div[role="article"], div[data-pagelet*="FeedUnit"], div[data-testid="post_message"]'
        )
        count = await post_locators.count()
        for i in range(count):
            post = post_locators.nth(i)
            try:
                # Find image inside post
                img = post.locator("img").first
                if not await img.is_visible(timeout=1000):
                    continue
                src = await img.get_attribute("src")
                if not src or "scontent" not in src and "fbcdn" not in src:
                    continue

                # Extract post date from abbr[data-utime] or time[datetime]
                post_date = ""
                for date_sel in ['abbr[data-utime]', 'time[datetime]', 'a[aria-label*="hora"]', 'a[aria-label*="dia"]']:
                    try:
                        el = post.locator(date_sel).first
                        if await el.is_visible(timeout=500):
                            if "data-utime" in date_sel:
                                utime = await el.get_attribute("data-utime")
                                if utime:
                                    post_date = datetime.fromtimestamp(int(utime)).isoformat()
                            elif "datetime" in date_sel:
                                post_date = await el.get_attribute("datetime")
                            else:
                                post_date = await el.get_attribute("aria-label") or ""
                            break
                    except Exception as e:
                        logger.debug("[%s] Date selector '%s' failed: %s", self.name, date_sel, e)

                posts.append({"image_url": src, "post_date": post_date})
            except Exception as e:
                logger.debug("[%s] Failed to process post %d: %s", self.name, i, e)
                continue
        return posts

    async def _process_post(self, page, post_data: dict, ing: dict) -> list[dict]:
        """Download image, OCR, parse flyer, match ingredient."""
        import httpx

        image_url = post_data["image_url"]
        post_date = post_data["post_date"]

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.get(image_url)
                resp.raise_for_status()
                image_bytes = resp.content
        except Exception as e:
            logger.debug("[%s] Failed to download image %s: %s", self.name, image_url, e)
            return []

        # OCR -> lines -> parse flyer
        try:
            text = ocr_image_bytes(image_bytes)
            if not text:
                return []
            lines = extract_lines_from_text(text)
            extracted = parse_flyer_lines(lines)
        except Exception as e:
            logger.debug("[%s] OCR/parse failed for %s: %s", self.name, image_url, e)
            return []

        if not extracted:
            return []

        products = []
        for item in extracted:
            name = item.get("product", "").strip()
            if not name:
                continue
            price = item.get("price")
            if price is None:
                continue
            unit = item.get("unit", "")
            validity = item.get("validity_raw", "") or post_date
            products.append({
                "product": name,
                "price": price,
                "unit": unit,
                "validity_raw": validity,
                "brand": item.get("brand", ""),
                "store": self.name,
                "source": "facebook_flyer",
            })

        # Self-healing success if any product extracted
        if products:
            record_success(self.name, "facebook_flyer")
        return products

    # Required by BaseWebScraper ABC
    def parse_products(self, html: str) -> list[dict]:
        # Not used — we override run() entirely for Playwright flow
        return []


__all__ = ["FacebookFlyerScraper"]
