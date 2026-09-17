"""LLM 辅助评分模块。

默认不启用外部调用；只有显式传入配置或环境变量启用时，才会请求
OpenAI-compatible Chat Completions 接口。
"""
from .llm_scorer import LLMScoringConfig, score_events_with_cache

__all__ = ["LLMScoringConfig", "score_events_with_cache"]
