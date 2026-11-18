"""Google Colab CLI + OpenSSH port-forward lifecycle manager for desktop execution."""
from __future__ import annotations

import hashlib
import logging
import os
from pathlib import Path
import re
import secrets
import shutil
import socket
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
from typing import Any, Callable, Optional

from .colab_client import ColabClient

logger = logging.getLogger(__name__)

DEFAULT_SESSION_NAME = "rtmlib-worker"
SUPPORTED_GPUS: tuple[str, ...] = ("T4", "L4", "A100", "G4", "H100")
HIGH_MEM_UNSUPPORTED_GPUS: frozenset[str] = frozenset({"L4"})
REMOTE_APP_PORT = 8000
REMOTE_REPO_DIR = "/content/rtmlib-pose-estimation"
REMOTE_BUNDLE_PATH = "/content/rtmlib_src.tar.gz"
REMOTE_DRIVE_CACHE_DIR = "/content/drive/MyDrive/rtmlib_pose_cache"
REMOTE_LOCAL_CACHE_DIR = "/content/.cache"

_AUTH_URL_RE = re.compile(r"https://accounts\.google\.com/o/oauth2/auth\S+")
_SESSION_LINE_RE = re.compile(
    r"^\[(?P<name>[^\]]+)\]\s+(?P<endpoint>\S+)\s+\|\s+Hardware:\s+(?P<hw>[^|]+?)\s*\|\s+Shape:\s+(?P<shape>[^|\r\n]+)"
)
_BALANCE_RE = re.compile(r"Current balance:\s*([0-9.]+)\s+compute units", re.IGNORECASE)
_RATE_RE = re.compile(r"Usage rate:\s*([0-9.]+)/hr", re.IGNORECASE)
_ASSIGNMENTS_RE = re.compile(r"Active assignments:\s*(\d+)", re.IGNORECASE)


class ColabCliError(RuntimeError):
    """Structured error carrying UI hints for Colab CLI operations."""

    def __init__(
        self,
        message: str,
        *,
        suggest_switch_to_t4: bool = False,
        code: str = "cli_error",
    ) -> None:
        super().__init__(message)
        self.suggest_switch_to_t4 = suggest_switch_to_t4
        self.code = code


def normalize_gpu_choice(gpu: str | None) -> str:
    candidate = str(gpu or "T4").strip().upper()
    return candidate if candidate in SUPPORTED_GPUS else "T4"


def effective_high_mem_for_gpu(gpu: str, requested_high_mem: bool) -> bool:
    return False if normalize_gpu_choice(gpu) in HIGH_MEM_UNSUPPORTED_GPUS else bool(requested_high_mem)


def parse_usage_output(text: str) -> dict[str, Any] | None:
    """Extracts compute-unit balance, burn rate, and assignment count from `colab usage` output."""
    if not text:
        return None
    bal_m = _BALANCE_RE.search(text)
    rate_m = _RATE_RE.search(text)
    assign_m = _ASSIGNMENTS_RE.search(text)
    if not (bal_m or rate_m or assign_m):
        return None
    return {
        "balance": float(bal_m.group(1)) if bal_m else None,
        "usage_rate": float(rate_m.group(1)) if rate_m else None,
        "active_assignments": int(assign_m.group(1)) if assign_m else None,
    }


def parse_sessions_output(text: str) -> list[dict[str, str]]:
    """Parses `colab sessions` lines into structured session records."""
    records: list[dict[str, str]] = []
    for raw_line in str(text or "").splitlines():
        line = raw_line.strip()
        m = _SESSION_LINE_RE.match(line)
        if not m:
            continue
        records.append(
            {
                "name": m.group("name").strip(),
                "endpoint": m.group("endpoint").strip(),
                "hardware": m.group("hw").strip().upper(),
                "shape": m.group("shape").strip(),
            }
        )
    return records


def collect_bundle_source_files(base_dir: Path) -> list[tuple[Path, str]]:
    """Collects minimal source files needed by the remote Colab worker."""
    root = Path(base_dir).resolve()
    items: list[tuple[Path, str]] = []
    for filename in ("gui.py", "reservation_queue.py"):
        fpath = root / filename
        if fpath.is_file():
            items.append((fpath, filename))

    for subdir in ("colab_server", "pose_estimators"):
        sdir = root / subdir
        if not sdir.is_dir():
            continue
        for file_path in sorted(sdir.rglob("*")):
            if not file_path.is_file():
                continue
            if "__pycache__" in file_path.parts or file_path.suffix == ".pyc":
                continue
            if file_path.suffix == ".py" or file_path.name == "requirements-colab.txt":
                rel = file_path.relative_to(root).as_posix()
                items.append((file_path, rel))

    items.sort(key=lambda pair: pair[1])
    return items


def build_source_bundle(base_dir: Path, dest_path: Path) -> str:
    """Packs minimal remote server source files into dest_path (.tar.gz) and returns SHA-256."""
    files = collect_bundle_source_files(base_dir)
    if not files:
        raise ColabCliError("Colab 転送用のサーバーソースファイルが見つかりません。")

    dest_path.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(dest_path, "w:gz") as tar:
        for src_path, arcname in files:
            tar.add(src_path, arcname=arcname, recursive=False)

    hasher = hashlib.sha256()
    with dest_path.open("rb") as f:
        while True:
            chunk = f.read(65536)
            if not chunk:
                break
            hasher.update(chunk)
    return hasher.hexdigest().lower()


