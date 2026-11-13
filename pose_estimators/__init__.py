"""Pose estimation Strategy package supporting RTMPose (ONNX) and ViTPose++ (PyTorch)."""
from .base import BasePoseEstimator, clear_cuda_cache, clamped_target_box, draw_pose_skeleton
from .factory import (
    create_pose_estimator,
    resolve_pose_selection,
    validate_pose_settings,
)
from .rtmpose import RTMLIB_POSE_ASSETS, RTMPoseEstimator, resolve_rtmlib_selection
from .vitpose import (
    VITPOSE_ASSETS,
    ViTPoseEstimator,
    configure_hf_environment,
    resolve_vitpose_selection,
)

__all__ = [
    "BasePoseEstimator",
    "RTMLIB_POSE_ASSETS",
    "RTMPoseEstimator",
    "VITPOSE_ASSETS",
    "ViTPoseEstimator",
    "clear_cuda_cache",
    "clamped_target_box",
    "configure_hf_environment",
    "create_pose_estimator",
    "draw_pose_skeleton",
    "resolve_pose_selection",
    "resolve_rtmlib_selection",
    "resolve_vitpose_selection",
    "validate_pose_settings",
]
