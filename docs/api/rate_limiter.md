# `rate_limiter` — API

> Última atualização: 2026-08-08 14:34 UTC
> Gerado por AST parsing dos serviços em `services/rate_limiter.py`.

## Funções Públicas (9)

### clear_attempts(self, key: str)

### consume(self, key: str, tokens: float)

Try to consume tokens. Returns True if allowed.

### is_limited(self, key: str)

### record_attempt(self, key: str)

### remaining_attempts(self, key: str)

### reset(self, key: str)

### reset_all(self)

### retry_after(self, key: str)

### wait_time(self, key: str, tokens: float)

Seconds until `tokens` are available.

