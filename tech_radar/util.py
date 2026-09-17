from __future__ import annotations

import hashlib
import json
import re
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_now() -> str:
    return utc_now().isoformat()


def parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        return None


def stable_hash(value: Any, length: int = 16) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:length]


def read_json(path: str | Path, default: Any = None) -> Any:
    p = Path(path)
    if not p.exists():
        return default
    return json.loads(p.read_text(encoding="utf-8-sig"))


def write_json(path: str | Path, data: Any) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")


def normalize_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def normalize_title(value: str) -> str:
    text = normalize_whitespace(value).lower()
    text = re.sub(r"\s+[-|–—]\s+(the verge|techcrunch|ars technica|wired|mit technology review)$", "", text)
    text = re.sub(r"[^\w\s\-./:+#]", " ", text, flags=re.UNICODE)
    return normalize_whitespace(text)


def canonicalize_url(url: str) -> str:
    if not url:
        return ""
    try:
        parsed = urllib.parse.urlsplit(url.strip())
        scheme = parsed.scheme.lower() or "https"
        netloc = parsed.netloc.lower()
        path = re.sub(r"/+$", "", parsed.path or "/")
        drop_prefixes = ("utm_",)
        drop_names = {"fbclid", "gclid", "mc_cid", "mc_eid", "ref", "ref_src", "source"}
        pairs = []
        for k, v in urllib.parse.parse_qsl(parsed.query, keep_blank_values=True):
            lk = k.lower()
            if lk in drop_names or any(lk.startswith(x) for x in drop_prefixes):
                continue
            pairs.append((k, v))
        query = urllib.parse.urlencode(sorted(pairs))
        return urllib.parse.urlunsplit((scheme, netloc, path, query, ""))
    except Exception:
        return url.strip()


def mask_secret(value: str) -> str:
    if not value:
        return ""
    return value[:3] + "***" + value[-3:] if len(value) > 8 else "***"


def mask_url(url: str) -> str:
    try:
        parsed = urllib.parse.urlsplit(url)
        qs = []
        for k, v in urllib.parse.parse_qsl(parsed.query, keep_blank_values=True):
            if re.search(r"token|key|secret|password|passwd|auth", k, re.I):
                v = mask_secret(v)
            qs.append((k, v))
        return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urllib.parse.urlencode(qs), parsed.fragment))
    except Exception:
        return re.sub(r"(token=)[^&\s]+", r"\1***", url, flags=re.I)
