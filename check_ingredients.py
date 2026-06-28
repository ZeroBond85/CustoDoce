# mypy: ignore-errors
from supabase import create_client
import os

url = os.environ.get("SUPABASE_URL")
key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
if url and key:
    s = create_client(url, key)
    r = s.table("ingredients").select("*").eq("active", True).execute()
    for row in r.data:
        row_dict = dict(row) if row else {}  # type: ignore
        print(f"id={row_dict.get('id')}, canonical={row_dict.get('canonical')}, aliases={row_dict.get('aliases')}")
