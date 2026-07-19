# `email_service` — API

> Última atualização: 2026-07-19 05:08 UTC
> Gerado por AST parsing dos serviços em `services/email_service.py`.

## Funções Públicas (6)

### build_full_report_html(prices_by_ingredient: dict)

Gera relatório HTML responsivo - melhor preço por loja por ingrediente.

### is_email_configured()

Retorna True se as credenciais SMTP/Gmail estão presentes nas env vars.

### send_critical_alert(ingredient_name: str, price: float, store: str, to_email: str | None)

### send_daily_report(report_html: str, csv_bytes: bytes | None, to_email: str | None, subject: str | None)

### send_email(to_email: str, subject: str, html_body: str)

Simple email sender using the existing SMTP config.

### send_scraper_error(store_name: str, error: str, to_email: str | None)

