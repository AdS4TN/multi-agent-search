"""RSS Worker 实现

支持采集 RSS/Atom feed 并转换为 RawItem。
"""
from __future__ import annotations

import hashlib
import time
import threading
from datetime import datetime, timezone, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any
from urllib.request import Request, urlopen, build_opener, ProxyHandler
from urllib.error import HTTPError, URLError

try:
    import feedparser
    FEEDPARSER_AVAILABLE = True
except ImportError:
    FEEDPARSER_AVAILABLE = False
    print("警告: feedparser 未安装，将使用基础解析")

from ..models import RawItem, WorkerResult, SourceType, RunStatus
from ..image_extraction import (
    extract_feed_entry_image,
    extract_image_from_html,
    image_metadata,
    normalize_image_url,
)
from . import BaseWorker


class RSSWorker(BaseWorker):
    """RSS Worker 实现"""
    
    def __init__(self, worker_id: str, config: dict[str, Any], cache_dir: str = None):
        super().__init__(worker_id, config)
        self.cache_dir = cache_dir or "D:/Temp/tech-radar-runtime/cache"
        self.timeout = config.get("timeout_seconds", 30)
        self.max_items_per_source = config.get("max_items_per_source", 20)
        self.lookback_hours = config.get("lookback_hours", 48)
        self.max_concurrent_sources = max(1, int(config.get("max_concurrent_sources", 6)))
        self.proxy_url = str(config.get("proxy_url") or "").strip()
        self._cache_lock = threading.Lock()
        
        # 加载缓存
        self._cache = self._load_cache()
    
    def _load_cache(self) -> dict[str, Any]:
        """加载 ETag/Last-Modified 缓存"""
        from pathlib import Path
        import json
        
        cache_file = Path(self.cache_dir) / f"{self.worker_id}-cache.json"
        if cache_file.exists():
            try:
                return json.loads(cache_file.read_text(encoding="utf-8"))
            except Exception:
                return {}
        return {}
    
    def _save_cache(self):
        """保存缓存"""
        from pathlib import Path
        import json
        
        cache_file = Path(self.cache_dir) / f"{self.worker_id}-cache.json"
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(json.dumps(self._cache, ensure_ascii=False, indent=2), encoding="utf-8")
    
    def fetch(self, run_id: str, **kwargs) -> WorkerResult:
        """采集 RSS feeds"""
        started_at = datetime.now(timezone.utc)
        sources = self.config.get("sources", [])
        
        items: list[RawItem] = []
        errors: list[dict[str, Any]] = []
        success_count = 0
        
        cutoff = datetime.now(timezone.utc) - timedelta(hours=self.lookback_hours)
        
        enabled_sources = [source for source in sources if source.get("enabled", True)]

        # RSS 源之间相互独立，组内并发可以避免一个慢源拖住整个 Worker。
        # 与 tech-news-digest 的 RSS 抓取策略保持一致，但并发数保守控制，
        # 防止一次性对外部源造成过高压力。
        with ThreadPoolExecutor(max_workers=min(self.max_concurrent_sources, max(1, len(enabled_sources)))) as executor:
            future_to_source = {
                executor.submit(self._fetch_feed, source, cutoff, run_id): source
                for source in enabled_sources
            }
            for future in as_completed(future_to_source):
                source = future_to_source[future]
                source_id = source["id"]
                try:
                    source_items = future.result()
                    items.extend(source_items)
                    success_count += 1
                except HTTPError as e:
                    errors.append({
                        "source_id": source_id,
                        "error_type": "http_error",
                        "message": f"HTTP {e.code}",
                        "retryable": e.code not in [404, 410]
                    })
                except URLError as e:
                    errors.append({
                        "source_id": source_id,
                        "error_type": "network_error",
                        "message": str(e.reason),
                        "retryable": True
                    })
                except Exception as e:
                    errors.append({
                        "source_id": source_id,
                        "error_type": "parse_error",
                        "message": str(e),
                        "retryable": False
                    })
        
        finished_at = datetime.now(timezone.utc)
        
        # 决定状态
        if success_count == 0:
            status = RunStatus.FAILED
        elif len(errors) > 0:
            status = RunStatus.PARTIAL
        else:
            status = RunStatus.SUCCESS
        
        self._save_cache()
        
        return WorkerResult(
            worker_id=self.worker_id,
            run_id=run_id,
            status=status,
            items=items,
            errors=errors,
            started_at=started_at,
            finished_at=finished_at,
            stats={
                "sources_total": len(sources),
                "sources_enabled": len(enabled_sources),
                "sources_success": success_count,
                "sources_failed": len(errors),
                "items_count": len(items),
                "max_concurrent_sources": self.max_concurrent_sources,
            }
        )
    
    def _fetch_feed(self, source: dict[str, Any], cutoff: datetime, run_id: str) -> list[RawItem]:
        """采集单个 feed"""
        source_id = source["id"]
        source_name = source["name"]
        url = source["url"]
        proxy_url = str(source.get("proxy_url") or self.proxy_url or "").strip()
        topics = source.get("topics", [])
        priority = source.get("priority", False)
        
        # 构建请求头
        headers = {
            "User-Agent": "TechRadar/0.1 (Tech News Aggregator)"
        }
        
        # 添加条件请求头
        cache_key = source_id
        if cache_key in self._cache:
            cached = self._cache[cache_key]
            if cached.get("etag"):
                headers["If-None-Match"] = cached["etag"]
            if cached.get("last_modified"):
                headers["If-Modified-Since"] = cached["last_modified"]
        
        # 发起请求
        req = Request(url, headers=headers)
        
        try:
            opener = None
            if proxy_url:
                opener = build_opener(ProxyHandler({"http": proxy_url, "https": proxy_url}))

            with (opener.open(req, timeout=self.timeout) if opener else urlopen(req, timeout=self.timeout)) as resp:
                # 更新缓存
                etag = resp.headers.get("ETag")
                last_modified = resp.headers.get("Last-Modified")
                if etag or last_modified:
                    with self._cache_lock:
                        self._cache[cache_key] = {
                            "etag": etag,
                            "last_modified": last_modified,
                            "updated_at": datetime.now(timezone.utc).isoformat()
                        }
                
                # 读取内容
                content = resp.read()
                
                # 解析 feed
                if FEEDPARSER_AVAILABLE:
                    entries = self._parse_with_feedparser(content, source_id)
                else:
                    entries = self._parse_basic(content, source_id)
                
                # 转换为 RawItem
                items: list[RawItem] = []
                for entry in entries[:self.max_items_per_source]:
                    published_at = entry.get("published_at")
                    if not published_at or published_at < cutoff:
                        continue
                    
                    raw_id = self._generate_raw_id(source_id, entry["url"], published_at)
                    
                    metadata = {"priority": priority}
                    if entry.get("image"):
                        metadata.update(entry["image"])

                    item = RawItem(
                        raw_id=raw_id,
                        source_type=SourceType.RSS,
                        source_id=source_id,
                        source_name=source_name,
                        worker_id=self.worker_id,
                        title=entry["title"],
                        url=entry["url"],
                        raw_text=entry.get("summary", ""),
                        published_at=published_at,
                        fetched_at=datetime.now(timezone.utc),
                        topics=topics,
                        metadata=metadata
                    )
                    items.append(item)
                
                return items
        
        except HTTPError as e:
            if e.code == 304:
                # Not Modified，视为成功但无新内容
                return []
            raise
    
    def _parse_with_feedparser(self, content: bytes, source_id: str) -> list[dict[str, Any]]:
        """使用 feedparser 解析"""
        feed = feedparser.parse(content)
        entries = []
        
        for entry in feed.entries:
            title = entry.get("title", "").strip()
            link = entry.get("link", "").strip()
            
            if not title or not link:
                continue
            
            # 解析发布时间
            published_at = None
            for time_field in ["published_parsed", "updated_parsed"]:
                time_struct = entry.get(time_field)
                if time_struct:
                    try:
                        published_at = datetime(*time_struct[:6], tzinfo=timezone.utc)
                        break
                    except Exception:
                        pass
            
            if not published_at:
                published_at = datetime.now(timezone.utc)
            
            # 获取摘要
            summary = ""
            if hasattr(entry, "summary"):
                summary = entry.summary
            elif hasattr(entry, "description"):
                summary = entry.description

            # 获取配图：优先 RSS/Atom 原生媒体字段，再退回摘要 HTML 首图。
            image = extract_feed_entry_image(entry, base_url=link)
            if not image:
                content_html = ""
                content = entry.get("content") if isinstance(entry, dict) else getattr(entry, "content", None)
                if isinstance(content, list) and content:
                    content_html = str(content[0].get("value") or "")
                image = extract_image_from_html(
                    content_html or summary,
                    base_url=link,
                    source="rss_summary_img",
                )
            
            entries.append({
                "title": title,
                "url": link,
                "summary": summary[:500] if summary else "",
                "published_at": published_at,
                "image": image,
            })
        
        return entries
    
    def _parse_basic(self, content: bytes, source_id: str) -> list[dict[str, Any]]:
        """基础 XML 解析降级"""
        import xml.etree.ElementTree as ET
        import re
        
        try:
            root = ET.fromstring(content)
        except Exception:
            return []
        
        entries = []

        def local_name(tag: str) -> str:
            return str(tag).rsplit("}", 1)[-1].lower()

        def child_text(parent, names: set[str]) -> str:
            for child in parent:
                if local_name(child.tag) in names and child.text:
                    return child.text.strip()
            return ""

        def image_from_xml(parent, base_url: str) -> dict[str, Any]:
            for elem in parent.iter():
                name = local_name(elem.tag)
                if name not in {"content", "thumbnail", "enclosure", "image"}:
                    continue
                candidate = elem.get("url") or elem.get("href")
                url = normalize_image_url(candidate, base_url=base_url)
                if not url:
                    continue
                media_type = (elem.get("type") or "").lower()
                medium = (elem.get("medium") or "").lower()
                if media_type and not media_type.startswith("image/") and medium != "image":
                    continue
                return image_metadata(
                    url,
                    source=f"rss_xml_{name}",
                    width=elem.get("width"),
                    height=elem.get("height"),
                )
            html_text = child_text(parent, {"description", "summary", "content", "encoded"})
            return extract_image_from_html(html_text, base_url=base_url, source="rss_xml_summary_img")
        
        # 尝试 RSS 2.0
        for item in root.findall(".//item"):
            title_elem = item.find("title")
            link_elem = item.find("link")
            
            if title_elem is not None and link_elem is not None:
                title = title_elem.text or ""
                link = link_elem.text or ""
                
                if title and link:
                    description = child_text(item, {"description", "summary", "encoded"})
                    entries.append({
                        "title": title.strip(),
                        "url": link.strip(),
                        "summary": description[:500] if description else "",
                        "published_at": datetime.now(timezone.utc),
                        "image": image_from_xml(item, link.strip()),
                    })
        
        # 如果没有找到 RSS item，尝试 Atom
        if not entries:
            ns = {"atom": "http://www.w3.org/2005/Atom"}
            for entry in root.findall(".//atom:entry", ns):
                title_elem = entry.find("atom:title", ns)
                link_elem = entry.find("atom:link[@rel='alternate']", ns)
                if link_elem is None:
                    link_elem = entry.find("atom:link", ns)
                
                if title_elem is not None and link_elem is not None:
                    title = title_elem.text or ""
                    link = link_elem.get("href", "")
                    
                    if title and link:
                        summary = child_text(entry, {"summary", "content"})
                        entries.append({
                            "title": title.strip(),
                            "url": link.strip(),
                            "summary": summary[:500] if summary else "",
                            "published_at": datetime.now(timezone.utc),
                            "image": image_from_xml(entry, link.strip()),
                        })
        
        return entries
