#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RUN_DIR = PROJECT_ROOT / ".run"
PID_FILE = RUN_DIR / "web_app.pid"
META_FILE = RUN_DIR / "web_app.meta.json"
LOG_FILE = RUN_DIR / "web_app.log"


def _ensure_run_dir() -> None:
    RUN_DIR.mkdir(parents=True, exist_ok=True)


def _read_pid() -> int | None:
    try:
        return int(PID_FILE.read_text(encoding="utf-8").strip())
    except Exception:
        return None


def _write_pid(pid: int) -> None:
    _ensure_run_dir()
    PID_FILE.write_text(str(pid), encoding="utf-8")


def _remove_pid() -> None:
    try:
        PID_FILE.unlink()
    except FileNotFoundError:
        pass


def _read_meta() -> dict[str, Any]:
    try:
        return json.loads(META_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _write_meta(meta: dict[str, Any]) -> None:
    _ensure_run_dir()
    META_FILE.write_text(json.dumps(meta, indent=2), encoding="utf-8")


def _remove_meta() -> None:
    try:
        META_FILE.unlink()
    except FileNotFoundError:
        pass


def _pid_alive(pid: int | None) -> bool:
    if not pid or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _clear_stale_pid() -> None:
    pid = _read_pid()
    if pid and not _pid_alive(pid):
        _remove_pid()
        _remove_meta()


def _health_url(host: str, port: int) -> str:
    check_host = "127.0.0.1" if host in {"0.0.0.0", "::"} else host
    return f"http://{check_host}:{port}/healthz"


def _wait_for_health(host: str, port: int, timeout_s: int = 20) -> tuple[bool, str | None]:
    url = _health_url(host, port)
    deadline = time.time() + timeout_s
    last_err: str | None = None
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as r:
                body = r.read().decode("utf-8", errors="replace")
                if 200 <= r.status < 300:
                    return True, body
                last_err = f"HTTP {r.status}: {body[:200]}"
        except Exception as exc:
            last_err = str(exc)
        time.sleep(0.5)
    return False, last_err


def _preferred_ffmpeg_full_bin() -> str | None:
    for p in (Path("/opt/homebrew/opt/ffmpeg-full/bin"), Path("/usr/local/opt/ffmpeg-full/bin")):
        if p.exists():
            return str(p)
    return None


def cmd_start(args: argparse.Namespace) -> int:
    _clear_stale_pid()
    pid = _read_pid()
    if _pid_alive(pid):
        meta = _read_meta()
        url = f"http://{meta.get('host', '127.0.0.1')}:{meta.get('port', 8000)}"
        print(f"Already running (PID {pid}) -> {url}")
        print(f"Log: {LOG_FILE}")
        return 0

    _ensure_run_dir()
    host = args.host
    port = args.port
    env = os.environ.copy()
    env["TV_WEB_HOST"] = host
    env["PORT"] = str(port)
    ffmpeg_full_bin = _preferred_ffmpeg_full_bin()
    if ffmpeg_full_bin:
        env["PATH"] = ffmpeg_full_bin + os.pathsep + env.get("PATH", "")

    if args.foreground:
        print(f"Starting in foreground at http://{host}:{port}")
        return subprocess.call([sys.executable, str(PROJECT_ROOT / "web_app.py")], cwd=str(PROJECT_ROOT), env=env)

    log_fh = LOG_FILE.open("a", encoding="utf-8")
    log_fh.write(f"\n=== start {time.strftime('%Y-%m-%d %H:%M:%S')} ===\n")
    log_fh.flush()
    try:
        proc = subprocess.Popen(
            [sys.executable, str(PROJECT_ROOT / "web_app.py")],
            cwd=str(PROJECT_ROOT),
            env=env,
            stdout=log_fh,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
            close_fds=True,
        )
    except Exception:
        log_fh.close()
        raise

    _write_pid(proc.pid)
    _write_meta({"pid": proc.pid, "host": host, "port": port, "started_at": int(time.time())})

    ok, detail = _wait_for_health(host, port, timeout_s=args.wait)
    if ok:
        print(f"Started TradeVera local web UI")
        print(f"URL: http://{host}:{port}")
        print(f"Health: {_health_url(host, port)}")
        print(f"PID: {proc.pid}")
        print(f"Log: {LOG_FILE}")
        if detail:
            print(f"Health payload: {detail}")
        return 0

    if _pid_alive(proc.pid):
        print(f"Server process started (PID {proc.pid}) but health check did not pass in time.")
        print(f"Log: {LOG_FILE}")
        if detail:
            print(f"Last health error: {detail}")
        return 1

    print("Server failed to start.")
    print(f"Log: {LOG_FILE}")
    if detail:
        print(f"Last health error: {detail}")
    _remove_pid()
    _remove_meta()
    return 1


def cmd_stop(args: argparse.Namespace) -> int:
    _clear_stale_pid()
    pid = _read_pid()
    if not pid:
        print("TradeVera local web UI is not running.")
        return 0

    if not _pid_alive(pid):
        _remove_pid()
        _remove_meta()
        print("Stale PID file removed. Server not running.")
        return 0

    sig = signal.SIGTERM
    try:
        os.kill(pid, sig)
    except OSError as exc:
        _remove_pid()
        _remove_meta()
        print(f"Failed to signal process {pid}: {exc}")
        return 1

    deadline = time.time() + args.wait
    while time.time() < deadline:
        if not _pid_alive(pid):
            _remove_pid()
            _remove_meta()
            print(f"Stopped (PID {pid}).")
            return 0
        time.sleep(0.25)

    if args.force and _pid_alive(pid):
        try:
            os.kill(pid, signal.SIGKILL)
        except OSError:
            pass
        time.sleep(0.2)
    if not _pid_alive(pid):
        _remove_pid()
        _remove_meta()
        print(f"Stopped (PID {pid}).")
        return 0

    print(f"Process {pid} is still running. Try again or inspect {LOG_FILE}")
    return 1


def cmd_status(args: argparse.Namespace) -> int:
    _clear_stale_pid()
    pid = _read_pid()
    meta = _read_meta()
    if pid and _pid_alive(pid):
        host = str(meta.get("host") or "127.0.0.1")
        port = int(meta.get("port") or 8000)
        ok, _ = _wait_for_health(host, port, timeout_s=2)
        print(f"running pid={pid} url=http://{host}:{port} health={'ok' if ok else 'fail'}")
        print(f"log={LOG_FILE}")
        return 0
    print("stopped")
    return 1


def cmd_logs(args: argparse.Namespace) -> int:
    if not LOG_FILE.exists():
        print(f"No log file yet: {LOG_FILE}")
        return 1
    text = LOG_FILE.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    tail = lines[-args.lines :] if args.lines > 0 else lines
    print("\n".join(tail))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Manage local TradeVera Reels Factory web UI")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("start", help="Start local web UI")
    s.add_argument("--host", default="127.0.0.1", help="Bind host (default: 127.0.0.1)")
    s.add_argument("--port", type=int, default=8000, help="Port (default: 8000)")
    s.add_argument("--wait", type=int, default=20, help="Health-check wait timeout in seconds")
    s.add_argument("--foreground", action="store_true", help="Run in foreground instead of daemon mode")
    s.set_defaults(func=cmd_start)

    t = sub.add_parser("stop", help="Stop local web UI")
    t.add_argument("--wait", type=int, default=8, help="Graceful stop timeout in seconds")
    t.add_argument("--force", action="store_true", help="Force kill if graceful stop fails")
    t.set_defaults(func=cmd_stop)

    st = sub.add_parser("status", help="Show status")
    st.set_defaults(func=cmd_status)

    lg = sub.add_parser("logs", help="Show recent logs")
    lg.add_argument("--lines", type=int, default=60, help="Tail line count")
    lg.set_defaults(func=cmd_logs)

    return p


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
