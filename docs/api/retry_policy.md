# `retry_policy` — API

> Última atualização: 2026-07-27 21:15 UTC
> Gerado por AST parsing dos serviços em `services/retry_policy.py`.

## Funções Públicas (6)

### classify(self, exception: Exception)

### get_delay(self, attempt: int, retry_after: int | None)

### get_policy(name: str)

### should_retry(self, exception: Exception, attempt: int)

### with_retry(fn: Callable, policy: RetryPolicy | None, context: str, retryable_exceptions: tuple[type[Exception], ...] | None)

### wrapper()

