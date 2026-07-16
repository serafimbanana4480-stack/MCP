from pathlib import Path


def info(root: Path) -> dict:
    try:
        from git import Repo

        repo = Repo(root)
        return {
            "branch": repo.active_branch.name,
            "commit": repo.head.commit.hexsha,
            "dirty": repo.is_dirty(),
            "recent_commits": [
                c.hexsha[:8] + " " + c.message.strip()
                for c in list(repo.iter_commits(max_count=10))
            ],
        }
    except Exception as exc:
        return {"available": False, "error": str(exc)}
