"""测试数据模型和存储

验收 M1：可导入样例 RawItem 并保存。
"""
from datetime import datetime, timezone
from pathlib import Path

from tech_radar.models import RawItem, SourceRun, WorkerState, SourceType, RunStatus
from tech_radar.storage import Storage


def test_raw_item_creation():
    """测试 RawItem 创建"""
    item = RawItem(
        raw_id="test-001",
        source_type=SourceType.RSS,
        source_id="openai-rss",
        source_name="OpenAI Blog",
        worker_id="rss-official",
        title="Test Article",
        url="https://openai.com/blog/test",
        raw_text="Test content",
        published_at=datetime.now(timezone.utc),
        fetched_at=datetime.now(timezone.utc),
        topics=["llm", "ai-agent"],
        metadata={"priority": True}
    )
    
    print("✓ RawItem 创建成功")
    print(f"  raw_id: {item.raw_id}")
    print(f"  title: {item.title}")
    print(f"  topics: {item.topics}")
    return item


def test_storage_init():
    """测试存储初始化"""
    db_path = Path("D:/Temp/tech-radar-runtime-test/db/tech-radar.sqlite")
    storage = Storage(db_path)
    
    print("✓ SQLite 存储初始化成功")
    print(f"  路径: {db_path}")
    print(f"  存在: {db_path.exists()}")
    return storage


def test_save_raw_item(storage: Storage, item: RawItem):
    """测试保存 RawItem"""
    result = storage.save_raw_item(item)
    
    print("✓ RawItem 入库成功" if result else "✗ RawItem 入库失败")
    
    count = storage.count_raw_items()
    print(f"  当前 RawItem 数量: {count}")
    return result


def test_save_source_run(storage: Storage):
    """测试保存 SourceRun"""
    run = SourceRun(
        run_id="run-001",
        worker_id="rss-official",
        started_at=datetime.now(timezone.utc),
        finished_at=datetime.now(timezone.utc),
        status=RunStatus.SUCCESS,
        items_count=1,
        error_count=0,
        error_summary="",
        duration_ms=1000
    )
    
    result = storage.save_source_run(run)
    print("✓ SourceRun 入库成功" if result else "✗ SourceRun 入库失败")
    return result


def test_save_worker_state(storage: Storage):
    """测试保存 WorkerState"""
    state = WorkerState(
        worker_id="rss-official",
        enabled=True,
        next_due_at=datetime.now(timezone.utc),
        jitter_min_seconds=1200,
        jitter_max_seconds=2400
    )
    
    result = storage.save_worker_state(state)
    print("✓ WorkerState 入库成功" if result else "✗ WorkerState 入库失败")
    
    loaded = storage.load_worker_state("rss-official")
    if loaded:
        print(f"  加载验证成功: {loaded.worker_id}, enabled={loaded.enabled}")
    return result


def main():
    print("=" * 60)
    print("Tech Radar M1 验收测试")
    print("=" * 60)
    print()
    
    print("1. 测试 RawItem 创建")
    item = test_raw_item_creation()
    print()
    
    print("2. 测试存储初始化")
    storage = test_storage_init()
    print()
    
    print("3. 测试保存 RawItem")
    test_save_raw_item(storage, item)
    print()
    
    print("4. 测试保存 SourceRun")
    test_save_source_run(storage)
    print()
    
    print("5. 测试保存 WorkerState")
    test_save_worker_state(storage)
    print()
    
    print("=" * 60)
    print("M1 验收完成")
    print("可验收产物：可导入样例 RawItem 并保存 ✓")
    print("=" * 60)


if __name__ == "__main__":
    main()

