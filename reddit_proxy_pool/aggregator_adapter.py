from __future__ import annotations

import os
import re
import sys
import types
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from .config import PoolConfig
from .util import mask_url


def _install_urlvalidator_shim() -> None:
    """aggregator 依赖 urlvalidator；本机 pip 安装曾卡住，MVP 内置最小兼容 shim。"""
    if "urlvalidator" in sys.modules:
        return
    module = types.ModuleType("urlvalidator")
    module.isurl = lambda url: bool(re.match(r"^https?://[^\s]+$", str(url or ""), re.I))
    sys.modules["urlvalidator"] = module


def _prepare_aggregator(cfg: PoolConfig) -> tuple[Any, Any, Any]:
    home = cfg.aggregator_home
    if not home.exists():
        raise FileNotFoundError(f"aggregator_home 不存在：{home}")
    subscribe_dir = home / "subscribe"
    if not subscribe_dir.exists():
        raise FileNotFoundError(f"aggregator subscribe 目录不存在：{subscribe_dir}")

    _install_urlvalidator_shim()
    if str(subscribe_dir) not in sys.path:
        sys.path.insert(0, str(subscribe_dir))

    cwd = os.getcwd()
    os.chdir(str(home))
    try:
        from airport import AirPort  # type: ignore
        import executable  # type: ignore
        from clash import QuotedStr, quoted_scalar  # type: ignore
    finally:
        os.chdir(cwd)
    return AirPort, executable, (QuotedStr, quoted_scalar)


def _ascii_safe_url(url: str) -> str:
    """把包含中文路径等非 ASCII 字符的订阅 URL 转为 urllib 可请求的形式。"""
    parts = urllib.parse.urlsplit(url)
    netloc = parts.netloc.encode("idna").decode("ascii") if parts.netloc else ""
    path = urllib.parse.quote(parts.path, safe="/%:@!$&'()*+,;=-._~")
    query = urllib.parse.quote(parts.query, safe="=&%:@/?!$'()*+,;.-_~")
    fragment = urllib.parse.quote(parts.fragment, safe="=&%:@/?!$'()*+,;.-_~")
    return urllib.parse.urlunsplit((parts.scheme, netloc, path, query, fragment))


def _cleanup_subconverter_artifacts(cfg: PoolConfig, artifact: str | None = None) -> None:
    """清理 aggregator/subconverter 的临时转换文件，避免 generate.ini 累积重复 section。"""
    sub_dir = (cfg.aggregator_home / "subconverter").resolve()
    if not sub_dir.exists() or not sub_dir.is_dir():
        return

    targets = [sub_dir / "generate.ini"]
    if artifact:
        targets.extend([sub_dir / f"{artifact}.txt", sub_dir / f"{artifact}.yaml"])

    for target in targets:
        try:
            resolved = target.resolve()
            if sub_dir == resolved.parent and resolved.exists():
                resolved.unlink()
        except OSError:
            # 临时文件清理失败不应阻断源解析；后续异常会进入 report。
            pass


def fetch_subscription(url: str, timeout: int = 45) -> str:
    req = urllib.request.Request(_ascii_safe_url(url), headers={"User-Agent": "Mozilla/5.0 reddit-proxy-pool/0.1"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        content = resp.read()
    return content.decode("utf-8", errors="ignore")


def parse_sources(cfg: PoolConfig, sources: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    AirPort, executable, _ = _prepare_aggregator(cfg)
    _, subconverter_bin = executable.which_bin()

    nodes: list[dict[str, Any]] = []
    reports: list[dict[str, Any]] = []
    cwd = os.getcwd()
    os.chdir(str(cfg.aggregator_home))
    try:
        for source in sorted(sources, key=lambda x: int(x.get("priority", 0)), reverse=True):
            source_id = str(source.get("id") or source.get("name") or "unknown")
            url = str(source.get("url") or "")
            report = {"source_id": source_id, "url": mask_url(url), "ok": False, "nodes": 0, "error": ""}
            if not url:
                report["error"] = "missing url"
                reports.append(report)
                continue
            try:
                text = fetch_subscription(url)
                artifact = re.sub(r"[^a-zA-Z0-9_-]+", "_", source_id)[:48] or "source"
                _cleanup_subconverter_artifacts(cfg, artifact)
                parsed = AirPort.decode(
                    text=text,
                    program=subconverter_bin,
                    artifact=f"reddit_pool_{artifact}",
                    special=True,
                    throw=False,
                )
                _cleanup_subconverter_artifacts(cfg, artifact)
                for node in parsed:
                    if isinstance(node, dict):
                        item = dict(node)
                        item["_source_id"] = source_id
                        nodes.append(item)
                report["ok"] = True
                report["nodes"] = len(parsed)
            except Exception as exc:
                _cleanup_subconverter_artifacts(cfg, re.sub(r"[^a-zA-Z0-9_-]+", "_", source_id)[:48] or "source")
                report["error"] = f"{type(exc).__name__}: {exc}"
            reports.append(report)
    finally:
        os.chdir(cwd)
    return nodes, reports


def get_yaml_representer(cfg: PoolConfig):
    _, _, pair = _prepare_aggregator(cfg)
    return pair
