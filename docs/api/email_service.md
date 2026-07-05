# `email_service` — API

> Última atualização: 2026-07-05 13:32 UTC
> Gerado por AST parsing dos serviços em `services/email_service.py`.

## Funções Públicas (6)

### build_full_report_html(prices_by_ingredient: dict)

Gera relatório HTML responsivo - melhor preço por loja por ingrediente.

### send_critical_alert(ingredient_name: str, price: float, store: str, to_email: str | None)

### send_daily_report(report_html: str, csv_bytes: bytes | None, to_email: str | None, subject: str | None)

### send_email(to_email: str, subject: str, html_body: str)

Simple email sender using the existing SMTP config.

### send_scraper_error(store_name: str, error: str, to_email: str | None)

### send_telegram_report(token: str, chat_id: str, ingredients: list[dict], prices_by_ingredient: dict)

Envia 1 única mensagem Telegram com top-5 por ingrediente (deduplicado por loja).

