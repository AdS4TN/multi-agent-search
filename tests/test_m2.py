"""测试 RSS Worker

验收 M2：可采集多组 RSS 并入库。
"""
from datetime import datetime, timezone
from pathlib import Path
import json

from tech_radar.models import SourceType
from tech_radar.storage import Storage
from tech_radar.workers.rss_worker import RSSWorker


def test_rss_worker():
    """测试 RSS Worker 采集"""
    print("=" * 60)
    print("Tech Radar M2 验收测试 - RSS Worker")
    print("=" * 60)
    print()
    
    # 加载配置
    config_path = Path("config/sources/rss-official.json")
    config = json.loads(config_path.read_text(encoding="utf-8-sig"))
    
    print(f"1. 加载配置: {config_path}")
    print(f"   Worker ID: {config['worker_id']}")
    print(f"   源数量: {len(config['sources'])}")
    print()
    
    # 创建 Worker
    worker = RSSWorker(
        worker_id=config["worker_id"],
        config=config
    )
    
    print("2. 创建 RSS Worker")
    print(f"   超时: {worker.timeout}s")
    print(f"   lookback: {worker.lookback_hours}h")
    print()
    
    # 运行采集
    print("3. 开始采集 RSS feeds...")
    result = worker.run()
    
    print(f"   状态: {result.status.value}")
    print(f"   采集项数: {len(result.items)}")
    print(f"   错误数: {len(result.errors)}")
    print(f"   耗时: {(result.finished_at - result.started_at).total_seconds():.1f}s")
    
    if result.errors:
        print("   错误:")
        for err in result.errors[:3]:
            print(f"     - {err['source_id']}: {err['error_type']} - {err['message']}")
    
    print()
    
    # 保存到数据库
    if result.items:
        db_path = Path("D:/Temp/tech-radar-runtime-test/db/tech-radar.sqlite")
        storage = Storage(db_path)
        
        print("4. 保存到数据库")
        saved = 0
        for item in result.items[:10]:  # 只保存前 10 条测试
            if storage.save_raw_item(item):
                saved += 1
        
        print(f"   已保存: {saved}/{min(len(result.items), 10)}")
        
        total = storage.count_raw_items()
        print(f"   数据库总 RawItem 数: {total}")
        print()
        
        # 展示样例
        if result.items:
            print("5. 采集样例:")
            for i, item in enumerate(result.items[:3], 1):
                print(f"   [{i}] {item.title[:60]}")
                print(f"       来源: {item.source_name}")
                print(f"       URL: {item.url[:80]}")
                print(f"       发布: {item.published_at.strftime('%Y-%m-%d %H:%M')}")
                print(f"       主题: {', '.join(item.topics)}")
                print()
    
    print("=" * 60)
    print("M2 验收完成")
    print(f"可验收产物：可采集多组 RSS 并入库 {'✓' if result.items else '✗'}")
    print("=" * 60)
    
    return result


if __name__ == "__main__":
    test_rss_worker()

