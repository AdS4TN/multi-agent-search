from __future__ import annotations

import json
import copy
import random
import re
import shutil
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import yaml

from . import runtime
from .aggregator_adapter import parse_sources
from .config import PoolConfig
from .config import load_sources
from .health import summarize_nodes
from .inventory import build_inventory
from .mihomo_config import write_mihomo_config
from .util import stable_hash, write_json, read_json
from tech_radar.image_extraction import extract_image_from_html


STATE_VERSION = 2
GROUP_NAME = "REDDIT-POOL"
AUTO_GROUP_NAME = "REDDIT-AUTO"
DEFAULT_REGISTRY_PATH = "config/reddit-subreddits.json"
DEFAULT_PROXY_SOURCES_PATH = "config/proxy-sources.json"


@dataclass(frozen=True)
class RedditView:
    key: str
    label: str
    path: str
    weight: int


@dataclass(frozen=True)
class SubredditSpec:
    name: str
    category: str
    enabled: bool
    priority: bool
    topics: list[str]
    note: str


@dataclass(frozen=True)
class MonitorSettings:
    interval_min_minutes: int
    interval_max_minutes: int
    global_min_request_seconds: int
    timezone: str
    include_crypto: bool
    views: list[RedditView]


@dataclass(frozen=True)
class MonitorRegistry:
    settings: MonitorSettings
    subreddits: list[SubredditSpec]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_now() -> str:
    return utc_now().isoformat()


def parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        return None


def local_tz(name: str) -> timezone:
    # 当前项目默认 Asia/Shanghai；避免额外依赖，先实现固定偏移。
    if name == "Asia/Shanghai":
        return timezone(timedelta(hours=8))
    return timezone.utc


def monitor_root(cfg: PoolConfig) -> Path:
    return cfg.reddit_monitor_dir


def monitor_state_file(cfg: PoolConfig) -> Path:
    return monitor_root(cfg) / "state.json"


def monitor_latest_dir(cfg: PoolConfig) -> Path:
    return monitor_root(cfg) / "latest"


def monitor_runs_dir(cfg: PoolConfig) -> Path:
    return monitor_root(cfg) / "runs"


def load_registry(path: str | Path = DEFAULT_REGISTRY_PATH) -> MonitorRegistry:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    raw_settings = data.get("settings", {})
    views = [
        RedditView(
            key=str(x.get("key", "")).strip(),
            label=str(x.get("label", "")).strip(),
            path=str(x.get("path", "")).strip(),
            weight=int(x.get("weight", 1)),
        )
        for x in raw_settings.get("views", [])
        if isinstance(x, dict) and x.get("key") and x.get("path")
    ]
    if not views:
        raise ValueError("reddit subreddit registry missing views")

    settings = MonitorSettings(
        interval_min_minutes=int(raw_settings.get("interval_min_minutes", 30)),
        interval_max_minutes=int(raw_settings.get("interval_max_minutes", 60)),
        global_min_request_seconds=int(raw_settings.get("global_min_request_seconds", 60)),
        timezone=str(raw_settings.get("timezone", "Asia/Shanghai")),
        include_crypto=bool(raw_settings.get("include_crypto", True)),
        views=views,
    )
    if settings.interval_min_minutes <= 0 or settings.interval_max_minutes < settings.interval_min_minutes:
        raise ValueError("invalid reddit monitor interval settings")

    specs: list[SubredditSpec] = []
    for raw in data.get("subreddits", []):
        if not isinstance(raw, dict) or not raw.get("name"):
            continue
        category = str(raw.get("category", "general"))
        if category == "crypto" and not settings.include_crypto:
            continue
        specs.append(
            SubredditSpec(
                name=str(raw.get("name")).strip().strip("/"),
                category=category,
                enabled=bool(raw.get("enabled", True)),
                priority=bool(raw.get("priority", False)),
                topics=[str(x) for x in raw.get("topics", []) if str(x).strip()],
                note=str(raw.get("note", "")),
            )
        )
    return MonitorRegistry(settings=settings, subreddits=specs)


