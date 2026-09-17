"""Tech Radar 第一版验收脚本

不发起网络请求，只检查当前实现、配置、数据库和导出产物是否满足第一版模块要求。
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path


def assert_true(cond: bool, msg: str) -> None:
    if not cond:
        raise AssertionError(msg)
    print(f"✓ {msg}")


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    runtime = Path("D:/Temp/tech-radar-runtime")
    db_path = runtime / "db" / "tech-radar.sqlite"
    exports = runtime / "exports"

    print("=" * 70)
    print("Tech Radar 第一版验收")
    print("=" * 70)

    # 1. 模块文件
    required_modules = [
        "tech_radar/models/__init__.py",
        "tech_radar/storage/__init__.py",
        "tech_radar/workers/__init__.py",
        "tech_radar/workers/rss_worker.py",
        "tech_radar/workers/github_worker.py",
        "tech_radar/workers/reddit_worker.py",
        "tech_radar/orchestrator/__init__.py",
        "tech_radar/ranking/dedup.py",
        "tech_radar/ranking/__init__.py",
        "tech_radar/scoring/__init__.py",
        "tech_radar/scoring/llm_scorer.py",
        "tech_radar/exporters/__init__.py",
        "tech_radar/cli.py",
    ]
    for rel in required_modules:
        assert_true((root / rel).exists(), f"模块存在：{rel}")

    # 2. 配置文件
    rss_configs = sorted((root / "config" / "sources").glob("rss-*.json"))
    assert_true(len(rss_configs) >= 4, f"RSS 配置已拆分：{len(rss_configs)} 个")
    required_configs = [p.name for p in rss_configs] + [
        "github-releases.json",
        "github-trending.json",
        "reddit.json",
    ]
    for name in required_configs:
        p = root / "config" / "sources" / name
        data = json.loads(p.read_text(encoding="utf-8-sig"))
        assert_true(bool(data.get("worker_id")), f"配置有效：{name}")

    # 2.1 RSS 信源对齐：当前项目应覆盖 tech-news-digest 默认 RSS ID。
    skill_sources = Path("C:/Users/28377/.agents/skills/tech-news-digest/config/defaults/sources.json")
    if skill_sources.exists():
        skill_data = json.loads(skill_sources.read_text(encoding="utf-8-sig"))
        skill_rss_ids = {
            item["id"]
            for item in skill_data.get("sources", [])
            if isinstance(item, dict) and item.get("type") == "rss" and item.get("id")
        }
        configured_rss_ids = set()
        for cfg_path in rss_configs:
            data = json.loads(cfg_path.read_text(encoding="utf-8-sig"))
            for item in data.get("sources", []):
                if isinstance(item, dict) and item.get("id"):
                    configured_rss_ids.add(item["id"])
        missing = sorted(skill_rss_ids - configured_rss_ids)
        assert_true(not missing, f"tech-news-digest RSS 已全部配置：{len(skill_rss_ids)} 个")

    # 3. 数据库结构和数据
    assert_true(db_path.exists(), f"数据库存在：{db_path}")
    conn = sqlite3.connect(str(db_path))
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    for table in [
        "raw_items",
        "source_runs",
        "worker_state",
        "news_events",
        "event_sources",
        "leaderboard_snapshots",
        "source_cache",
        "llm_event_scores",
        "system_kv",
    ]:
        assert_true(table in tables, f"数据表存在：{table}")

    raw_count = conn.execute("SELECT COUNT(*) FROM raw_items").fetchone()[0]
    event_count = conn.execute("SELECT COUNT(*) FROM news_events").fetchone()[0]
    worker_count = conn.execute("SELECT COUNT(*) FROM worker_state").fetchone()[0]
    snapshot = conn.execute("SELECT value FROM system_kv WHERE key='latest_leaderboard_snapshot'").fetchone()
    conn.close()

    assert_true(worker_count >= 5, f"Worker 状态已初始化：{worker_count} 个")
    assert_true(raw_count > 0, f"RawItem 已入库：{raw_count} 条")
    assert_true(event_count > 0, f"NewsEvent 已入库：{event_count} 个")
    assert_true(snapshot is not None, "最新榜单快照已记录")

    # 4. 导出产物
    json_path = exports / "leaderboard.json"
    md_path = exports / "leaderboard.md"
    assert_true(json_path.exists(), f"JSON 榜单存在：{json_path}")
    assert_true(md_path.exists(), f"Markdown 榜单存在：{md_path}")
    leaderboard = json.loads(json_path.read_text(encoding="utf-8"))
    assert_true(leaderboard.get("items_count", 0) > 0, "JSON 榜单包含条目")

    # 5. Reddit 边界：适配器不应直接导入 urllib 发请求
    reddit_worker = (root / "tech_radar" / "workers" / "reddit_worker.py").read_text(encoding="utf-8-sig")
    assert_true("urllib" not in reddit_worker, "Reddit Worker 只读本地产物，不直接请求 Reddit")

    conn = sqlite3.connect(str(db_path))
    github_rows = conn.execute(
        "SELECT COUNT(*) FROM raw_items WHERE source_type IN ('github_release','github_trending')"
    ).fetchone()[0]
    github_enabled = conn.execute(
        "SELECT COUNT(*) FROM worker_state WHERE worker_id LIKE 'github-%' AND enabled = 1"
    ).fetchone()[0]
    conn.close()
    assert_true(github_rows == 0, "GitHub RawItem 已按当前需求清空")
    assert_true(github_enabled == 0, "GitHub Worker 已按当前需求禁用")

    print("=" * 70)
    print("验收通过 ✓")
    print("=" * 70)


if __name__ == "__main__":
    main()
