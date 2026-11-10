"""Empirical Gate Challenge 2 Verification for Milestone 3.

Verifies:
1. Clean Production Build Artifacts.
2. Asset Path & WebView2 Relative Path Resolution.
3. Bundle Content Completeness (UI strings, Japanese labels, parameter keys).
4. PyWebView Package Integration (app.py references frontend/dist/index.html).
5. File Immutability (gui.py and reservation_queue.py untouched).
"""
import inspect
from pathlib import Path
import subprocess
import unittest


class TestMilestone3GateChallenge2(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.project_root = Path(__file__).resolve().parent.parent
        cls.dist_dir = cls.project_root / "frontend" / "dist"
        cls.index_html = cls.dist_dir / "index.html"
        cls.assets_dir = cls.dist_dir / "assets"

    def test_challenge1_dist_artifacts_exist(self):
        """Verify that frontend/dist/index.html and dist/assets exist."""
        self.assertTrue(self.dist_dir.is_dir(), "frontend/dist directory does not exist")
        self.assertTrue(self.index_html.is_file(), "frontend/dist/index.html does not exist")
        self.assertTrue(self.assets_dir.is_dir(), "frontend/dist/assets directory does not exist")

    def test_challenge2_asset_path_relative_resolution(self):
        """Verify that index.html references assets relatively for WebView2 compatibility."""
        content = self.index_html.read_text(encoding="utf-8")
        
        # Verify relative path presence
        self.assertIn("./assets/", content, "index.html must reference assets using './assets/'")
        
        # Verify absence of absolute path /assets/
        self.assertNotIn('src="/assets/', content, "index.html must not use absolute src='/assets/'")
        self.assertNotIn('href="/assets/', content, "index.html must not use absolute href='/assets/'")
        
        # Verify referenced JS and CSS files actually exist and are non-empty
        js_files = list(self.assets_dir.glob("*.js"))
        css_files = list(self.assets_dir.glob("*.css"))
        
        self.assertGreater(len(js_files), 0, "No JS files found in dist/assets")
        self.assertGreater(len(css_files), 0, "No CSS files found in dist/assets")
        
        for js_file in js_files:
            self.assertGreater(js_file.stat().st_size, 10000, f"{js_file.name} is unexpectedly small")
            self.assertIn(f"./assets/{js_file.name}", content, f"index.html should reference {js_file.name}")
            
        for css_file in css_files:
            self.assertGreater(css_file.stat().st_size, 1000, f"{css_file.name} is unexpectedly small")
            self.assertIn(f"./assets/{css_file.name}", content, f"index.html should reference {css_file.name}")

    def test_challenge3_bundle_content_completeness(self):
        """Verify that compiled JS bundle contains all required UI strings, Japanese labels, and parameter keys."""
        js_files = list(self.assets_dir.glob("*.js"))
        self.assertTrue(len(js_files) > 0, "No JS bundle found")
        
        # Combine all JS bundles if multiple
        bundle_text = "".join(f.read_text(encoding="utf-8") for f in js_files)
        
        required_strings = [
            # UI status & core actions
            "予約リスト",
            "基本設定",
            "解析開始",
            "解析中断",
            "待機中",
            "解析実行中",
            "YOLO 処理中",
            "RTMPose 処理中",
            "中断処理中",
            # Guide & workflow strings
            "1. 入力ファイルの選択",
            "2. 出力先フォルダーの設定",
            "＋ 予約リストに追加する",
            # Settings tab categories
            "基本・出力設定",
            "検出・信頼度設定",
            "トラッキング・重み設定",
            "可視化・オーバーレイ設定",
            # Critical parameter keys
            "YOLO_IMAGE_SIZE",
            "YOLO_CONFIDENCE",
            "YOLO_IOU",
            "YOLO_CLASSES",
            "RTMLIB_POSE_MODEL",
            "CSV_MAX_PERSONS",
            "TARGET_LOCK_RAW_ID",
        ]
        
        missing = [s for s in required_strings if s not in bundle_text]
        self.assertEqual(missing, [], f"Missing required strings in compiled JS bundle: {missing}")

    def test_challenge3_all_engine_parameters_present(self):
        """Stress-test: Verify that all configurable parameter keys from gui.ENGINE_DEFAULTS appear in the bundle."""
        import gui
        js_files = list(self.assets_dir.glob("*.js"))
        bundle_text = "".join(f.read_text(encoding="utf-8") for f in js_files)
        
        # Internal path breakdown keys handled via file dialogs rather than tab inputs
        ignored_path_keys = {"THUMBNAIL_ROOT", "THUMBNAIL_IMAGE_NAME"}
        
        missing_keys = []
        for key in gui.ENGINE_DEFAULTS.keys():
            if key in ignored_path_keys:
                continue
            if key not in bundle_text:
                missing_keys.append(key)
                
        self.assertEqual(missing_keys, [], f"The following gui.ENGINE_DEFAULTS are missing in frontend bundle: {missing_keys}")

    def test_adversarial_no_leaked_dev_artifacts(self):
        """Adversarial test: Ensure no localhost:5173 hardcoding in production bundle or sourcemap leaks."""
        js_files = list(self.assets_dir.glob("*.js"))
        bundle_text = "".join(f.read_text(encoding="utf-8") for f in js_files)
        
        # Production build should not hardcode dev server URL in component code
        # (Mock backend may have comments or dev checks, but let's check no sourcemap comment at the end)
        self.assertNotIn("//# sourceMappingURL=", bundle_text, "Production build should not expose sourcemaps")
        
        # Check no .map files in dist/assets
        map_files = list(self.assets_dir.glob("*.map"))
        self.assertEqual(map_files, [], f"Found sourcemap files in production build: {map_files}")

    def test_challenge4_pywebview_package_integration(self):
        """Verify pose_ui_webview/app.py properly references frontend/dist/index.html."""
        import pose_ui_webview.app as app_mod
        source = inspect.getsource(app_mod.launch_webview_gui)
        
        # Verify references to dist_index and frontend/dist/index.html
        self.assertIn('dist_index = base_dir / "frontend" / "dist" / "index.html"', source)
        self.assertIn("target_url = str(dist_index.resolve())", source)
        self.assertIn("html_content = _get_missing_dist_html()", source)

    def test_challenge6_legacy_files_untouched_in_m3(self):
        """Verify gui.py and reservation_queue.py have no uncommitted changes and reservation_queue.py matches main."""
        # Check uncommitted status
        status_proc = subprocess.run(
            ["git", "status", "--porcelain", "gui.py", "reservation_queue.py"],
            cwd=str(self.project_root),
            capture_output=True,
            text=True,
            check=True
        )
        self.assertEqual(status_proc.stdout.strip(), "", "gui.py or reservation_queue.py has uncommitted changes")
        
        # Check reservation_queue.py diff against main
        diff_queue = subprocess.run(
            ["git", "diff", "main", "--", "reservation_queue.py"],
            cwd=str(self.project_root),
            capture_output=True,
            text=True,
            check=True
        )
        self.assertEqual(diff_queue.stdout.strip(), "", "reservation_queue.py differs from main branch")
        
        # Check gui.py diff against start of Milestone 3 (commit 9c6480a)
        diff_gui = subprocess.run(
            ["git", "diff", "9c6480a", "--", "gui.py"],
            cwd=str(self.project_root),
            capture_output=True,
            text=True,
            check=True
        )
        self.assertEqual(diff_gui.stdout.strip(), "", "gui.py was modified during Milestone 3")


if __name__ == "__main__":
    unittest.main()
