from __future__ import annotations

import os
import signal
import socket
import subprocess
import sys
import time
import json
import urllib.request
from pathlib import Path

from .config import PoolConfig


def _is_windows() -> bool:
    return os.name == "nt"


def port_open(host: str, port: int, timeout: float = 1.0) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(timeout)
        return sock.connect_ex((host, port)) == 0


def controller_host_port(cfg: PoolConfig) -> tuple[str, int]:
    host, port = cfg.external_controller.rsplit(":", 1)
    return host, int(port)


def mihomo_binary(cfg: PoolConfig) -> Path:
    exe = "clash-windows-amd.exe" if _is_windows() else "clash-linux-amd"
    path = cfg.aggregator_home / "clash" / exe
    if not path.exists():
        raise FileNotFoundError(f"找不到 Mihomo/Clash 可执行文件：{path}")
    return path


def read_pid(cfg: PoolConfig) -> int | None:
    try:
        if cfg.pid_file.exists():
            return int(cfg.pid_file.read_text(encoding="utf-8").strip())
    except Exception:
        return None
    return None


def is_process_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if _is_windows():
        try:
            result = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                timeout=5,
            )
            return str(pid) in result.stdout
        except Exception:
            return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False
    except Exception:
        return False


def start(cfg: PoolConfig, wait_seconds: int = 8) -> int:
    if not cfg.config_file.exists():
        raise FileNotFoundError(f"配置文件不存在，请先 update：{cfg.config_file}")
    if port_open("127.0.0.1", cfg.mixed_port):
        raise RuntimeError(f"端口 {cfg.mixed_port} 已被占用，拒绝启动")
    chost, cport = controller_host_port(cfg)
    if port_open(chost, cport):
        raise RuntimeError(f"控制端口 {cfg.external_controller} 已被占用，拒绝启动")

    binpath = mihomo_binary(cfg)
    workspace = cfg.aggregator_home / "clash"
    log_file = cfg.logs_dir / "mihomo-runtime.log"
    stdout = log_file.open("ab")

    creationflags = 0
    if _is_windows():
        creationflags = (
            getattr(subprocess, "CREATE_NO_WINDOW", 0)
            | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
            | 0x00000008  # DETACHED_PROCESS
        )

    proc = subprocess.Popen(
        [str(binpath), "-d", str(workspace), "-f", str(cfg.config_file)],
        stdout=stdout,
        stderr=subprocess.STDOUT,
        creationflags=creationflags,
        close_fds=True,
    )
    cfg.pid_file.write_text(str(proc.pid), encoding="utf-8")

    deadline = time.time() + wait_seconds
    while time.time() < deadline:
        if port_open("127.0.0.1", cfg.mixed_port) and port_open(chost, cport):
            return proc.pid
        if proc.poll() is not None:
            raise RuntimeError(f"Mihomo 启动后立即退出，退出码：{proc.returncode}，查看日志：{log_file}")
        time.sleep(0.5)
    return proc.pid


def stop(cfg: PoolConfig) -> bool:
    pid = read_pid(cfg)
    if not pid:
        return False
    try:
        if _is_windows():
            subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            os.kill(pid, signal.SIGTERM)
        cfg.pid_file.unlink(missing_ok=True)
        return True
    except Exception:
        return False


def status(cfg: PoolConfig) -> dict[str, object]:
    pid = read_pid(cfg)
    chost, cport = controller_host_port(cfg)
    return {
        "pid": pid,
        "process_alive": bool(pid and is_process_alive(pid)),
        "mixed_port_open": port_open("127.0.0.1", cfg.mixed_port),
        "controller_open": port_open(chost, cport),
        "config_file": str(cfg.config_file),
    }


def controller_get(cfg: PoolConfig, path: str, timeout: int = 5) -> str:
    url = f"http://{cfg.external_controller}{path}"
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="ignore")


def controller_put(cfg: PoolConfig, path: str, payload: dict[str, object], timeout: int = 5) -> str:
    url = f"http://{cfg.external_controller}{path}"
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="PUT", headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="ignore")
