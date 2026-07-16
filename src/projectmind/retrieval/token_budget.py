def trim_to_budget(items: list[dict], token_budget: int) -> list[dict]:
    out = []
    used = 0
    for item in sorted(items, key=lambda x: x.get("relevance", 0), reverse=True):
        text = str(item.get("content", item.get("body", "")))
        cost = max(1, len(text) // 4)
        if used + cost > token_budget and out:
            continue
        item = {**item, "content": text[: max(200, (token_budget - used) * 4)]}
        out.append(item)
        used += min(cost, token_budget - used)
        if used >= token_budget:
            break
    return out
