"""Tech Radar 运行时组装逻辑。

这里放 CLI 和 HTTP 服务共享的 Worker 注册、榜单重建函数。
"""
from __future__ import annotations

import json
import uuid
from pathlib import Path

from .models import RawItem
from .orchestrator import Orchestrator
from .ranking import generate_leaderboard
from .ranking.dedup import Deduplicator
from .scoring import LLMScoringConfig, score_events_with_cache
from .storage import Storage
from .workers.github_worker import GitHubReleasesWorker, GitHubTrendingWorker
from .workers.reddit_worker import RedditWorker
from .workers.rss_worker import RSSWorker


def load_worker_config(config_path: Path) -> dict:
    """加载 Worker 配置。"""
    return json.loads(config_path.read_text(encoding="utf-8-sig"))


def register_configured_workers(
    orchestrator: Orchestrator,
    config_root: str | Path,
    *,
    include_github: bool = False,
) -> int:
    """按 config/sources 注册所有启用 Worker。

    GitHub 当前按用户要求默认不启用。后续如果要恢复，可传 include_github=True。
    """
    sources_dir = Path(config_root) / "sources"
    count = 0
    active_worker_ids: set[str] = set()

    def maybe_register(worker) -> None:
        nonlocal count
        orchestrator.register_worker(worker)
        active_worker_ids.add(worker.worker_id)
        cfg = worker.config
        orchestrator.init_worker_state(
            worker.worker_id,
            int(cfg.get("jitter_min_seconds", 1800)),
            int(cfg.get("jitter_max_seconds", 3600)),
        )
        count += 1

    for rss_config_file in sorted(sources_dir.glob("rss-*.json")):
        config = load_worker_config(rss_config_file)
        if config.get("enabled", True):
            maybe_register(RSSWorker(config["worker_id"], config))

    reddit_file = sources_dir / "reddit.json"
    if reddit_file.exists():
        config = load_worker_config(reddit_file)
        if config.get("enabled", True):
            maybe_register(RedditWorker(config["worker_id"], config))

    if include_github:
        releases_file = sources_dir / "github-releases.json"
        if releases_file.exists():
            config = load_worker_config(releases_file)
            if config.get("enabled", True):
                maybe_register(GitHubReleasesWorker(config["worker_id"], config))

        trending_file = sources_dir / "github-trending.json"
        if trending_file.exists():
            config = load_worker_config(trending_file)
            if config.get("enabled", True):
                maybe_register(GitHubTrendingWorker(config["worker_id"], config))
    else:
        # 旧数据库中可能已有 GitHub WorkerState；当前需求明确 GitHub 先不做，
        # 因此注册阶段主动禁用，避免 status/daemon 误调度。
        orchestrator.storage.set_worker_enabled("github-releases", False)
        orchestrator.storage.set_worker_enabled("github-trending", False)

    # 配置拆分或重命名后，旧数据库中可能残留已经不存在的 rss-* / reddit*
    # WorkerState。调度器的 due 列表来自数据库，如果不禁用这些陈旧状态，
    # 后台循环会尝试运行未注册 Worker。这里只清理本项目管理的采集 Worker，
    # 不影响未来可能加入的其它自定义状态。
    for state in orchestrator.storage.load_all_worker_states():
        if state.worker_id in active_worker_ids:
            continue
        if state.worker_id.startswith("rss-") or state.worker_id.startswith("reddit"):
            orchestrator.storage.set_worker_enabled(state.worker_id, False)

    return count


def build_leaderboard(
    storage: Storage,
    *,
    limit: int,
    top: int,
    llm_config: LLMScoringConfig | None = None,
    llm_weight: float = 0.3,
) -> tuple[list[RawItem], list, list, dict]:
    """从 RawItem 重建 NewsEvent 和 LeaderboardItem。"""
    items = storage.load_raw_items(limit=limit)
    dedup = Deduplicator()
    for item in items:
        dedup.add_item(item)
    events = dedup.get_events()
    raw_by_id = {item.raw_id: item for item in items}
    llm_scores = {}

    if llm_config and llm_config.enabled:
        # 先用规则分给所有事件建立候选顺序，再对高分候选做 LLM 编辑评分。
        generate_leaderboard(events, raw_items_by_id=raw_by_id, top_n=len(events) or top)
        llm_scores = score_events_with_cache(
            storage=storage,
            events=events,
            raw_items_by_id=raw_by_id,
            config=llm_config,
        )

    leaderboard = generate_leaderboard(
        events,
        raw_items_by_id=raw_by_id,
        top_n=top,
        llm_scores_by_event_id=llm_scores,
        llm_weight=llm_weight,
    )
    return items, events, leaderboard, llm_scores


def rebuild_and_persist_leaderboard(
    storage: Storage,
    *,
    limit: int = 500,
    top: int = 50,
    trigger: str = "manual",
    llm_enabled: bool = False,
    llm_candidate_limit: int = 80,
    llm_weight: float = 0.3,
) -> dict:
    """重建事件和榜单，保存快照，返回摘要。"""
    llm_config = LLMScoringConfig.from_env(enabled=llm_enabled)
    llm_config.max_candidates = int(llm_candidate_limit)
    items, events, leaderboard, llm_scores = build_leaderboard(
        storage,
        limit=limit,
        top=top,
        llm_config=llm_config,
        llm_weight=llm_weight,
    )
    saved_events = storage.replace_news_events(events)
    snapshot_id = f"leaderboard-{uuid.uuid4().hex[:12]}"
    storage.save_leaderboard_snapshot(
        snapshot_id,
        leaderboard,
        metadata={
            "raw_items": len(items),
            "events": len(events),
            "top": top,
            "trigger": trigger,
            "llm_enabled": llm_config.enabled,
            "llm_model": llm_config.model,
            "llm_scores": len(llm_scores),
            "llm_weight": llm_weight,
        },
    )
    return {
        "snapshot_id": snapshot_id,
        "raw_items": len(items),
        "events": len(events),
        "saved_events": saved_events,
        "items": len(leaderboard),
        "llm_enabled": llm_config.enabled,
        "llm_model": llm_config.model,
        "llm_scores": len(llm_scores),
        "leaderboard": leaderboard,
    }
