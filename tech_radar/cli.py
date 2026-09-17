"""Tech Radar CLI

主命令行入口。
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from .storage import Storage
from .orchestrator import Orchestrator
from .app_runtime import register_configured_workers, rebuild_and_persist_leaderboard
from .exporters import export_json, export_markdown
from .service import serve


def cmd_run_once(args: argparse.Namespace) -> int:
    """运行一轮到期 Worker"""
    db_path = Path(args.runtime_dir) / "db" / "tech-radar.sqlite"
    storage = Storage(db_path)
    
    orchestrator = Orchestrator(storage, config_dir=args.config_dir)
    
    registered = register_configured_workers(orchestrator, args.config_dir, include_github=args.include_github)
    if args.worker:
        results = [orchestrator.run_worker(worker_id) for worker_id in args.worker]
        result = {"ok": True, "workers_run": len(results), "results": results}
    else:
        result = orchestrator.run_once(max_workers=args.max_workers)
    result["workers_registered"] = registered

    saved_total = sum(int(x.get("saved_count", 0)) for x in result.get("results", []))
    if saved_total > 0 and not args.no_leaderboard:
        built = rebuild_and_persist_leaderboard(
            storage,
            limit=args.leaderboard_limit,
            top=args.leaderboard_top,
            trigger="run-once",
            llm_enabled=args.llm_score,
            llm_candidate_limit=args.llm_candidates,
            llm_weight=args.llm_weight,
        )
        result["leaderboard"] = {
            "snapshot_id": built["snapshot_id"],
            "raw_items": built["raw_items"],
            "events": built["events"],
            "items": built["items"],
        }
    
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    """查看系统状态"""
    db_path = Path(args.runtime_dir) / "db" / "tech-radar.sqlite"
    storage = Storage(db_path)
    
    orchestrator = Orchestrator(storage)
    result = orchestrator.status()
    
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def cmd_leaderboard(args: argparse.Namespace) -> int:
    """生成榜单"""
    storage = Storage(Path(args.runtime_dir) / "db" / "tech-radar.sqlite")
    built = rebuild_and_persist_leaderboard(
        storage,
        limit=args.limit,
        top=args.top,
        trigger=args.command,
        llm_enabled=args.llm_score,
        llm_candidate_limit=args.llm_candidates,
        llm_weight=args.llm_weight,
    )
    leaderboard = built["leaderboard"]

    print(f"读取 {built['raw_items']} 条 RawItem")
    print(f"去重后: {built['events']} 个事件")
    print(f"事件入库: {built['saved_events']}")
    print(f"榜单: Top {len(leaderboard)}")
    print(f"快照: {built['snapshot_id']}")
    
    # 导出
    export_dir = Path(args.runtime_dir) / "exports"
    
    if args.format == "json" or args.format == "all":
        json_path = export_dir / "leaderboard.json"
        export_json(leaderboard, json_path)
        print(f"已导出: {json_path}")
    
    if args.format == "markdown" or args.format == "all":
        md_path = export_dir / "leaderboard.md"
        export_markdown(leaderboard, md_path)
        print(f"已导出: {md_path}")
    
    # 显示 Top N
    print(f"\nTop {min(10, len(leaderboard))}:")
    for item in leaderboard[:10]:
        print(f"  [{item.rank}] {item.title[:60]}")
        print(f"      得分: {item.score:.1f} | 来源: {item.source_count} | {item.reason}")
    
    return 0


def cmd_init(args: argparse.Namespace) -> int:
    """初始化系统"""
    db_path = Path(args.runtime_dir) / "db" / "tech-radar.sqlite"
    storage = Storage(db_path)
    orchestrator = Orchestrator(storage, config_dir=args.config_dir)
    registered = register_configured_workers(orchestrator, args.config_dir, include_github=args.include_github)
    
    print(f"✓ 初始化数据库: {db_path}")
    print(f"  存在: {db_path.exists()}")
    print(f"  Worker 状态: {registered} 个")
    
    return 0


def cmd_daemon(args: argparse.Namespace) -> int:
    """常驻调度。"""
    db_path = Path(args.runtime_dir) / "db" / "tech-radar.sqlite"
    storage = Storage(db_path)
    orchestrator = Orchestrator(storage, config_dir=args.config_dir)
    register_configured_workers(orchestrator, args.config_dir, include_github=args.include_github)

    cycles = 0
    while True:
        result = orchestrator.run_once(max_workers=args.max_workers)
        if result.get("workers_run"):
            print(json.dumps(result, ensure_ascii=False, indent=2))
        cycles += 1
        if args.max_cycles is not None and cycles >= args.max_cycles:
            return 0
        time.sleep(max(10, args.poll_seconds))


def cmd_serve(args: argparse.Namespace) -> int:
    """启动 HTTP 服务。"""
    serve(
        host=args.host,
        port=args.port,
        runtime_dir=args.runtime_dir,
        config_dir=args.config_dir,
        include_github=args.include_github,
        poll_seconds=args.poll_seconds,
        max_workers=args.max_workers,
        leaderboard_limit=args.leaderboard_limit,
        leaderboard_top=args.leaderboard_top,
        llm_enabled=args.llm_score,
        llm_candidate_limit=args.llm_candidates,
        llm_weight=args.llm_weight,
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Tech Radar - 科技新闻采集与榜单工具")
    parser.add_argument(
        "--runtime-dir",
        default="D:/Temp/tech-radar-runtime",
        help="运行时目录"
    )
    parser.add_argument(
        "--config-dir",
        default="config",
        help="配置目录"
    )
    parser.add_argument(
        "--include-github",
        action="store_true",
        help="临时启用 GitHub Worker；默认按当前需求不启用"
    )
    
    sub = parser.add_subparsers(dest="command", required=True)
    
    # init
    p_init = sub.add_parser("init", help="初始化系统")
    p_init.set_defaults(func=cmd_init)
    
    # run-once
    p_run = sub.add_parser("run-once", help="运行一轮到期 Worker")
    p_run.add_argument("--max-workers", type=int, default=10, help="最多运行 Worker 数")
    p_run.add_argument("--worker", action="append", help="只运行指定 Worker，可重复传入；会忽略 next_due_at")
    p_run.add_argument("--no-leaderboard", action="store_true", help="采集后不自动更新榜单")
    p_run.add_argument("--leaderboard-limit", type=int, default=500, help="自动榜单读取最近 N 条 RawItem")
    p_run.add_argument("--leaderboard-top", type=int, default=50, help="自动榜单 Top N")
    p_run.add_argument("--llm-score", action="store_true", help="启用 LLM 编辑评分融合；需配置 API Key")
    p_run.add_argument("--llm-candidates", type=int, default=80, help="每轮最多送入 LLM 的候选事件数")
    p_run.add_argument("--llm-weight", type=float, default=0.3, help="LLM 编辑分融合权重，0-1")
    p_run.set_defaults(func=cmd_run_once)
    
    # status
    p_status = sub.add_parser("status", help="查看系统状态")
    p_status.set_defaults(func=cmd_status)
    
    # leaderboard
    p_board = sub.add_parser("leaderboard", help="生成榜单")
    p_board.add_argument("--limit", type=int, default=100, help="读取最近 N 条 RawItem")
    p_board.add_argument("--top", type=int, default=50, help="榜单 Top N")
    p_board.add_argument("--format", choices=["json", "markdown", "all"], default="all", help="导出格式")
    p_board.add_argument("--llm-score", action="store_true", help="启用 LLM 编辑评分融合；需配置 API Key")
    p_board.add_argument("--llm-candidates", type=int, default=80, help="最多送入 LLM 的候选事件数")
    p_board.add_argument("--llm-weight", type=float, default=0.3, help="LLM 编辑分融合权重，0-1")
    p_board.set_defaults(func=cmd_leaderboard)

    # rebuild：leaderboard 的语义化别名
    p_rebuild = sub.add_parser("rebuild", help="从 RawItem 重建事件和榜单")
    p_rebuild.add_argument("--limit", type=int, default=500, help="读取最近 N 条 RawItem")
    p_rebuild.add_argument("--top", type=int, default=50, help="榜单 Top N")
    p_rebuild.add_argument("--format", choices=["json", "markdown", "all"], default="all", help="导出格式")
    p_rebuild.add_argument("--llm-score", action="store_true", help="启用 LLM 编辑评分融合；需配置 API Key")
    p_rebuild.add_argument("--llm-candidates", type=int, default=80, help="最多送入 LLM 的候选事件数")
    p_rebuild.add_argument("--llm-weight", type=float, default=0.3, help="LLM 编辑分融合权重，0-1")
    p_rebuild.set_defaults(func=cmd_leaderboard)

    # export：导出当前可重建榜单
    p_export = sub.add_parser("export", help="导出榜单 JSON/Markdown")
    p_export.add_argument("--limit", type=int, default=500, help="读取最近 N 条 RawItem")
    p_export.add_argument("--top", type=int, default=50, help="榜单 Top N")
    p_export.add_argument("--format", choices=["json", "markdown", "all"], default="all", help="导出格式")
    p_export.add_argument("--llm-score", action="store_true", help="启用 LLM 编辑评分融合；需配置 API Key")
    p_export.add_argument("--llm-candidates", type=int, default=80, help="最多送入 LLM 的候选事件数")
    p_export.add_argument("--llm-weight", type=float, default=0.3, help="LLM 编辑分融合权重，0-1")
    p_export.set_defaults(func=cmd_leaderboard)

    # daemon
    p_daemon = sub.add_parser("daemon", help="常驻运行调度器")
    p_daemon.add_argument("--poll-seconds", type=int, default=60, help="轮询间隔")
    p_daemon.add_argument("--max-workers", type=int, default=10, help="每轮最多运行 Worker 数")
    p_daemon.add_argument("--max-cycles", type=int, default=None, help="最多循环次数，调试用")
    p_daemon.set_defaults(func=cmd_daemon)

    # serve
    p_serve = sub.add_parser("serve", help="启动 HTTP 服务和后台采集循环")
    p_serve.add_argument("--host", default="0.0.0.0", help="监听地址")
    p_serve.add_argument("--port", type=int, default=5080, help="监听端口")
    p_serve.add_argument("--poll-seconds", type=int, default=300, help="后台调度轮询间隔")
    p_serve.add_argument("--max-workers", type=int, default=5, help="每轮最多运行 Worker 数")
    p_serve.add_argument("--leaderboard-limit", type=int, default=500, help="榜单读取最近 N 条 RawItem")
    p_serve.add_argument("--leaderboard-top", type=int, default=50, help="榜单 Top N")
    p_serve.add_argument("--llm-score", action="store_true", help="启用 LLM 编辑评分融合；需配置 API Key")
    p_serve.add_argument("--llm-candidates", type=int, default=80, help="每轮最多送入 LLM 的候选事件数")
    p_serve.add_argument("--llm-weight", type=float, default=0.3, help="LLM 编辑分融合权重，0-1")
    p_serve.set_defaults(func=cmd_serve)
    
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
