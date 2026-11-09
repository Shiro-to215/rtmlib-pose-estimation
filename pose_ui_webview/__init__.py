"""PyWebView Desktop Application Host & JS-Python Bridge for Pose Estimation."""
from .api_bridge import BackendApi, serialize_reservation
from .app import launch_webview_gui
from .worker_manager import AnalysisWorkerManager

__version__ = "1.0.0"

__all__ = [
    "launch_webview_gui",
    "BackendApi",
    "AnalysisWorkerManager",
    "serialize_reservation",
]
