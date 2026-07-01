"""
Download the most recent GitHub Actions artifact matching a prefix.
"""

import argparse
import os
import sys
import requests


def download_latest_artifact(repo: str, prefix: str, token: str, output_dir: str):
    os.makedirs(output_dir, exist_ok=True)

    # Use GitHub REST API directly (more reliable than PyGithub for artifacts)
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    url = f"https://api.github.com/repos/{repo}/actions/artifacts"
    resp = requests.get(url, headers=headers, params={"per_page": 100}, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    artifacts = [
        a for a in data.get("artifacts", [])
        if a["name"].startswith(prefix)
    ]
    artifacts.sort(key=lambda a: a["created_at"], reverse=True)

    if not artifacts:
        print(f"No artifacts found with prefix '{prefix}'")
        sys.exit(1)

    latest = artifacts[0]
    print(f"Downloading {latest['name']} (created {latest['created_at'][:10]})")

    # Download artifact zip
    download_url = latest["archive_download_url"]
    resp = requests.get(download_url, headers=headers, stream=True, timeout=60)
    resp.raise_for_status()

    # Extract zip to output_dir
    import zipfile
    import io
    with zipfile.ZipFile(io.BytesIO(resp.content)) as z:
        z.extractall(output_dir)

    print(f"Saved to: {output_dir}")
    return latest["name"]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Download latest GitHub artifact by prefix")
    parser.add_argument("--repo", required=True, help="owner/repo")
    parser.add_argument("--prefix", required=True, help="Artifact name prefix")
    parser.add_argument("--token", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()

    name = download_latest_artifact(args.repo, args.prefix, args.token, args.output_dir)
    print(f"Downloaded: {name}")
