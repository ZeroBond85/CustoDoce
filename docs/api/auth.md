# `auth` — API

> Última atualização: 2026-07-21 22:01 UTC
> Gerado por AST parsing dos serviços em `services/auth.py`.

## Funções Públicas (9)

### create_token(user_id: str, secret_key: str, expiry_hours: int)

### generate_secret_key(length: int)

### generate_totp_secret()

### get_totp_uri(secret: str, label: str, issuer: str)

### hash_password(password: str)

### load_config()

### verify_password(password: str, stored: str)

### verify_token(token: str, secret_key: str)

### verify_totp(secret: str, code: str, window: int)

