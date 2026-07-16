# `logger` — API

> Última atualização: 2026-07-16 03:50 UTC
> Gerado por AST parsing dos serviços em `services/logger.py`.

## Funções Públicas (1)

### setup_logger()

Configures structlog for structured logging.
- Local: Pretty colored console output.
- CI: Console output without colors (ANSI-free for grep).
- Prod/Staging: JSON output for log aggregators.

