"""Factory and validation helpers for selecting and instantiating pose estimators."""
from __future__ import annotations

from typing import Any, Mapping

from .base import BasePoseEstimator
from .rtmpose import RTMPoseEstimator, resolve_rtmlib_selection
from .vitpose import ViTPoseEstimator, resolve_vitpose_selection

VALID_POSE_ENGINES = ("rtmpose", "vitpose")


def normalize_pose_engine(raw_engine: Any) -> str:
    """Normalize POSE_ENGINE value to 'rtmpose' or 'vitpose'."""
    val = str(raw_engine or "rtmpose").strip().lower()
    if val in VALID_POSE_ENGINES:
        return val
    return "rtmpose"


def resolve_pose_selection(settings: Mapping[str, Any]) -> dict[str, Any]:
    """Validate and resolve active pose engine selection without loading model weights."""
    engine = normalize_pose_engine(settings.get("POSE_ENGINE", "rtmpose"))
    if engine == "vitpose":
        resolved = resolve_vitpose_selection(
            str(settings.get("VITPOSE_MODEL", "h")),
            str(settings.get("VITPOSE_INPUT_SIZE", "256x192")),
        )
        return {"engine": "vitpose", **resolved}

    resolved = resolve_rtmlib_selection(
        str(settings.get("RTMLIB_POSE_MODEL", "x")),
        str(settings.get("RTMLIB_POSE_INPUT_SIZE", "384x288")),
    )
    return {"engine": "rtmpose", **resolved}


def validate_pose_settings(settings: Mapping[str, Any]) -> dict[str, Any]:
    """Validate settings for the currently selected pose estimation engine."""
    return resolve_pose_selection(settings)


def create_pose_estimator(
    settings: Mapping[str, Any],
    device: str,
) -> BasePoseEstimator:
    """Instantiate the configured BasePoseEstimator strategy for Pass 2."""
    engine = normalize_pose_engine(settings.get("POSE_ENGINE", "rtmpose"))
    if engine == "vitpose":
        return ViTPoseEstimator(
            model_size=str(settings.get("VITPOSE_MODEL", "h")),
            input_size=str(settings.get("VITPOSE_INPUT_SIZE", "256x192")),
            device=device,
            flip_test=bool(settings.get("VITPOSE_FLIP_TEST", True)),
        )

    return RTMPoseEstimator(
        pose_model=str(settings.get("RTMLIB_POSE_MODEL", "x")),
        pose_input_size=str(settings.get("RTMLIB_POSE_INPUT_SIZE", "384x288")),
        backend=str(settings.get("BACKEND", "onnxruntime")),
        device=device,
    )
