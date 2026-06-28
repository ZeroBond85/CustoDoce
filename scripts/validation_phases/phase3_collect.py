import os
import subprocess
import sys
from pathlib import Path


def run():
    """Executes Full Production Collection Phase (forced Saturday)."""
    auto = os.environ.get("VALIDATION_AUTO") == "1"

    print("--- Starting Full Production Collection (FORCED) ---")

    root = str(Path(__file__).resolve().parent.parent)
    python = sys.executable

    wrapper_code = f"""import sys
sys.path.insert(0, {root!r})
import os
os.environ.setdefault("SUPABASE_URL", "")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "")
from main import main
from scripts.force_saturday import ForceSaturday
with ForceSaturday():
    main()
"""

    wrapper_path = Path("temp_main_forced.py")
    try:
        wrapper_path.write_text(wrapper_code, encoding="utf-8")

        if auto:
            result = subprocess.run(
                [
                    python,
                    "-c",
                    f"import sys; sys.path.insert(0, {root!r}); from scripts.force_saturday import ForceSaturday; print('ForceSaturday OK')",
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode != 0:
                return False, f"Wrapper validation failed: {result.stderr}"
            print("Auto mode: collection wrapper validated, execution skipped.")
            return True, "Collection wrapper validated (--execute skipped in auto mode)"

        result = subprocess.run(
            [python, wrapper_path.name],
            capture_output=True,
            text=True,
            timeout=2700,
        )
        if result.returncode != 0:
            return False, f"Collection failed: {result.stdout or result.stderr}"
    finally:
        if wrapper_path.exists():
            wrapper_path.unlink()

    if not os.path.exists("data/prices_latest.json"):
        return False, "Collection finished but data/prices_latest.json was not created"

    return True, "Full production collection passed"
