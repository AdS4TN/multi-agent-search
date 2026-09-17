from __future__ import annotations

import hashlib
import json
import re
import urllib.parse
from pathlib import Path
from typing import Any


def mask_url(url: str) -> str:
    """隐藏常见 token/query/path 敏感片段，避免日志泄露。"""
    if not url:
        return ""
    try:
        parsed = urllib.parse.urlsplit(url)

        def mask_value(value: str) -> str:
            return (value[:3] + "***" + value[-3:]) if len(value) > 8 else "***"

        def mask_path_segment(segment: str) -> str:
            raw = urllib.parse.unquote(segment)
            # 订阅链接常把 token/UUID 放在路径中；对长随机串做保守脱敏。
            looks_like_secret = (
                len(raw) >= 16
                and re.fullmatch(r"[A-Za-z0-9._~%-]+", raw) is not None
                and re.search(r"[A-Za-z]", raw) is not None
                and re.search(r"[0-9]", raw) is not None
            )
            if looks_like_secret:
                return urllib.parse.quote(mask_value(raw), safe="*")
            return segment

        path = "/".join(mask_path_segment(x) for x in parsed.path.split("/"))
        qs = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
        masked = []
        for k, v in qs:
            if re.search(r"token|key|secret|password|passwd|auth", k, re.I):
                v = mask_value(v)
            masked.append((k, v))
        return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, path, urllib.parse.urlencode(masked), parsed.fragment))
    except Exception:
        return re.sub(r"(token=)[^&\s]+", r"\1***", url, flags=re.I)


def stable_hash(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))
