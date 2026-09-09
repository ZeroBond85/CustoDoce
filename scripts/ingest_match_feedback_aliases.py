#!/usr/bin/env python3
"""
Extract confirmed aliases from match_feedback and upsert into ingredients table.
Runs as step in scrape pipeline. Idempotent (deduplicates aliases).
"""

import os
import re
import sys
from datetime import UTC, datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.supabase_client import get_service_client, rpc_execute


def main() -> None:
    client = get_service_client()

    # Parse "alias → Canonical" from decision_reason
    sql = """
    SELECT DISTINCT mf.matched_ingredient, mf.decision_reason, mf.product_text
    FROM match_feedback mf
    WHERE mf.decision IN ('llm_confirmed', 'manual_approve')
      AND mf.decision_reason ILIKE '%alias%'
    """
    result = rpc_execute(client, "exec_sql_query", {"sql": sql})
    if not result:
        print("No confirmed alias decisions found")
        return

    now = datetime.now(UTC).isoformat()
    processed = 0
    errors = 0

    for row in result:
        # Parse "alias → Canonical" pattern from decision_reason
        match = re.search(r"alias\s*[→:]\s*([^→\n]+)", row.get("decision_reason", ""), re.IGNORECASE)
        if not match:
            continue
        canonical = match.group(1).strip().split()[0]

        # Upsert alias into ingredients table
        ingredient = client.table("ingredients").select("aliases").eq("canonical_name", canonical).maybe_single().execute()
        if not ingredient.data:
            print(f"[WARN] Ingredient not found in DB: {canonical}")
            continue

        aliases = list(set(ingredient.data.get("aliases") or []))
        product_text = row.get("product_text", "")
        if product_text and product_text not in aliases:
            aliases.append(product_text)

        try:
            client.table("ingredients").update({
                "aliases": aliases,
                "updated_at": datetime.now(UTC).isoformat()
            }).eq("canonical_name", canonical).execute()
            processed += 1
        except Exception as e:
            print(f"[ERROR] {canonical}: {e}")
            errors += 1

    print(f"Processed: {processed}, Errors: {errors}")


if __name__ == "__main__":
    main()