def _allocate_free_local_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _subprocess_env() -> dict[str, str]:
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def _default_run_cmd(
    args: list[str],
    *,
    input_text: str | None = None,
    timeout: float = 60.0,
) -> subprocess.CompletedProcess[str]:
    kwargs: dict[str, Any] = {
        "capture_output": True,
        "text": True,
        "encoding": "utf-8",
        "errors": "replace",
        "timeout": timeout,
        "env": _subprocess_env(),
    }
    if input_text is None:
        kwargs["stdin"] = subprocess.DEVNULL
    else:
        kwargs["input"] = input_text
    if os.name == "nt" and hasattr(subprocess, "CREATE_NO_WINDOW"):
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    return subprocess.run(args, **kwargs)


def _default_popen(
    args: list[str],
    *,
    pipe_stdin: bool = False,
) -> subprocess.Popen[str]:
    kwargs: dict[str, Any] = {
        "stdin": subprocess.PIPE if pipe_stdin else subprocess.DEVNULL,
        "stdout": subprocess.PIPE,
        "stderr": subprocess.STDOUT,
        "text": True,
        "encoding": "utf-8",
        "errors": "replace",
        "env": _subprocess_env(),
    }
    if os.name == "nt" and hasattr(subprocess, "CREATE_NO_WINDOW"):
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    return subprocess.Popen(args, **kwargs)


