"""Tech Radar HTTP 服务。

使用 Python 标准库实现，避免服务器部署时额外依赖：

- GET /                 简单网页榜单
- GET /health           健康检查
- GET /api/status       Worker 和数据库状态
- GET /api/leaderboard  当前榜单 JSON
- GET /api/raw          最近 RawItem
- POST /api/run-once    手动触发一轮到期 Worker

后台循环会按 WorkerState 的 next_due_at 运行到期 Worker，并在有新数据入库时
自动重建榜单。GitHub Worker 默认不注册。
"""
from __future__ import annotations

import json
import mimetypes
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .app_runtime import rebuild_and_persist_leaderboard, register_configured_workers
from .exporters import export_json, export_markdown
from .orchestrator import Orchestrator
from .storage import Storage


WEB_DIR = Path(__file__).with_name("web")
FRONTEND_ROUTES = {"/", "/sources", "/ops"}


class TechRadarRuntime:
    """服务运行时状态。"""

    def __init__(
        self,
        *,
        runtime_dir: str | Path,
        config_dir: str | Path,
        include_github: bool = False,
        poll_seconds: int = 300,
        max_workers: int = 5,
        leaderboard_limit: int = 500,
        leaderboard_top: int = 50,
        llm_enabled: bool = False,
        llm_candidate_limit: int = 80,
        llm_weight: float = 0.3,
    ):
        self.runtime_dir = Path(runtime_dir)
        self.config_dir = Path(config_dir)
        self.include_github = include_github
        self.poll_seconds = max(30, int(poll_seconds))
        self.max_workers = max(1, int(max_workers))
        self.leaderboard_limit = int(leaderboard_limit)
        self.leaderboard_top = int(leaderboard_top)
        self.llm_enabled = bool(llm_enabled)
        self.llm_candidate_limit = int(llm_candidate_limit)
        self.llm_weight = float(llm_weight)

        self.storage = Storage(self.runtime_dir / "db" / "tech-radar.sqlite")
        self.orchestrator = Orchestrator(self.storage, config_dir=self.config_dir)
        self.registered_workers = register_configured_workers(
            self.orchestrator,
            self.config_dir,
            include_github=self.include_github,
        )

        self.lock = threading.Lock()
        self.last_cycle_at: str | None = None
        self.last_cycle_result: dict | None = None
        self.last_error: str = ""
        self.stop_event = threading.Event()
        self.thread: threading.Thread | None = None

    def start_background_loop(self) -> None:
        """启动后台循环。"""
        if self.thread and self.thread.is_alive():
            return
        self.thread = threading.Thread(target=self._loop, name="tech-radar-loop", daemon=True)
        self.thread.start()

    def _loop(self) -> None:
        while not self.stop_event.is_set():
            try:
                self.run_cycle()
            except Exception as exc:  # 后台循环不能因为一次异常退出
                self.last_error = f"{type(exc).__name__}: {exc}"
            self.stop_event.wait(self.poll_seconds)

    def run_cycle(self) -> dict:
        """运行一轮到期 Worker。"""
        with self.lock:
            result = self.orchestrator.run_once(max_workers=self.max_workers)
            saved_total = sum(int(x.get("saved_count", 0)) for x in result.get("results", []))
            if saved_total > 0:
                built = rebuild_and_persist_leaderboard(
                    self.storage,
                    limit=self.leaderboard_limit,
                    top=self.leaderboard_top,
                    trigger="service-loop",
                    llm_enabled=self.llm_enabled,
                    llm_candidate_limit=self.llm_candidate_limit,
                    llm_weight=self.llm_weight,
                )
                result["leaderboard"] = {
                    "snapshot_id": built["snapshot_id"],
                    "raw_items": built["raw_items"],
                    "events": built["events"],
                    "items": built["items"],
                    "llm_enabled": built.get("llm_enabled", False),
                    "llm_scores": built.get("llm_scores", 0),
                }
                export_dir = self.runtime_dir / "exports"
                export_json(built["leaderboard"], export_dir / "leaderboard.json")
                export_markdown(built["leaderboard"], export_dir / "leaderboard.md")
            self.last_cycle_at = datetime.now(timezone.utc).isoformat()
            self.last_cycle_result = result
            self.last_error = ""
            return result

    def status(self) -> dict:
        """服务状态。"""
        data = self.orchestrator.status()
        data.update(
            {
                "service": {
                    "registered_workers": self.registered_workers,
                    "include_github": self.include_github,
                    "poll_seconds": self.poll_seconds,
                    "max_workers": self.max_workers,
                    "leaderboard_limit": self.leaderboard_limit,
                    "leaderboard_top": self.leaderboard_top,
                    "llm_enabled": self.llm_enabled,
                    "llm_candidate_limit": self.llm_candidate_limit,
                    "llm_weight": self.llm_weight,
                    "llm_scores_count": self.storage.count_llm_event_scores(),
                    "last_cycle_at": self.last_cycle_at,
                    "last_cycle_result": self.last_cycle_result,
                    "last_error": self.last_error,
                    "runtime_dir": str(self.runtime_dir),
                    "config_dir": str(self.config_dir),
                }
            }
        )
        return data

    def leaderboard(self) -> dict:
        """读取当前导出的榜单；如果不存在则重建。"""
        path = self.runtime_dir / "exports" / "leaderboard.json"
        if not path.exists():
            built = rebuild_and_persist_leaderboard(
                self.storage,
                limit=self.leaderboard_limit,
                top=self.leaderboard_top,
                trigger="service-read",
                llm_enabled=self.llm_enabled,
                llm_candidate_limit=self.llm_candidate_limit,
                llm_weight=self.llm_weight,
            )
            return {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "items_count": built["items"],
                "items": [x.model_dump(mode="json") for x in built["leaderboard"]],
            }
        return json.loads(path.read_text(encoding="utf-8"))


