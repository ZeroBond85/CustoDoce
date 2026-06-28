from supabase import create_client
import os

url = os.environ.get("SUPABASE_URL")
key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
if url and key:
    s = create_client(url, key)
    r = s.rpc(
        "exec_sql_query",
        {
            "sql": "SELECT column_name, is_nullable, column_default FROM information_schema.columns WHERE table_name = 'flyers' ORDER BY ordinal_position;"
        },
    ).execute()
    if r.data and isinstance(r.data, list):
        for row in r.data:
            print(row)
