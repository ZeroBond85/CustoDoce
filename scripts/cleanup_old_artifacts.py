"""
Cleanup old GitHub Artifacts.
Keeps only the N most recent artifacts matching a prefix.
"""

import argparse
import sys


def cleanup_old_artifacts(repo: str, artifact_prefix: str, keep: int, token: str):
    try:
        from github import Github
    except ImportError:
        print("pip install PyGithub")
        sys.exit(1)

    g = Github(token)
    repo_obj = g.get_repo(repo)
    artifacts = sorted(
        repo_obj.get_actions_artifacts(),
        key=lambda a: a.created_at,
        reverse=True,
    )

    prefix_filtered = [a for a in artifacts if a.name.startswith(artifact_prefix)]
    to_delete = prefix_filtered[keep:]

    for artifact in to_delete:
        print(f"Deleting {artifact.name} (created {artifact.created_at})")
        artifact.delete()

    print(f"Deleted {len(to_delete)} artifacts, kept {min(len(prefix_filtered), keep)}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Cleanup old GitHub Artifacts")
    parser.add_argument("--repo", required=True)
    parser.add_argument("--artifact-prefix", required=True)
    parser.add_argument("--keep", type=int, default=4)
    parser.add_argument("--token", required=True)
    args = parser.parse_args()

    cleanup_old_artifacts(args.repo, args.artifact_prefix, args.keep, args.token)
