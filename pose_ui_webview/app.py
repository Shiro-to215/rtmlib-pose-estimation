"""PyWebView Window Host, Desktop Application Controller & Lifecycle Orchestrator."""
from __future__ import annotations

import base64
import ctypes
import json
import logging
import os
from pathlib import Path
import queue
import sys
import tempfile
import threading
import time
from typing import Any, Callable, Optional, Sequence

import webview

import gui
from reservation_queue import ReservationQueue
from .api_bridge import BackendApi
from .worker_manager import AnalysisWorkerManager

logger = logging.getLogger(__name__)


class ThumbnailDaemon:
    """Asynchronous background worker extracting frame 0 of video files using OpenCV."""

    def __init__(self, window_getter: Callable[[], Optional[webview.Window]]) -> None:
        self._get_window = window_getter
        self._queue: queue.Queue[tuple[str, str]] = queue.Queue()
        self._cache: dict[str, str] = {}
        self._info: dict[str, str] = {}
        self._seen: set[str] = set()
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._worker_thread = threading.Thread(
            target=self._run, daemon=True, name="ThumbnailDaemon"
        )
        self._worker_thread.start()

    def enqueue(self, job_id: str, video_path: str) -> None:
        """Enqueues a video for thumbnail extraction if not already cached."""
        with self._lock:
            if job_id in self._cache or job_id in self._seen:
                return
            self._seen.add(job_id)
        self._queue.put((job_id, video_path))

    def enqueue_jobs(self, jobs: Sequence[Any]) -> None:
        """Enqueues all pending/running/failed jobs that lack thumbnails."""
        for job in jobs:
            if getattr(job, "state", "") != "done":
                self.enqueue(job.id, str(job.video))

    def get_thumbnail(self, job_id: str) -> str:
        """Returns the cached Base64 data URI, or empty string if not ready."""
        with self._lock:
            return self._cache.get(job_id, "")

    def get_info(self, job_id: str) -> str:
        """Returns the resolution string (e.g. '1920×1080 px')."""
        with self._lock:
            return self._info.get(job_id, "")

    def prune(self, active_job_ids: set[str]) -> None:
        """Prunes cached items for deleted or completed jobs to conserve RAM."""
        with self._lock:
            stale_ids = set(self._cache.keys()) - active_job_ids
            for sid in stale_ids:
                self._cache.pop(sid, None)
                self._info.pop(sid, None)
                self._seen.discard(sid)

    def stop(self) -> None:
        """Signals the background extraction thread to terminate."""
        self._stop_event.set()
        self._queue.put(("", ""))

    def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                job_id, video_path = self._queue.get(timeout=0.5)
            except queue.Empty:
                continue

            if self._stop_event.is_set() or not job_id:
                break

            data_uri, info_text = self._extract_frame(video_path)

            with self._lock:
                self._cache[job_id] = data_uri
                self._info[job_id] = info_text

            self._dispatch_to_window(job_id, data_uri, info_text)
            self._queue.task_done()

    def _extract_frame(self, video_path: str) -> tuple[str, str]:
        if not os.path.exists(video_path):
            return "", "動画が見つかりません"
        try:
            import cv2
        except ImportError:
            return "", "OpenCV未検出"

        cap = cv2.VideoCapture(str(video_path))
        try:
            ok, frame = cap.read()
            if not ok or frame is None:
                return "", "プレビュー取得不可"

            h, w = frame.shape[:2]
            scale = min(640 / max(1, w), 360 / max(1, h), 1.0)
            target_w = max(1, int(w * scale))
            target_h = max(1, int(h * scale))

            resized = cv2.resize(frame, (target_w, target_h), interpolation=cv2.INTER_AREA)
            ok, buf = cv2.imencode(".jpg", resized, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
            if not ok:
                return "", f"{w}×{h} px"

            b64_str = base64.b64encode(buf.tobytes()).decode("ascii")
            return f"data:image/jpeg;base64,{b64_str}", f"{w}×{h} px"
        except Exception:
            return "", ""
        finally:
            cap.release()

    def _dispatch_to_window(self, job_id: str, data_uri: str, info_text: str) -> None:
        win = self._get_window()
        if win is None:
            return
        payload = json.dumps({"job_id": job_id, "data_url": data_uri, "info": info_text}, ensure_ascii=False)
        escaped_id = json.dumps(job_id)
        escaped_uri = json.dumps(data_uri)
        escaped_info = json.dumps(info_text)
        js_code = (
            f"if (typeof window.onJobThumbnail === 'function') {{ "
            f"  window.onJobThumbnail({escaped_id}, {escaped_uri}, {escaped_info}); "
            f"}} "
            f"if (typeof window.__onBackendEvent === 'function') {{ "
            f"  window.__onBackendEvent('thumbnail', {payload}); "
            f"}} "
            f"window.dispatchEvent(new CustomEvent('pywebview:thumbnail', {{ "
            f"  detail: {payload} "
            f"}}));"
        )
        try:
            win.evaluate_js(js_code)
        except Exception:
            pass


def _get_missing_dist_html() -> str:
    """Fallback HTML if frontend/dist/index.html has not yet been built."""
    return """<!DOCTYPE html>
<html lang="ja">
<head>
  <meta charset="utf-8" />
  <title>動画姿勢推定 — ビルドが必要です</title>
  <style>
    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
           background: #F2F5F4; display: flex; align-items: center; justify-content: center;
           height: 100vh; margin: 0; color: #1E293B; }
    .card { background: white; padding: 36px 44px; border-radius: 12px; border: 1px solid #CBD5E1;
            box-shadow: 0 10px 15px -3px rgba(0,0,0,0.07); max-width: 620px; }
    h2 { color: #0F766E; margin-top: 0; }
    code { background: #E2E8F0; padding: 3px 6px; border-radius: 4px; font-size: 13px; font-weight: 600; }
    pre { background: #F8FAFC; border: 1px solid #E2E8F0; padding: 12px; border-radius: 6px; }
  </style>
</head>
<body>
  <div class="card">
    <h2>フロントエンドのビルドが必要です</h2>
    <p><code>frontend/dist/index.html</code> が検出されませんでした。</p>
    <p>以下の手順でフロントエンドをビルドしてください:</p>
    <pre>cd frontend
npm install
npm run build</pre>
    <p>開発モードで実行する場合は:</p>
    <pre>cd frontend
npm run dev
# 別ターミナルで:
python gui.py --dev</pre>
  </div>
</body>
</html>"""


def launch_webview_gui(
    base_dir: Path | str | None = None,
    settings_file: Path | str | None = None,
    engine_defaults: dict[str, Any] | None = None,
    choices: dict[str, Any] | None = None,
    bool_keys: set[str] | None = None,
    int_keys: set[str] | None = None,
    float_keys: set[str] | None = None,
    resolve_rtmlib_fn: Callable | None = None,
    output_names_fn: Callable | None = None,
    debug: bool = False,
    dev_server: bool | str | None = None,
    on_startup: Callable[[webview.Window], None] | None = None,
    storage_path: str | None = None,
) -> None:
    """Main application launcher that configures and starts the PyWebView desktop host."""
    if base_dir is None:
        base_dir = Path(__file__).resolve().parent.parent
    else:
        base_dir = Path(base_dir).resolve()

    # Determine URL or HTML
    dev_env = os.environ.get("VITE_DEV_SERVER")
    is_dev = bool(dev_server or dev_env)

    html_content: Optional[str] = None
    target_url: Optional[str] = None

    if is_dev:
        if isinstance(dev_server, str) and dev_server.startswith("http"):
            target_url = dev_server
        elif dev_env and dev_env.startswith("http"):
            target_url = dev_env
        else:
            target_url = "http://localhost:5173"
    else:
        dist_index = base_dir / "frontend" / "dist" / "index.html"
        if dist_index.is_file():
            target_url = str(dist_index.resolve())
        else:
            html_content = _get_missing_dist_html()

    # Window reference container
    main_window: list[Optional[webview.Window]] = [None]

    def _get_window() -> Optional[webview.Window]:
        return main_window[0]

    # Initialize Thumbnail Background Daemon
    thumbnail_daemon = ThumbnailDaemon(_get_window)

    # Instantiate Backend API Bridge & Subprocess Worker Manager
    backend_api = BackendApi(
        base_dir=base_dir,
        settings_file=settings_file,
        engine_defaults=engine_defaults,
        choices=choices,
        bool_keys=bool_keys,
        int_keys=int_keys,
        float_keys=float_keys,
        resolve_rtmlib_fn=resolve_rtmlib_fn,
        output_names_fn=output_names_fn,
        thumbnail_provider=thumbnail_daemon,
    )

    # Determine 16:9 window dimensions
    screen_w, screen_h = 1920, 1080
    if getattr(webview, "screens", None):
        try:
            screen_w = webview.screens[0].width
            screen_h = webview.screens[0].height
        except Exception:
            pass

    win_w = min(1440, max(1200, int(screen_w * 0.90)))
    win_h = int(win_w * 9 / 16)
    if win_h > int(screen_h * 0.88):
        win_h = int(screen_h * 0.88)
        win_w = int(win_h * 16 / 9)

    win_w = max(1200, win_w)
    win_h = max(675, win_h)

    # Create PyWebView Window
    window = webview.create_window(
        title="動画姿勢推定 (RTMpose + YOLO)",
        url=target_url,
        html=html_content,
        js_api=backend_api,
        width=win_w,
        height=win_h,
        min_size=(1200, 675),
        background_color="#F2F5F4",
        text_select=False,
        confirm_close=False,
    )
    main_window[0] = window
    backend_api.set_window(window)

    # Window lifecycle hooks
    def on_shown() -> None:
        thumbnail_daemon.enqueue_jobs(backend_api.reservations.jobs)

    def on_closing() -> bool:
        if getattr(backend_api, "queue_active", False):
            msg = (
                "現在解析が実行中です。\n"
                "解析を中断してアプリケーションを終了しますか？\n\n"
                "※ 中断した動画は次回起動時に未完了として残ります。"
            )
            title = "解析を中断して終了"
            try:
                MB_YESNO = 0x04
                MB_ICONWARNING = 0x30
                IDYES = 6
                res = ctypes.windll.user32.MessageBoxW(0, msg, title, MB_YESNO | MB_ICONWARNING)
                if res != IDYES:
                    return False
            except Exception:
                pass

            backend_api.cancel_current_job()
            time.sleep(0.3)

        return True

    def on_closed() -> None:
        thumbnail_daemon.stop()
        backend_api.shutdown()

    window.events.shown += on_shown
    window.events.closing += on_closing
    window.events.closed += on_closed

    # Start PyWebView loop (Edge WebView2 on Windows)
    use_http_server = bool(target_url and not target_url.startswith("http"))
    cache_path = (
        storage_path
        or os.environ.get("PYWEBVIEW_STORAGE_PATH")
        or os.path.join(tempfile.gettempdir(), "pywebview_cache")
    )

    def _startup_callback() -> None:
        if on_startup:
            try:
                on_startup(window)
            except Exception as e:
                logger.error("Error in on_startup callback: %s", e)
                try:
                    window.destroy()
                except Exception:
                    pass

    webview.start(
        _startup_callback if on_startup else None,
        debug=debug,
        http_server=use_http_server,
        storage_path=cache_path,
        private_mode=False,
    )