def jitter_seconds(settings: MonitorSettings, *, cooldown: str | None = None) -> int:
    rng = random.SystemRandom()
    if cooldown == "403":
        return rng.randint(30 * 60, 60 * 60)
    if cooldown == "429":
        return rng.randint(10 * 60, 30 * 60)
    return rng.randint(settings.interval_min_minutes * 60, settings.interval_max_minutes * 60)


def seconds_until(value: str | None) -> int:
    """计算某个 ISO 时间距离现在还剩多少秒；过期或空值返回 0。"""
    stamp = parse_iso(value)
    if not stamp:
        return 0
    return max(0, int((stamp - utc_now()).total_seconds()))


def global_reddit_cooldown_remaining(state: dict[str, Any]) -> int:
    """403/429 后的全局冷却；冷却期间不继续请求任何 subreddit。"""
    return seconds_until(state.setdefault("global", {}).get("reddit_cooldown_until"))


def apply_global_reddit_cooldown(state: dict[str, Any], settings: MonitorSettings, code: int) -> int:
    seconds = jitter_seconds(settings, cooldown=str(code))
    now = utc_now()
    state.setdefault("global", {}).update(
        {
            "reddit_cooldown_until": (now + timedelta(seconds=seconds)).isoformat(),
            "last_block_code": code,
            "last_block_at": now.isoformat(),
        }
    )
    return seconds


def init_state(cfg: PoolConfig, registry: MonitorRegistry, *, reset: bool = False, due_now: bool = False) -> dict[str, Any]:
    path = monitor_state_file(cfg)
    now = utc_now()
    state: dict[str, Any]
    if path.exists() and not reset:
        state = read_json(path, {})
    else:
        state = {}

    state["version"] = STATE_VERSION
    state.setdefault("created_at", now.isoformat())
    state["updated_at"] = now.isoformat()
    state.setdefault("global", {})
    state["global"].setdefault("last_request_at", None)
    state["global"].setdefault("node_cursor", 0)
    state["global"].setdefault("reddit_cooldown_until", None)
    state["global"].setdefault("last_block_code", None)
    state["global"].setdefault("last_block_at", None)
    state.setdefault("node_failures", {})
    state.setdefault("subreddits", {})

    enabled_names = set()
    for spec in registry.subreddits:
        if not spec.enabled:
            continue
        enabled_names.add(spec.name)
        current = state["subreddits"].get(spec.name, {})
        if due_now:
            next_due = now
        elif current.get("next_due_at"):
            next_due = parse_iso(current.get("next_due_at")) or now
        else:
            next_due = now + timedelta(seconds=random.SystemRandom().randint(0, jitter_seconds(registry.settings)))

        state["subreddits"][spec.name] = {
            **current,
            "enabled": True,
            "category": spec.category,
            "priority": spec.priority,
            "topics": spec.topics,
            "note": spec.note,
            "next_due_at": next_due.isoformat(),
            "last_success_at": current.get("last_success_at"),
            "last_error": current.get("last_error", ""),
            "consecutive_failures": int(current.get("consecutive_failures", 0)),
            "last_run_file": current.get("last_run_file"),
            "last_run_summary": current.get("last_run_summary"),
        }

    for name, item in list(state["subreddits"].items()):
        if name not in enabled_names:
            item["enabled"] = False

    write_json(path, state)
    return state


def load_state(cfg: PoolConfig, registry: MonitorRegistry) -> dict[str, Any]:
    path = monitor_state_file(cfg)
    if not path.exists():
        return init_state(cfg, registry)
    state = read_json(path, {})
    if int(state.get("version", 0)) != STATE_VERSION:
        state["version"] = STATE_VERSION
    return init_state(cfg, registry, reset=False)


def subreddit_url(subreddit: str, view: RedditView) -> str:
    path = view.path.lstrip("/")
    return f"https://www.reddit.com/r/{urllib.parse.quote(subreddit, safe='')}/{path}"


