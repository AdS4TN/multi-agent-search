"""去重与聚合模块

负责 URL 规范化、标题去重和事件聚合。
"""
from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse, urlunparse, parse_qs, urlencode

from ..models import RawItem, NewsEvent


def canonicalize_url(url: str) -> str:
    """URL 规范化"""
    try:
        parsed = urlparse(url)
        
        # 移除常见跟踪参数
        query_params = parse_qs(parsed.query)
        cleaned = {}
        
        tracking_params = {
            'utm_source', 'utm_medium', 'utm_campaign', 'utm_content', 'utm_term',
            'fbclid', 'gclid', 'ref', 'source'
        }
        
        for key, value in query_params.items():
            if key.lower() not in tracking_params:
                cleaned[key] = value
        
        # 重建 query
        new_query = urlencode(cleaned, doseq=True) if cleaned else ''
        
        # 规范化 path
        path = parsed.path.rstrip('/') if parsed.path != '/' else parsed.path
        
        # 统一 scheme
        scheme = parsed.scheme.lower() if parsed.scheme else 'https'
        
        return urlunparse((
            scheme,
            parsed.netloc.lower(),
            path,
            '',
            new_query,
            ''
        ))
    except Exception:
        return url


def normalize_title(title: str) -> str:
    """标题规范化"""
    # 转小写
    normalized = title.lower().strip()
    
    # 移除站点后缀
    patterns = [
        r'\s*[-–—|]\s*[^-–—|]*$',  # 移除 " - Site Name"
        r'\s*\([^)]*\)$',  # 移除尾部括号
    ]
    
    for pattern in patterns:
        normalized = re.sub(pattern, '', normalized)
    
    # 合并空白
    normalized = re.sub(r'\s+', ' ', normalized).strip()
    
    return normalized


def title_similarity(title1: str, title2: str) -> float:
    """计算标题相似度（简化版）"""
    norm1 = normalize_title(title1)
    norm2 = normalize_title(title2)
    
    if norm1 == norm2:
        return 1.0
    
    # 简单 token 匹配
    tokens1 = set(norm1.split())
    tokens2 = set(norm2.split())
    
    if not tokens1 or not tokens2:
        return 0.0
    
    intersection = tokens1 & tokens2
    union = tokens1 | tokens2
    
    return len(intersection) / len(union)


class Deduplicator:
    """去重器"""
    
    def __init__(self):
        self.events: list[NewsEvent] = []
        self.url_index: dict[str, str] = {}  # canonical_url -> event_id
        self.title_index: dict[str, str] = {}  # normalized_title -> event_id
    
    def add_item(self, item: RawItem) -> str:
        """添加 RawItem，返回对应 event_id"""
        # 规范化 URL
        canonical = canonicalize_url(item.url)
        
        # 1. URL 完全匹配
        if canonical in self.url_index:
            event_id = self.url_index[canonical]
            self._merge_item_to_event(event_id, item)
            return event_id
        
        # 2. 标题相似度匹配
        normalized_title = normalize_title(item.title)
        
        for event in self.events:
            event_title = normalize_title(event.canonical_title)
            if title_similarity(normalized_title, event_title) > 0.85:
                self._merge_item_to_event(event.event_id, item)
                return event.event_id
        
        # 3. 创建新事件
        event_id = self._generate_event_id(item)
        
        event = NewsEvent(
            event_id=event_id,
            canonical_title=item.title,
            canonical_url=canonical,
            summary_text=item.raw_text[:500],
            topics=item.topics,
            source_count=1,
            raw_item_ids=[item.raw_id],
            first_seen_at=item.fetched_at,
            latest_seen_at=item.fetched_at,
            published_at=item.published_at,
            score=0.0,
            score_breakdown={}
        )
        
        self.events.append(event)
        self.url_index[canonical] = event_id
        self.title_index[normalized_title] = event_id
        
        return event_id
    
    def _merge_item_to_event(self, event_id: str, item: RawItem):
        """合并 RawItem 到已有事件"""
        for event in self.events:
            if event.event_id == event_id:
                if item.raw_id not in event.raw_item_ids:
                    event.raw_item_ids.append(item.raw_id)
                    event.source_count = len(event.raw_item_ids)
                    event.latest_seen_at = max(event.latest_seen_at, item.fetched_at)
                    
                    # 合并 topics
                    for topic in item.topics:
                        if topic not in event.topics:
                            event.topics.append(topic)
                break
    
    def _generate_event_id(self, item: RawItem) -> str:
        """生成 event_id"""
        raw = f"{item.canonical_url or item.url}:{item.published_at.isoformat()}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]
    
    def get_events(self) -> list[NewsEvent]:
        """获取所有事件"""
        return self.events
