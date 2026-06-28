import hashlib

from scrapers.base_web_scraper import BaseWebScraper


class TendaApiScraper(BaseWebScraper):
    def __init__(self, store_config: dict):
        super().__init__(store_config)
        self.api_base = store_config.get("api_base", "https://api.tendaatacado.com.br/api/public/branch")
        self.endpoints = store_config.get("api_endpoints", {})
        self._http.headers.update(
            {
                "Content-Type": "application/json; charset=utf-8",
                "desktop-platform": "true",
            }
        )

    def get_all_flyers(self, page: int = 1, per_page: int = 12) -> list[dict]:
        url = f"{self.api_base}{self.endpoints.get('flyers', '/flyers?per_page=12&page=1')}"
        url = url.replace("{page}", str(page))
        data = self.fetch_json(url)
        return data.get("data", []) if isinstance(data, dict) else data if isinstance(data, list) else []

    def get_flyers_by_branch(self, branch_id: int, per_page: int = 12) -> list[dict]:
        url = f"{self.api_base}{self.endpoints.get('branch_flyers', '/{branch_id}/flyers?per_page=12')}"
        url = url.replace("{branch_id}", str(branch_id))
        data = self.fetch_json(url)
        return data.get("data", []) if isinstance(data, dict) else data if isinstance(data, list) else []

    def get_branches_with_flyers(self) -> list[dict]:
        url = f"{self.api_base}{self.endpoints.get('all_branches', '/flyers/all-branchs')}"
        data = self.fetch_json(url)
        return data if isinstance(data, list) else []

    def parse_flyer(self, flyer: dict) -> list[dict]:
        entries = []
        pages = flyer.get("pages", [])
        branch = flyer.get("branch", {})
        branch_name = branch.get("name", "Unknown")
        branch_city = branch.get("address", {}).get("city", "Unknown")

        for page in pages:
            image_url = page.get("image", "")
            if image_url:
                entries.append(
                    {
                        "product": f"Encarte Tenda - {branch_name} ({branch_city})",
                        "price": 0.0,
                        "unit": "encarte",
                        "image_url": image_url,
                        "image_hash": hashlib.md5(image_url.encode(), usedforsecurity=False).hexdigest(),
                        "flyer_name": flyer.get("name", ""),
                        "start_date": flyer.get("startDate", ""),
                        "end_date": flyer.get("endDate", ""),
                    }
                )
        return entries

    def parse_products(self, raw_data) -> list[dict]:
        return []

    def run(self, ingredients: list[dict]) -> list[dict]:
        all_entries = []
        branches = self.get_branches_with_flyers()

        for branch in branches:
            branch_id = branch.get("id")
            if not branch_id:
                continue
            flyers = self.get_flyers_by_branch(branch_id)
            for flyer in flyers:
                parsed = self.parse_flyer(flyer)
                all_entries.extend(parsed)

        return all_entries