def ensure_selectable_reddit_pool_config(cfg: PoolConfig) -> bool:
    """确保 REDDIT-POOL 是 select 组，默认指向 REDDIT-AUTO，监控器可手动轮换节点。"""
    if not cfg.config_file.exists():
        raise FileNotFoundError(f"代理池配置不存在，请先运行 update：{cfg.config_file}")

    data = yaml.safe_load(cfg.config_file.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"无法读取 Mihomo 配置：{cfg.config_file}")
    proxies = data.get("proxies", [])
    names = [str(x.get("name")) for x in proxies if isinstance(x, dict) and x.get("name")]
    if not names:
        raise ValueError("Mihomo 配置中没有代理节点")

    expected_select = {"name": GROUP_NAME, "type": "select", "proxies": [AUTO_GROUP_NAME, *names]}
    expected_auto = {
        "name": AUTO_GROUP_NAME,
        "type": "fallback",
        "proxies": names,
        "url": cfg.health_url,
        "interval": cfg.health_interval_seconds,
    }

    groups = [x for x in data.get("proxy-groups", []) if isinstance(x, dict)]
    existing_select = next((x for x in groups if x.get("name") == GROUP_NAME), None)
    existing_auto = next((x for x in groups if x.get("name") == AUTO_GROUP_NAME), None)
    already_ok = existing_select == expected_select and existing_auto == expected_auto
    if already_ok:
        return False

    preserved = [x for x in groups if x.get("name") not in {GROUP_NAME, AUTO_GROUP_NAME}]
    data["proxy-groups"] = [expected_select, expected_auto, *preserved]

    tmp = cfg.config_file.with_suffix(".yaml.tmp")
    tmp.write_text(yaml.dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")
    tmp.replace(cfg.config_file)
    shutil.copyfile(cfg.config_file, cfg.last_good_config_file)
    return True


def ensure_runtime_ready(cfg: PoolConfig, *, allow_restart: bool = True) -> dict[str, Any]:
    changed = ensure_selectable_reddit_pool_config(cfg)
    status = runtime.status(cfg)
    running = bool(status.get("process_alive") and status.get("mixed_port_open") and status.get("controller_open"))
    if changed and running:
        if not allow_restart:
            raise RuntimeError("Mihomo 配置已更新但当前进程仍在运行；请重启后再监控")
        runtime.stop(cfg)
        running = False
    if not running:
        pid = runtime.start(cfg)
        status = runtime.status(cfg)
        status["started_by_monitor"] = True
        status["pid"] = pid
    status["config_rewritten"] = changed
    return status


def update_proxy_pool_config(
    cfg: PoolConfig,
    sources_path: str | Path = DEFAULT_PROXY_SOURCES_PATH,
) -> dict[str, Any]:
    """拉取订阅并重建 Mihomo 配置。

    Reddit RSS 采集强依赖代理池。这里在每次真实采集前主动刷新订阅：
    - 至少解析出一个节点时，写入新的 reddit-pool.yaml。
    - 若所有订阅均失败，不覆盖已有配置，采集可继续尝试使用 last-good 配置。
    """
    started = iso_now()
    try:
        sources = load_sources(sources_path)
        nodes, reports = parse_sources(cfg, sources)
        inventory, config_nodes = build_inventory(cfg, nodes)
        reports_file = cfg.logs_dir / "aggregator-report.json"
        write_json(reports_file, reports)
        summary: dict[str, Any] = {
            "ok": bool(config_nodes),
            "started_at": started,
            "finished_at": iso_now(),
            "sources": len(sources),
            "parsed_nodes": len(nodes),
            "inventory_nodes": len(inventory),
            "config_nodes": len(config_nodes),
            "node_summary": summarize_nodes(config_nodes),
            "reports_file": str(reports_file),
            "reports": reports,
        }
        if not config_nodes:
            summary["error"] = "没有解析到可用代理节点，保留上一份代理配置"
            return summary
        path = write_mihomo_config(cfg, config_nodes)
        summary["config_file"] = str(path)
        return summary
    except Exception as exc:
        return {
            "ok": False,
            "started_at": started,
            "finished_at": iso_now(),
            "sources_path": str(sources_path),
            "error": f"{type(exc).__name__}: {exc}",
        }


def proxy_names_from_config(cfg: PoolConfig) -> list[str]:
    data = yaml.safe_load(cfg.config_file.read_text(encoding="utf-8"))
    proxies = data.get("proxies", []) if isinstance(data, dict) else []
    return [str(x.get("name")) for x in proxies if isinstance(x, dict) and x.get("name")]


def unique_names(names: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for name in names:
        if not name or name in seen:
            continue
        seen.add(name)
        result.append(name)
    return result


def inventory_by_name(cfg: PoolConfig) -> dict[str, dict[str, Any]]:
    data = read_json(cfg.inventory_file, {})
    nodes = data.get("nodes", []) if isinstance(data, dict) else []
    return {str(x.get("name")): x for x in nodes if isinstance(x, dict) and x.get("name")}


def node_cooldown_remaining(state: dict[str, Any], node_name: str) -> int:
    item = state.setdefault("node_failures", {}).get(node_name, {})
    if not isinstance(item, dict):
        return 0
    return seconds_until(item.get("cooldown_until"))


def choose_nodes(
    state: dict[str, Any],
    proxy_names: list[str],
    count: int,
    *,
    inventory: dict[str, dict[str, Any]] | None = None,
) -> list[str]:
    names = unique_names(proxy_names)
    if not names:
        raise ValueError("没有可轮换的代理节点")
    cursor = int(state.setdefault("global", {}).get("node_cursor", 0)) % len(names)
    rotated = names[cursor:] + names[:cursor]
    inventory = inventory or {}

    eligible: list[str] = []
    fallback: list[str] = []
    for name in rotated:
        inv = inventory.get(name, {})
        if inv.get("disabled"):
            continue
        if node_cooldown_remaining(state, name) > 0:
            fallback.append(name)
            continue
        # health-check 还没落地时 alive 通常为 None；None 不跳过，只有显式 False 才跳过。
        if inv.get("alive") is False:
            fallback.append(name)
            continue
        eligible.append(name)

    ordered = eligible + [x for x in fallback if x not in eligible]
    if not ordered:
        ordered = rotated

    selected: list[str] = []
    for name in ordered:
        if name not in selected:
            selected.append(name)
        if len(selected) >= count:
            break
    while len(selected) < count:
        selected.append(ordered[len(selected) % len(ordered)])

    state["global"]["node_cursor"] = (cursor + count) % len(names)
    return selected


def should_cool_node(record: dict[str, Any]) -> bool:
    if record.get("ok"):
        return False
    status = record.get("status")
    if status in (401, 404):
        return False
    return bool(record.get("requested_at") or record.get("error") or status)


def node_failure_cooldown_seconds(settings: MonitorSettings, record: dict[str, Any]) -> int:
    status = record.get("status")
    if status in (403, 429):
        return jitter_seconds(settings, cooldown=str(status))
    # TLS EOF、连接超时、代理链路失败等通常是节点层问题；短期冷却即可。
    return random.SystemRandom().randint(20 * 60, 45 * 60)


def record_node_result(
    state: dict[str, Any],
    node_name: str,
    record: dict[str, Any],
    settings: MonitorSettings,
) -> None:
    if not node_name:
        return
    nodes = state.setdefault("node_failures", {})
    item = nodes.setdefault(node_name, {})
    now = iso_now()
    if record.get("ok"):
        item.update(
            {
                "last_success_at": now,
                "last_status": record.get("status"),
                "last_error": "",
                "fail_count": 0,
                "cooldown_until": None,
            }
        )
        item["success_count"] = int(item.get("success_count", 0)) + 1
        return

    if not should_cool_node(record):
        return
    cooldown = node_failure_cooldown_seconds(settings, record)
    item.update(
        {
            "last_failure_at": now,
            "last_status": record.get("status"),
            "last_error": str(record.get("error", ""))[:300],
            "fail_count": int(item.get("fail_count", 0)) + 1,
            "cooldown_until": (utc_now() + timedelta(seconds=cooldown)).isoformat(),
        }
    )


def summarize_node_cooldowns(state: dict[str, Any]) -> dict[str, Any]:
    active = []
    for name, item in state.get("node_failures", {}).items():
        if not isinstance(item, dict):
            continue
        remaining = seconds_until(item.get("cooldown_until"))
        if remaining > 0:
            active.append(
                {
                    "name": name,
                    "remaining_seconds": remaining,
                    "last_status": item.get("last_status"),
                    "fail_count": item.get("fail_count", 0),
                    "last_error": item.get("last_error", ""),
                }
            )
    active.sort(key=lambda x: int(x["remaining_seconds"]), reverse=True)
    return {"active_count": len(active), "sample": active[:10]}


def select_proxy_node(cfg: PoolConfig, node_name: str) -> None:
    encoded = urllib.parse.quote(GROUP_NAME, safe="")
    runtime.controller_put(cfg, f"/proxies/{encoded}", {"name": node_name}, timeout=5)


def wait_for_reddit_slot(state: dict[str, Any], settings: MonitorSettings) -> int:
    last = parse_iso(state.setdefault("global", {}).get("last_request_at"))
    if not last:
        return 0
    due = last + timedelta(seconds=settings.global_min_request_seconds)
    seconds = max(0, int((due - utc_now()).total_seconds()))
    if seconds > 0:
        time.sleep(seconds)
    return seconds


def fetch_rss(cfg: PoolConfig, url: str) -> tuple[int, str, bytes]:
    proxy = f"http://127.0.0.1:{cfg.mixed_port}"
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({"http": proxy, "https": proxy}))
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": cfg.reddit_user_agent,
            "Accept": "application/atom+xml, application/rss+xml, application/xml;q=0.9, text/xml;q=0.8, */*;q=0.5",
            "Accept-Language": "en-US,en;q=0.9",
        },
    )
    with opener.open(req, timeout=cfg.reddit_timeout_seconds) as resp:
        return int(resp.status), str(resp.headers.get("content-type", "")), resp.read()


