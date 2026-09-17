"""SQLite 存储层

本模块负责初始化数据库、表结构和基础读写操作。
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from ..models import (
    LLMEventScore,
    LeaderboardItem,
    NewsEvent,
    RawItem,
    RunStatus,
    SourceRun,
    SourceType,
    WorkerState,
)


class Storage:
    """SQLite 存储管理器"""
    
    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
    
    def _init_db(self):
        """初始化数据库和表结构"""
        conn = sqlite3.connect(str(self.db_path))
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        
        # raw_items 表
        conn.execute("""
            CREATE TABLE IF NOT EXISTS raw_items (
                raw_id TEXT PRIMARY KEY,
                source_type TEXT NOT NULL,
                source_id TEXT NOT NULL,
                source_name TEXT NOT NULL,
                worker_id TEXT NOT NULL,
                title TEXT NOT NULL,
                url TEXT NOT NULL,
                canonical_url TEXT,
                raw_text TEXT,
                published_at TEXT NOT NULL,
                fetched_at TEXT NOT NULL,
                topics TEXT,
                metadata TEXT,
                created_at TEXT NOT NULL
            )
        """)
        
        # source_runs 表
        conn.execute("""
            CREATE TABLE IF NOT EXISTS source_runs (
                run_id TEXT PRIMARY KEY,
                worker_id TEXT NOT NULL,
                started_at TEXT NOT NULL,
                finished_at TEXT,
                status TEXT NOT NULL,
                items_count INTEGER DEFAULT 0,
                error_count INTEGER DEFAULT 0,
                error_summary TEXT,
                duration_ms INTEGER
            )
        """)
        
        # worker_state 表
        conn.execute("""
            CREATE TABLE IF NOT EXISTS worker_state (
                worker_id TEXT PRIMARY KEY,
                enabled INTEGER NOT NULL,
                next_due_at TEXT NOT NULL,
                last_run_at TEXT,
                last_success_at TEXT,
                consecutive_failures INTEGER DEFAULT 0,
                last_error TEXT,
                jitter_min_seconds INTEGER NOT NULL,
                jitter_max_seconds INTEGER NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        
        # news_events 表
        conn.execute("""
            CREATE TABLE IF NOT EXISTS news_events (
                event_id TEXT PRIMARY KEY,
                canonical_title TEXT NOT NULL,
                canonical_url TEXT NOT NULL,
                summary_text TEXT,
                topics TEXT,
                source_count INTEGER NOT NULL,
                raw_item_ids TEXT,
                first_seen_at TEXT NOT NULL,
                latest_seen_at TEXT NOT NULL,
                published_at TEXT NOT NULL,
                score REAL DEFAULT 0,
                score_breakdown TEXT,
                updated_at TEXT NOT NULL
            )
        """)

        # event_sources 表：NewsEvent 与 RawItem 的关联，便于追溯。
        conn.execute("""
            CREATE TABLE IF NOT EXISTS event_sources (
                event_id TEXT NOT NULL,
                raw_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY(event_id, raw_id)
            )
        """)
        
        # leaderboard_snapshots 表
        conn.execute("""
            CREATE TABLE IF NOT EXISTS leaderboard_snapshots (
                snapshot_id TEXT PRIMARY KEY,
                generated_at TEXT NOT NULL,
                items TEXT NOT NULL,
                metadata TEXT
            )
        """)
        
        # system_kv 表
        conn.execute("""
            CREATE TABLE IF NOT EXISTS system_kv (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)

        # source_cache 表：保存 RSS/GitHub 条件请求和源级状态。
        conn.execute("""
            CREATE TABLE IF NOT EXISTS source_cache (
                cache_key TEXT PRIMARY KEY,
                cache_value TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)

        # llm_event_scores 表：缓存 LLM 编辑评分，避免同一事件重复付费调用。
        conn.execute("""
            CREATE TABLE IF NOT EXISTS llm_event_scores (
                event_id TEXT NOT NULL,
                input_hash TEXT NOT NULL,
                model TEXT NOT NULL,
                provider TEXT NOT NULL,
                importance REAL DEFAULT 0,
                trend_value REAL DEFAULT 0,
                novelty REAL DEFAULT 0,
                audience_fit REAL DEFAULT 0,
                noise_penalty REAL DEFAULT 0,
                confidence REAL DEFAULT 0,
                labels TEXT,
                reason TEXT,
                raw_response TEXT,
                error TEXT,
                created_at TEXT NOT NULL,
                PRIMARY KEY(event_id, input_hash, model)
            )
        """)
        
        # 索引
        conn.execute("CREATE INDEX IF NOT EXISTS idx_raw_items_url ON raw_items(canonical_url)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_raw_items_published ON raw_items(published_at)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_raw_items_worker ON raw_items(worker_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_source_runs_worker ON source_runs(worker_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_news_events_url ON news_events(canonical_url)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_event_sources_raw ON event_sources(raw_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_llm_event_scores_event ON llm_event_scores(event_id)")
        
        conn.commit()
        conn.close()
    
    def save_raw_item(self, item: RawItem) -> bool:
        """保存 RawItem"""
        import json
        
        conn = sqlite3.connect(str(self.db_path))
        try:
            conn.execute("""
                INSERT OR REPLACE INTO raw_items
                (raw_id, source_type, source_id, source_name, worker_id,
                 title, url, canonical_url, raw_text, published_at, fetched_at,
                 topics, metadata, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                item.raw_id,
                item.source_type.value,
                item.source_id,
                item.source_name,
                item.worker_id,
                item.title,
                item.url,
                item.canonical_url,
                item.raw_text,
                item.published_at.isoformat(),
                item.fetched_at.isoformat(),
                json.dumps(item.topics, ensure_ascii=False),
                json.dumps(item.metadata, ensure_ascii=False),
                datetime.now(timezone.utc).isoformat()
            ))
            conn.commit()
            return True
        except Exception as e:
            print(f"保存 RawItem 失败: {e}")
            return False
        finally:
            conn.close()
    
    def save_source_run(self, run: SourceRun) -> bool:
        """保存 SourceRun"""
        conn = sqlite3.connect(str(self.db_path))
        try:
            conn.execute("""
                INSERT OR REPLACE INTO source_runs
                (run_id, worker_id, started_at, finished_at, status,
                 items_count, error_count, error_summary, duration_ms)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                run.run_id,
                run.worker_id,
                run.started_at.isoformat(),
                run.finished_at.isoformat() if run.finished_at else None,
                run.status.value,
                run.items_count,
                run.error_count,
                run.error_summary,
                run.duration_ms
            ))
            conn.commit()
            return True
        except Exception as e:
            print(f"保存 SourceRun 失败: {e}")
            return False
        finally:
            conn.close()
    
    def save_worker_state(self, state: WorkerState) -> bool:
        """保存 WorkerState"""
        conn = sqlite3.connect(str(self.db_path))
        try:
            conn.execute("""
                INSERT OR REPLACE INTO worker_state
                (worker_id, enabled, next_due_at, last_run_at, last_success_at,
                 consecutive_failures, last_error, jitter_min_seconds, jitter_max_seconds, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                state.worker_id,
                1 if state.enabled else 0,
                state.next_due_at.isoformat(),
                state.last_run_at.isoformat() if state.last_run_at else None,
                state.last_success_at.isoformat() if state.last_success_at else None,
                state.consecutive_failures,
                state.last_error,
                state.jitter_min_seconds,
                state.jitter_max_seconds,
                datetime.now(timezone.utc).isoformat()
            ))
            conn.commit()
            return True
        except Exception as e:
            print(f"保存 WorkerState 失败: {e}")
            return False
        finally:
            conn.close()
    
    def load_worker_state(self, worker_id: str) -> Optional[WorkerState]:
        """加载 WorkerState"""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        try:
            row = conn.execute(
                "SELECT * FROM worker_state WHERE worker_id = ?",
                (worker_id,)
            ).fetchone()
            if not row:
                return None
            return WorkerState(
                worker_id=row["worker_id"],
                enabled=bool(row["enabled"]),
                next_due_at=datetime.fromisoformat(row["next_due_at"]),
                last_run_at=datetime.fromisoformat(row["last_run_at"]) if row["last_run_at"] else None,
                last_success_at=datetime.fromisoformat(row["last_success_at"]) if row["last_success_at"] else None,
                consecutive_failures=row["consecutive_failures"],
                last_error=row["last_error"] or "",
                jitter_min_seconds=row["jitter_min_seconds"],
                jitter_max_seconds=row["jitter_max_seconds"]
            )
        finally:
            conn.close()
    
    def load_all_worker_states(self) -> list[WorkerState]:
        """加载所有 WorkerState"""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute("SELECT * FROM worker_state").fetchall()
            return [
                WorkerState(
                    worker_id=row["worker_id"],
                    enabled=bool(row["enabled"]),
                    next_due_at=datetime.fromisoformat(row["next_due_at"]),
                    last_run_at=datetime.fromisoformat(row["last_run_at"]) if row["last_run_at"] else None,
                    last_success_at=datetime.fromisoformat(row["last_success_at"]) if row["last_success_at"] else None,
                    consecutive_failures=row["consecutive_failures"],
                    last_error=row["last_error"] or "",
                    jitter_min_seconds=row["jitter_min_seconds"],
                    jitter_max_seconds=row["jitter_max_seconds"]
                )
                for row in rows
            ]
        finally:
            conn.close()

    def set_worker_enabled(self, worker_id: str, enabled: bool) -> None:
        """设置 Worker 启用状态；如果不存在则忽略。"""
        conn = sqlite3.connect(str(self.db_path))
        try:
            conn.execute(
                "UPDATE worker_state SET enabled = ?, updated_at = ? WHERE worker_id = ?",
                (1 if enabled else 0, datetime.now(timezone.utc).isoformat(), worker_id),
            )
            conn.commit()
        finally:
            conn.close()
    
    def count_raw_items(self) -> int:
        """统计 RawItem 数量"""
        conn = sqlite3.connect(str(self.db_path))
        try:
            return conn.execute("SELECT COUNT(*) FROM raw_items").fetchone()[0]
        finally:
            conn.close()

    def load_raw_items(self, limit: int = 1000) -> list[RawItem]:
        """读取最近的 RawItem。"""
        import json

        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                "SELECT * FROM raw_items ORDER BY published_at DESC LIMIT ?",
                (int(limit),),
            ).fetchall()
            return [
                RawItem(
                    raw_id=row["raw_id"],
                    source_type=SourceType(row["source_type"]),
                    source_id=row["source_id"],
                    source_name=row["source_name"],
                    worker_id=row["worker_id"],
                    title=row["title"],
                    url=row["url"],
                    canonical_url=row["canonical_url"],
                    raw_text=row["raw_text"] or "",
                    published_at=datetime.fromisoformat(row["published_at"]),
                    fetched_at=datetime.fromisoformat(row["fetched_at"]),
                    topics=json.loads(row["topics"] or "[]"),
                    metadata=json.loads(row["metadata"] or "{}"),
                )
                for row in rows
            ]
        finally:
            conn.close()

    def save_news_event(self, event: NewsEvent) -> bool:
        """保存 NewsEvent。"""
        import json

        conn = sqlite3.connect(str(self.db_path))
        try:
            conn.execute(
                """
                INSERT OR REPLACE INTO news_events
                (event_id, canonical_title, canonical_url, summary_text, topics,
                 source_count, raw_item_ids, first_seen_at, latest_seen_at,
                 published_at, score, score_breakdown, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.event_id,
                    event.canonical_title,
                    event.canonical_url,
                    event.summary_text,
                    json.dumps(event.topics, ensure_ascii=False),
                    event.source_count,
                    json.dumps(event.raw_item_ids, ensure_ascii=False),
                    event.first_seen_at.isoformat(),
                    event.latest_seen_at.isoformat(),
                    event.published_at.isoformat(),
                    event.score,
                    json.dumps(event.score_breakdown, ensure_ascii=False),
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            now = datetime.now(timezone.utc).isoformat()
            for raw_id in event.raw_item_ids:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO event_sources(event_id, raw_id, created_at)
                    VALUES (?, ?, ?)
                    """,
                    (event.event_id, raw_id, now),
                )
            conn.commit()
            return True
        finally:
            conn.close()

    def save_news_events(self, events: list[NewsEvent]) -> int:
        """批量保存 NewsEvent，返回保存数量。"""
        count = 0
        for event in events:
            if self.save_news_event(event):
                count += 1
        return count

    def replace_news_events(self, events: list[NewsEvent]) -> int:
        """用当前重建结果替换 NewsEvent 和 event_sources。"""
        conn = sqlite3.connect(str(self.db_path))
        try:
            conn.execute("DELETE FROM event_sources")
            conn.execute("DELETE FROM news_events")
            conn.commit()
        finally:
            conn.close()
        return self.save_news_events(events)

    def count_news_events(self) -> int:
        """统计 NewsEvent 数量。"""
        conn = sqlite3.connect(str(self.db_path))
        try:
            return conn.execute("SELECT COUNT(*) FROM news_events").fetchone()[0]
        finally:
            conn.close()

    def save_leaderboard_snapshot(
        self,
        snapshot_id: str,
        items: list[LeaderboardItem],
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        """保存榜单快照，并把 latest_leaderboard_snapshot 指向该快照。"""
        import json

        now = datetime.now(timezone.utc).isoformat()
        payload = [
            item.model_dump(mode="json")
            for item in items
        ]
        conn = sqlite3.connect(str(self.db_path))
        try:
            conn.execute(
                """
                INSERT OR REPLACE INTO leaderboard_snapshots
                (snapshot_id, generated_at, items, metadata)
                VALUES (?, ?, ?, ?)
                """,
                (
                    snapshot_id,
                    now,
                    json.dumps(payload, ensure_ascii=False),
                    json.dumps(metadata or {}, ensure_ascii=False, default=str),
                ),
            )
            conn.execute(
                """
                INSERT OR REPLACE INTO system_kv(key, value, updated_at)
                VALUES (?, ?, ?)
                """,
                ("latest_leaderboard_snapshot", snapshot_id, now),
            )
            conn.commit()
            return True
        finally:
            conn.close()

    def get_kv(self, key: str) -> str | None:
        """读取 system_kv。"""
        conn = sqlite3.connect(str(self.db_path))
        try:
            row = conn.execute("SELECT value FROM system_kv WHERE key = ?", (key,)).fetchone()
            return str(row[0]) if row else None
        finally:
            conn.close()

    def save_llm_event_score(self, score: LLMEventScore) -> bool:
        """保存 LLM 事件评分。"""
        import json

        conn = sqlite3.connect(str(self.db_path))
        try:
            conn.execute(
                """
                INSERT OR REPLACE INTO llm_event_scores
                (event_id, input_hash, model, provider, importance, trend_value,
                 novelty, audience_fit, noise_penalty, confidence, labels, reason,
                 raw_response, error, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    score.event_id,
                    score.input_hash,
                    score.model,
                    score.provider,
                    float(score.importance),
                    float(score.trend_value),
                    float(score.novelty),
                    float(score.audience_fit),
                    float(score.noise_penalty),
                    float(score.confidence),
                    json.dumps(score.labels, ensure_ascii=False),
                    score.reason,
                    score.raw_response,
                    score.error,
                    score.created_at.isoformat(),
                ),
            )
            conn.commit()
            return True
        finally:
            conn.close()

    def load_llm_event_score(self, event_id: str, input_hash: str, model: str) -> LLMEventScore | None:
        """按事件、输入指纹和模型读取 LLM 评分缓存。"""
        import json

        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        try:
            row = conn.execute(
                """
                SELECT * FROM llm_event_scores
                WHERE event_id = ? AND input_hash = ? AND model = ?
                """,
                (event_id, input_hash, model),
            ).fetchone()
            if not row:
                return None
            return LLMEventScore(
                event_id=row["event_id"],
                input_hash=row["input_hash"],
                model=row["model"],
                provider=row["provider"],
                importance=float(row["importance"] or 0),
                trend_value=float(row["trend_value"] or 0),
                novelty=float(row["novelty"] or 0),
                audience_fit=float(row["audience_fit"] or 0),
                noise_penalty=float(row["noise_penalty"] or 0),
                confidence=float(row["confidence"] or 0),
                labels=json.loads(row["labels"] or "[]"),
                reason=row["reason"] or "",
                raw_response=row["raw_response"] or "",
                error=row["error"] or "",
                created_at=datetime.fromisoformat(row["created_at"]),
            )
        finally:
            conn.close()

    def count_llm_event_scores(self) -> int:
        """统计 LLM 评分缓存数量。"""
        conn = sqlite3.connect(str(self.db_path))
        try:
            return int(conn.execute("SELECT COUNT(*) FROM llm_event_scores").fetchone()[0])
        finally:
            conn.close()
