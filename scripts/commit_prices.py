"""Commits data/prices_latest.json to git (sobrescreve .gitignore com --force)."""

import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def _git(cmd: list[str], capture: bool = True) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(
            ["git"] + cmd,
            capture_output=capture,
            text=capture,
            cwd=REPO_ROOT,
            timeout=30,
        )
    except Exception as e:
        return subprocess.CompletedProcess(["git"] + cmd, 1, "", str(e))


def main():
    prices_path = REPO_ROOT / "data" / "prices_latest.json"

    snapshot = None
    if prices_path.exists():
        with open(prices_path) as f:
            snapshot = json.load(f)
        total = snapshot.get("total_prices", len(snapshot) if isinstance(snapshot, list) else 0)
        print(f"Snapshot local: {total} precos")
    else:
        url = os.environ.get("SUPABASE_URL")
        key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
        if url and key:
            try:
                from services.price_repository import get_latest_prices

                prices = get_latest_prices(valid_only=True, limit=2000)
                snapshot = {
                    "collected_at": datetime.now(UTC).isoformat(),
                    "total_prices": len(prices),
                    "ingredients_found": len({p["ingredient_id"] for p in prices}),
                }
                prices_path.parent.mkdir(exist_ok=True)
                with open(prices_path, "w") as f:
                    json.dump(snapshot, f, indent=2, ensure_ascii=False)
                print(f"Snapshot do Supabase: {snapshot['total_prices']} precos")
            except Exception as e:
                print(f"Sem Supabase creds ou erro: {e}")
                print("Nada a commitar.")
                return
        else:
            print("Sem snapshot local nem Supabase creds - nada a commitar.")
            return

    _git(["config", "user.name", "github-actions[bot]"])
    _git(["config", "user.email", "github-actions[bot]@users.noreply.github.com"])

    r = _git(["add", "--force", "data/prices_latest.json"])
    if r.returncode != 0:
        print(f"Erro git add: {r.stderr or r.stdout}")
        sys.exit(1)

    r = _git(["diff", "--cached", "--exit-code", "data/prices_latest.json"])
    if r.returncode == 0:
        print("Nenhuma mudanca - nada a commitar.")
        return

    collected = snapshot.get("collected_at", datetime.now(UTC).isoformat())
    total = snapshot.get("total_prices", 0)
    ingredients = snapshot.get("ingredients_found", 0)
    msg = f"chore: snapshot prices_latest.json ({total} precos, {ingredients} ingredientes)"
    r = _git(["commit", "-m", msg])
    if r.returncode != 0:
        print(f"Erro commit: {r.stderr or r.stdout}")
        sys.exit(1)
    print(f"Commit: {msg}")

    token = os.environ.get("GITHUB_TOKEN", "")
    repo = os.environ.get("GITHUB_REPOSITORY", "ZeroBond85/CustoDoce")
    ref = os.environ.get("GITHUB_REF", "HEAD")
    remote = f"https://x-access-token:{token}@github.com/{repo}.git" if token else "origin"
    r = _git(["push", remote, ref])
    if r.returncode != 0:
        print(f"Erro push: {r.stderr or r.stdout}")
        sys.exit(1)
    print("Push OK.")


if __name__ == "__main__":
    main()
