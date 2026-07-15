"""Pausa/retoma lojas no scrape regular durante testes isolados.

Uso:
    python scripts/toggle_store_pause.py <enable|disable> "Loja A,Loja B"

Ao testar uma loja isoladamente (test_store_recovery.yml), desativamos sua
linha em ``scrape_frequencies`` (enabled=False) para que o scrape agendado
regular não a processe em paralelo. Após o teste, reativamos (enabled=True).
"""

from __future__ import annotations

import sys

from services.supabase_client import get_supabase


def main() -> int:
    if len(sys.argv) < 3:
        print("uso: toggle_store_pause.py <enable|disable> '<nome1>,<nome2>'")
        return 2
    action = sys.argv[1]
    if action not in ("enable", "disable"):
        print("ação deve ser 'enable' ou 'disable'")
        return 2
    names = [n.strip() for n in sys.argv[2].split(",") if n.strip()]
    enabled = action == "enable"

    client = get_supabase()
    for name in names:
        rows = client.table("stores").select("id").eq("name", name).execute()
        if not rows.data:
            print(f"  ! loja {name!r} não encontrada no Supabase")
            continue
        sid = rows.data[0]["id"]
        client.table("scrape_frequencies").upsert(
            {"store_id": sid, "enabled": enabled}
        ).execute()
        print(f"  {name}: enabled={enabled}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
