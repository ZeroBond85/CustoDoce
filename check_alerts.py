from supabase import create_client
import os

url = os.environ.get("SUPABASE_URL")
key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
if url and key:
    s = create_client(url, key)
    r = s.table("alert_rules").select("*").limit(5).execute()
    for row in r.data:
        print(row)
