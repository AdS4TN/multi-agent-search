"""GitHub Worker 实现

支持采集 GitHub Releases 和 Trending 仓库。
"""
from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timezone, timedelta
from typing import Any, Optional
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from urllib.parse import quote

from ..models import RawItem, WorkerResult, SourceType, RunStatus
from . import BaseWorker


class GitHubReleasesWorker(BaseWorker):
    """GitHub Releases Worker"""
    
    def __init__(self, worker_id: str, config: dict[str, Any]):
        super().__init__(worker_id, config)
        self.timeout = config.get("timeout_seconds", 30)
        self.max_releases = config.get("max_releases_per_repo", 5)
        self.lookback_hours = config.get("lookback_hours", 168)  # 默认 7 天
        self.token = self._resolve_token()
    
    def _resolve_token(self) -> Optional[str]:
        """解析 GitHub token"""
        # 1. 环境变量
        token = os.environ.get("GITHUB_TOKEN")
        if token:
            return token
        
        # 2. gh CLI
        try:
            result = subprocess.run(
                ["gh", "auth", "token"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception:
            pass
        
        return None
    
    def fetch(self, run_id: str, **kwargs) -> WorkerResult:
        """采集 GitHub releases"""
        started_at = datetime.now(timezone.utc)
        repos = self.config.get("repos", [])
        
        items: list[RawItem] = []
        errors: list[dict[str, Any]] = []
        success_count = 0
        
        cutoff = datetime.now(timezone.utc) - timedelta(hours=self.lookback_hours)
        
        for repo in repos:
            if not repo.get("enabled", True):
                continue
            
            repo_id = repo["id"]
            try:
                repo_items = self._fetch_releases(repo, cutoff)
                items.extend(repo_items)
                success_count += 1
            except HTTPError as e:
                errors.append({
                    "source_id": repo_id,
                    "error_type": "http_error",
                    "message": f"HTTP {e.code}",
                    "retryable": e.code not in [404, 410]
                })
            except Exception as e:
                errors.append({
                    "source_id": repo_id,
                    "error_type": "fetch_error",
                    "message": str(e),
                    "retryable": True
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
                "repos_total": len(repos),
                "repos_success": success_count,
                "items_count": len(items)
            }
        )
    
    def _fetch_releases(self, repo: dict[str, Any], cutoff: datetime) -> list[RawItem]:
        """采集单个仓库的 releases"""
        repo_id = repo["id"]
        owner_repo = repo["repo"]  # 格式: owner/repo
        topics = repo.get("topics", [])
        priority = repo.get("priority", False)
        
        url = f"https://api.github.com/repos/{owner_repo}/releases?per_page={self.max_releases}"
        
        headers = {
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "TechRadar/0.1"
        }
        
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        
        req = Request(url, headers=headers)
        
        with urlopen(req, timeout=self.timeout) as resp:
            data = json.loads(resp.read().decode())
        
        items: list[RawItem] = []
        
        for release in data:
            published_at_str = release.get("published_at")
            if not published_at_str:
                continue
            
            published_at = datetime.fromisoformat(published_at_str.replace("Z", "+00:00"))
            
            if published_at < cutoff:
                continue
            
            tag = release.get("tag_name", "")
            name = release.get("name") or tag
            body = release.get("body", "")
            html_url = release.get("html_url", "")
            
            raw_id = self._generate_raw_id(repo_id, html_url, published_at)
            
            item = RawItem(
                raw_id=raw_id,
                source_type=SourceType.GITHUB_RELEASE,
                source_id=repo_id,
                source_name=owner_repo,
                worker_id=self.worker_id,
                title=f"{owner_repo} {tag}: {name}",
                url=html_url,
                raw_text=body[:1000] if body else "",
                published_at=published_at,
                fetched_at=datetime.now(timezone.utc),
                topics=topics,
                metadata={
                    "priority": priority,
                    "tag": tag,
                    "repo": owner_repo
                }
            )
            items.append(item)
        
        return items


class GitHubTrendingWorker(BaseWorker):
    """GitHub Trending Worker（新近趋势仓库）

    注意：GitHub Search API 没有官方“星标增速”字段。第一版这里采用
    “近期创建 + 达到一定 stars + 按 stars 排序”的近似口径，避免 LangChain、
    Transformers、Dify 这类历史高星老项目占据趋势榜。
    """
    
    def __init__(self, worker_id: str, config: dict[str, Any]):
        super().__init__(worker_id, config)
        self.timeout = config.get("timeout_seconds", 30)
        self.min_stars = config.get("min_stars", 20)
        self.lookback_days = config.get("lookback_days", 30)
        self.max_repo_age_days = config.get("max_repo_age_days", self.lookback_days)
        self.per_topic = config.get("per_topic", 10)
        self.token = self._resolve_token()
    
    def _resolve_token(self) -> Optional[str]:
        """解析 GitHub token"""
        token = os.environ.get("GITHUB_TOKEN")
        if token:
            return token
        
        try:
            result = subprocess.run(
                ["gh", "auth", "token"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception:
            pass
        
        return None
    
    def fetch(self, run_id: str, **kwargs) -> WorkerResult:
        """采集 GitHub trending"""
        started_at = datetime.now(timezone.utc)
        
        # 预定义搜索主题
        queries = [
            {"topic": "llm", "query": "large-language-model OR llm OR inference", "topics": ["llm"]},
            {"topic": "ai-agent", "query": "ai-agent OR agent-framework", "topics": ["ai-agent"]},
            {"topic": "devtools", "query": "developer-tools OR cli", "topics": ["developer-tools"]},
        ]
        
        items: list[RawItem] = []
        errors: list[dict[str, Any]] = []
        
        cutoff = datetime.now(timezone.utc) - timedelta(days=self.lookback_days)
        since_date = cutoff.strftime("%Y-%m-%d")
        seen_repos: set[str] = set()
        
        for query_def in queries:
            try:
                query_items = self._search_repos(query_def, since_date, cutoff)
                for item in query_items:
                    repo = str(item.metadata.get("repo", "")).lower()
                    if repo in seen_repos:
                        continue
                    seen_repos.add(repo)
                    items.append(item)
            except Exception as e:
                errors.append({
                    "source_id": f"trending-{query_def['topic']}",
                    "error_type": "search_error",
                    "message": str(e),
                    "retryable": True
                })
        
        finished_at = datetime.now(timezone.utc)
        
        status = RunStatus.SUCCESS if not errors else RunStatus.PARTIAL
        
        return WorkerResult(
            worker_id=self.worker_id,
            run_id=run_id,
            status=status,
            items=items,
            errors=errors,
            started_at=started_at,
            finished_at=finished_at,
            stats={
                "queries": len(queries),
                "lookback_days": self.lookback_days,
                "max_repo_age_days": self.max_repo_age_days,
                "min_stars": self.min_stars,
                "items_count": len(items)
            }
        )
    
    def _search_repos(self, query_def: dict[str, Any], since_date: str, cutoff: datetime) -> list[RawItem]:
        """搜索仓库"""
        q = f"{query_def['query']} in:name,description,topics created:>{since_date} stars:>{self.min_stars} fork:false archived:false"
        url = f"https://api.github.com/search/repositories?q={quote(q)}&sort=stars&order=desc&per_page={self.per_topic}"
        
        headers = {
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "TechRadar/0.1"
        }
        
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        
        req = Request(url, headers=headers)
        
        with urlopen(req, timeout=self.timeout) as resp:
            data = json.loads(resp.read().decode())
        
        items: list[RawItem] = []
        
        for repo in data.get("items", []):
            full_name = repo.get("full_name", "")
            html_url = repo.get("html_url", "")
            description = repo.get("description", "")
            stars = repo.get("stargazers_count", 0)
            forks = repo.get("forks_count", 0)
            created_at_str = repo.get("created_at")
            pushed_at_str = repo.get("pushed_at")
            
            if not created_at_str or not pushed_at_str:
                continue
            
            created_at = datetime.fromisoformat(created_at_str.replace("Z", "+00:00"))
            pushed_at = datetime.fromisoformat(pushed_at_str.replace("Z", "+00:00"))
            repo_age_days = (datetime.now(timezone.utc) - created_at).total_seconds() / 86400
            if created_at < cutoff or repo_age_days > self.max_repo_age_days:
                continue
            
            raw_id = self._generate_raw_id(f"trending-{query_def['topic']}", html_url, created_at)
            
            item = RawItem(
                raw_id=raw_id,
                source_type=SourceType.GITHUB_TRENDING,
                source_id=f"trending-{query_def['topic']}",
                source_name="GitHub Trending",
                worker_id=self.worker_id,
                title=f"{full_name}: {description[:100]}",
                url=html_url,
                raw_text=description,
                published_at=created_at,
                fetched_at=datetime.now(timezone.utc),
                topics=query_def.get("topics", []),
                metadata={
                    "stars": stars,
                    "forks": forks,
                    "repo": full_name,
                    "created_at": created_at.isoformat(),
                    "pushed_at": pushed_at.isoformat(),
                    "repo_age_days": round(repo_age_days, 2),
                    "trend_basis": "created_recently"
                }
            )
            items.append(item)
        
        return items
