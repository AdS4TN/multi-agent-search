"""排序与榜单生成

规则评分和榜单生成。
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Any

from ..models import LLMEventScore, LeaderboardItem, NewsEvent, RawItem, SourceType
from ..scoring.llm_scorer import llm_editor_points


def calculate_score(event: NewsEvent, now: datetime = None, effective_source_count: int | None = None) -> dict[str, float]:
    """计算事件得分"""
    if now is None:
        now = datetime.now(timezone.utc)
    
    breakdown = {}
    
    # 1. 来源权重（多源优先）
    source_count = effective_source_count if effective_source_count is not None else event.source_count
    source_weight = min(source_count * 10, 50)
    breakdown["source_weight"] = source_weight
    
    # 2. 时效性得分
    hours_old = (now - event.published_at).total_seconds() / 3600
    
    if hours_old < 6:
        freshness = 30
    elif hours_old < 24:
        freshness = 20
    elif hours_old < 48:
        freshness = 10
    else:
        freshness = 5
    
    breakdown["freshness_score"] = freshness
    
    # 3. 主题权重
    topic_weight = 0
    priority_topics = {"llm", "ai-agent", "frontier-tech"}
    
    for topic in event.topics:
        if topic in priority_topics:
            topic_weight += 10
        else:
            topic_weight += 5
    
    topic_weight = min(topic_weight, 30)
    breakdown["topic_weight"] = topic_weight
    
    # 4. 多源加分
    if source_count >= 3:
        cross_source_bonus = 15
    elif source_count >= 2:
        cross_source_bonus = 5
    else:
        cross_source_bonus = 0
    
    breakdown["cross_source_score"] = cross_source_bonus
    
    # 总分
    total = sum(breakdown.values())
    breakdown["total"] = total
    
    return breakdown


def generate_leaderboard(
    events: list[NewsEvent],
    raw_items_by_id: dict[str, RawItem] | None = None,
    top_n: int = 50,
    llm_scores_by_event_id: dict[str, LLMEventScore] | None = None,
    llm_weight: float = 0.3,
) -> list[LeaderboardItem]:
    """生成榜单"""
    now = datetime.now(timezone.utc)
    llm_scores_by_event_id = llm_scores_by_event_id or {}
    llm_weight = max(0.0, min(1.0, float(llm_weight)))
    raw_items_by_event_id: dict[str, list[RawItem]] = {}
    
    for event in events:
        effective_source_count = None
        event_raw_items: list[RawItem] = []
        if raw_items_by_id:
            event_raw_items = [
                raw_items_by_id[raw_id]
                for raw_id in event.raw_item_ids
                if raw_id in raw_items_by_id
            ]
            source_ids = {
                raw.source_id
                for raw in event_raw_items
            }
            effective_source_count = max(1, len(source_ids))
            event.source_count = effective_source_count
        raw_items_by_event_id[event.event_id] = event_raw_items
        breakdown = calculate_score(event, now, effective_source_count=effective_source_count)
        github_signal = _github_trend_signal(event_raw_items)
        if github_signal:
            breakdown["github_signal_score"] = github_signal
            breakdown["total"] = sum(v for k, v in breakdown.items() if k != "total")
        rule_total = float(breakdown["total"])
        llm_score = llm_scores_by_event_id.get(event.event_id)
        if llm_score and not llm_score.error:
            editor_points = llm_editor_points(llm_score)
            breakdown["rule_total"] = rule_total
            breakdown["llm_editor_score"] = editor_points
            breakdown["llm_weight"] = llm_weight
            breakdown["llm_importance"] = llm_score.importance
            breakdown["llm_trend_value"] = llm_score.trend_value
            breakdown["llm_novelty"] = llm_score.novelty
            breakdown["llm_audience_fit"] = llm_score.audience_fit
            breakdown["llm_noise_penalty"] = llm_score.noise_penalty
            breakdown["llm_confidence"] = llm_score.confidence
            breakdown["total"] = round(rule_total * (1.0 - llm_weight) + editor_points * llm_weight, 2)
        event.score = breakdown["total"]
        event.score_breakdown = breakdown
    
    # 排序
    sorted_events = sorted(events, key=lambda e: e.score, reverse=True)[:top_n]
    
    # 生成榜单项
    items = []
    for rank, event in enumerate(sorted_events, 1):
        reason = _generate_reason(event)
        source_names = []
        event_raw_items = raw_items_by_event_id.get(event.event_id, [])
        if raw_items_by_id:
            for raw_id in event.raw_item_ids:
                raw = raw_items_by_id.get(raw_id)
                if raw and raw.source_name not in source_names:
                    source_names.append(raw.source_name)
        if event.score_breakdown.get("github_signal_score", 0) >= 20 and "GitHub 新项目快速升温" not in reason:
            reason = f"{reason}、GitHub 新项目快速升温"
        llm_score = llm_scores_by_event_id.get(event.event_id)
        if llm_score and not llm_score.error and llm_score.reason:
            reason = f"{reason}、编辑评分：{llm_score.reason}"
        image = _select_event_image(event_raw_items)
        
        item = LeaderboardItem(
            rank=rank,
            event_id=event.event_id,
            title=event.canonical_title,
            url=event.canonical_url,
            image_url=image.get("image_url"),
            image_source=image.get("image_source"),
            image_alt=event.canonical_title if image else None,
            topics=event.topics,
            score=event.score,
            source_count=event.source_count,
            source_names=source_names,
            reason=reason,
            updated_at=now
        )
        items.append(item)
    
    return items


def _github_trend_signal(raw_items: list[RawItem]) -> float:
    """根据新仓库 stars / age 估算 GitHub 趋势信号。

    这里只用于 github_trending，不奖励普通 release，避免老项目版本更新压过新趋势。
    """
    best = 0.0
    for raw in raw_items:
        if raw.source_type != SourceType.GITHUB_TRENDING:
            continue
        stars = float(raw.metadata.get("stars") or 0)
        age = max(1.0, float(raw.metadata.get("repo_age_days") or 30))
        velocity = stars / age
        # sqrt 压缩极端明星项目，避免单项爆表；上限 35。
        signal = min(35.0, (velocity ** 0.5) * 2.0)
        if age <= 7:
            signal = min(35.0, signal + 5.0)
        best = max(best, signal)
    return round(best, 2)


def _select_event_image(raw_items: list[RawItem]) -> dict[str, str]:
    """从事件关联 RawItem 中选择一张代表图。

    Worker 已负责把 RSS/Reddit 图片统一写入 metadata.image_url。这里不做
    下载或探测，只基于来源优先级挑选最适合展示的一张。
    """
    source_priority = {
        "rss_media_content": 10,
        "rss_media_thumbnail": 20,
        "rss_enclosure": 30,
        "rss_summary_img": 40,
        "rss_xml_content": 50,
        "rss_xml_thumbnail": 50,
        "rss_xml_enclosure": 50,
        "rss_xml_image": 55,
        "rss_xml_summary_img": 60,
        "reddit_atom_img": 70,
        "candidate_image_url": 80,
        "candidate_preview": 85,
        "candidate_media_metadata": 85,
        "candidate_thumbnail": 90,
        "candidate_thumbnail_url": 90,
        "candidate_preview_image": 90,
        "candidate_preview_url": 90,
        "candidate_url_overridden_by_dest": 95,
    }

    candidates: list[tuple[int, int, str, str]] = []
    for index, raw in enumerate(raw_items):
        metadata = raw.metadata or {}
        image_url = str(metadata.get("image_url") or "").strip()
        if not image_url.startswith(("http://", "https://")):
            continue
        image_source = str(metadata.get("image_source") or "raw_metadata")
        priority = source_priority.get(image_source, 100)
        candidates.append((priority, index, image_url, image_source))

    if not candidates:
        return {}

    _, _, image_url, image_source = sorted(candidates, key=lambda x: (x[0], x[1]))[0]
    return {
        "image_url": image_url,
        "image_source": image_source,
    }


def _generate_reason(event: NewsEvent) -> str:
    """生成上榜原因"""
    reasons = []
    
    if event.source_count >= 3:
        reasons.append("多信源交叉报道")
    
    hours_old = (datetime.now(timezone.utc) - event.published_at).total_seconds() / 3600
    if hours_old < 6:
        reasons.append("最新发布")
    
    priority_topics = {"llm", "ai-agent"}
    if any(t in priority_topics for t in event.topics):
        reasons.append("重点主题")
    
    if not reasons:
        reasons.append("科技新闻")
    
    return "、".join(reasons)
