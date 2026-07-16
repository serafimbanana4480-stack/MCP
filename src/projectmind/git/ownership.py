def ownership(root, path: str) -> dict:
    try:
        from git import Repo

        commits = list(Repo(root).iter_commits(paths=path, max_count=10))
        return {
            "path": path,
            "owners": sorted({c.author.email for c in commits}),
            "commits": len(commits),
        }
    except Exception as exc:
        return {"path": path, "owners": [], "error": str(exc)}
