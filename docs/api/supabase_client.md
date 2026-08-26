# `supabase_client` — API

> Última atualização: 2026-08-26 16:42 UTC
> Gerado por AST parsing dos serviços em `services/supabase_client.py`.

## Funções Públicas (7)

### get_client()

Alias compatível para get_supabase().

### get_service_client()

### get_supabase()

### require_service_client()

Service-role client gated on an authenticated admin Streamlit session.

### rpc_execute(client: Any, fn_name: str, params: dict[str, Any])

Executa RPC no client fornecido com safe_execute (DI p/ testabilidade).

### safe_execute(query: Any)

Executa query e garante list[dict] não-None.

### safe_single_execute(query: Any)

Executa query e retorna single dict ou None.

