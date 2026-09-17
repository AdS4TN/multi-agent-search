from __future__ import annotations

import urllib.error
import urllib.request

from .config import PoolConfig


def test_reddit_rss(cfg: PoolConfig) -> dict[str, object]:
    proxy = f"http://127.0.0.1:{cfg.mixed_port}"
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({"http": proxy, "https": proxy}))
    req = urllib.request.Request(
        cfg.reddit_test_url,
        headers={
            "User-Agent": cfg.reddit_user_agent,
            "Accept": "application/atom+xml, application/rss+xml, application/xml;q=0.9, text/xml;q=0.8, */*;q=0.5",
            "Accept-Language": "en-US,en;q=0.9",
        },
    )
    try:
        with opener.open(req, timeout=cfg.reddit_timeout_seconds) as resp:
            body = resp.read(4096)
            return {
                "ok": 200 <= resp.status < 300,
                "status": resp.status,
                "content_type": resp.headers.get("content-type"),
                "sample": body[:120].decode("utf-8", errors="ignore").replace("\n", " "),
                "via_proxy": proxy,
            }
    except urllib.error.HTTPError as exc:
        sample = exc.read(300).decode("utf-8", errors="ignore").replace("\n", " ")
        return {"ok": False, "status": exc.code, "error": sample, "via_proxy": proxy}
    except Exception as exc:
        return {"ok": False, "status": None, "error": f"{type(exc).__name__}: {exc}", "via_proxy": proxy}
