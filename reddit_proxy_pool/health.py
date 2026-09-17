from __future__ import annotations

from typing import Any

from .config import PoolConfig


def summarize_nodes(nodes: list[dict[str, Any]]) -> dict[str, Any]:
    by_type: dict[str, int] = {}
    for node in nodes:
        t = str(node.get("type", "unknown"))
        by_type[t] = by_type.get(t, 0) + 1
    return {"total": len(nodes), "by_type": by_type}