class ColabCliLauncher:
    """Manages google-colab-cli runtime lifecycle, OpenSSH forwarding, setup, and idle auto-stop."""

    def __init__(
        self,
        base_dir: Path | str,
        *,
        session_name: str = DEFAULT_SESSION_NAME,
        is_busy_fn: Callable[[], bool] | None = None,
        on_status_change: Callable[[dict[str, Any]], None] | None = None,
        run_cmd: Callable[..., subprocess.CompletedProcess[str]] | None = None,
        popen_fn: Callable[..., subprocess.Popen[str]] | None = None,
        health_checker: Callable[[str, str, float], dict[str, Any]] | None = None,
        port_allocator: Callable[[], int] | None = None,
        home_dir: Path | None = None,
        idle_poll_interval_sec: float = 5.0,
    ) -> None:
        self.base_dir = Path(base_dir).resolve()
        self.session_name = session_name
        self._is_busy_fn = is_busy_fn or (lambda: False)
        self._on_status_change = on_status_change
        self._run_cmd = run_cmd or _default_run_cmd
        self._popen = popen_fn or _default_popen
        self._health_checker = health_checker or self._default_health_check
        self._port_allocator = port_allocator or _allocate_free_local_port
        self._home_dir = Path(home_dir) if home_dir is not None else Path.home()
        self._idle_poll_interval_sec = max(0.05, float(idle_poll_interval_sec))

        self._state_lock = threading.Lock()
        self._op_lock = threading.Lock()
        self._shutdown_event = threading.Event()

        # Live runtime state
        self._state = "stopped"
        self._gpu = "T4"
        self._high_mem = False
        self._use_drive_cache = False
        self._idle_timeout_minutes = 30
        self._last_active_at = time.monotonic()
        self._active_session_name: str | None = None
        self._local_port: int | None = None
        self._api_token = ""
        self._server_url = ""
        self._last_health: dict[str, Any] | None = None
        self._warnings: list[str] = []
        self._error: str | None = None
        self._suggest_switch_to_t4 = False
        self._status_message = "停止中（「解析開始」時に自動起動）"
        self._ssh_proc: subprocess.Popen[str] | None = None
        self._last_uploaded_bundle_sha = ""
        self._last_reqs_sha = ""

        # Interactive GUI OAuth state
        self._auth_lock = threading.Lock()
        self._auth_proc: subprocess.Popen[str] | None = None
        self._auth_output_lines: list[str] = []

        self._idle_thread = threading.Thread(
            target=self._idle_monitor_loop,
            daemon=True,
            name="ColabCliIdleMonitor",
        )
        self._idle_thread.start()

    @staticmethod
    def _default_health_check(server_url: str, api_token: str, timeout: float) -> dict[str, Any]:
        return ColabClient(server_url, api_token).check_health(timeout=timeout)

    def _find_executable(self, name: str) -> str:
        found = shutil.which(name)
        if found:
            return found
        candidates: list[Path] = []
        if name in ("colab", "uv"):
            ext = ".exe" if os.name == "nt" else ""
            candidates.append(self._home_dir / ".local" / "bin" / f"{name}{ext}")
            candidates.append(self._home_dir / "AppData" / "Roaming" / "uv" / "tools" / "google-colab-cli" / "Scripts" / f"{name}{ext}")
        elif name in ("ssh", "ssh-keygen") and os.name == "nt":
            sys_root = Path(os.environ.get("SystemRoot", r"C:\Windows"))
            candidates.append(sys_root / "System32" / "OpenSSH" / f"{name}.exe")
        for cand in candidates:
            if cand.is_file():
                return str(cand)
        return ""

    def _ssh_key_path(self) -> Path:
        return self._home_dir / ".ssh" / "id_ed25519"

    def _emit_status_change(self) -> None:
        if callable(self._on_status_change):
            try:
                self._on_status_change(self.get_status())
            except Exception:
                pass

    @property
    def is_running(self) -> bool:
        with self._state_lock:
            return self._state == "running" and bool(self._server_url) and bool(self._api_token)

    def update_preferences(
        self,
        *,
        gpu: str | None = None,
        high_mem: bool | None = None,
        use_drive_cache: bool | None = None,
        idle_timeout_minutes: int | None = None,
    ) -> None:
        with self._state_lock:
            if gpu is not None:
                self._gpu = normalize_gpu_choice(gpu)
            if high_mem is not None:
                self._high_mem = effective_high_mem_for_gpu(self._gpu, high_mem)
            else:
                self._high_mem = effective_high_mem_for_gpu(self._gpu, self._high_mem)
            if use_drive_cache is not None:
                self._use_drive_cache = bool(use_drive_cache)
            if idle_timeout_minutes is not None:
                self._idle_timeout_minutes = max(0, min(240, int(idle_timeout_minutes)))

    def mark_activity(self) -> None:
        """Resets idle countdown on real runtime activity (never called by get_status)."""
        with self._state_lock:
            self._last_active_at = time.monotonic()

    def get_status(self) -> dict[str, Any]:
        """Pure in-memory snapshot; intentionally does NOT update _last_active_at."""
        with self._state_lock:
            idle_remaining_sec: int | None = None
            if self._state == "running" and self._idle_timeout_minutes > 0:
                if self._is_busy_fn():
                    idle_remaining_sec = self._idle_timeout_minutes * 60
                else:
                    elapsed = max(0.0, time.monotonic() - self._last_active_at)
                    idle_remaining_sec = max(0, int(self._idle_timeout_minutes * 60 - elapsed))
            return {
                "state": self._state,
                "session_name": self._active_session_name or self.session_name,
                "gpu": self._gpu,
                "high_mem": self._high_mem,
                "use_drive_cache": self._use_drive_cache,
                "idle_timeout_minutes": self._idle_timeout_minutes,
                "idle_remaining_sec": idle_remaining_sec,
                "server_url": self._server_url,
                "last_health": dict(self._last_health) if isinstance(self._last_health, dict) else None,
                "warnings": list(self._warnings),
                "error": self._error,
                "suggest_switch_to_t4": self._suggest_switch_to_t4,
                "status_message": self._status_message,
            }

    # ---- Prerequisite Checks & GUI-Only Setup -------------------------------

    def check_prereqs(self) -> dict[str, Any]:
        colab_path = self._find_executable("colab")
        uv_path = self._find_executable("uv")
        ssh_path = self._find_executable("ssh")
        key_path = self._ssh_key_path()
        ssh_key_exists = key_path.is_file() and Path(f"{key_path}.pub").is_file()

        auth_ok = False
        usage_summary: dict[str, Any] | None = None
        error_msg = ""

        if colab_path:
            try:
                res = self._run_cmd([colab_path, "usage"], timeout=15.0)
                combined = f"{res.stdout or ''}\n{res.stderr or ''}"
                if res.returncode == 0 and ("Current balance:" in combined or "Usage rate:" in combined):
                    auth_ok = True
                    usage_summary = parse_usage_output(combined)
                elif "To authorize colab-cli" in combined or "authorization code" in combined:
                    auth_ok = False
                elif res.returncode != 0:
                    error_msg = combined.strip()[:300]
            except subprocess.TimeoutExpired:
                auth_ok = False
            except Exception as exc:
                error_msg = str(exc)

        ok = bool(colab_path and ssh_path and ssh_key_exists and auth_ok)
        return {
            "ok": ok,
            "colab_installed": bool(colab_path),
            "colab_path": colab_path,
            "uv_installed": bool(uv_path),
            "ssh_installed": bool(ssh_path),
            "ssh_key_exists": ssh_key_exists,
            "ssh_key_path": str(key_path),
            "auth_ok": auth_ok,
            "usage_summary": usage_summary,
            "error": error_msg,
        }

    def install_cli(self) -> dict[str, Any]:
        uv_path = self._find_executable("uv")
        if not uv_path:
            return {
                "ok": False,
                "message": "uv が見つかりません。PowerShell で uv を導入後「再確認」してください。",
                "prereqs": self.check_prereqs(),
            }
        try:
            res = self._run_cmd([uv_path, "tool", "install", "google-colab-cli"], timeout=180.0)
        except Exception as exc:
            return {
                "ok": False,
                "message": f"google-colab-cli のインストールに失敗しました: {exc}",
                "prereqs": self.check_prereqs(),
            }

        prereqs = self.check_prereqs()
        if res.returncode == 0 and prereqs["colab_installed"]:
            return {
                "ok": True,
                "message": "google-colab-cli のインストールが完了しました。",
                "prereqs": prereqs,
            }
        detail = (res.stderr or res.stdout or "").strip()[-400:]
        return {
            "ok": False,
            "message": f"google-colab-cli のインストールに失敗しました。\n{detail}".strip(),
            "prereqs": prereqs,
        }

    def generate_ssh_key(self) -> dict[str, Any]:
        keygen_path = self._find_executable("ssh-keygen")
        if not keygen_path:
            return {
                "ok": False,
                "message": "Windows の ssh-keygen が見つかりません（OpenSSH クライアントを有効化してください）。",
                "prereqs": self.check_prereqs(),
            }
        key_path = self._ssh_key_path()
        key_path.parent.mkdir(parents=True, exist_ok=True)
        if not (key_path.is_file() and Path(f"{key_path}.pub").is_file()):
            try:
                res = self._run_cmd(
                    [keygen_path, "-t", "ed25519", "-N", "", "-f", str(key_path)],
                    timeout=20.0,
                )
            except Exception as exc:
                return {
                    "ok": False,
                    "message": f"SSH 鍵の生成に失敗しました: {exc}",
                    "prereqs": self.check_prereqs(),
                }
            if res.returncode != 0:
                detail = (res.stderr or res.stdout or "").strip()
                return {
                    "ok": False,
                    "message": f"SSH 鍵の生成に失敗しました: {detail}",
                    "prereqs": self.check_prereqs(),
                }
        return {
            "ok": True,
            "message": "SSH 鍵 (id_ed25519) の準備が完了しました。",
            "prereqs": self.check_prereqs(),
        }

    def _close_auth_proc(self) -> None:
        with self._auth_lock:
            proc = self._auth_proc
            self._auth_proc = None
        if proc is not None and proc.poll() is None:
            try:
                proc.terminate()
                proc.wait(timeout=1.5)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass

    def start_auth_flow(self) -> dict[str, Any]:
        """Launches `colab usage` interactively to extract the Google OAuth URL for the modal."""
        colab_path = self._find_executable("colab")
        if not colab_path:
            return {"status": "error", "message": "colab CLI がインストールされていません。"}

        self._close_auth_proc()
        try:
            proc = self._popen([colab_path, "usage"], pipe_stdin=True)
        except Exception as exc:
            return {"status": "error", "message": f"認証プロセスの起動に失敗しました: {exc}"}

        lines: list[str] = []
        url_found = threading.Event()
        extracted_url: list[str] = [""]

        def _reader() -> None:
            if proc.stdout is None:
                return
            try:
                for line in proc.stdout:
                    lines.append(line)
                    m = _AUTH_URL_RE.search(line)
                    if m and not extracted_url[0]:
                        extracted_url[0] = m.group(0).strip()
                        url_found.set()
            except Exception:
                pass

        reader_thread = threading.Thread(target=_reader, daemon=True, name="ColabAuthReader")
        reader_thread.start()

        with self._auth_lock:
            self._auth_proc = proc
            self._auth_output_lines = lines

        deadline = time.monotonic() + 15.0
        while time.monotonic() < deadline:
            if url_found.is_set():
                return {
                    "status": "awaiting_code",
                    "auth_url": extracted_url[0],
                    "message": "表示された URL をブラウザで開いて許可し、取得した認証コードを貼り付けてください。",
                }
            if proc.poll() is not None:
                reader_thread.join(timeout=1.0)
                combined = "".join(lines)
                if proc.returncode == 0 and ("Current balance:" in combined or "Usage rate:" in combined):
                    self._close_auth_proc()
                    return {
                        "status": "already_authenticated",
                        "message": "すでに Google アカウントで認証済みです。",
                        "prereqs": self.check_prereqs(),
                    }
                self._close_auth_proc()
                return {
                    "status": "error",
                    "message": f"認証 URL の取得に失敗しました: {combined.strip()[-300:]}",
                }
            time.sleep(0.1)

        self._close_auth_proc()
        return {
            "status": "error",
            "message": "認証 URL の取得がタイムアウトしました。再度お試しください。",
        }

    def submit_auth_code(self, code: str) -> dict[str, Any]:
        """Forwards the pasted Google authorization code to the awaiting `colab usage` process."""
        cleaned = str(code or "").strip()
        if not cleaned:
            return {"ok": False, "message": "認証コードが空です。"}

        with self._auth_lock:
            proc = self._auth_proc
            lines = self._auth_output_lines

        if proc is None or proc.poll() is not None or proc.stdin is None:
            return {
                "ok": False,
                "message": "認証待ちのセッションがありません。「Google 認証を開始」からやり直してください。",
                "prereqs": self.check_prereqs(),
            }

        try:
            proc.stdin.write(cleaned + "\n")
            proc.stdin.flush()
            proc.stdin.close()
            rc = proc.wait(timeout=25.0)
        except subprocess.TimeoutExpired:
            self._close_auth_proc()
            return {
                "ok": False,
                "message": "認証コードの確認がタイムアウトしました。",
                "prereqs": self.check_prereqs(),
            }
        except Exception as exc:
            self._close_auth_proc()
            return {
                "ok": False,
                "message": f"認証コード送信に失敗しました: {exc}",
                "prereqs": self.check_prereqs(),
            }
        finally:
            with self._auth_lock:
                self._auth_proc = None

        prereqs = self.check_prereqs()
        if rc == 0 and prereqs["auth_ok"]:
            return {
                "ok": True,
                "message": "Google アカウント認証が完了しました。",
                "prereqs": prereqs,
            }
        detail = "".join(lines).strip()[-350:]
        return {
            "ok": False,
            "message": f"認証に失敗しました。コードを確認してやり直してください。\n{detail}".strip(),
            "prereqs": prereqs,
        }

    # ---- Session & Tunnel Lifecycle -----------------------------------------

    def _terminate_ssh_proc(self) -> None:
        with self._state_lock:
            proc = self._ssh_proc
            self._ssh_proc = None
        if proc is None:
            return
        if proc.poll() is None:
            try:
                proc.terminate()
                proc.wait(timeout=2.0)
            except Exception:
                try:
                    proc.kill()
                    proc.wait(timeout=1.0)
                except Exception:
                    pass

    def _inspect_sessions(self, colab_path: str) -> tuple[dict[str, str] | None, list[dict[str, str]]]:
        res = self._run_cmd([colab_path, "sessions"], timeout=20.0)
        if res.returncode != 0:
            return None, []
        combined = f"{res.stdout or ''}\n{res.stderr or ''}"
        sessions = parse_sessions_output(combined)
        local_match = next((s for s in sessions if s["name"] == self.session_name), None)
        foreign = [s for s in sessions if s["name"] == "?"]
        return local_match, foreign

    def _translate_new_session_error(self, output: str, gpu: str) -> ColabCliError:
        lower = output.lower()
        if "precondition failed" in lower or "allocation refused" in lower or "toomanyassignmentserror" in lower:
            return ColabCliError(
                f"GPU ({gpu}) の割り当てに失敗しました（同時セッション上限または一時的な空き枠不足）。"
                "Google Colab の別タブ／別 PC でセッションが残っていないか確認するか、T4 へ切り替えて再試行してください。",
                suggest_switch_to_t4=(gpu != "T4"),
                code="too_many_assignments",
            )
        if "rejected accelerator" in lower or "not have quota or entitlement" in lower:
            return ColabCliError(
                f"選択中のプラン・クォータでは GPU ({gpu}) を利用できないため拒否されました。T4 など利用可能な GPU に切り替えて再試行してください。",
                suggest_switch_to_t4=(gpu != "T4"),
                code="gpu_not_entitled",
            )
        return ColabCliError(f"Colab セッション作成に失敗しました: {output.strip()[-400:]}")

    def _build_ssh_tunnel_args(self, colab_path: str, ssh_path: str, local_port: int) -> list[str]:
        proxy_cmd = subprocess.list2cmdline(
            [colab_path, "ssh", "--proxy-mode", "-s", self.session_name]
        )
        return [
            ssh_path,
            "-N",
            "-T",
            "-L",
            f"{local_port}:127.0.0.1:{REMOTE_APP_PORT}",
            "-o",
            f"ProxyCommand={proxy_cmd}",
            "-o",
            "StrictHostKeyChecking=no",
            "-o",
            f"UserKnownHostsFile={os.devnull}",
            "-o",
            "ExitOnForwardFailure=yes",
            "-o",
            "ServerAliveInterval=30",
            "-o",
            "ServerAliveCountMax=3",
            "-i",
            str(self._ssh_key_path()),
            "root@colab-runtime",
        ]

    def _open_tunnel_and_wait_health(
        self,
        colab_path: str,
        ssh_path: str,
        api_token: str,
        *,
        cancel_event: threading.Event | None = None,
        timeout_sec: float = 20.0,
    ) -> tuple[int, dict[str, Any]]:
        self._terminate_ssh_proc()
        local_port = self._port_allocator()
        tunnel_args = self._build_ssh_tunnel_args(colab_path, ssh_path, local_port)
        proc = self._popen(tunnel_args, pipe_stdin=False)
        with self._state_lock:
            self._ssh_proc = proc

        target_url = f"http://127.0.0.1:{local_port}"
        deadline = time.monotonic() + timeout_sec
        last_err: Exception | None = None
        while time.monotonic() < deadline:
            if cancel_event is not None and cancel_event.is_set():
                self._terminate_ssh_proc()
                raise ColabCliError("Colab 接続が中断されました。", code="cancelled")
            if proc.poll() is not None:
                out = ""
                if proc.stdout is not None:
                    try:
                        out = proc.stdout.read()
                    except Exception:
                        pass
                self._terminate_ssh_proc()
                raise ColabCliError(
                    f"SSH トンネルが予期せず終了しました (code={proc.returncode}): {out.strip()[-300:]}",
                    code="tunnel_exited",
                )
            try:
                health = self._health_checker(target_url, api_token, 3.0)
                with self._state_lock:
                    self._local_port = local_port
                    self._server_url = target_url
                    self._last_health = dict(health)
                return local_port, health
            except Exception as exc:
                last_err = exc
                err_s = str(exc)
                if "401" in err_s or "403" in err_s:
                    raise ColabCliError(err_s, code="auth_mismatch") from exc
                time.sleep(0.5)

        raise ColabCliError(
            f"SSH トンネル経由の /health 応答待機がタイムアウトしました: {last_err}",
            code="health_timeout",
        )

    def _try_mount_drive(
        self,
        colab_path: str,
        use_drive_cache: bool,
        log_fn: Callable[[str], None] | None,
    ) -> tuple[bool, list[str]]:
        if not use_drive_cache:
            return False, []
        if log_fn:
            log_fn("[Colab SSH] Google Drive キャッシュ同期のためマウントを試行しています...\n")
        try:
            res = self._run_cmd([colab_path, "drivemount", "-s", self.session_name], timeout=45.0)
            combined = f"{res.stdout or ''}\n{res.stderr or ''}"
            if res.returncode == 0 and "credential propagation was unsuccessful" not in combined.lower():
                return True, []
            msg = "Google Drive のマウントに失敗したため、ローカルキャッシュ (/content/.cache) のみで続行します。"
            if log_fn:
                log_fn(f"[Colab SSH] 警告: {msg}\n")
            return False, [msg]
        except Exception:
            msg = "Google Drive のマウントがタイムアウト/失敗したため、ローカルキャッシュ (/content/.cache) のみで続行します。"
            if log_fn:
                log_fn(f"[Colab SSH] 警告: {msg}\n")
            return False, [msg]

    def _requirements_sha256(self) -> str:
        req_file = self.base_dir / "colab_server" / "requirements-colab.txt"
        if not req_file.is_file():
            return "none"
        return hashlib.sha256(req_file.read_bytes()).hexdigest().lower()

    def _build_remote_bootstrap_script(
        self,
        *,
        api_token: str,
        bundle_sha: str,
        reqs_sha: str,
        use_drive_cache: bool,
        remote_idle_sec: int,
        sync_code: bool,
    ) -> str:
        drive_dir = REMOTE_DRIVE_CACHE_DIR if use_drive_cache else ""
        return f"""
import os, shutil, socket, subprocess, sys, tarfile, time, urllib.request
from pathlib import Path

REPO_DIR = Path({REMOTE_REPO_DIR!r})
BUNDLE_PATH = Path({REMOTE_BUNDLE_PATH!r})
BUNDLE_SHA = {bundle_sha!r}
REQS_SHA = {reqs_sha!r}
API_TOKEN = {api_token!r}
DRIVE_DIR = {drive_dir!r}
LOCAL_CACHE = Path({REMOTE_LOCAL_CACHE_DIR!r})
REMOTE_IDLE_SEC = {int(remote_idle_sec)!r}
SYNC_CODE = {bool(sync_code)!r}

REPO_DIR.mkdir(parents=True, exist_ok=True)
sha_marker = REPO_DIR / ".bundle_sha256"
deps_marker = REPO_DIR / ".deps_reqs_sha256"

if SYNC_CODE and BUNDLE_PATH.is_file():
    with tarfile.open(BUNDLE_PATH, "r:gz") as tf:
        tf.extractall(REPO_DIR)
    sha_marker.write_text(BUNDLE_SHA, encoding="utf-8")

def _pip_install(args):
    try:
        subprocess.check_call(["uv", "pip", "install", "--system", *args])
    except Exception:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", *args])

if not deps_marker.is_file() or deps_marker.read_text(encoding="utf-8").strip() != REQS_SHA:
    _pip_install(["-r", str(REPO_DIR / "colab_server" / "requirements-colab.txt")])
    _pip_install(["--no-deps", "rtmlib==0.0.16"])
    deps_marker.write_text(REQS_SHA, encoding="utf-8")

os.environ["VITPOSE_ONNX_CACHE_DIR"] = str(LOCAL_CACHE / "vitpose_onnx")
os.environ["HF_HOME"] = str(LOCAL_CACHE / "huggingface")
os.environ["YOLO_CONFIG_DIR"] = str(LOCAL_CACHE / "ultralytics")
os.environ["TORCH_HOME"] = str(LOCAL_CACHE / "torch")
for env_key in ("VITPOSE_ONNX_CACHE_DIR", "HF_HOME", "YOLO_CONFIG_DIR", "TORCH_HOME"):
    Path(os.environ[env_key]).mkdir(parents=True, exist_ok=True)

if str(REPO_DIR) not in sys.path:
    sys.path.insert(0, str(REPO_DIR))

if DRIVE_DIR:
    try:
        Path(DRIVE_DIR).mkdir(parents=True, exist_ok=True)
        from colab_server.cache_sync import sync_drive_to_local
        sync_drive_to_local(DRIVE_DIR, LOCAL_CACHE)
    except Exception as exc:
        print(f"DRIVE_SYNC_WARN: {{exc}}")

subprocess.run(["pkill", "-f", r"colab_server\\.app|gui\\.py --persistent-worker"], check=False)
for _ in range(20):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        if s.connect_ex(("127.0.0.1", {REMOTE_APP_PORT})) != 0:
            break
    time.sleep(0.25)

child_env = os.environ.copy()
child_env["COLAB_API_TOKEN"] = API_TOKEN
child_env["COLAB_WORK_DIR"] = "/content/colab_work"
child_env["COLAB_LOCAL_CACHE_DIR"] = str(LOCAL_CACHE)
child_env["COLAB_DRIVE_CACHE_DIR"] = DRIVE_DIR
child_env["COLAB_REMOTE_IDLE_SHUTDOWN_SEC"] = str(REMOTE_IDLE_SEC)

with open("/tmp/colab_server.log", "wb") as log_file:
    proc = subprocess.Popen(
        [sys.executable, "-u", "-m", "colab_server.app"],
        cwd=str(REPO_DIR),
        stdin=subprocess.DEVNULL,
        stdout=log_file,
        stderr=subprocess.STDOUT,
        start_new_session=True,
        env=child_env,
    )

for _ in range(120):
    if proc.poll() is not None:
        tail = Path("/tmp/colab_server.log").read_text(encoding="utf-8", errors="replace")[-2000:]
        raise RuntimeError(f"colab_server exited early (code={{proc.returncode}}):\\n{{tail}}")
    try:
        req = urllib.request.Request(
            "http://127.0.0.1:{REMOTE_APP_PORT}/health",
            headers={{"Authorization": f"Bearer {{API_TOKEN}}"}},
        )
        with urllib.request.urlopen(req, timeout=2) as resp:
            if resp.status == 200:
                print("COLAB_SERVER_READY")
                break
    except Exception:
        time.sleep(0.5)
else:
    tail = Path("/tmp/colab_server.log").read_text(encoding="utf-8", errors="replace")[-2000:]
    raise RuntimeError(f"Timed out waiting for colab_server /health:\\n{{tail}}")
""".strip()

    def _push_code_and_start_remote_server(
        self,
        colab_path: str,
        *,
        api_token: str,
        use_drive_cache: bool,
        idle_timeout_minutes: int,
        force_upload: bool,
        log_fn: Callable[[str], None] | None,
    ) -> list[str]:
        warnings: list[str] = []
        effective_drive, drive_warnings = self._try_mount_drive(colab_path, use_drive_cache, log_fn)
        warnings.extend(drive_warnings)

        with tempfile.TemporaryDirectory(prefix="rtmlib_colab_bundle_") as tmpdir:
            bundle_path = Path(tmpdir) / "rtmlib_src.tar.gz"
            bundle_sha = build_source_bundle(self.base_dir, bundle_path)
            reqs_sha = self._requirements_sha256()
            need_upload = force_upload or (bundle_sha != self._last_uploaded_bundle_sha)
            if need_upload:
                if log_fn:
                    log_fn("[Colab SSH] サーバーコード最小バンドルをアップロードしています...\n")
                up_res = self._run_cmd(
                    [colab_path, "upload", "-s", self.session_name, str(bundle_path), REMOTE_BUNDLE_PATH],
                    timeout=120.0,
                )
                if up_res.returncode != 0:
                    detail = f"{up_res.stdout or ''}\n{up_res.stderr or ''}".strip()[-400:]
                    raise ColabCliError(f"ソースコードのアップロードに失敗しました: {detail}")

        remote_idle_sec = max(0, int(idle_timeout_minutes)) * 60
        if log_fn:
            log_fn("[Colab SSH] Colab VM 側で依存確認・推論サーバーを起動しています...\n")
        remote_script = self._build_remote_bootstrap_script(
            api_token=api_token,
            bundle_sha=bundle_sha,
            reqs_sha=reqs_sha,
            use_drive_cache=effective_drive,
            remote_idle_sec=remote_idle_sec,
            sync_code=need_upload,
        )
        exec_res = self._run_cmd(
            [colab_path, "exec", "-s", self.session_name],
            input_text=remote_script,
            timeout=360.0,
        )
        combined = f"{exec_res.stdout or ''}\n{exec_res.stderr or ''}"
        if exec_res.returncode != 0 or "COLAB_SERVER_READY" not in combined:
            raise ColabCliError(f"Colab サーバー起動に失敗しました:\n{combined.strip()[-1000:]}")

        self._last_uploaded_bundle_sha = bundle_sha
        self._last_reqs_sha = reqs_sha
        return warnings

    def ensure_started(
        self,
        *,
        gpu: str | None = None,
        high_mem: bool | None = None,
        use_drive_cache: bool | None = None,
        idle_timeout_minutes: int | None = None,
        log_fn: Callable[[str], None] | None = None,
        cancel_event: threading.Event | None = None,
    ) -> dict[str, Any]:
        """Ensures Colab runtime, remote FastAPI server, and SSH port-forward are ready."""
        self.update_preferences(
            gpu=gpu,
            high_mem=high_mem,
            use_drive_cache=use_drive_cache,
            idle_timeout_minutes=idle_timeout_minutes,
        )

        with self._op_lock:
            with self._state_lock:
                target_gpu = self._gpu
                target_high_mem = self._high_mem
                target_drive = self._use_drive_cache
                target_idle = self._idle_timeout_minutes
                existing_proc = self._ssh_proc
                existing_port = self._local_port
                existing_token = self._api_token
                existing_url = self._server_url

            # Fast path: tunnel alive & health responsive
            if (
                existing_proc is not None
                and existing_proc.poll() is None
                and existing_port is not None
                and existing_url
                and existing_token
            ):
                try:
                    health = self._health_checker(existing_url, existing_token, 4.0)
                    with self._state_lock:
                        self._state = "running"
                        self._last_health = dict(health)
                        self._error = None
                        self._suggest_switch_to_t4 = False
                        self._status_message = f"稼働中 ({target_gpu})"
                    self.mark_activity()
                    self._emit_status_change()
                    return {
                        "server_url": existing_url,
                        "api_token": existing_token,
                        "health": health,
                        "warnings": self.get_status()["warnings"],
                    }
                except Exception:
                    pass

            colab_path = self._find_executable("colab")
            ssh_path = self._find_executable("ssh")
            if not colab_path or not ssh_path or not self._ssh_key_path().is_file():
                msg = "Colab CLI または SSH 鍵が未準備です。「Colab 接続設定」から初期セットアップを行ってください。"
                with self._state_lock:
                    self._state = "error"
                    self._error = msg
                    self._status_message = "要セットアップ"
                self._emit_status_change()
                raise ColabCliError(msg, code="prereq_missing")

            with self._state_lock:
                self._state = "starting"
                self._error = None
                self._suggest_switch_to_t4 = False
                self._status_message = f"起動中 ({target_gpu})..."
            self._emit_status_change()

            warnings: list[str] = []
            try:
                local_session, foreign_sessions = self._inspect_sessions(colab_path)
                if foreign_sessions:
                    foreign_msg = (
                        f"別 PC（または別環境）で起動されたセッションが {len(foreign_sessions)} 件稼働中です。"
                        "同時セッション上限になる場合は Google Colab ブラウザ側の「ランタイム → セッションを管理」から終了してください。"
                    )
                    warnings.append(foreign_msg)
                    if log_fn:
                        log_fn(f"[Colab SSH] 警告: {foreign_msg}\n")

                reusable = False
                if local_session is not None:
                    shape_is_hm = local_session["shape"].strip().lower() == "high-ram"
                    if local_session["hardware"] == target_gpu and shape_is_hm == target_high_mem:
                        reusable = True
                    else:
                        if log_fn:
                            log_fn(
                                f"[Colab SSH] GPU構成変更のため既存セッション ({local_session['hardware']}) を停止して再作成します...\n"
                            )
                        self._terminate_ssh_proc()
                        self._run_cmd([colab_path, "stop", "-s", self.session_name], timeout=30.0)
                        self._last_uploaded_bundle_sha = ""

                if not self._api_token:
                    self._api_token = secrets.token_urlsafe(24)

                # Tier 1 / Tier 2 recovery when reusing existing VM
                if reusable:
                    if log_fn:
                        log_fn(f"[Colab SSH] 既存セッション '{self.session_name}' ({target_gpu}) を再利用して再接続します...\n")
                    try:
                        _, health = self._open_tunnel_and_wait_health(
                            colab_path,
                            ssh_path,
                            self._api_token,
                            cancel_event=cancel_event,
                            timeout_sec=12.0,
                        )
                        with self._state_lock:
                            self._state = "running"
                            self._active_session_name = self.session_name
                            self._warnings = list(warnings)
                            self._error = None
                            self._suggest_switch_to_t4 = False
                            self._status_message = f"稼働中 ({target_gpu})"
                        self.mark_activity()
                        self._emit_status_change()
                        return {
                            "server_url": self._server_url,
                            "api_token": self._api_token,
                            "health": health,
                            "warnings": list(warnings),
                        }
                    except ColabCliError as tier1_exc:
                        if log_fn:
                            log_fn(f"[Colab SSH] 既存トンネル再接続不可 ({tier1_exc.code})。同一VM上でサーバーを再起動します...\n")
                        self._terminate_ssh_proc()
                        try:
                            srv_warnings = self._push_code_and_start_remote_server(
                                colab_path,
                                api_token=self._api_token,
                                use_drive_cache=target_drive,
                                idle_timeout_minutes=target_idle,
                                force_upload=False,
                                log_fn=log_fn,
                            )
                            warnings.extend(srv_warnings)
                            _, health = self._open_tunnel_and_wait_health(
                                colab_path,
                                ssh_path,
                                self._api_token,
                                cancel_event=cancel_event,
                                timeout_sec=20.0,
                            )
                            with self._state_lock:
                                self._state = "running"
                                self._active_session_name = self.session_name
                                self._warnings = list(warnings)
                                self._error = None
                                self._suggest_switch_to_t4 = False
                                self._status_message = f"稼働中 ({target_gpu})"
                            self.mark_activity()
                            self._emit_status_change()
                            return {
                                "server_url": self._server_url,
                                "api_token": self._api_token,
                                "health": health,
                                "warnings": list(warnings),
                            }
                        except Exception as tier2_exc:
                            if log_fn:
                                log_fn(f"[Colab SSH] 既存セッション復旧失敗のため新規セッションを作成します: {tier2_exc}\n")
                            self._terminate_ssh_proc()
                            self._run_cmd([colab_path, "stop", "-s", self.session_name], timeout=30.0)
                            self._last_uploaded_bundle_sha = ""

                # Fresh VM creation
                if cancel_event is not None and cancel_event.is_set():
                    raise ColabCliError("Colab 起動を中断しました。", code="cancelled")

                if log_fn:
                    hm_label = " (High-RAM)" if target_high_mem else ""
                    log_fn(f"[Colab SSH] 新規 GPU ランタイム ({target_gpu}{hm_label}) を割り当てています...\n")

                new_args = [colab_path, "new", "-s", self.session_name, "--gpu", target_gpu]
                if target_high_mem:
                    new_args.append("--high-mem")
                new_res = self._run_cmd(new_args, timeout=120.0)
                if new_res.returncode != 0:
                    combined_new = f"{new_res.stdout or ''}\n{new_res.stderr or ''}"
                    raise self._translate_new_session_error(combined_new, target_gpu)

                with self._state_lock:
                    self._active_session_name = self.session_name

                self._api_token = secrets.token_urlsafe(24)
                srv_warnings = self._push_code_and_start_remote_server(
                    colab_path,
                    api_token=self._api_token,
                    use_drive_cache=target_drive,
                    idle_timeout_minutes=target_idle,
                    force_upload=True,
                    log_fn=log_fn,
                )
                warnings.extend(srv_warnings)

                if log_fn:
                    log_fn("[Colab SSH] OpenSSH ポート転送を確立しています...\n")
                _, health = self._open_tunnel_and_wait_health(
                    colab_path,
                    ssh_path,
                    self._api_token,
                    cancel_event=cancel_event,
                    timeout_sec=25.0,
                )

                with self._state_lock:
                    self._state = "running"
                    self._active_session_name = self.session_name
                    self._warnings = list(warnings)
                    self._error = None
                    self._suggest_switch_to_t4 = False
                    self._status_message = f"稼働中 ({target_gpu})"
                self.mark_activity()
                self._emit_status_change()
                return {
                    "server_url": self._server_url,
                    "api_token": self._api_token,
                    "health": health,
                    "warnings": list(warnings),
                }
            except ColabCliError as exc:
                self._terminate_ssh_proc()
                with self._state_lock:
                    self._state = "error"
                    self._error = str(exc)
                    self._warnings = list(warnings)
                    self._suggest_switch_to_t4 = exc.suggest_switch_to_t4
                    self._status_message = "エラー"
                self._emit_status_change()
                raise
            except Exception as exc:
                self._terminate_ssh_proc()
                msg = str(exc)
                with self._state_lock:
                    self._state = "error"
                    self._error = msg
                    self._warnings = list(warnings)
                    self._suggest_switch_to_t4 = False
                    self._status_message = "エラー"
                self._emit_status_change()
                raise ColabCliError(msg) from exc

    def stop(self, *, reason: str = "manual") -> dict[str, Any]:
        """Stops the local SSH tunnel and releases the Colab backend session."""
        with self._op_lock:
            self._terminate_ssh_proc()
            colab_path = self._find_executable("colab")
            had_session = False
            with self._state_lock:
                had_session = (
                    self._state in ("running", "starting", "error")
                    or self._active_session_name is not None
                )
                self._state = "stopping"
                self._status_message = "停止処理中..."
            self._emit_status_change()

            if colab_path and had_session:
                try:
                    self._run_cmd([colab_path, "stop", "-s", self.session_name], timeout=30.0)
                except Exception as exc:
                    logger.warning("Failed to run `colab stop`: %s", exc)

            with self._state_lock:
                self._state = "stopped"
                self._active_session_name = None
                self._local_port = None
                self._server_url = ""
                self._api_token = ""
                self._last_health = None
                self._last_uploaded_bundle_sha = ""
                self._error = None
                self._suggest_switch_to_t4 = False
                if reason == "idle_timeout":
                    self._status_message = f"{self._idle_timeout_minutes}分間無操作のため自動停止しました"
                else:
                    self._status_message = "停止中（「解析開始」時に自動起動）"
            self._emit_status_change()
            return self.get_status()

    def _idle_monitor_loop(self) -> None:
        while not self._shutdown_event.wait(self._idle_poll_interval_sec):
            with self._state_lock:
                is_running = self._state == "running"
                timeout_min = self._idle_timeout_minutes
                last_active = self._last_active_at
            if not is_running or timeout_min <= 0:
                continue
            if self._is_busy_fn():
                self.mark_activity()
                continue
            if (time.monotonic() - last_active) >= timeout_min * 60.0:
                try:
                    self.stop(reason="idle_timeout")
                except Exception as exc:
                    logger.warning("Idle auto-stop failed: %s", exc)

    def shutdown(self) -> None:
        """Stops idle monitor, interactive auth process, SSH tunnel, and active Colab session."""
        self._shutdown_event.set()
        self._close_auth_proc()
        if self._idle_thread.is_alive() and threading.current_thread() != self._idle_thread:
            self._idle_thread.join(timeout=1.5)
        try:
            self.stop(reason="shutdown")
        except Exception as exc:
            logger.debug("Launcher shutdown cleanup warning: %s", exc)
