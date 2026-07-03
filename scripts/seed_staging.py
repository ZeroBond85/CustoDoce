import os
import sys
import random
from datetime import datetime, timedelta
from supabase import create_client
from dotenv import load_dotenv


def seed_staging_data(client):
    """
    Seeds the staging environment with synthetic data for testing.
    """
    print("Seeding staging data...")

    # 1. Ensure we have some core config (if sync_staging wasn't run)
    ingredients = client.table("ingredients").select("*").execute()
    if not ingredients.data:
        print("No ingredients found. Seeding basic ingredients...")
        basic_ings = [
            {"canonical_name": "Leite Condensado", "category": "lacteos"},
            {"canonical_name": "Creme de Leite", "category": "lacteos"},
            {"canonical_name": "Chocolate em Pó", "category": "chocolates"},
        ]
        client.table("ingredients").insert(basic_ings).execute()

    stores = client.table("stores").select("*").execute()
    if not stores.data:
        print("No stores found. Seeding basic stores...")
        basic_stores = [
            {"name": "Test Store 1", "tier": 1, "active": True},
            {"name": "Test Store 2", "tier": 2, "active": True},
        ]
        client.table("stores").insert(basic_stores).execute()

    # 2. Seed synthetic prices
    # Get IDs
    ings = client.table("ingredients").select("id, canonical_name").execute().data
    strs = client.table("stores").select("id, name").execute().data

    if not ings or not strs:
        print("Missing ingredients or stores. Cannot seed prices.")
        return

    prices_to_insert = []
    for store in strs:
        for ing in ings:
            # Create 5 historical price points for each product
            for i in range(5):
                date = datetime.now() - timedelta(days=i * 7)
                price = random.uniform(5.0, 20.0)
                prices_to_insert.append(
                    {
                        "store_id": store["id"],
                        "ingredient_id": ing["id"],
                        "price": price,
                        "raw_price": price,
                        "collected_at": date.isoformat(),
                        "match_type": "exato",
                        "confidence": 1.0,
                    }
                )

    # Batch insert
    batch_size = 100
    for i in range(0, len(prices_to_insert), batch_size):
        client.table("prices").insert(prices_to_insert[i : i + batch_size]).execute()

    print(f"Successfully seeded {len(prices_to_insert)} price records.")


def main():
    load_dotenv()

    staging_url = os.environ.get("SUPABASE_STAGING_URL")
    staging_key = os.environ.get("SUPABASE_STAGING_SERVICE_ROLE_KEY")

    if not staging_url or not staging_key:
        print("Error: Missing staging credentials in .env")
        print("Required: SUPABASE_STAGING_URL, SUPABASE_STAGING_SERVICE_ROLE_KEY")
        sys.exit(1)

    client = create_client(staging_url, staging_key)

    try:
        seed_staging_data(client)
        print("\nStaging seed completed successfully!")
    except Exception as e:
        print(f"\nError during seeding: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
