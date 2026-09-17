from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .util import stable_hash, write_json
from .config import PoolConfig

_META_KEYS = {"_source_id"}


def node_identity(node: dict[str, Any]) -> dict[str, Any]:
    keys = [
        "type", "server", "port", "uuid", "password", "cipher", "sni", "servername",
        "network", "tls", "flow", "obfs", "protocol",
    ]
    return {k: node.get(k) for k in keys if node.get(k) not in (None, "")}


def strip_meta(node: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in node.items() if k not in _META_KEYS}


def build_inventory(cfg: PoolConfig, nodes: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    now = datetime.now(timezone.utc).isoformat()
    seen: dict[str, dict[str, Any]] = {}
    for node in nodes:
        if not node.get("server") or not node.get("port") or not node.get("type"):
            continue
        identity = node_identity(node)
        node_id = stable_hash(identity)
        if node_id in seen:
            # 保留较早节点名称，但合并来源。
            srcs = set(seen[node_id].get("source_ids", []))
            if node.get("_source_id"):
                srcs.add(str(node.get("_source_id")))
            seen[node_id]["source_ids"] = sorted(srcs)
            continue
        record = {
            "node_id": node_id,
            "source_ids": [str(node.get("_source_id"))] if node.get("_source_id") else [],
            "name": str(node.get("name", "")),
            "type": str(node.get("type", "")),
            "server": str(node.get("server", "")),
            "port": node.get("port"),
            "alive": None,
            "latency_ms": None,
            "fail_count": 0,
            "first_seen_at": now,
            "last_seen_at": now,
            "last_checked_at": None,
            "disabled": False,
            "identity": identity,
            "node": strip_meta(node),
        }
        seen[node_id] = record

    inventory = list(seen.values())
    config_nodes = [x["node"] for x in inventory if not x.get("disabled")]
    write_json(cfg.inventory_file, {"updated_at": now, "nodes": inventory})
    return inventory, config_nodes
