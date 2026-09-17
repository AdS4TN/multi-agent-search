from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import yaml

from .config import PoolConfig
from .aggregator_adapter import get_yaml_representer


def _unique_node_names(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts: dict[str, int] = {}
    result: list[dict[str, Any]] = []
    for idx, node in enumerate(nodes, start=1):
        item = dict(node)
        name = str(item.get("name") or f"node-{idx}")
        count = counts.get(name, 0)
        counts[name] = count + 1
        if count:
            item["name"] = f"{name} {count + 1}"
        else:
            item["name"] = name
        result.append(item)
    return result


def build_mihomo_config(cfg: PoolConfig, nodes: list[dict[str, Any]]) -> dict[str, Any]:
    nodes = _unique_node_names(nodes)
    names = [str(x["name"]) for x in nodes]
    if not names:
        raise ValueError("没有可写入 Mihomo 配置的代理节点")

    return {
        "mixed-port": cfg.mixed_port,
        "bind-address": cfg.bind_address,
        "allow-lan": cfg.allow_lan,
        "external-controller": cfg.external_controller,
        "mode": cfg.mode,
        "log-level": cfg.log_level,
        "proxies": nodes,
        "proxy-groups": [
            {
                "name": "REDDIT-POOL",
                "type": "select",
                "proxies": ["REDDIT-AUTO", *names],
            },
            {
                "name": "REDDIT-AUTO",
                "type": "fallback",
                "proxies": names,
                "url": cfg.health_url,
                "interval": cfg.health_interval_seconds,
            }
        ],
        "rules": [
            "DOMAIN-SUFFIX,reddit.com,REDDIT-POOL",
            "DOMAIN-SUFFIX,old.reddit.com,REDDIT-POOL",
            "DOMAIN-SUFFIX,redd.it,REDDIT-POOL",
            "DOMAIN-SUFFIX,redditmedia.com,REDDIT-POOL",
            "DOMAIN-SUFFIX,redditstatic.com,REDDIT-POOL",
            "MATCH,REDDIT-POOL",
        ],
    }


def write_mihomo_config(cfg: PoolConfig, nodes: list[dict[str, Any]]) -> Path:
    config = build_mihomo_config(cfg, nodes)
    QuotedStr, quoted_scalar = get_yaml_representer(cfg)
    yaml.add_representer(QuotedStr, quoted_scalar)

    tmp = cfg.config_file.with_suffix(".yaml.tmp")
    with tmp.open("w", encoding="utf-8") as f:
        yaml.dump(config, f, allow_unicode=True, sort_keys=False)
    tmp.replace(cfg.config_file)
    shutil.copyfile(cfg.config_file, cfg.last_good_config_file)
    return cfg.config_file
