#!/usr/bin/env python3
"""
CustoDoce - Data Quality Gates
Valida a integridade dos dados no Supabase usando Great Expectations.
若是 dadosruins, o CI deve falhar (exit code 1).
"""

import os
import sys
import logging
from supabase import create_client
import great_expectations as gx
from great_expectations.core import ExpectationSuite

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def get_client():
    url = os.environ.get("SUPABASE_URL", "")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    if not url or not key:
        print("ERROR: SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set")
        sys.exit(1)
    return create_client(url, key)


def build_suite() -> ExpectationSuite:
    suite = gx.ExpectationSuite(name="custodoce_data_quality")

    # Expectation 1: price_per_kg > 0
    suite.add_expectation(
        gx.expectations.ExpectColumnValuesToBeGreaterThan(
            column="price_per_kg",
            strictly=True,
            value=0,
            catch_exceptions=True,
        )
    )

    # Expectation 2: confidence >= 0.55
    suite.add_expectation(
        gx.expectations.ExpectColumnValuesToBeGreaterThan(
            column="confidence",
            strictly=False,
            value=0.55,
            catch_exceptions=True,
        )
    )

    # Expectation 3: No null values in critical columns
    for col in ["ingredient_id", "store_id", "raw_price", "collected_at"]:
        suite.add_expectation(
            gx.expectations.ExpectColumnValuesToNotBeNull(
                column=col,
                catch_exceptions=True,
            )
        )

    # Expectation 4: raw_price > 0
    suite.add_expectation(
        gx.expectations.ExpectColumnValuesToBeGreaterThan(
            column="raw_price",
            strictly=True,
            value=0,
            catch_exceptions=True,
        )
    )

    return suite


def run_quality_checks():
    client = get_client()

    print("=== Data Quality Gates ===\n")

    # Fetch prices data
    try:
        result = client.table("prices").select("*").execute()
        df = result.dataframe
    except Exception as e:
        print(f"ERROR: Failed to fetch prices data: {e}")
        return False

    if df.empty:
        print("WARNING: No prices data found. Skipping checks.")
        return True

    print(f"Loaded {len(df)} prices from database.")

    # Build and run the suite
    suite = build_suite()
    results = suite.validate(df)

    # Report results
    total_checks = len(results.results)
    passed_checks = sum(1 for r in results.results if r.success)
    failed_checks = total_checks - passed_checks

    print("\n--- Validation Results ---")
    print(f"Total: {total_checks}, Passed: {passed_checks}, Failed: {failed_checks}")

    if failed_checks > 0:
        print("\nFailed Expectations:")
        for r in results.results:
            if not r.success:
                print(f"  - {r.expectation_config}")

    return results.success


if __name__ == "__main__":
    try:
        success = run_quality_checks()
        if success:
            print("\nALL DATA QUALITY CHECKS PASSED ✅")
            sys.exit(0)
        else:
            print("\nDATA QUALITY CHECKS FAILED ❌")
            sys.exit(1)
    except Exception as e:
        print(f"\nUnexpected error during quality gates: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
