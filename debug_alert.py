import sys
from pathlib import Path
import uuid
from dotenv import load_dotenv
from services import config_db

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

rule_id = str(uuid.uuid4())
rule_data = {
    "id": rule_id,
    "name": "Test Alert Rule",
    "channel": "email",
    "trigger": "price_drop",
    "threshold": 10.0,
    "enabled": True,
    "description": "Test rule description",
}

print(f"Upserting rule: {rule_id}")
result = config_db.upsert_alert_rule(rule_data)
print(f"Upsert result: {result}")

enabled_rules = config_db.get_enabled_alert_rules()
print(f"Enabled rules count: {len(enabled_rules)}")
for r in enabled_rules:
    print(f"  - {r['id']}: {r['name']} (enabled={r['enabled']})")

print(f"Rule found: {any(r['id'] == rule_id for r in enabled_rules)}")
