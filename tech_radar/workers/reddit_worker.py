"""Reddit Worker 适配器

适配 reddit_proxy_pool 的输出为 Tech Radar RawItem。
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..image_extraction import extract_image_from_candidate
from ..models import RawItem, WorkerResult, SourceType, RunStatus
from . import BaseWorker


class RedditWorker(BaseWorker):
    """Reddit Worker 适配器"""
    
    def __init__(self, worker_id: str, config: dict[str, Any]):
        super().__init__(worker_id, config)
        self.reddit_monitor_dir = self._resolve_monitor_dir(config)
        self.subreddits = config.get("subreddits", [])

    @staticmethod
    def _resolve_monitor_dir(config: dict[str, Any]) -> Path:
        """解析 reddit_monitor 产物目录，兼容本地 Windows 与服务器 Linux。

        systemd 已通过 TECH_RADAR_REDDIT_MONITOR_DIR 显式设置 Linux 路径；
        这里额外做存在性回退，避免手动在服务器跑 CLI 时被本地配置里的
        D:/Temp 路径误导。
        """
        candidates: list[Path] = []
        for value in (
            os.environ.get("TECH_RADAR_REDDIT_MONITOR_DIR"),
            config.get("reddit_monitor_dir"),
            "/var/lib/reddit-proxy-pool-runtime/reddit-monitor",
            "D:/Temp/reddit-proxy-pool-runtime/reddit-monitor",
        ):
            if value:
                path = Path(str(value))
                if path not in candidates:
                    candidates.append(path)

        for path in candidates:
            if (path / "latest").exists() or path.exists():
                return path

        return candidates[0]
    
    def fetch(self, run_id: str, **kwargs) -> WorkerResult:
        """读取 reddit_monitor 输出并转换"""
        started_at = datetime.now(timezone.utc)
        
        items: list[RawItem] = []
        errors: list[dict[str, Any]] = []
        
        latest_dir = self.reddit_monitor_dir / "latest"
        
        if not latest_dir.exists():
            errors.append({
                "source_id": "reddit-monitor",
                "error_type": "missing_directory",
                "message": f"reddit_monitor latest 目录不存在: {latest_dir}",
                "retryable": False
            })
            
            return WorkerResult(
                worker_id=self.worker_id,
                run_id=run_id,
                status=RunStatus.FAILED,
                items=[],
                errors=errors,
                started_at=started_at,
                finished_at=datetime.now(timezone.utc),
                stats={}
            )
        
        success_count = 0
        
        for subreddit in self.subreddits:
            if not subreddit.get("enabled", True):
                continue
            
            subreddit_name = subreddit["name"]
            
            try:
                subreddit_items = self._load_subreddit(subreddit, latest_dir)
                items.extend(subreddit_items)
                success_count += 1
            except FileNotFoundError:
                errors.append({
                    "source_id": f"reddit-{subreddit_name}",
                    "error_type": "file_not_found",
                    "message": f"未找到 {subreddit_name}.json",
                    "retryable": True
                })
            except Exception as e:
                errors.append({
                    "source_id": f"reddit-{subreddit_name}",
                    "error_type": "parse_error",
                    "message": str(e),
                    "retryable": False
                })
        
        finished_at = datetime.now(timezone.utc)
        
        if success_count == 0:
            status = RunStatus.FAILED
        elif len(errors) > 0:
            status = RunStatus.PARTIAL
        else:
            status = RunStatus.SUCCESS
        
        return WorkerResult(
            worker_id=self.worker_id,
            run_id=run_id,
            status=status,
            items=items,
            errors=errors,
            started_at=started_at,
            finished_at=finished_at,
            stats={
                "subreddits_total": len(self.subreddits),
                "subreddits_success": success_count,
                "items_count": len(items)
            }
        )
    
    def _load_subreddit(self, subreddit: dict[str, Any], latest_dir: Path) -> list[RawItem]:
        """加载单个 subreddit 的 latest 结果"""
        subreddit_name = subreddit["name"]
        topics = subreddit.get("topics", [])
        
        latest_file = latest_dir / f"{subreddit_name}.json"
        
        if not latest_file.exists():
            raise FileNotFoundError(f"{latest_file}")
        
        data = json.loads(latest_file.read_text(encoding="utf-8"))
        
        candidates = data.get("today_candidates", []) or data.get("candidates", [])
        
        items: list[RawItem] = []
        
        for candidate in candidates[:20]:  # 最多取 20 条
            title = candidate.get("title", "").strip()
            url = candidate.get("url", "").strip()
            
            if not title or not url:
                continue
            
            published_str = candidate.get("published")
            if published_str:
                try:
                    published_at = datetime.fromisoformat(published_str.replace("Z", "+00:00"))
                except Exception:
                    published_at = datetime.now(timezone.utc)
            else:
                published_at = datetime.now(timezone.utc)
            
            raw_id = self._generate_raw_id(f"reddit-{subreddit_name}", url, published_at)
            
            metadata = {
                "subreddit": subreddit_name,
                "reddit_score": candidate.get("reddit_score"),
                "view_hits": candidate.get("view_hits", []),
                "author": candidate.get("author")
            }
            image = extract_image_from_candidate(candidate, base_url=url)
            if image:
                metadata.update(image)

            item = RawItem(
                raw_id=raw_id,
                source_type=SourceType.REDDIT,
                source_id=f"reddit-{subreddit_name}",
                source_name=f"r/{subreddit_name}",
                worker_id=self.worker_id,
                title=title,
                url=url,
                raw_text="",
                published_at=published_at,
                fetched_at=datetime.now(timezone.utc),
                topics=topics,
                metadata=metadata
            )
            items.append(item)
        
        return items
