def changed_paths(repo) -> list[str]:
    try:
        return [item.a_path for item in repo.index.diff(None)]
    except Exception:
        return []
