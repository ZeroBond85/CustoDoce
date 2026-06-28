import httpx

actions = {
    "actions/setup-python": 8,
    "actions/cache": 8,
    "actions/upload-artifact": 8,
}
for repo, count in actions.items():
    r = httpx.get(
        f"https://api.github.com/repos/{repo}/tags",
        headers={"Accept": "application/vnd.github+json"},
    )
    if r.status_code == 200:
        tags = [t["name"] for t in r.json()[:count]]
        print(f"{repo}: {', '.join(tags)}")
    else:
        print(f"{repo}: HTTP {r.status_code}")