def parse_atom_entries(feed_bytes: bytes, tz_name: str) -> list[dict[str, Any]]:
    root = ET.fromstring(feed_bytes)
    ns = {"a": "http://www.w3.org/2005/Atom"}
    tz = local_tz(tz_name)
    entries: list[dict[str, Any]] = []
    for entry in root.findall("a:entry", ns):
        title = (entry.findtext("a:title", default="", namespaces=ns) or "").strip()
        published = (entry.findtext("a:published", default="", namespaces=ns) or "").strip()
        updated = (entry.findtext("a:updated", default="", namespaces=ns) or "").strip()
        entry_id = (entry.findtext("a:id", default="", namespaces=ns) or "").strip()
        author = (entry.findtext("a:author/a:name", default="", namespaces=ns) or "").strip()
        summary_html = (entry.findtext("a:summary", default="", namespaces=ns) or "").strip()
        content_html = (entry.findtext("a:content", default="", namespaces=ns) or "").strip()
        href = ""
        for link in entry.findall("a:link", ns):
            if link.attrib.get("rel", "alternate") == "alternate" and link.attrib.get("href"):
                href = link.attrib["href"]
                break
        stamp = published or updated
        local_date = ""
        if stamp:
            try:
                raw = stamp[:-1] + "+00:00" if stamp.endswith("Z") else stamp
                local_date = datetime.fromisoformat(raw).astimezone(tz).date().isoformat()
            except Exception:
                local_date = ""
        image = extract_image_from_html(
            content_html or summary_html,
            base_url=href,
            source="reddit_atom_img",
        )
        item = {
            "title": title,
            "url": href,
            "id": entry_id,
            "post_id": extract_post_id(href) or extract_post_id(entry_id),
            "author": author,
            "published": published,
            "updated": updated,
            "local_date": local_date,
        }
        item.update(image)
        entries.append(
            item
        )
    return entries


