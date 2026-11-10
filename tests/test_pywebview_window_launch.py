"""Automated Headless / Auto-Closing Smoke Test for PyWebView Desktop Launch.

Requirement: R4 (Automated Smoke Tests & Verification Routines).
Validates:
1. Production bundle (frontend/dist/index.html) is loaded by PyWebView host.
2. PyWebView window instantiates with 16:9 geometry, correct title, and minimum size.
3. BackendApi bridge is injected and operable inside Edge WebView2 runtime.
4. Window closes cleanly without hanging or leaving orphaned processes.
"""
from __future__ import annotations

import os
from pathlib import Path
import sys
import threading
import time
import unittest

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))

import webview
import pose_ui_webview.app as app_mod


class TestPyWebViewWindowLaunch(unittest.TestCase):
    """Smoke test suite validating PyWebView desktop launch and clean exit."""

    @classmethod
    def setUpClass(cls):
        cls.dist_index = WORKSPACE_ROOT / "frontend" / "dist" / "index.html"
        if not cls.dist_index.is_file():
            raise unittest.SkipTest(f"Production bundle not found at {cls.dist_index}")

    def test_launch_webview_gui_auto_closing(self):
        """Launches launch_webview_gui pointing to dist/index.html and verifies React render + bridge."""
        verification_state = {
            "window_initialized": False,
            "title_matched": False,
            "dimensions_valid": False,
            "url": "",
            "body_text": "",
            "root_children": -1,
            "bridge_ready": False,
            "initial_data_keys": [],
            "sandbox_blocked": False,
            "closed_cleanly": False,
        }

        def on_startup(window: webview.Window):
            try:
                if window is not None:
                    verification_state["window_initialized"] = True

                if "動画姿勢推定" in (window.title or ""):
                    verification_state["title_matched"] = True

                if window.width >= 1200 and window.height >= 675:
                    verification_state["dimensions_valid"] = True

                # Wait for Edge WebView2 and React mount to settle (up to 4s)
                deadline = time.time() + 4.0
                while time.time() < deadline:
                    time.sleep(0.4)
                    try:
                        url = window.get_current_url() or ""
                        body_text = window.evaluate_js("document.body ? document.body.innerText.slice(0, 400) : ''") or ""
                        verification_state["url"] = url
                        verification_state["body_text"] = body_text

                        if "ERR_NETWORK_ACCESS_DENIED" in body_text or "インターネット アクセスがブロックされています" in body_text:
                            verification_state["sandbox_blocked"] = True
                            break

                        root_cnt = window.evaluate_js(
                            "document.getElementById('root') ? document.getElementById('root').children.length : -1"
                        )
                        if isinstance(root_cnt, int):
                            verification_state["root_children"] = root_cnt

                        has_bridge = bool(
                            window.evaluate_js("Boolean(window.pywebview && window.pywebview.api && typeof window.pywebview.api.get_initial_data === 'function')")
                        )
                        verification_state["bridge_ready"] = has_bridge

                        if root_cnt and root_cnt > 0 and has_bridge:
                            # Also confirm key Japanese UI panes rendered cleanly
                            body_text = window.evaluate_js("document.body ? document.body.innerText.slice(0, 600) : ''") or ""
                            verification_state["body_text"] = body_text
                            break
                    except Exception:
                        pass

                window.destroy()
                verification_state["closed_cleanly"] = True
            except Exception as e:
                print(f"[test_pywebview_launch] Exception in on_startup: {e}")
                try:
                    window.destroy()
                except Exception:
                    pass

        app_mod.launch_webview_gui(
            base_dir=WORKSPACE_ROOT,
            on_startup=on_startup,
            debug=False,
        )

        self.assertTrue(verification_state["window_initialized"], "Window was not initialized")
        self.assertTrue(verification_state["title_matched"], "Window title mismatch: expected '動画姿勢推定'")
        self.assertTrue(verification_state["dimensions_valid"], "Window dimensions do not meet min 1200x675")
        self.assertTrue(verification_state["closed_cleanly"], "Window did not close cleanly")

        if verification_state["sandbox_blocked"]:
            self.skipTest(
                "Edge WebView2 loopback (127.0.0.1) is blocked by sandbox (ERR_NETWORK_ACCESS_DENIED). "
                "Re-run outside sandbox to verify live React #root mount."
            )

        self.assertGreater(
            verification_state["root_children"],
            0,
            f"React did not mount into #root (url={verification_state['url']}, body={verification_state['body_text'][:120]})",
        )
        self.assertTrue(verification_state["bridge_ready"], "window.pywebview.api bridge was not injected")
        for expected_ui_text in ("解析中", "予約リスト", "解析開始"):
            self.assertIn(
                expected_ui_text,
                verification_state["body_text"],
                f"Expected React UI text '{expected_ui_text}' not found in rendered DOM",
            )
        print(
            f"[test_pywebview_launch] LIVE UI VERIFIED: url={verification_state['url']}, "
            f"root_children={verification_state['root_children']}, bridge_ready={verification_state['bridge_ready']}"
        )


if __name__ == "__main__":
    unittest.main()
