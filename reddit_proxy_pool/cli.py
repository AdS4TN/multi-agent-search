from __future__ import annotations

import argparse
import json
import sys

from .aggregator_adapter import parse_sources
from .config import load_pool_config, load_sources
from .health import summarize_nodes
from .inventory import build_inventory
from .mihomo_config import write_mihomo_config
from .reddit_test import test_reddit_rss
from . import reddit_monitor
from . import runtime
from .util import write_json


def cmd_update(args: argparse.Namespace) -> int:
    cfg = load_pool_config(args.config)
    sources = load_sources(args.sources)
    nodes, reports = parse_sources(cfg, sources)
    inventory, config_nodes = build_inventory(cfg, nodes)
    reports_file = cfg.logs_dir / "aggregator-report.json"
    write_json(reports_file, reports)
    if not config_nodes:
        print("没有解析到可用代理节点，未生成配置", file=sys.stderr)
        print(json.dumps({"reports": reports}, ensure_ascii=False, indent=2))
        return 2
    path = write_mihomo_config(cfg, config_nodes)
    summary = {
        "sources": len(sources),
        "parsed_nodes": len(nodes),
        "inventory_nodes": len(inventory),
        "config_nodes": len(config_nodes),
        "node_summary": summarize_nodes(config_nodes),
        "config_file": str(path),
        "inventory_file": str(cfg.inventory_file),
        "reports_file": str(reports_file),
        "reports": reports,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))
    return 0


def cmd_start(args: argparse.Namespace) -> int:
    cfg = load_pool_config(args.config)
    pid = runtime.start(cfg)
    print(json.dumps({"started": True, "pid": pid, "mixed_port": cfg.mixed_port, "controller": cfg.external_controller}, ensure_ascii=False, indent=2))
    return 0


def cmd_stop(args: argparse.Namespace) -> int:
    cfg = load_pool_config(args.config)
    stopped = runtime.stop(cfg)
    print(json.dumps({"stopped": stopped}, ensure_ascii=False, indent=2))
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    cfg = load_pool_config(args.config)
    print(json.dumps(runtime.status(cfg), ensure_ascii=False, indent=2, default=str))
    return 0


def cmd_test_reddit(args: argparse.Namespace) -> int:
    cfg = load_pool_config(args.config)
    result = test_reddit_rss(cfg)
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0 if result.get("ok") else 3


def cmd_restart(args: argparse.Namespace) -> int:
    cfg = load_pool_config(args.config)
    runtime.stop(cfg)
    pid = runtime.start(cfg)
    print(json.dumps({"restarted": True, "pid": pid}, ensure_ascii=False, indent=2))
    return 0


def cmd_reddit_monitor_init(args: argparse.Namespace) -> int:
    cfg = load_pool_config(args.config)
    registry = reddit_monitor.load_registry(args.registry)
    state = reddit_monitor.init_state(cfg, registry, reset=args.reset, due_now=args.due_now)
    print(json.dumps({"ok": True, "state_file": str(reddit_monitor.monitor_state_file(cfg)), "subreddits": len(state.get("subreddits", {}))}, ensure_ascii=False, indent=2, default=str))
    return 0


def cmd_reddit_monitor_status(args: argparse.Namespace) -> int:
    cfg = load_pool_config(args.config)
    result = reddit_monitor.status(cfg, args.registry)
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0


