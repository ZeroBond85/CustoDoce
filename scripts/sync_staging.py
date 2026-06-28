import os
import sys
from supabase import create_client
from dotenv import load_dotenv


def sync_core_data(prod_client, staging_client):
    """
    Syncs core configuration tables from production to staging.
    Tables: ingredients, stores, features
    """
    tables = ["ingredients", "stores", "features"]

    for table in tables:
        print(f"Syncing {table}...")
        # Fetch from prod
        data = prod_client.table(table).select("*").execute()
        if not data.data:
            print(f"No data found in {table} on production. Skipping.")
            continue

        # Upsert to staging
        staging_client.table(table).upsert(data.data).execute()
        print(f"Successfully synced {len(data.data)} rows for {table}.")


def main():
    load_dotenv()

    # Production credentials
    prod_url = os.environ.get("SUPABASE_URL")
    prod_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")

    # Staging credentials
    staging_url = os.environ.get("SUPABASE_STAGING_URL")
    staging_key = os.environ.get("SUPABASE_STAGING_SERVICE_ROLE_KEY")

    if not all([prod_url, prod_key, staging_url, staging_key]):
        print("Error: Missing Supabase credentials in .env")
        print(
            "Required: SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, SUPABASE_STAGING_URL, SUPABASE_STAGING_SERVICE_ROLE_KEY"
        )
        sys.exit(1)

    prod_client = create_client(prod_url, prod_key)
    staging_client = create_client(staging_url, staging_key)

    try:
        sync_core_data(prod_client, staging_client)
        print("\nCore data synchronization completed successfully!")
    except Exception as e:
        print(f"\nError during synchronization: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
