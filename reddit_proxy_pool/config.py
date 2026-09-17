from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class PoolConfig:
    aggregator_home: Path
    runtime_dir: Path
    mixed_port: int
    external_controller: str
    bind_address: str
    allow_lan: bool
    mode: str
    log_level: str
    health_url: str
    health_timeout_ms: int
    health_max_delay_ms: int
    health_interval_seconds: int
    reddit_test_url: str
    reddit_user_agent: str
    reddit_timeout_seconds: int

    @property
    def generated_dir(self) -> Path:
        return self.runtime_dir / "generated"

    @property
    def state_dir(self) -> Path:
        return self.runtime_dir / "state"

    @property
    def logs_dir(self) -> Path:
        return self.runtime_dir / "logs"

    @property
    def pid_file(self) -> Path:
        return self.state_dir / "reddit-mihomo.pid"

    @property
    def inventory_file(self) -> Path:
        return self.state_dir / "proxy-inventory.json"

    @property
    def config_file(self) -> Path:
        return self.generated_dir / "reddit-pool.yaml"

    @property
    def last_good_config_file(self) -> Path:
        return self.generated_dir / "reddit-pool.last-good.yaml"

    @property
    def reddit_monitor_dir(self) -> Path:
        return self.runtime_dir / "reddit-monitor"


def _read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def load_pool_config(path: str | Path = "config/reddit-proxy-pool.json") -> PoolConfig:
    p = Path(path)
    data = _read_json(p)
    ports = data.get("ports", {})
    mihomo = data.get("mihomo", {})
    health = data.get("health", {})
    reddit = data.get("reddit_test", {})

    cfg = PoolConfig(
        aggregator_home=Path(data.get("aggregator_home", "D:/Temp/wzdnzd-aggregator")),
        runtime_dir=Path(data.get("runtime_dir", "D:/Temp/reddit-proxy-pool-runtime")),
        mixed_port=int(ports.get("mixed_port", 7898)),
        external_controller=str(ports.get("external_controller", "127.0.0.1:9098")),
        bind_address=str(mihomo.get("bind_address", "127.0.0.1")),
        allow_lan=bool(mihomo.get("allow_lan", False)),
        mode=str(mihomo.get("mode", "rule")),
        log_level=str(mihomo.get("log_level", "info")),
        health_url=str(health.get("url", "https://www.google.com/generate_204")),
        health_timeout_ms=int(health.get("timeout_ms", 5000)),
        health_max_delay_ms=int(health.get("max_delay_ms", 10000)),
        health_interval_seconds=int(health.get("interval_seconds", 600)),
        reddit_test_url=str(reddit.get("url", "https://www.reddit.com/r/artificial/.rss")),
        reddit_user_agent=str(reddit.get("user_agent", "windows:reddit-proxy-pool:0.1 (by /u/local-test; contact: local-test)")),
        reddit_timeout_seconds=int(reddit.get("timeout_seconds", 30)),
    )

    for d in (cfg.runtime_dir, cfg.generated_dir, cfg.state_dir, cfg.logs_dir, cfg.reddit_monitor_dir):
        d.mkdir(parents=True, exist_ok=True)
    return cfg


def load_sources(path: str | Path = "config/proxy-sources.json") -> list[dict[str, Any]]:
    data = _read_json(Path(path))
    if not isinstance(data, list):
        raise ValueError("proxy sources config must be a JSON array")
    return [x for x in data if isinstance(x, dict) and x.get("enabled", True)]
