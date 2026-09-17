"""导出模块

支持 JSON 和 Markdown 格式导出。
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from ..models import LeaderboardItem


def export_json(items: list[LeaderboardItem], output_path: str | Path) -> bool:
    """导出 JSON"""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    data = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "items_count": len(items),
        "items": [
            {
                "rank": item.rank,
                "event_id": item.event_id,
                "title": item.title,
                "url": item.url,
                "image_url": item.image_url,
                "image_source": item.image_source,
                "image_alt": item.image_alt,
                "topics": item.topics,
                "score": item.score,
                "source_count": item.source_count,
                "source_names": item.source_names,
                "reason": item.reason,
                "updated_at": item.updated_at.isoformat()
            }
            for item in items
        ]
    }
    
    output_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    
    return True


def export_markdown(items: list[LeaderboardItem], output_path: str | Path) -> bool:
    """导出 Markdown"""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    lines = [
        "# Tech Radar 科技新闻榜单",
        "",
        f"生成时间: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}",
        "",
        f"总条数: {len(items)}",
        "",
        "---",
        ""
    ]
    
    for item in items:
        lines.append(f"## {item.rank}. {item.title}")
        lines.append("")
        if item.image_url:
            alt = (item.image_alt or item.title).replace("[", "").replace("]", "")
            lines.append(f"![{alt}]({item.image_url})")
            lines.append("")
        lines.append(f"**链接**: {item.url}")
        lines.append("")
        lines.append(f"**得分**: {item.score:.1f} | **来源数**: {item.source_count}")
        lines.append("")
        lines.append(f"**主题**: {', '.join(item.topics)}")
        lines.append("")
        lines.append(f"**上榜原因**: {item.reason}")
        lines.append("")
        lines.append("---")
        lines.append("")
    
    output_path.write_text("\n".join(lines), encoding="utf-8")
    
    return True
