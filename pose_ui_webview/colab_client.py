"""HTTP / SSE client for communicating with the Google Colab FastAPI worker."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import tempfile
import threading
import time
from typing import Any, Callable
from urllib.parse import urlparse
import uuid
import zipfile

import requests


class ColabCancelledError(Exception):
    """Raised when a remote Colab transfer or execution is cancelled locally."""


def normalize_server_url(server_url: str) -> str:
    """Validate and normalize Colab server base URL (without trailing slash)."""
    raw = str(server_url or "").strip().rstrip("/")
    if not raw:
        raise ValueError("Colab サーバー URL が空です。")
    parsed = urlparse(raw)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ValueError(f"無効な URL 形式です（http:// または https:// で始めてください）: {server_url}")
    return raw


def compute_file_sha256(
    file_path: Path,
    cancel_event: threading.Event | None = None,
    chunk_size: int = 1024 * 1024,
) -> str:
    """Stream SHA-256 hex digest of a local video file with optional cooperative cancellation."""
    hasher = hashlib.sha256()
    with Path(file_path).open("rb") as f:
        while True:
            if cancel_event is not None and cancel_event.is_set():
                raise ColabCancelledError("SHA-256 計算中に中断されました。")
            block = f.read(chunk_size)
            if not block:
                break
            hasher.update(block)
    return hasher.hexdigest().lower()


class ColabClient:
    """Synchronous REST + SSE client for Google Colab worker endpoints."""

    def __init__(
        self,
        server_url: str,
        api_token: str,
        *,
        session: Any | None = None,
    ) -> None:
        self.base_url = normalize_server_url(server_url)
        self.api_token = str(api_token or "").strip()
        self._session = session if session is not None else requests.Session()

    def _headers(self) -> dict[str, str]:
        if not self.api_token:
            return {}
        return {"Authorization": f"Bearer {self.api_token}"}

    def _url(self, path: str) -> str:
        return f"{self.base_url}{path}"

    def check_health(self, timeout: float = 10.0) -> dict[str, Any]:
        started = time.perf_counter()
        resp = self._session.get(self._url("/health"), headers=self._headers(), timeout=timeout)
        resp.raise_for_status()
        data = dict(resp.json())
        data["latency_ms"] = round((time.perf_counter() - started) * 1000.0, 1)
        return data

    def ensure_video_uploaded(
        self,
        video_path: Path,
        *,
        cancel_event: threading.Event | None = None,
        log_cb: Callable[[str], None] | None = None,
        chunk_size: int = 8 * 1024 * 1024,
    ) -> tuple[str, bool]:
        """Ensure raw video exists on Colab by hash check, uploading chunks only if absent.

        Returns (sha256_hex, skipped_upload).
        """
        vpath = Path(video_path)
        size = vpath.stat().st_size
        sha256 = compute_file_sha256(vpath, cancel_event=cancel_event)

        check_resp = self._session.post(
            self._url("/videos/check"),
            headers=self._headers(),
            json={"sha256": sha256, "filename": vpath.name, "size": size},
            timeout=20.0,
        )
        check_resp.raise_for_status()
        if bool(check_resp.json().get("exists")):
            if log_cb:
                log_cb(f"Colab キャッシュヒット: 動画アップロードをスキップしました ({vpath.name})\n")
            return sha256, True

        total_chunks = max(1, (size + chunk_size - 1) // chunk_size)
        if log_cb:
            size_mb = size / (1024 * 1024)
            log_cb(f"Colab へ無劣化元動画を送信中: {vpath.name} ({size_mb:.2f} MB, {total_chunks} チャンク)\n")

        with vpath.open("rb") as f:
            for chunk_idx in range(total_chunks):
                if cancel_event is not None and cancel_event.is_set():
                    raise ColabCancelledError("動画アップロードを中断しました。")
                chunk_bytes = f.read(chunk_size)
                last_exc: Exception | None = None
                for attempt in range(3):
                    try:
                        up_resp = self._session.post(
                            self._url("/videos/upload"),
                            headers=self._headers(),
                            data={
                                "sha256": sha256,
                                "filename": vpath.name,
                                "chunk_index": str(chunk_idx),
                                "total_chunks": str(total_chunks),
                            },
                            files={"chunk": (f"chunk_{chunk_idx}.bin", chunk_bytes, "application/octet-stream")},
                            timeout=60.0,
                        )
                        up_resp.raise_for_status()
                        last_exc = None
                        break
                    except requests.RequestException as exc:
                        last_exc = exc
                        if cancel_event is not None and cancel_event.is_set():
                            raise ColabCancelledError("動画アップロードを中断しました。") from exc
                        if attempt < 2:
                            time.sleep(1.0 * (attempt + 1))
                if last_exc is not None:
                    raise last_exc
        return sha256, False

    def submit_job(
        self,
        video_sha256: str,
        settings: dict[str, Any],
        *,
        output_mode: str = "data_only",
    ) -> str:
        resp = self._session.post(
            self._url("/jobs"),
            headers=self._headers(),
            json={
                "video_sha256": video_sha256,
                "settings": settings,
                "output_mode": output_mode,
            },
            timeout=20.0,
        )
        resp.raise_for_status()
        return str(resp.json()["job_id"])

    def get_job_status(self, remote_job_id: str) -> dict[str, Any]:
        resp = self._session.get(
            self._url(f"/jobs/{remote_job_id}/status"),
            headers=self._headers(),
            timeout=15.0,
        )
        resp.raise_for_status()
        return dict(resp.json())

    def cancel_job(self, remote_job_id: str) -> dict[str, Any]:
        resp = self._session.post(
            self._url(f"/jobs/{remote_job_id}/cancel"),
            headers=self._headers(),
            timeout=15.0,
        )
        resp.raise_for_status()
        return dict(resp.json())

    def stream_job_events(
        self,
        remote_job_id: str,
        *,
        on_progress: Callable[[float, str], None],
        on_log: Callable[[str], None],
        cancel_event: threading.Event | None = None,
        max_reconnects: int = 8,
    ) -> int:
        """Stream SSE events from Colab job, auto-recovering across transient tunnel drops."""
        last_seq = 0
        reconnect_attempts = 0
        terminal_states = {"done", "failed", "cancelled"}

        while True:
            if cancel_event is not None and cancel_event.is_set():
                raise ColabCancelledError("Colab 解析を中断しました。")

            resp = None
            try:
                resp = self._session.get(
                    self._url(f"/jobs/{remote_job_id}/events"),
                    headers=self._headers(),
                    params={"from_seq": str(last_seq)},
                    stream=True,
                    timeout=(10.0, 45.0),
                )
                resp.raise_for_status()

                event_data_lines: list[str] = []
                event_id: str | None = None

                for raw_line in resp.iter_lines(decode_unicode=True):
                    if cancel_event is not None and cancel_event.is_set():
                        raise ColabCancelledError("Colab 解析を中断しました。")

                    line = raw_line if isinstance(raw_line, str) else (
                        raw_line.decode("utf-8", errors="replace") if raw_line is not None else ""
                    )

                    if line == "":
                        if event_data_lines:
                            raw_json = "\n".join(event_data_lines)
                            event_data_lines = []
                            ev = json.loads(raw_json)
                            ev_seq = int(ev.get("seq") or (int(event_id) if event_id and event_id.isdigit() else 0))
                            last_seq = max(last_seq, ev_seq)
                            reconnect_attempts = 0

                            ev_type = ev.get("type")
                            if ev_type == "progress":
                                on_progress(float(ev.get("pct", 0.0)), str(ev.get("phase", "")))
                            elif ev_type == "log":
                                on_log(str(ev.get("line", "")))
                            elif ev_type == "status":
                                state = str(ev.get("state", ""))
                                if state in terminal_states:
                                    err = str(ev.get("error") or "").strip()
                                    if state != "done" and err:
                                        on_log(f"Colab ジョブ終了 ({state}): {err}\n")
                                    raw_code = ev.get("exit_code")
                                    if raw_code is not None:
                                        return int(raw_code)
                                    return 0 if state == "done" else 1
                            event_id = None
                        continue

                    if line.startswith(":"):
                        reconnect_attempts = 0
                        continue
                    if line.startswith("id:"):
                        event_id = line[3:].strip()
                    elif line.startswith("data:"):
                        event_data_lines.append(line[5:].lstrip())
                    # event: / retry: handled cleanly via JSON payload type

                # Stream closed; verify job state via REST before deciding to reconnect
                status_info = self.get_job_status(remote_job_id)
                state = str(status_info.get("state", ""))
                if state in terminal_states:
                    raw_code = status_info.get("exit_code")
                    if raw_code is not None:
                        return int(raw_code)
                    return 0 if state == "done" else 1
            except ColabCancelledError:
                raise
            except requests.RequestException as exc:
                if cancel_event is not None and cancel_event.is_set():
                    raise ColabCancelledError("Colab 解析を中断しました。") from exc
                reconnect_attempts += 1
                if reconnect_attempts > max_reconnects:
                    raise RuntimeError(
                        f"Colab SSE 接続が復旧しませんでした ({max_reconnects}回再試行後): {exc}"
                    ) from exc
                try:
                    status_info = self.get_job_status(remote_job_id)
                    state = str(status_info.get("state", ""))
                    if state in terminal_states:
                        raw_code = status_info.get("exit_code")
                        return int(raw_code) if raw_code is not None else (0 if state == "done" else 1)
                except requests.RequestException:
                    pass
                time.sleep(min(8.0, 0.8 * (2 ** min(reconnect_attempts - 1, 3))))
            finally:
                if resp is not None and hasattr(resp, "close"):
                    try:
                        resp.close()
                    except Exception:
                        pass

    def download_and_extract_result(
        self,
        remote_job_id: str,
        output_dir: Path,
        *,
        cancel_event: threading.Event | None = None,
    ) -> list[Path]:
        """Download result ZIP, validate paths against Zip-Slip, extract into output_dir, and delete remote job."""
        dest_dir = Path(output_dir)
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest_resolved = dest_dir.resolve()

        extracted: list[Path] = []
        with tempfile.TemporaryDirectory(prefix="colab_zip_") as tmpdir:
            zip_path = Path(tmpdir) / f"{remote_job_id}.zip"
            resp = self._session.get(
                self._url(f"/jobs/{remote_job_id}/result"),
                headers=self._headers(),
                stream=True,
                timeout=(15.0, 120.0),
            )
            resp.raise_for_status()
            try:
                with zip_path.open("wb") as out_f:
                    for chunk in resp.iter_content(chunk_size=1024 * 1024):
                        if cancel_event is not None and cancel_event.is_set():
                            raise ColabCancelledError("結果ZIPのダウンロードを中断しました。")
                        if chunk:
                            out_f.write(chunk)
            finally:
                if hasattr(resp, "close"):
                    try:
                        resp.close()
                    except Exception:
                        pass

            with zipfile.ZipFile(zip_path, "r") as zf:
                members: list[tuple[zipfile.ZipInfo, Path]] = []
                for info in zf.infolist():
                    if info.is_dir():
                        continue
                    rel_name = info.filename.replace("\\", "/")
                    if rel_name.startswith("/") or ".." in Path(rel_name).parts:
                        raise ValueError(f"Unsafe ZIP entry path rejected: {info.filename!r}")
                    # Reject symlinks encoded in Unix external_attr
                    if (info.external_attr >> 16) & 0o170000 == 0o120000:
                        raise ValueError(f"Symlink ZIP entry rejected: {info.filename!r}")
                    target = (dest_resolved / Path(rel_name).name).resolve()
                    if not target.is_relative_to(dest_resolved):
                        raise ValueError(f"ZIP entry escapes destination directory: {info.filename!r}")
                    members.append((info, target))

                for info, target in members:
                    tmp_target = target.parent / f".{target.name}.{uuid.uuid4().hex[:8]}.tmp"
                    try:
                        with zf.open(info, "r") as src_f, tmp_target.open("wb") as dst_f:
                            while True:
                                buf = src_f.read(256 * 1024)
                                if not buf:
                                    break
                                dst_f.write(buf)
                        os.replace(tmp_target, target)
                        extracted.append(target)
                    finally:
                        if tmp_target.exists():
                            try:
                                tmp_target.unlink()
                            except OSError:
                                pass

        self.cleanup_job(remote_job_id)
        return extracted

    def cleanup_job(self, remote_job_id: str) -> None:
        """Best-effort cleanup of remote job temporary files on Colab."""
        try:
            self._session.delete(
                self._url(f"/jobs/{remote_job_id}"),
                headers=self._headers(),
                timeout=10.0,
            )
        except Exception:
            pass
