"""Worker 基类与协议

本模块定义 Worker 通用协议和基类。
"""
from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any

from ..models import WorkerResult, RawItem, RunStatus


class BaseWorker(ABC):
    """Worker 基类"""
    
    def __init__(self, worker_id: str, config: dict[str, Any]):
        self.worker_id = worker_id
        self.config = config
    
    @abstractmethod
    def fetch(self, run_id: str, **kwargs) -> WorkerResult:
        """
        采集数据并返回 WorkerResult
        
        Args:
            run_id: 本次运行 ID
            **kwargs: 运行参数，例如 since
        
        Returns:
            WorkerResult
        """
        pass
    
    def run(self, **kwargs) -> WorkerResult:
        """运行 Worker"""
        run_id = str(uuid.uuid4())
        started_at = datetime.now(timezone.utc)
        
        try:
            result = self.fetch(run_id, **kwargs)
            return result
        except Exception as e:
            finished_at = datetime.now(timezone.utc)
            return WorkerResult(
                worker_id=self.worker_id,
                run_id=run_id,
                status=RunStatus.FAILED,
                items=[],
                errors=[{
                    "error_type": "worker_exception",
                    "message": str(e),
                    "retryable": True
                }],
                started_at=started_at,
                finished_at=finished_at,
                stats={"exception": str(type(e).__name__)}
            )
    
    def _generate_raw_id(self, source_id: str, url: str, published_at: datetime) -> str:
        """生成 raw_id"""
        import hashlib
        raw = f"{source_id}:{url}:{published_at.isoformat()}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]