def cmd_reddit_monitor_run_once(args: argparse.Namespace) -> int:
    cfg = load_pool_config(args.config)
    result = reddit_monitor.run_once(
        cfg,
        args.registry,
        subreddits=args.subreddit or None,
        max_subreddits=args.max_subreddits,
        force=args.force,
        dry_run=args.dry_run,
        proxy_sources_path=args.proxy_sources,
        update_proxies_before_run=not args.no_update_proxies,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0


def cmd_reddit_monitor_daemon(args: argparse.Namespace) -> int:
    cfg = load_pool_config(args.config)
    result = reddit_monitor.daemon(
        cfg,
        args.registry,
        poll_seconds=args.poll_seconds,
        max_cycles=args.max_cycles,
        proxy_sources_path=args.proxy_sources,
        update_proxies_before_run=not args.no_update_proxies,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Reddit RSS 专用代理池 MVP")
    parser.add_argument("--config", default="config/reddit-proxy-pool.json", help="代理池配置文件")
    sub = parser.add_subparsers(dest="command", required=True)

    p_update = sub.add_parser("update", help="读取代理源，解析节点并生成 reddit-pool.yaml")
    p_update.add_argument("--sources", default="config/proxy-sources.json", help="代理源配置文件")
    p_update.set_defaults(func=cmd_update)

    p_start = sub.add_parser("start", help="启动 Reddit 专用 Mihomo 实例")
    p_start.set_defaults(func=cmd_start)

    p_stop = sub.add_parser("stop", help="停止 Reddit 专用 Mihomo 实例")
    p_stop.set_defaults(func=cmd_stop)

    p_restart = sub.add_parser("restart", help="重启 Reddit 专用 Mihomo 实例")
    p_restart.set_defaults(func=cmd_restart)

    p_status = sub.add_parser("status", help="查看运行状态")
    p_status.set_defaults(func=cmd_status)

    p_test = sub.add_parser("test-reddit", help="通过 7898 单次测试 Reddit RSS")
    p_test.set_defaults(func=cmd_test_reddit)

    p_monitor = sub.add_parser("reddit-monitor", help="Reddit RSS 四路视角监控")
    p_monitor.add_argument("--registry", default="config/reddit-subreddits.json", help="subreddit 监控配置文件")
    monitor_sub = p_monitor.add_subparsers(dest="monitor_command", required=True)

    p_monitor_init = monitor_sub.add_parser("init", help="初始化 Reddit 监控状态")
    p_monitor_init.add_argument("--reset", action="store_true", help="重置已有状态")
    p_monitor_init.add_argument("--due-now", action="store_true", help="让所有启用社区立即到期")
    p_monitor_init.set_defaults(func=cmd_reddit_monitor_init)

    p_monitor_status = monitor_sub.add_parser("status", help="查看 Reddit 监控状态")
    p_monitor_status.set_defaults(func=cmd_reddit_monitor_status)

    p_monitor_once = monitor_sub.add_parser("run-once", help="执行一轮到期社区采集")
    p_monitor_once.add_argument("--subreddit", action="append", help="只采集指定 subreddit，可重复传入")
    p_monitor_once.add_argument("--max-subreddits", type=int, default=1, help="本轮最多采集几个社区，默认 1")
    p_monitor_once.add_argument("--force", action="store_true", help="忽略 next_due_at，强制执行")
    p_monitor_once.add_argument("--dry-run", action="store_true", help="只展示计划，不请求 Reddit")
    p_monitor_once.add_argument("--proxy-sources", default="config/proxy-sources.json", help="采集前用于刷新代理池的订阅源配置")
    p_monitor_once.add_argument("--no-update-proxies", action="store_true", help="本次采集前不刷新代理订阅")
    p_monitor_once.set_defaults(func=cmd_reddit_monitor_run_once)

    p_monitor_daemon = monitor_sub.add_parser("daemon", help="常驻调度 Reddit RSS 四路监控")
    p_monitor_daemon.add_argument("--poll-seconds", type=int, default=60, help="无到期任务时的轮询间隔")
    p_monitor_daemon.add_argument("--max-cycles", type=int, default=None, help="最多循环次数；调试用，默认不限制")
    p_monitor_daemon.add_argument("--proxy-sources", default="config/proxy-sources.json", help="每次真实采集前用于刷新代理池的订阅源配置")
    p_monitor_daemon.add_argument("--no-update-proxies", action="store_true", help="采集前不刷新代理订阅")
    p_monitor_daemon.set_defaults(func=cmd_reddit_monitor_daemon)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