def extract_post_id(value: str) -> str:
    if not value:
        return ""
    match = re.search(r"/comments/([a-z0-9]+)/", value, re.I)
    if match:
        return match.group(1).lower()
    match = re.search(r"\bt3_([a-z0-9]+)\b", value, re.I)
    if match:
        return match.group(1).lower()
    return ""


def entry_key(entry: dict[str, Any]) -> str:
    if entry.get("post_id"):
        return f"post:{entry['post_id']}"
    if entry.get("url"):
        return f"url:{entry['url']}"
    return f"title:{stable_hash(entry.get('title', ''))}"


def score_candidates(view_results: list[dict[str, Any]], registry: MonitorRegistry) -> list[dict[str, Any]]:
    weights = {v.key: v.weight for v in registry.settings.views}
    by_key: dict[str, dict[str, Any]] = {}
    for result in view_results:
        view = result.get("key")
        for entry in result.get("entries", []):
            key = entry_key(entry)
            item = by_key.setdefault(
                key,
                {
                    **entry,
                    "view_hits": [],
                    "reddit_score": 0,
                    "first_seen_view": view,
                },
            )
            if view not in item["view_hits"]:
                item["view_hits"].append(view)
                item["reddit_score"] += int(weights.get(str(view), 1))
    for item in by_key.values():
        hits = item.get("view_hits", [])
        if len(hits) > 1:
            item["reddit_score"] += min(3, len(hits) - 1)
    return sorted(by_key.values(), key=lambda x: (int(x.get("reddit_score", 0)), x.get("published") or x.get("updated") or ""), reverse=True)


