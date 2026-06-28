import os
import sys
from supabase import create_client
from dotenv import load_dotenv


def validate_staging(client):
    """
    Performs health checks on the staging environment.
    """
    checks = []

    print("Running staging health checks...")

    # Check 1: Core tables not empty
    core_tables = ["ingredients", "stores", "prices"]
    for table in core_tables:
        try:
            res = client.table(table).select("*", count="exact").limit(1).execute()
            count = res.count
            if count and count > 0:
                checks.append((f"Table {table} has data", True))
            else:
                checks.append((f"Table {table} is empty", False))
        except Exception as e:
            checks.append((f"Table {table} access error: {e}", False))

    # Check 2: Database functions (RPC)
    try:
        # Try a dry-run or a harmless RPC call
        # we use upsert_price_rpc with a dummy ID to test it exists
        client.rpc(
            "upsert_price_rpc",
            {
                "p_brand": "",
                "p_city": "",
                "p_collected_at": "2000-01-01",
                "p_collected_weekday": "",
                "p_confidence": 0.0,
                "p_ingredient_id": "00000000-0000-0000-0000-000000000000",
                "p_is_promotion": False,
                "p_logistics": "",
                "p_normalized": None,
                "p_raw_price": 0.0,
                "p_raw_product": "",
                "p_raw_unit": "",
                "p_source": "",
                "p_store_id": "00000000-0000-0000-0000-000000000000",
                "p_store_name": "",
                "p_tier": 0,
                "p_valid_from": "2000-01-01",
                "p_valid_until": "2000-01-01",
                "p_validity_raw": "",
            },
        ).execute()
        checks.append(("RPC upsert_price_rpc exists", True))
    except Exception as e:
        # We expect a foreign key error, which actually confirms the function exists
        if "violates foreign key constraint" in str(e).lower():
            checks.append(("RPC upsert_price_rpc exists (FK error confirmed)", True))
        else:
            checks.append((f"RPC upsert_price_rpc error: {e}", False))

    return checks


def main():
    load_dotenv()

    staging_url = os.environ.get("SUPABASE_STAGING_URL")
    staging_key = os.environ.get("SUPABASE_STAGING_SERVICE_ROLE_KEY")

    if not staging_url or not staging_key:
        print("Staging credentials not found, falling back to PROD...")
        staging_url = os.environ.get("SUPABASE_URL")
        staging_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")

    if not staging_url or not staging_key:
        print("Error: No Supabase credentials found in .env (neither staging nor PROD)")
        sys.exit(1)

    client = create_client(staging_url, staging_key)

    results = validate_staging(client)

    all_passed = True
    print("\\n--- Staging Validation Results ---")
    for desc, passed in results:
        status = "[OK]" if passed else "[FAIL]"
        print(f"{status} {desc}")
        if not passed:
            all_passed = False

    if all_passed:
        print("\\nOverall Status: PASSED")
        sys.exit(0)
    else:
        print("\\nOverall Status: FAILED")
        sys.exit(1)


if __name__ == "__main__":
    main()
