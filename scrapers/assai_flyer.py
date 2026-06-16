from scrapers.base_flyer import BaseFlyerScraper
from scrapers.flyer_parser import extract_lines_from_text, parse_flyer_lines


class AssaiFlyerScraper(BaseFlyerScraper):
    def parse_products(self, text: str) -> list[dict]:
        lines = extract_lines_from_text(text)
        return parse_flyer_lines(lines)