def write_run_result(cfg: PoolConfig, subreddit: str, result: dict[str, Any], tz_name: str) -> Path:
    tz = local_tz(tz_name)
    now_local = utc_now().astimezone(tz)
    date_dir = monitor_runs_dir(cfg) / now_local.date().isoformat()
    date_dir.mkdir(parents=True, exist_ok=True)
    latest_dir = monitor_latest_dir(cfg)
    latest_dir.mkdir(parents=True, exist_ok=True)
    run_path = date_dir / f"{now_local.strftime('%H%M%S')}-{subreddit}.json"
    write_json(run_path, result)
    write_json(latest_dir / f"{subreddit}.json", result)
    return run_path


def run_subreddit(
    cfg: PoolConfig,
    registry: MonitorRegistry,
    state: dict[str, Any],
    spec: SubredditSpec,
    *,
    dry_run: bool = False,
) -> dict[str, Any]:
    if dry_run and not cfg.config_file.exists():
        proxy_names = [f"DRY-RUN-NODE-{i}" for i in range(1, len(registry.settings.views) + 1)]
    else:
        proxy_names = proxy_names_from_config(cfg)
    nodes = choose_nodes(state, proxy_names, len(registry.settings.views), inventory=inventory_by_name(cfg))
    started = iso_now()
    view_results: list[dict[str, Any]] = []
    blocked_code: int | None = None

    for view, node_name in zip(registry.settings.views, nodes):
        url = subreddit_url(spec.name, view)
        record: dict[str, Any] = {
            "key": view.key,
            "label": view.label,
            "url": url,
            "proxy_node": node_name,
            "ok": False,
            "status": None,
            "content_type": "",
            "entry_count": 0,
            "today_count": 0,
            "entries": [],
            "error": "",
            "requested_at": None,
            "waited_seconds": 0,
        }
        if dry_run:
            record["ok"] = True
            record["dry_run"] = True
            view_results.append(record)
            continue

        waited = wait_for_reddit_slot(state, registry.settings)
        record["waited_seconds"] = waited
        record["requested_at"] = iso_now()
        try:
            select_proxy_node(cfg, node_name)
            status, content_type, body = fetch_rss(cfg, url)
            state["global"]["last_request_at"] = iso_now()
            record.update({"status": status, "content_type": content_type})
            entries = parse_atom_entries(body, registry.settings.timezone)
            today = utc_now().astimezone(local_tz(registry.settings.timezone)).date().isoformat()
            record.update(
                {
                    "ok": 200 <= status < 300,
                    "entry_count": len(entries),
                    "today_count": sum(1 for x in entries if x.get("local_date") == today),
                    "entries": entries,
                }
            )
        except urllib.error.HTTPError as exc:
            state["global"]["last_request_at"] = iso_now()
            sample = exc.read(300).decode("utf-8", errors="ignore").replace("\n", " ")
            record.update({"status": exc.code, "error": sample})
            if exc.code in (403, 429):
                blocked_code = exc.code
        except Exception as exc:
            state["global"]["last_request_at"] = iso_now()
            record.update({"error": f"{type(exc).__name__}: {exc}"})
        view_results.append(record)
        record_node_result(state, node_name, record, registry.settings)
        if blocked_code:
            apply_global_reddit_cooldown(state, registry.settings, blocked_code)
        write_json(monitor_state_file(cfg), state)
        if blocked_code:
            break

    candidates = score_candidates(view_results, registry)
    today = utc_now().astimezone(local_tz(registry.settings.timezone)).date().isoformat()
    today_candidates = [x for x in candidates if x.get("local_date") == today]
    ok_views = sum(1 for x in view_results if x.get("ok"))
    result = {
        "subreddit": spec.name,
        "category": spec.category,
        "topics": spec.topics,
        "started_at": started,
        "finished_at": iso_now(),
        "timezone": registry.settings.timezone,
        "today_local": today,
        "dry_run": dry_run,
        "views": view_results,
        "candidates": candidates,
        "today_candidates": today_candidates,
        "summary": {
            "view_count": len(view_results),
            "ok_views": ok_views,
            "entry_count": sum(int(x.get("entry_count", 0)) for x in view_results),
            "today_entry_count": sum(int(x.get("today_count", 0)) for x in view_results),
            "candidate_count": len(candidates),
            "today_candidate_count": len(today_candidates),
            "blocked_code": blocked_code,
            "nodes": nodes[: len(view_results)],
        },
    }

    if not dry_run:
        run_path = write_run_result(cfg, spec.name, result, registry.settings.timezone)
        item = state["subreddits"].setdefault(spec.name, {})
        cooldown = str(blocked_code) if blocked_code in (403, 429) else None
        item["next_due_at"] = (utc_now() + timedelta(seconds=jitter_seconds(registry.settings, cooldown=cooldown))).isoformat()
        item["last_run_file"] = str(run_path)
        item["last_run_summary"] = result["summary"]
        if ok_views:
            item["last_success_at"] = iso_now()
            item["last_error"] = ""
            item["consecutive_failures"] = 0
        else:
            item["last_error"] = "; ".join([str(x.get("error")) for x in view_results if x.get("error")])[:500]
            item["consecutive_failures"] = int(item.get("consecutive_failures", 0)) + 1
    return result


