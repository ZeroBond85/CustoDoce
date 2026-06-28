# Flyer Service API

Gestão de flyers (catálogos PDF de ofertas) — upload, processamento, e cleanup.

## Flyers

### `upsert_flyer(flyer: dict) -> dict`

Inscreve ou atualiza um flyer. Usa `source` + `url` como unique constraint.

```python
flyer = upsert_flyer({
    "store_id": "uuid",
    "store_name": "Assaí",
    "source": "website",
    "url": "https://example.com/flyer.pdf",
    "published_at": "2026-06-25",
    "status": "pending",
    "raw_content": b"...pdf bytes...",
})
print(f"Flyer {flyer['id']} - status: {flyer['status']}")
```

**Campos:**
| Campo | Tipo | Descrição |
|-------|------|-----------|
| `store_id` | `uuid` | FK para stores |
| `store_name` | `str` | Nome da loja |
| `source` | `str` | `website`, `email`, `manual` |
| `url` | `str` | URL do PDF |
| `published_at` | `date` | Data de publicação |
| `status` | `str` | `pending`, `processing`, `done`, `failed` |
| `thumbnail_url` | `str` | URL da thumbnail (opcional) |
| `raw_content` | `bytes` | Bytes do PDF (opcional) |

---

### `mark_processed(flyer_id: str, products_count=0) -> dict`

Marca flyer como processado (`status="done"`).

---

### `mark_failed(flyer_id: str) -> dict`

Marca flyer como falho (`status="failed"`).

---

### `get_pending_flyers(limit=20) -> list[dict]`

Retorna flyers com `status="pending"`, ordenados por `created_at`.

```python
pending = get_pending_flyers(limit=10)
for f in pending:
    print(f"Processar: {f['store_name']} - {f['url']}")
```

---

### `get_recent_flyers(days=7, source=None) -> list[dict]`

Flyers dos últimos `days` dias.

```python
recent = get_recent_flyers(days=7)
# ou filtrado por source:
tendeo = get_recent_flyers(days=7, source="tiendoo")
```

---

### `get_flyer_detail(flyer_id: str) -> dict`

Detalhe de um flyer (com contagem de produtos).

---

### `delete_flyer(flyer_id: str) -> dict`

Remove flyer e thumbnail asociada.

---

## Cleanup

### `cleanup_old_flyers(retention_days=60) -> dict`

Remove flyers com `created_at` > `retention_days` dias e `status IN ('done','failed')`.

Retorna `{deleted, errors}`.

```python
result = cleanup_old_flyers(retention_days=30)
print(f"Deleted: {result['deleted']}, Errors: {result['errors']}")
```

---

### `cleanup_non_food_flyers() -> dict`

Remove flyers whose extracted text does not contain food-related keywords. Usa uma blocklist de categorias (Limpeza, Beleza, etc.).

---

## Storage

### `_upload_flyer_thumbnail(store_name, thumbnail_bytes) -> str`

Upload de thumbnail PNG para Supabase Storage (`thumbnails` bucket). Retorna public URL ou string vazia em caso de erro.

---

## Alertas

O serviço monitora execuções de cleanup e faz log de alerta se 3+ dias consecutivos sem deleções.