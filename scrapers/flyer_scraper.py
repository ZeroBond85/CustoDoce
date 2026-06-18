import logging

from scrapers.base_flyer import BaseFlyerScraper
from scrapers.flyer_parser import extract_lines_from_text, parse_flyer_lines

logger = logging.getLogger(__name__)


class FlyerScraper(BaseFlyerScraper):

    def parse_products(self, text: str) -> list[dict]:
        lines = extract_lines_from_text(text)
        return parse_flyer_lines(lines)
