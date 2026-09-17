"""主节点 Orchestrator

负责调度 Worker、接收结果、去重聚合和榜单更新。
"""
from __future__ import annotations

import random
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Optional
import json

from ..models import WorkerState, SourceRun, RunStatus
from ..storage import Storage
from ..workers import BaseWorker


class Orchestrator:
    """主节点"""
    
    def __init__(self, storage: Storage, config_dir: str | Path = "config"):
        self.storage = storage
        self.config_dir = Path(config_dir)
        self.workers: dict[str, BaseWorker] = {}
    
    def register_worker(self, worker: BaseWorker):
        """注册 Worker"""
        self.workers[worker.worker_id] = worker
    
    def init_worker_state(self, worker_id: str, jitter_min: int, jitter_max: int):
        """初始化 Worker 状态"""
        existing = self.storage.load_worker_state(worker_id)
        if existing:
            return
        
        state = WorkerState(
            worker_id=worker_id,
            enabled=True,
            next_due_at=datetime.now(timezone.utc),
            jitter_min_seconds=jitter_min,
            jitter_max_seconds=jitter_max
        )
        self.storage.save_worker_state(state)
    
    def get_due_workers(self) -> list[str]:
        """获取到期 Worker"""
        now = datetime.now(timezone.utc)
        states = self.storage.load_all_worker_states()
        
        due = []
        for state in states:
            if not state.enabled:
                continue
            if state.next_due_at <= now:
                due.append(state.worker_id)
        
        # 按到期时间和优先级排序
        due.sort(key=lambda wid: (
            self.storage.load_worker_state(wid).next_due_at,
            wid
        ))
        
        return due
    
    def run_worker(self, worker_id: str) -> dict[str, Any]:
        """运行单个 Worker"""
        worker = self.workers.get(worker_id)
        if not worker:
            return {"ok": False, "error": f"Worker {worker_id} not registered"}
        
        state = self.storage.load_worker_state(worker_id)
        if not state:
            return {"ok": False, "error": f"Worker {worker_id} state not found"}
        
        # 更新状态：开始运行
        state.last_run_at = datetime.now(timezone.utc)
        self.storage.save_worker_state(state)
        
        # 运行 Worker
        result = worker.run()
        
        # 保存 RawItem
        saved_count = 0
        for item in result.items:
            if self.storage.save_raw_item(item):
                saved_count += 1
        
        # 保存 SourceRun
        run = SourceRun(
            run_id=result.run_id,
            worker_id=worker_id,
            started_at=result.started_at,
            finished_at=result.finished_at,
            status=result.status,
            items_count=len(result.items),
            error_count=len(result.errors),
            error_summary="; ".join([e.get("message", "") for e in result.errors[:3]]),
            duration_ms=int((result.finished_at - result.started_at).total_seconds() * 1000)
        )
        self.storage.save_source_run(run)
        
        # 更新 WorkerState
        if result.status == RunStatus.SUCCESS or result.status == RunStatus.PARTIAL:
            state.last_success_at = datetime.now(timezone.utc)
            state.consecutive_failures = 0
            state.last_error = ""
        else:
            state.consecutive_failures += 1
            state.last_error = run.error_summary[:500]
        
        # 计算下次运行时间
        jitter = random.randint(state.jitter_min_seconds, state.jitter_max_seconds)
        
        # 失败退避
        if state.consecutive_failures >= 2:
            jitter *= (2 ** min(state.consecutive_failures - 1, 4))
        
        state.next_due_at = datetime.now(timezone.utc) + timedelta(seconds=jitter)
        self.storage.save_worker_state(state)
        
        return {
            "ok": True,
            "worker_id": worker_id,
            "status": result.status.value,
            "items_count": len(result.items),
            "saved_count": saved_count,
            "error_count": len(result.errors),
            "next_due_at": state.next_due_at.isoformat()
        }
    
    def run_once(self, max_workers: int = 10) -> dict[str, Any]:
        """运行一轮到期 Worker"""
        due_workers = self.get_due_workers()[:max_workers]
        
        if not due_workers:
            return {
                "ok": True,
                "workers_run": 0,
                "message": "无到期 Worker"
            }
        
        results = []
        for worker_id in due_workers:
            result = self.run_worker(worker_id)
            results.append(result)
        
        return {
            "ok": True,
            "workers_run": len(results),
            "results": results
        }
    
    def status(self) -> dict[str, Any]:
        """获取系统状态"""
        states = self.storage.load_all_worker_states()
        now = datetime.now(timezone.utc)
        
        rows = []
        for state in states:
            due_seconds = int((state.next_due_at - now).total_seconds())
            rows.append({
                "worker_id": state.worker_id,
                "enabled": state.enabled,
                "due_in_seconds": due_seconds,
                "last_success_at": state.last_success_at.isoformat() if state.last_success_at else None,
                "consecutive_failures": state.consecutive_failures,
                "last_error": state.last_error[:100] if state.last_error else ""
            })
        
        rows.sort(key=lambda x: x["due_in_seconds"])
        
        return {
            "workers_total": len(states),
            "workers_enabled": sum(1 for s in states if s.enabled),
            "workers_due": sum(1 for s in states if s.enabled and s.next_due_at <= now),
            "raw_items_count": self.storage.count_raw_items(),
            "news_events_count": self.storage.count_news_events(),
            "latest_leaderboard_snapshot": self.storage.get_kv("latest_leaderboard_snapshot"),
            "workers": rows
        }
