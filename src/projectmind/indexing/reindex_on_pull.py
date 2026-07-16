def should_reindex(previous_head: str | None, current_head: str | None) -> bool:
    return bool(previous_head and current_head and previous_head != current_head)
