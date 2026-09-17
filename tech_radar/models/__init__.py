"""数据模型定义

本模块定义 Tech Radar 所有核心数据对象。
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional
from enum import Enum

from pydantic import BaseModel, Field


class SourceType(str, Enum):
    """信源类型"""
    RSS = "rss"
    GITHUB_RELEASE = "github_release"
    GITHUB_TRENDING = "github_trending"
    REDDIT = "reddit"


class RunStatus(str, Enum):
    """运行状态"""
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"


class RawItem(BaseModel):
    """原始新闻项，由 Worker 返回"""
    raw_id: str = Field(description="原始项唯一标识")
    source_type: SourceType = Field(description="信源类型")
    source_id: str = Field(description="信源配置中的唯一 ID")
    source_name: str = Field(description="人类可读信源名")
    worker_id: str = Field(description="产生该项的 Worker")
    title: str = Field(description="原始标题")
    url: str = Field(description="原始链接")
    canonical_url: Optional[str] = Field(default=None, description="规范化后的链接")
    raw_text: str = Field(default="", description="原始文本")
    published_at: datetime = Field(description="原始发布时间")
    fetched_at: datetime = Field(description="抓取时间")
    topics: list[str] = Field(default_factory=list, description="主题标签")
    metadata: dict[str, Any] = Field(default_factory=dict, description="信源特有字段")

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class SourceRun(BaseModel):
    """Worker 运行记录"""
    run_id: str = Field(description="本轮运行 ID")
    worker_id: str = Field(description="Worker 名称")
    started_at: datetime = Field(description="开始时间")
    finished_at: Optional[datetime] = Field(default=None, description="结束时间")
    status: RunStatus = Field(description="运行状态")
    items_count: int = Field(default=0, description="返回 RawItem 数量")
    error_count: int = Field(default=0, description="错误数量")
    error_summary: str = Field(default="", description="简要错误信息")
    duration_ms: Optional[int] = Field(default=None, description="耗时毫秒")

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class WorkerState(BaseModel):
    """Worker 调度状态"""
    worker_id: str = Field(description="Worker ID")
    enabled: bool = Field(default=True, description="是否启用")
    next_due_at: datetime = Field(description="下次运行时间")
    last_run_at: Optional[datetime] = Field(default=None, description="上次运行时间")
    last_success_at: Optional[datetime] = Field(default=None, description="上次成功时间")
    consecutive_failures: int = Field(default=0, description="连续失败次数")
    last_error: str = Field(default="", description="最近错误")
    jitter_min_seconds: int = Field(description="最小随机间隔")
    jitter_max_seconds: int = Field(description="最大随机间隔")

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class NewsEvent(BaseModel):
    """聚合后的新闻事件"""
    event_id: str = Field(description="事件 ID")
    canonical_title: str = Field(description="代表标题")
    canonical_url: str = Field(description="代表链接")
    summary_text: str = Field(default="", description="摘要")
    topics: list[str] = Field(default_factory=list, description="合并后的主题")
    source_count: int = Field(description="命中的信源数量")
    raw_item_ids: list[str] = Field(default_factory=list, description="关联 RawItem ID")
    first_seen_at: datetime = Field(description="系统首次发现时间")
    latest_seen_at: datetime = Field(description="最近一次出现时间")
    published_at: datetime = Field(description="代表发布时间")
    score: float = Field(default=0.0, description="当前总分")
    score_breakdown: dict[str, float] = Field(default_factory=dict, description="评分明细")

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class LeaderboardItem(BaseModel):
    """榜单项"""
    rank: int = Field(description="排名")
    event_id: str = Field(description="对应 NewsEvent")
    title: str = Field(description="展示标题")
    url: str = Field(description="展示链接")
    image_url: Optional[str] = Field(default=None, description="代表配图 URL")
    image_source: Optional[str] = Field(default=None, description="代表配图来源")
    image_alt: Optional[str] = Field(default=None, description="代表配图替代文本")
    topics: list[str] = Field(default_factory=list, description="主题")
    score: float = Field(description="总分")
    source_count: int = Field(description="信源数量")
    source_names: list[str] = Field(default_factory=list, description="信源名列表")
    reason: str = Field(default="", description="上榜原因")
    updated_at: datetime = Field(description="榜单更新时间")

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class LLMEventScore(BaseModel):
    """LLM 对 NewsEvent 的编辑评分结果。

    该模型只保存“今天是否值得上榜”的语义判断，不直接替代规则分。
    """
    event_id: str = Field(description="对应 NewsEvent")
    input_hash: str = Field(description="评分输入指纹，用于缓存和复现")
    model: str = Field(description="评分模型名称")
    provider: str = Field(default="openai-compatible", description="模型供应商或兼容协议")
    importance: float = Field(default=0.0, ge=0, le=10, description="新闻重要性 0-10")
    trend_value: float = Field(default=0.0, ge=0, le=10, description="趋势价值 0-10")
    novelty: float = Field(default=0.0, ge=0, le=10, description="新鲜/非旧闻程度 0-10")
    audience_fit: float = Field(default=0.0, ge=0, le=10, description="目标受众相关性 0-10")
    noise_penalty: float = Field(default=0.0, ge=0, le=10, description="噪声惩罚 0-10")
    confidence: float = Field(default=0.0, ge=0, le=1, description="模型置信度 0-1")
    labels: list[str] = Field(default_factory=list, description="编辑标签")
    reason: str = Field(default="", description="简短上榜/降权理由")
    raw_response: str = Field(default="", description="模型原始响应，便于排错")
    error: str = Field(default="", description="调用或解析错误")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="创建时间")

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class WorkerResult(BaseModel):
    """Worker 返回结果"""
    worker_id: str = Field(description="Worker 标识")
    run_id: str = Field(description="本次运行 ID")
    status: RunStatus = Field(description="运行状态")
    items: list[RawItem] = Field(default_factory=list, description="RawItem 列表")
    errors: list[dict[str, Any]] = Field(default_factory=list, description="错误列表")
    started_at: datetime = Field(description="开始时间")
    finished_at: datetime = Field(description="结束时间")
    stats: dict[str, Any] = Field(default_factory=dict, description="统计信息")

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }
