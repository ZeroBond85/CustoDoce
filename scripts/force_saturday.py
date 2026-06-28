class ForceSaturday:
    """
    Context manager that patches collect_tier1_pdfs to ignore publish_day.
    This allows validating the PDF pipeline regardless of the current weekday.
    """

    def __enter__(self):
        # We patch the function that filters stores based on publish_day
        # Note: The actual function to patch is in services.collector
        from services import collector

        self.original_func = collector.collect_tier1_pdfs

        def forced_collect(ingredients):
            # Original logic but forced to include all tier 1 PDF stores
            from services.collector import load_stores

            stores = [s for s in load_stores() if s.get("tier") == 1 and s.get("type") == "pdf_flyer"]

            # Use the same internal _collect_prices logic as original
            from services.collector import _collect_prices, FlyerScraper

            return _collect_prices(stores, FlyerScraper, ingredients, "PDF (FORCED)")

        collector.collect_tier1_pdfs = forced_collect
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        from services import collector

        collector.collect_tier1_pdfs = self.original_func