def due_subreddits(registry: MonitorRegistry, state: dict[str, Any], *, force: bool = False, only: list[str] | None = None) -> list[SubredditSpec]:
    now = utc_now()
    only_set = {x.lower() for x in only or []}
    by_name = {s.name: s for s in registry.subreddits if s.enabled}
    specs: list[SubredditSpec] = []
    for name, item in state.get("subreddits", {}).items():
        spec = by_name.get(name)
        if not spec or not item.get("enabled", True):
            continue
        if only_set and name.lower() not in only_set:
            continue
        next_due = parse_iso(item.get("next_due_at"))
        if force or not next_due or next_due <= now:
            specs.append(spec)
    return sorted(specs, key=lambda s: (not s.priority, parse_iso(state["subreddits"].get(s.name, {}).get("next_due_at")) or now, s.name.lower()))


def run_once(
    cfg: PoolConfig,
    registry_path: str | Path = DEFAULT_REGISTRY_PATH,
    *,
    subreddits: list[str] | None = None,
    max_subreddits: int = 1,
    force: bool = False,
    dry_run: bool = False,
    proxy_sources_path: str | Path = DEFAULT_PROXY_SOURCES_PATH,
    update_proxies_before_run: bool = True,
) -> dict[str, Any]:
    registry = load_registry(registry_path)
    state = load_state(cfg, registry)
    if dry_run:
        state = copy.deepcopy(state)
    selected = due_subreddits(registry, state, force=force, only=subreddits)[: max(1, max_subreddits)]
    runtime_info: dict[str, Any] | None = None
    cooldown_remaining = global_reddit_cooldown_remaining(state)
    if selected and not dry_run and cooldown_remaining > 0:
        state["updated_at"] = iso_now()
        write_json(monitor_state_file(cfg), state)
        return {
            "ok": True,
            "dry_run": dry_run,
            "selected": [],
            "skipped": [s.name for s in selected],
            "skipped_reason": "global_reddit_cooldown",
            "cooldown_remaining_seconds": cooldown_remaining,
            "runtime": None,
            "results": [],
        }
    proxy_update: dict[str, Any] | None = None
    if selected and not dry_run and update_proxies_before_run:
        proxy_update = update_proxy_pool_config(cfg, proxy_sources_path)

    if selected and not dry_run:
        runtime_info = ensure_runtime_ready(cfg)
        if proxy_update is not None:
            runtime_info["proxy_update"] = proxy_update

    results = []
    for spec in selected:
        results.append(run_subreddit(cfg, registry, state, spec, dry_run=dry_run))
        if not dry_run:
            write_json(monitor_state_file(cfg), state)

    if not dry_run:
        state["updated_at"] = iso_now()
        write_json(monitor_state_file(cfg), state)
    return {
        "ok": True,
        "dry_run": dry_run,
        "selected": [s.name for s in selected],
        "runtime": runtime_info,
        "proxy_update": proxy_update,
        "results": [
            {
                "subreddit": x["subreddit"],
                "summary": x["summary"],
                "latest_file": str(monitor_latest_dir(cfg) / f"{x['subreddit']}.json") if not dry_run else None,
            }
            for x in results
        ],
    }


