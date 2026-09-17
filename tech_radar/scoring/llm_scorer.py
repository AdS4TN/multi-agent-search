"""LLM 编辑评分器。

设计目标：

- 只对已经去重后的 NewsEvent 评分，而不是逐条 RawItem 评分。
- 使用 input_hash 做缓存，避免同一输入重复请求模型。
- 默认走 OpenAI-compatible Chat Completions 协议，便于接入 OpenAI、Grok
  或其他兼容网关。
- 失败时写入带 error 的缓存，不中断榜单生成。
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from ..models import LLMEventScore, NewsEvent, RawItem
from ..storage import Storage


@dataclass(slots=True)
class LLMScoringConfig:
    """LLM 评分配置。"""

    enabled: bool = False
    provider: str = "openai-compatible"
    base_url: str = "https://api.openai.com/v1"
    api_key: str = ""
    model: str = "gpt-4o-mini"
    timeout_seconds: int = 25
    max_candidates: int = 80
    max_raw_items_per_event: int = 8
    temperature: float = 0.0

    @classmethod
    def from_env(cls, *, enabled: bool | None = None) -> "LLMScoringConfig":
        """从环境变量构造配置。

        支持：
        - TECH_RADAR_LLM_SCORING=1
        - TECH_RADAR_LLM_API_KEY / OPENAI_API_KEY
        - TECH_RADAR_LLM_BASE_URL
        - TECH_RADAR_LLM_MODEL
        """
        env_enabled = str(os.environ.get("TECH_RADAR_LLM_SCORING", "")).lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        return cls(
            enabled=env_enabled if enabled is None else bool(enabled),
            provider=os.environ.get("TECH_RADAR_LLM_PROVIDER", "openai-compatible"),
            base_url=os.environ.get("TECH_RADAR_LLM_BASE_URL", "https://api.openai.com/v1").rstrip("/"),
            api_key=os.environ.get("TECH_RADAR_LLM_API_KEY") or os.environ.get("OPENAI_API_KEY", ""),
            model=os.environ.get("TECH_RADAR_LLM_MODEL", "gpt-4o-mini"),
            timeout_seconds=int(os.environ.get("TECH_RADAR_LLM_TIMEOUT_SECONDS", "25")),
            max_candidates=int(os.environ.get("TECH_RADAR_LLM_MAX_CANDIDATES", "80")),
            max_raw_items_per_event=int(os.environ.get("TECH_RADAR_LLM_MAX_RAW_ITEMS_PER_EVENT", "8")),
            temperature=float(os.environ.get("TECH_RADAR_LLM_TEMPERATURE", "0")),
        )


def score_events_with_cache(
    *,
    storage: Storage,
    events: list[NewsEvent],
    raw_items_by_id: dict[str, RawItem],
    config: LLMScoringConfig,
) -> dict[str, LLMEventScore]:
    """给候选事件补充 LLM 评分，并返回 event_id -> score。

    这里不会重新排序；排序融合由 ranking 模块完成。
    """
    if not config.enabled:
        return {}

    candidates = sorted(events, key=lambda event: event.score, reverse=True)[: config.max_candidates]
    if not candidates:
        return {}

    scorer = OpenAICompatibleLLMScorer(config)
    scores: dict[str, LLMEventScore] = {}

    for event in candidates:
        event_raw_items = [
            raw_items_by_id[raw_id]
            for raw_id in event.raw_item_ids
            if raw_id in raw_items_by_id
        ]
        input_hash = build_event_input_hash(event, event_raw_items)
        cached = storage.load_llm_event_score(event.event_id, input_hash, config.model)
        if cached:
            # 成功评分长期复用；错误缓存只在当前仍无 API Key 时复用。
            # 这样后续补充 API Key 后会自动重试，不会被 missing_api_key 卡住。
            if not cached.error or not config.api_key:
                scores[event.event_id] = cached
                continue

        score = scorer.score_event(event, event_raw_items, input_hash=input_hash)
        storage.save_llm_event_score(score)
        scores[event.event_id] = score

    return scores


def build_event_input_hash(event: NewsEvent, raw_items: list[RawItem]) -> str:
    """构造稳定输入指纹。"""
    payload = {
        "event_id": event.event_id,
        "title": event.canonical_title,
        "url": event.canonical_url,
        "topics": sorted(event.topics),
        "published_at": event.published_at.isoformat(),
        "raw_items": [
            {
                "raw_id": item.raw_id,
                "source_id": item.source_id,
                "title": item.title,
                "url": item.canonical_url or item.url,
                "published_at": item.published_at.isoformat(),
                "topics": sorted(item.topics),
                "text": _clean_text(item.raw_text)[:600],
            }
            for item in sorted(raw_items, key=lambda x: x.raw_id)
        ],
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class OpenAICompatibleLLMScorer:
    """OpenAI-compatible Chat Completions 评分器。"""

    def __init__(self, config: LLMScoringConfig):
        self.config = config

    def score_event(
        self,
        event: NewsEvent,
        raw_items: list[RawItem],
        *,
        input_hash: str,
    ) -> LLMEventScore:
        if not self.config.api_key:
            return self._error_score(event, input_hash, "missing_api_key")

        prompt = build_scoring_prompt(
            event,
            raw_items[: self.config.max_raw_items_per_event],
        )
        try:
            raw_response = self._chat_completion(prompt)
            data = _extract_json_object(raw_response)
            return score_from_payload(
                event_id=event.event_id,
                input_hash=input_hash,
                model=self.config.model,
                provider=self.config.provider,
                raw_response=raw_response,
                payload=data,
            )
        except Exception as exc:  # 评分失败不能影响主流程
            return self._error_score(event, input_hash, f"{type(exc).__name__}: {exc}")

    def _chat_completion(self, user_prompt: str) -> str:
        url = f"{self.config.base_url}/chat/completions"
        payload = {
            "model": self.config.model,
            "temperature": self.config.temperature,
            "response_format": {"type": "json_object"},
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "你是科技新闻总榜的资深编辑。"
                        "你的任务是判断一个事件在“今天的科技趋势榜”中是否值得靠前，"
                        "不要因为品牌长期知名、项目历史 stars 高或旧项目普通版本更新而给高分。"
                        "不要做事实核查，也不要编造外部证据。只基于输入材料做编辑评分。"
                        "必须返回严格 JSON。"
                    ),
                },
                {"role": "user", "content": user_prompt},
            ],
        }
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=raw,
            headers={
                "Authorization": f"Bearer {self.config.api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.config.timeout_seconds) as response:
                body = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", "replace")
            raise RuntimeError(f"HTTP {exc.code}: {body[:500]}") from exc

        data = json.loads(body)
        return str(data["choices"][0]["message"]["content"])

    def _error_score(self, event: NewsEvent, input_hash: str, error: str) -> LLMEventScore:
        return LLMEventScore(
            event_id=event.event_id,
            input_hash=input_hash,
            model=self.config.model,
            provider=self.config.provider,
            confidence=0.0,
            labels=["llm-score-error"],
            reason="LLM 评分不可用，保留规则分。",
            error=error,
            created_at=datetime.now(timezone.utc),
        )


def build_scoring_prompt(event: NewsEvent, raw_items: list[RawItem]) -> str:
    """生成单个事件的评分提示词。"""
    event_payload = {
        "event": {
            "event_id": event.event_id,
            "title": event.canonical_title,
            "url": event.canonical_url,
            "topics": event.topics,
            "source_count": event.source_count,
            "published_at": event.published_at.isoformat(),
            "current_rule_score": event.score,
            "rule_score_breakdown": event.score_breakdown,
        },
        "raw_items": [
            {
                "source_type": item.source_type.value,
                "source_id": item.source_id,
                "source_name": item.source_name,
                "title": item.title,
                "url": item.canonical_url or item.url,
                "published_at": item.published_at.isoformat(),
                "topics": item.topics,
                "text": _clean_text(item.raw_text)[:900],
                "metadata": _safe_metadata(item.metadata),
            }
            for item in raw_items
        ],
    }
    return (
        "请为下面这个科技新闻事件打编辑分。评分目标是：今天是否值得进入科技趋势榜靠前位置。\n\n"
        "请输出严格 JSON，字段必须是：\n"
        "{\n"
        '  "importance": 0-10,\n'
        '  "trend_value": 0-10,\n'
        '  "novelty": 0-10,\n'
        '  "audience_fit": 0-10,\n'
        '  "noise_penalty": 0-10,\n'
        '  "confidence": 0-1,\n'
        '  "labels": ["短标签"],\n'
        '  "reason": "不超过80个中文字的理由"\n'
        "}\n\n"
        "评分解释：\n"
        "- importance：产业/技术/安全/政策影响的重要性。\n"
        "- trend_value：是否代表正在形成的技术趋势。\n"
        "- novelty：是否是今天的新信息，旧项目普通版本更新、重复转载应降低。\n"
        "- audience_fit：对 AI、开发者、科技从业者、创业者的相关性。\n"
        "- noise_penalty：营销稿、低信号、社区情绪、纯观点、重复角度、crypto 噪声等惩罚。\n"
        "- confidence：只基于输入材料判断的置信度。\n\n"
        "注意：不要因为公司或项目历史知名就高分；请关注今天的新变化和趋势价值。\n\n"
        f"事件材料：\n{json.dumps(event_payload, ensure_ascii=False, indent=2)}"
    )


def score_from_payload(
    *,
    event_id: str,
    input_hash: str,
    model: str,
    provider: str,
    raw_response: str,
    payload: dict[str, Any],
) -> LLMEventScore:
    """将模型 JSON 转成受控分数。"""
    labels = payload.get("labels") or []
    if not isinstance(labels, list):
        labels = [str(labels)]
    labels = [str(x).strip()[:40] for x in labels if str(x).strip()][:12]
    return LLMEventScore(
        event_id=event_id,
        input_hash=input_hash,
        model=model,
        provider=provider,
        importance=_clamp_float(payload.get("importance"), 0, 10),
        trend_value=_clamp_float(payload.get("trend_value"), 0, 10),
        novelty=_clamp_float(payload.get("novelty"), 0, 10),
        audience_fit=_clamp_float(payload.get("audience_fit"), 0, 10),
        noise_penalty=_clamp_float(payload.get("noise_penalty"), 0, 10),
        confidence=_clamp_float(payload.get("confidence"), 0, 1),
        labels=labels,
        reason=str(payload.get("reason") or "")[:220],
        raw_response=raw_response[:5000],
        created_at=datetime.now(timezone.utc),
    )


def llm_editor_points(score: LLMEventScore) -> float:
    """把 LLM 结构化评分折算到约 0-110 的编辑分。"""
    if score.error or score.confidence <= 0:
        return 0.0
    points = (
        score.importance * 4.0
        + score.trend_value * 3.0
        + score.novelty * 2.0
        + score.audience_fit * 2.0
        - score.noise_penalty * 5.0
    )
    return round(max(0.0, points) * score.confidence, 2)


def _extract_json_object(raw_response: str) -> dict[str, Any]:
    """从模型响应中提取 JSON 对象。"""
    text = raw_response.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, flags=re.S)
        if not match:
            raise
        data = json.loads(match.group(0))
    if not isinstance(data, dict):
        raise ValueError("LLM response is not a JSON object")
    return data


def _clamp_float(value: Any, minimum: float, maximum: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = minimum
    return max(minimum, min(maximum, number))


def _clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", value or "")).strip()


def _safe_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    """只把对评分可能有用的元信息给模型，避免提示过长。"""
    keep = {
        "priority",
        "subreddit",
        "reddit_score",
        "view_hits",
        "author",
        "stars",
        "repo_age_days",
        "language",
    }
    return {key: metadata.get(key) for key in keep if key in metadata}
