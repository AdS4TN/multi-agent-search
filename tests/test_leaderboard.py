"""完整榜单生成测试

验证去重、聚合、排序和导出的完整链路。
"""
from pathlib import Path
import sqlite3
from datetime import datetime

from tech_radar.storage import Storage
from tech_radar.models import RawItem, SourceType
from tech_radar.ranking.dedup import Deduplicator
from tech_radar.ranking import generate_leaderboard
from tech_radar.exporters import export_json, export_markdown


def test_leaderboard():
    """测试榜单生成"""
    print("=" * 70)
    print("Tech Radar 榜单生成测试")
    print("=" * 70)
    print()
    
    # 1. 读取数据库中的 RawItem
    db_path = Path("D:/Temp/tech-radar-runtime-test/db/tech-radar.sqlite")
    
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    
    rows = conn.execute("SELECT * FROM raw_items ORDER BY published_at DESC LIMIT 50").fetchall()
    conn.close()
    
    print(f"✓ 从数据库读取 {len(rows)} 条 RawItem")
    print()
    
    # 2. 转换为 RawItem 对象
    import json
    
    items = []
    for row in rows:
        item = RawItem(
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
            topics=json.loads(row["topics"]),
            metadata=json.loads(row["metadata"])
        )
        items.append(item)
    
    # 3. 去重聚合
    print("✓ 去重聚合...")
    dedup = Deduplicator()
    
    for item in items:
        dedup.add_item(item)
    
    events = dedup.get_events()
    print(f"  原始项: {len(items)}")
    print(f"  去重后事件: {len(events)}")
    print()
    
    # 4. 生成榜单
    print("✓ 生成榜单...")
    leaderboard = generate_leaderboard(events, top_n=20)
    
    print(f"  榜单条数: {len(leaderboard)}")
    print()
    
    # 5. 展示 Top 5
    print("✓ Top 5:")
    for item in leaderboard[:5]:
        print(f"  [{item.rank}] {item.title[:60]}")
        print(f"      得分: {item.score:.1f} | 来源: {item.source_count} | 原因: {item.reason}")
        print(f"      URL: {item.url[:80]}")
        print()
    
    # 6. 导出
    export_dir = Path("D:/Temp/tech-radar-runtime-test/exports")
    
    json_path = export_dir / "leaderboard.json"
    md_path = export_dir / "leaderboard.md"
    
    export_json(leaderboard, json_path)
    export_markdown(leaderboard, md_path)
    
    print(f"✓ 导出完成:")
    print(f"  JSON: {json_path}")
    print(f"  Markdown: {md_path}")
    print()
    
    print("=" * 70)
    print("榜单生成测试完成 ✓")
    print("=" * 70)


if __name__ == "__main__":
    test_leaderboard()