def make_handler(runtime: TechRadarRuntime):
    class Handler(BaseHTTPRequestHandler):
        server_version = "TechRadar/0.1"

        def _json(self, data: dict, status: int = 200) -> None:
            raw = json.dumps(data, ensure_ascii=False, indent=2, default=str).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def _html(self, html: str, status: int = 200) -> None:
            raw = html.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def _bytes(
            self,
            raw: bytes,
            content_type: str,
            status: int = 200,
            cache_control: str | None = None,
        ) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(raw)))
            if cache_control:
                self.send_header("Cache-Control", cache_control)
            self.end_headers()
            self.wfile.write(raw)

        def _frontend(self) -> None:
            index_path = WEB_DIR / "index.html"
            if not index_path.exists():
                return self._html(render_index(runtime))
            raw = index_path.read_bytes()
            return self._bytes(raw, "text/html; charset=utf-8", cache_control="no-store")

        def _static_file(self, request_path: str) -> None:
            rel = request_path.removeprefix("/web/").lstrip("/")
            root = WEB_DIR.resolve()
            target = (WEB_DIR / rel).resolve()
            if root not in target.parents and target != root:
                return self._json({"ok": False, "error": "not found"}, status=404)
            if not target.exists() or not target.is_file():
                return self._json({"ok": False, "error": "not found"}, status=404)
            content_type = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
            if target.suffix == ".js":
                content_type = "application/javascript; charset=utf-8"
            elif target.suffix == ".css":
                content_type = "text/css; charset=utf-8"
            elif target.suffix in {".svg", ".html"}:
                content_type = f"{content_type}; charset=utf-8"
            raw = target.read_bytes()
            cache_control = "no-store" if target.suffix in {".js", ".css", ".html"} else None
            return self._bytes(raw, content_type, cache_control=cache_control)

        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            path = parsed.path.rstrip("/") or "/"
            qs = parse_qs(parsed.query)
            try:
                if path in FRONTEND_ROUTES:
                    return self._frontend()
                if path.startswith("/web/"):
                    return self._static_file(path)
                if path == "/health":
                    return self._json({"ok": True, "time": datetime.now(timezone.utc).isoformat()})
                if path == "/api/status":
                    return self._json(runtime.status())
                if path == "/api/leaderboard":
                    return self._json(runtime.leaderboard())
                if path == "/api/raw":
                    limit = int(qs.get("limit", ["50"])[0])
                    items = runtime.storage.load_raw_items(limit=limit)
                    return self._json(
                        {
                            "items_count": len(items),
                            "items": [x.model_dump(mode="json") for x in items],
                        }
                    )
                return self._json({"ok": False, "error": "not found"}, status=404)
            except Exception as exc:
                return self._json({"ok": False, "error": f"{type(exc).__name__}: {exc}"}, status=500)

        def do_POST(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            path = parsed.path.rstrip("/") or "/"
            try:
                if path == "/api/run-once":
                    return self._json(runtime.run_cycle())
                return self._json({"ok": False, "error": "not found"}, status=404)
            except Exception as exc:
                return self._json({"ok": False, "error": f"{type(exc).__name__}: {exc}"}, status=500)

        def log_message(self, fmt: str, *args) -> None:
            # 保持日志简洁，避免过多请求日志刷屏。
            print(f"[{datetime.now().isoformat(timespec='seconds')}] {self.address_string()} {fmt % args}")

    return Handler


def render_index(runtime: TechRadarRuntime) -> str:
    status = runtime.status()
    leaderboard = runtime.leaderboard()
    items = leaderboard.get("items", [])
    rows = "\n".join(
        f"""
        <article class="item">
          <div class="rank">#{x.get('rank')}</div>
          <div>
            <h2><a href="{x.get('url')}" target="_blank" rel="noreferrer">{escape_html(x.get('title',''))}</a></h2>
            <p class="meta">score {x.get('score')} · sources {x.get('source_count')} · {escape_html(x.get('reason',''))}</p>
            <p class="topics">{escape_html(', '.join(x.get('topics', [])))}</p>
          </div>
        </article>
        """
        for x in items[:50]
    )
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <meta http-equiv="refresh" content="120" />
  <title>Tech Radar</title>
  <style>
    body {{ margin: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: #0b1020; color: #e5e7eb; }}
    header {{ padding: 28px 36px; border-bottom: 1px solid #24304a; background: linear-gradient(135deg, #111827, #172554); }}
    h1 {{ margin: 0 0 8px; font-size: 30px; }}
    .sub {{ color: #a5b4fc; }}
    main {{ max-width: 1080px; margin: 0 auto; padding: 28px; }}
    .cards {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 14px; margin-bottom: 24px; }}
    .card, .item {{ background: rgba(15,23,42,.88); border: 1px solid #25314f; border-radius: 16px; box-shadow: 0 12px 40px rgba(0,0,0,.25); }}
    .card {{ padding: 16px; }}
    .num {{ font-size: 24px; font-weight: 700; color: #93c5fd; }}
    .item {{ display: grid; grid-template-columns: 72px 1fr; gap: 16px; padding: 18px; margin-bottom: 14px; }}
    .rank {{ font-size: 24px; font-weight: 800; color: #38bdf8; }}
    h2 {{ margin: 0 0 8px; font-size: 18px; line-height: 1.35; }}
    a {{ color: #f8fafc; text-decoration: none; }}
    a:hover {{ color: #7dd3fc; }}
    .meta {{ margin: 0 0 6px; color: #cbd5e1; }}
    .topics {{ margin: 0; color: #93c5fd; font-size: 13px; }}
    .links a {{ color: #93c5fd; margin-right: 14px; }}
  </style>
</head>
<body>
  <header>
    <h1>Tech Radar</h1>
    <div class="sub">RSS + Reddit 科技新闻榜 · GitHub 当前已按要求禁用 · 自动刷新</div>
  </header>
  <main>
    <section class="cards">
      <div class="card"><div class="num">{status.get('raw_items_count')}</div><div>RawItem</div></div>
      <div class="card"><div class="num">{status.get('news_events_count')}</div><div>NewsEvent</div></div>
      <div class="card"><div class="num">{status.get('workers_enabled')}</div><div>Workers</div></div>
      <div class="card"><div class="num">{len(items)}</div><div>Leaderboard</div></div>
    </section>
    <p class="links"><a href="/api/status">/api/status</a><a href="/api/leaderboard">/api/leaderboard</a><a href="/api/raw">/api/raw</a></p>
    {rows}
  </main>
</body>
</html>"""


def escape_html(value: str) -> str:
    return (
        str(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def serve(
    *,
    host: str,
    port: int,
    runtime_dir: str | Path,
    config_dir: str | Path,
    include_github: bool = False,
    poll_seconds: int = 300,
    max_workers: int = 5,
    leaderboard_limit: int = 500,
    leaderboard_top: int = 50,
    llm_enabled: bool = False,
    llm_candidate_limit: int = 80,
    llm_weight: float = 0.3,
) -> None:
    runtime = TechRadarRuntime(
        runtime_dir=runtime_dir,
        config_dir=config_dir,
        include_github=include_github,
        poll_seconds=poll_seconds,
        max_workers=max_workers,
        leaderboard_limit=leaderboard_limit,
        leaderboard_top=leaderboard_top,
        llm_enabled=llm_enabled,
        llm_candidate_limit=llm_candidate_limit,
        llm_weight=llm_weight,
    )
    runtime.start_background_loop()
    server = ThreadingHTTPServer((host, int(port)), make_handler(runtime))
    print(f"Tech Radar service listening on http://{host}:{port}")
    print(f"runtime_dir={runtime.runtime_dir} config_dir={runtime.config_dir} include_github={include_github}")
    try:
        server.serve_forever()
    finally:
        runtime.stop_event.set()
        server.server_close()