def status(cfg: PoolConfig, registry_path: str | Path = DEFAULT_REGISTRY_PATH) -> dict[str, Any]:
    registry = load_registry(registry_path)
    state = load_state(cfg, registry)
    now = utc_now()
    rows = []
    for spec in registry.subreddits:
        item = state.get("subreddits", {}).get(spec.name, {})
        if not item.get("enabled", spec.enabled):
            continue
        next_due = parse_iso(item.get("next_due_at"))
        rows.append(
            {
                "subreddit": spec.name,
                "category": spec.category,
                "priority": spec.priority,
                "next_due_at": item.get("next_due_at"),
                "due_in_seconds": int((next_due - now).total_seconds()) if next_due else 0,
                "last_success_at": item.get("last_success_at"),
                "consecutive_failures": item.get("consecutive_failures", 0),
                "last_error": item.get("last_error", ""),
                "last_run_file": item.get("last_run_file"),
            }
        )
    rows.sort(key=lambda x: (int(x["due_in_seconds"]), not bool(x["priority"]), str(x["subreddit"]).lower()))
    requests_per_subreddit = len(registry.settings.views)
    min_seconds = max(1, registry.settings.global_min_request_seconds)
    return {
        "state_file": str(monitor_state_file(cfg)),
        "subreddits": len(rows),
        "due_now": sum(1 for x in rows if int(x["due_in_seconds"]) <= 0),
        "capacity": {
            "requests_per_subreddit": requests_per_subreddit,
            "global_min_request_seconds": min_seconds,
            "max_subreddit_runs_per_hour": round(3600 / (requests_per_subreddit * min_seconds), 2),
            "estimated_full_round_minutes": round(len(rows) * requests_per_subreddit * min_seconds / 60, 1),
        },
        "global": state.get("global", {}),
        "global_cooldown_remaining_seconds": global_reddit_cooldown_remaining(state),
        "node_cooldowns": summarize_node_cooldowns(state),
        "rows": rows,
    }


def daemon(
    cfg: PoolConfig,
    registry_path: str | Path = DEFAULT_REGISTRY_PATH,
    *,
    poll_seconds: int = 60,
    max_cycles: int | None = None,
    proxy_sources_path: str | Path = DEFAULT_PROXY_SOURCES_PATH,
    update_proxies_before_run: bool = True,
) -> dict[str, Any]:
    cycles = 0
    runs = []
    while True:
        result = run_once(
            cfg,
            registry_path,
            max_subreddits=1,
            force=False,
            dry_run=False,
            proxy_sources_path=proxy_sources_path,
            update_proxies_before_run=update_proxies_before_run,
        )
        if result.get("selected"):
            runs.append(result)
        cycles += 1
        if max_cycles is not None and cycles >= max_cycles:
            return {"ok": True, "cycles": cycles, "runs": runs}
        time.sleep(max(10, poll_seconds))
