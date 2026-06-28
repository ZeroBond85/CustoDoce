"""
Download the most recent GitHub Actions artifact matching a prefix.
"""

import argparse
import os
import sys


def download_latest_artifact(repo: str, prefix: str, token: str, output_dir: str):
    try:
        from github import Github
    except ImportError:
        print("ERROR: PyGithub required. Install with: pip install PyGithub")
        sys.exit(1)

    os.makedirs(output_dir, exist_ok=True)
    g = Github(token)
    repo_obj = g.get_repo(repo)

    artifacts = sorted(
        [a for a in repo_obj.get_actions_artifacts().get_page(0) if a.name.startswith(prefix)],
        key=lambda a: a.created_at,
        reverse=True,
    )

    if not artifacts:
        print(f"No artifacts found with prefix '{prefix}'")
        sys.exit(1)

    latest = artifacts[0]
    print(f"Downloading {latest.name} (created {latest.created_at.date()})")
    latest.download_archive(output_dir)
    print(f"Saved to: {output_dir}")
    return latest.name


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Download latest GitHub artifact by prefix")
    parser.add_argument("--repo", required=True, help="owner/repo")
    parser.add_argument("--prefix", required=True, help="Artifact name prefix")
    parser.add_argument("--token", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()

    name = download_latest_artifact(args.repo, args.prefix, args.token, args.output_dir)
    print(f"Downloaded: {name}")
