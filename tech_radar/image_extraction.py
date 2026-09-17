"""新闻配图抽取工具。

第一版只保存远程图片 URL，不下载、不缓存图片。这里集中处理 URL
规范化、RSS/Atom 媒体字段和 HTML 摘要中的首图提取，避免各 Worker
重复实现。
"""
from __future__ import annotations

import html
import re
from typing import Any
from urllib.parse import urljoin, urlparse


IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp", ".gif", ".avif")
PLACEHOLDER_VALUES = {"", "self", "default", "nsfw", "spoiler", "image", "unknown"}


def normalize_image_url(value: Any, base_url: str = "") -> str:
    """把候选图片地址规范化为可展示的 http(s) URL。"""
    if not value:
        return ""
    raw = html.unescape(str(value)).strip().strip("\"'")
    if not raw or raw.lower() in PLACEHOLDER_VALUES:
        return ""
    if raw.startswith("//"):
        raw = "https:" + raw
    elif base_url:
        raw = urljoin(base_url, raw)

    parsed = urlparse(raw)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    return raw


def looks_like_image_url(value: str) -> bool:
    """根据 URL 后缀判断是否明显是图片。"""
    parsed = urlparse(value)
    path = parsed.path.lower()
    return path.endswith(IMAGE_EXTENSIONS)


def first_non_empty(*values: Any) -> str:
    for value in values:
        if value not in (None, ""):
            return str(value)
    return ""


def int_or_none(value: Any) -> int | None:
    try:
        if value in (None, ""):
            return None
        return int(float(str(value)))
    except Exception:
        return None


def image_metadata(
    url: str,
    *,
    source: str,
    width: Any = None,
    height: Any = None,
) -> dict[str, Any]:
    """生成统一的图片元信息。"""
    if not url:
        return {}
    data: dict[str, Any] = {
        "image_url": url,
        "image_source": source,
    }
    w = int_or_none(width)
    h = int_or_none(height)
    if w:
        data["image_width"] = w
    if h:
        data["image_height"] = h
    return data


def extract_image_from_html(markup: str, base_url: str = "", source: str = "html_img") -> dict[str, Any]:
    """从 HTML 片段里提取第一张有意义的图片。"""
    if not markup:
        return {}

    for tag in re.findall(r"<img\b[^>]*>", markup, flags=re.I | re.S):
        attrs = _parse_html_attrs(tag)
        candidate = first_non_empty(
            attrs.get("src"),
            attrs.get("data-src"),
            attrs.get("data-original"),
            attrs.get("data-lazy-src"),
        )
        if not candidate and attrs.get("srcset"):
            candidate = _first_srcset_url(attrs["srcset"])
        if not candidate and attrs.get("data-srcset"):
            candidate = _first_srcset_url(attrs["data-srcset"])

        url = normalize_image_url(candidate, base_url=base_url)
        if not url:
            continue
        width = int_or_none(attrs.get("width"))
        height = int_or_none(attrs.get("height"))
        if width is not None and height is not None and width <= 2 and height <= 2:
            continue
        return image_metadata(url, source=source, width=width, height=height)

    return {}


def extract_feed_entry_image(entry: Any, base_url: str = "") -> dict[str, Any]:
    """从 feedparser entry 中提取 RSS/Atom 原生配图。"""
    # media:content
    image = _image_from_media_list(
        _entry_get(entry, "media_content"),
        source="rss_media_content",
        base_url=base_url,
    )
    if image:
        return image

    # media:thumbnail
    image = _image_from_media_list(
        _entry_get(entry, "media_thumbnail"),
        source="rss_media_thumbnail",
        base_url=base_url,
    )
    if image:
        return image

    # enclosure / links
    links = []
    for key in ("enclosures", "links"):
        value = _entry_get(entry, key)
        if isinstance(value, list):
            links.extend(value)
    image = _image_from_media_list(links, source="rss_enclosure", base_url=base_url, require_image_hint=True)
    if image:
        return image

    return {}


def extract_image_from_candidate(candidate: dict[str, Any], base_url: str = "") -> dict[str, Any]:
    """从 Reddit/其它候选项字典里提取图片字段。"""
    direct_fields = (
        "image_url",
        "thumbnail",
        "thumbnail_url",
        "preview_image",
        "preview_url",
        "url_overridden_by_dest",
    )
    for field in direct_fields:
        url = normalize_image_url(candidate.get(field), base_url=base_url)
        if url and (field != "url_overridden_by_dest" or looks_like_image_url(url)):
            return image_metadata(url, source=f"candidate_{field}")

    preview = candidate.get("preview")
    if isinstance(preview, dict):
        images = preview.get("images")
        if isinstance(images, list):
            for item in images:
                if not isinstance(item, dict):
                    continue
                source = item.get("source") or {}
                variants = item.get("variants") or {}
                url = normalize_image_url(source.get("url"), base_url=base_url)
                if not url and isinstance(variants, dict):
                    for variant in variants.values():
                        if isinstance(variant, dict):
                            url = normalize_image_url((variant.get("source") or {}).get("url"), base_url=base_url)
                            if url:
                                break
                if url:
                    return image_metadata(
                        url,
                        source="candidate_preview",
                        width=source.get("width"),
                        height=source.get("height"),
                    )

    media_metadata = candidate.get("media_metadata")
    if isinstance(media_metadata, dict):
        for media in media_metadata.values():
            if not isinstance(media, dict):
                continue
            if media.get("e") not in (None, "Image"):
                continue
            source = media.get("s") or {}
            url = normalize_image_url(source.get("u") or source.get("gif"), base_url=base_url)
            if url:
                return image_metadata(url, source="candidate_media_metadata", width=source.get("x"), height=source.get("y"))

    for html_field in ("summary", "content", "content_html", "selftext_html", "description"):
        image = extract_image_from_html(str(candidate.get(html_field) or ""), base_url=base_url, source=f"candidate_{html_field}_img")
        if image:
            return image

    return {}


def _entry_get(entry: Any, key: str) -> Any:
    if isinstance(entry, dict):
        return entry.get(key)
    return getattr(entry, key, None)


def _image_from_media_list(
    values: Any,
    *,
    source: str,
    base_url: str,
    require_image_hint: bool = False,
) -> dict[str, Any]:
    if not isinstance(values, list):
        return {}
    for item in values:
        if not isinstance(item, dict):
            continue
        url = normalize_image_url(item.get("url") or item.get("href"), base_url=base_url)
        if not url:
            continue
        media_type = str(item.get("type") or "").lower()
        medium = str(item.get("medium") or "").lower()
        has_image_hint = media_type.startswith("image/") or medium == "image" or looks_like_image_url(url)
        if require_image_hint and not has_image_hint:
            continue
        if media_type and not media_type.startswith("image/") and not has_image_hint:
            continue
        return image_metadata(
            url,
            source=source,
            width=item.get("width"),
            height=item.get("height"),
        )
    return {}


def _parse_html_attrs(tag: str) -> dict[str, str]:
    attrs: dict[str, str] = {}
    for match in re.finditer(
        r"([:\w-]+)\s*=\s*(?:\"([^\"]*)\"|'([^']*)'|([^\s\"'>/]+))",
        tag,
        flags=re.I,
    ):
        key = match.group(1).lower()
        value = first_non_empty(match.group(2), match.group(3), match.group(4))
        attrs[key] = html.unescape(value)
    return attrs


def _first_srcset_url(value: str) -> str:
    for part in str(value).split(","):
        url = part.strip().split(" ")[0].strip()
        if url:
            return url
    return ""
