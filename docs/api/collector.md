# `collector` — API

> Última atualização: 2026-07-13 00:03 UTC
> Gerado por AST parsing dos serviços em `services/collector.py`.

## Funções Públicas (17)

### build_product_entry(store: Store, ingredient: Ingredient, raw_product: str, raw_price: float, raw_unit: str, confidence: float, validity_raw: str, brand: str)

### collect_aggregators_js()

### collect_aggregators_ssr()

### collect_carrefour(ingredients: list[Ingredient])

### collect_extra_flyers(ingredients: list[Ingredient])

### collect_facebook_flyers(ingredients: list[Ingredient])

### collect_pao_flyers(ingredients: list[Ingredient])

### collect_roldao_flyer(ingredients: list[Ingredient])

### collect_tier1_api_flyers(ingredients: list[dict])

### collect_tier1_pdfs(ingredients: list[Ingredient])

### collect_tier2_js(ingredients: list[Ingredient])

### collect_tier2_vtex(ingredients: list[Ingredient])

### collect_tier3_websites(ingredients: list[Ingredient])

### load_ingredients()

### load_stores()

### process_ocr_queue()

### process_price_match(store: Store, product_text: str, raw_price: float, raw_unit: str, ingredients: list[Ingredient], validity_raw: str, brand: str, image_url: str, source_url: str)

