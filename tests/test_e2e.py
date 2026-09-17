"""完整端到端测试

验证从 Worker 采集到主节点调度的完整链路。
"""
from pathlib import Path
import json

from tech_radar.storage import Storage
from tech_radar.orchestrator import Orchestrator
from tech_radar.workers.rss_worker import RSSWorker


def test_end_to_end():
    """端到端测试"""
    print("=" * 70)
    print("Tech Radar 端到端测试")
    print("=" * 70)
    print()
    
    # 1. 初始化存储
    db_path = Path("D:/Temp/tech-radar-runtime-test/db/tech-radar.sqlite")
    storage = Storage(db_path)
    print(f"✓ 初始化存储: {db_path}")
    print()
    
    # 2. 创建主节点
    orchestrator = Orchestrator(storage, config_dir="config")
    print("✓ 创建主节点")
    print()
    
    # 3. 加载并注册 RSS Workers
    config_dir = Path("config/sources")
    workers_registered = 0
    
    for rss_config_file in config_dir.glob("rss-*.json"):
        config = json.loads(rss_config_file.read_text(encoding="utf-8-sig"))
        worker = RSSWorker(config["worker_id"], config)
        orchestrator.register_worker(worker)
        orchestrator.init_worker_state(
            config["worker_id"],
            config.get("jitter_min_seconds", 1200),
            config.get("jitter_max_seconds", 2400)
        )
        workers_registered += 1
        print(f"  注册 Worker: {config['worker_id']}")
    
    print(f"✓ 注册 {workers_registered} 个 RSS Workers")
    print()
    
    # 4. 查看状态
    status = orchestrator.status()
    print("✓ 系统状态:")
    print(f"  Worker 总数: {status['workers_total']}")
    print(f"  启用 Worker: {status['workers_enabled']}")
    print(f"  到期 Worker: {status['workers_due']}")
    print(f"  RawItem 总数: {status['raw_items_count']}")
    print()
    
    # 5. 运行一轮
    print("✓ 运行一轮采集...")
    result = orchestrator.run_once(max_workers=2)
    
    print(f"  运行 Worker 数: {result['workers_run']}")
    
    if result.get('results'):
        for r in result['results']:
            print(f"  - {r['worker_id']}: {r['status']}, items={r['items_count']}, saved={r['saved_count']}")
    
    print()
    
    # 6. 再次查看状态
    status_after = orchestrator.status()
    print("✓ 运行后状态:")
    print(f"  RawItem 总数: {status_after['raw_items_count']}")
    print(f"  新增: {status_after['raw_items_count'] - status['raw_items_count']}")
    print()
    
    print("=" * 70)
    print("端到端测试完成 ✓")
    print("=" * 70)


if __name__ == "__main__":
    test_end_to_end()

