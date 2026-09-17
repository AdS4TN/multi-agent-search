"""新闻配图抽取与榜单透传测试。"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from tech_radar.exporters import export_json
from tech_radar.image_extraction import (
    extract_feed_entry_image,
    extract_image_from_candidate,
    extract_image_from_html,
)
from tech_radar.models import NewsEvent, RawItem, SourceType
from tech_radar.ranking import generate_leaderboard


def test_extract_feed_media_content_image():
    entry = {
        "media_content": [
            {
                "url": "https://example.com/cover.webp",
                "type": "image/webp",
                "width": "1200",
                "height": "630",
            }
        ]
    }

    image = extract_feed_entry_image(entry, base_url="https://example.com/article")

    assert image["image_url"] == "https://example.com/cover.webp"
    assert image["image_source"] == "rss_media_content"
    assert image["image_width"] == 1200
    assert image["image_height"] == 630


def test_extract_html_first_image_with_relative_url():
    image = extract_image_from_html(
        '<p>hello</p><img src="/images/news.jpg" width="800" height="450">',
        base_url="https://example.com/posts/1",
        source="rss_summary_img",
    )

    assert image["image_url"] == "https://example.com/images/news.jpg"
    assert image["image_source"] == "rss_summary_img"


def test_extract_candidate_thumbnail_image():
    image = extract_image_from_candidate(
        {
            "thumbnail": "https://b.thumbs.redditmedia.com/demo.jpg",
        },
        base_url="https://www.reddit.com/r/MachineLearning/comments/demo",
    )

    assert image["image_url"] == "https://b.thumbs.redditmedia.com/demo.jpg"
    assert image["image_source"] == "candidate_thumbnail"


def test_leaderboard_selects_and_exports_representative_image(tmp_path):
    now = datetime.now(timezone.utc)
    raw = RawItem(
        raw_id="raw-1",
        source_type=SourceType.RSS,
        source_id="test-feed",
        source_name="Test Feed",
        worker_id="rss-test",
        title="Test story",
        url="https://example.com/story",
        canonical_url="https://example.com/story",
        raw_text="summary",
        published_at=now,
        fetched_at=now,
        topics=["ai"],
        metadata={
            "image_url": "https://example.com/story.jpg",
            "image_source": "rss_media_content",
        },
    )
    event = NewsEvent(
        event_id="event-1",
        canonical_title="Test story",
        canonical_url="https://example.com/story",
        summary_text="summary",
        topics=["ai"],
        source_count=1,
        raw_item_ids=["raw-1"],
        first_seen_at=now,
        latest_seen_at=now,
        published_at=now,
    )

    leaderboard = generate_leaderboard([event], raw_items_by_id={raw.raw_id: raw}, top_n=1)

    assert leaderboard[0].image_url == "https://example.com/story.jpg"
    assert leaderboard[0].image_source == "rss_media_content"
    assert leaderboard[0].image_alt == "Test story"

    output = tmp_path / "leaderboard.json"
    export_json(leaderboard, output)
    exported = json.loads(output.read_text(encoding="utf-8"))

    assert exported["items"][0]["image_url"] == "https://example.com/story.jpg"
    assert exported["items"][0]["image_source"] == "rss_media_content"
