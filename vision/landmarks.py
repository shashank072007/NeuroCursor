"""
Landmark extraction and face quality module for FLUX / NeuroCursor.

Uses MediaPipe FaceLandmarker (tasks API) to extract 468+ 3D facial landmarks, computes
a rigorous face.quality metric in [0.0, 1.0], measures processing latency (process_ms),
and enforces the strict null-out contract when the face is lost or quality is unacceptable.
"""

from __future__ import annotations

import math
import os
import sys
import tempfile
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

# Suppress matplotlib font cache warning
if "MPLCONFIGDIR" not in os.environ:
    os.environ["MPLCONFIGDIR"] = tempfile.gettempdir()

import cv2
import numpy as np

try:
    import mediapipe as mp
    from mediapipe.tasks.python import vision as mp_vision
    from mediapipe.tasks.python.core import base_options as mp_base_opt
    MEDIAPIPE_AVAILABLE = True
except ImportError:
    mp = None  # type: ignore
    mp_vision = None  # type: ignore
    mp_base_opt = None  # type: ignore
    MEDIAPIPE_AVAILABLE = False


# Key MediaPipe Face Mesh Landmark Indices
class LandmarkIndex:
    NOSE_TIP = 1
    FOREHEAD = 10
    CHIN = 152

    # Face contour boundaries (used for face width & orientation)
    FACE_LEFT = 234
    FACE_RIGHT = 454

    # Left eye landmarks
    LEFT_EYE_OUTER = 33
    LEFT_EYE_INNER = 133
    LEFT_EYE_TOP = 159
    LEFT_EYE_BOTTOM = 145
    LEFT_IRIS = 468

    # Right eye landmarks
    RIGHT_EYE_INNER = 362
    RIGHT_EYE_OUTER = 263
    RIGHT_EYE_TOP = 386
    RIGHT_EYE_BOTTOM = 374
    RIGHT_IRIS = 473

    # Mouth & Lips
    MOUTH_CORNER_LEFT = 61
    MOUTH_CORNER_RIGHT = 291
    LIP_TOP_OUTER = 0
    LIP_BOTTOM_OUTER = 17
    LIP_TOP_INNER = 13
    LIP_BOTTOM_INNER = 14

    # Eyebrows
    LEFT_EYEBROW = [70, 63, 105, 66, 107]
    RIGHT_EYEBROW = [300, 293, 334, 296, 336]
    LEFT_BROW_MID = 105
    RIGHT_BROW_MID = 334


@dataclass
class FaceMeshResult:
    """Encapsulates the face detection and landmark extraction payload."""
    detected: bool
    quality: float
    width_norm: Optional[float]
    center_x: Optional[float]
    center_y: Optional[float]
    process_ms: float
    landmarks: Optional[List[Tuple[float, float, float]]] = None
    blendshapes: Dict[str, float] = field(default_factory=dict)
    key_points: Dict[str, Tuple[float, float]] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def create_null(cls, process_ms: float = 0.0, reason: str = "no_face") -> FaceMeshResult:
        """Enforces the strict null-out contract: never repeat stale coordinates."""
        return cls(
            detected=False,
            quality=0.0,
            width_norm=None,
            center_x=None,
            center_y=None,
            process_ms=round(process_ms, 2),
            landmarks=None,
            blendshapes={},
            key_points={},
            metadata={"loss_reason": reason},
        )


class FaceMeshExtractor:
    """Extracts facial landmarks and computes quality metrics from camera frames."""

    def __init__(
        self,
        model_path: Optional[str] = None,
        min_detection_confidence: float = 0.5,
        min_tracking_confidence: float = 0.5,
        quality_threshold: float = 0.45,
    ) -> None:
        self.quality_threshold = quality_threshold
        self._landmarker = None
        self._legacy_mesh = None
        self._last_video_timestamp_ms = 0

        if not MEDIAPIPE_AVAILABLE:
            return

        # Resolve model path for MediaPipe Tasks
        if model_path is None:
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            model_path = os.path.join(base_dir, "models", "face_landmarker.task")

        # Try Tasks API first
        if os.path.isfile(model_path) and mp_vision is not None:
            try:
                base_options = mp_base_opt.BaseOptions(model_asset_path=model_path)
                options = mp_vision.FaceLandmarkerOptions(
                    base_options=base_options,
                    # VIDEO mode reuses temporal tracking between camera frames and
                    # avoids full image-mode detection work on every frame.
                    running_mode=mp_vision.RunningMode.VIDEO,
                    num_faces=1,
                    min_face_detection_confidence=min_detection_confidence,
                    min_face_presence_confidence=min_tracking_confidence,
                    output_face_blendshapes=True,
                )
                self._landmarker = mp_vision.FaceLandmarker.create_from_options(options)
            except Exception:
                self._landmarker = None

        # Fallback to legacy solutions if available
        if self._landmarker is None and hasattr(mp, "solutions") and hasattr(mp.solutions, "face_mesh"):
            try:
                self._legacy_mesh = mp.solutions.face_mesh.FaceMesh(
                    max_num_faces=1,
                    refine_landmarks=True,
                    min_detection_confidence=min_detection_confidence,
                    min_tracking_confidence=min_tracking_confidence,
                )
            except Exception:
                self._legacy_mesh = None

    def process_frame(self, frame: Optional[np.ndarray]) -> FaceMeshResult:
        """
        Processes a BGR image frame, extracts landmarks, and computes quality.

        Strict contract: If no face or quality < threshold, returns create_null().
        """
        if frame is None or frame.size == 0 or (self._landmarker is None and self._legacy_mesh is None):
            return FaceMeshResult.create_null(0.0, reason="frame_empty_or_model_unavailable")

        start_time = time.perf_counter()
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

        raw_landmarks: List[Tuple[float, float, float]] = []
        blendshapes_dict: Dict[str, float] = {}

        try:
            if self._landmarker is not None:
                # Tasks API
                mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame)
                timestamp_ms = max(self._last_video_timestamp_ms + 1, int(time.monotonic() * 1000))
                self._last_video_timestamp_ms = timestamp_ms
                result = self._landmarker.detect_for_video(mp_image, timestamp_ms)

                if not result.face_landmarks:
                    process_ms = (time.perf_counter() - start_time) * 1000.0
                    return FaceMeshResult.create_null(process_ms, reason="face_not_detected")

                face_lms = result.face_landmarks[0]
                raw_landmarks = [(lm.x, lm.y, lm.z) for lm in face_lms]

                if result.face_blendshapes and result.face_blendshapes[0]:
                    for cat in result.face_blendshapes[0]:
                        blendshapes_dict[cat.category_name] = round(cat.score, 3)

            elif self._legacy_mesh is not None:
                # Legacy API
                rgb_frame.flags.writeable = False
                res = self._legacy_mesh.process(rgb_frame)
                if not res.multi_face_landmarks:
                    process_ms = (time.perf_counter() - start_time) * 1000.0
                    return FaceMeshResult.create_null(process_ms, reason="face_not_detected")

                raw_landmarks = [(lm.x, lm.y, lm.z) for lm in res.multi_face_landmarks[0].landmark]

        except Exception as e:
            process_ms = (time.perf_counter() - start_time) * 1000.0
            return FaceMeshResult.create_null(process_ms, reason=f"error_{str(e)}")

        process_ms = (time.perf_counter() - start_time) * 1000.0

        if not raw_landmarks:
            return FaceMeshResult.create_null(process_ms, reason="no_landmarks")

        # Extract anchor points
        nose = raw_landmarks[LandmarkIndex.NOSE_TIP]
        chin = raw_landmarks[LandmarkIndex.CHIN]
        forehead = raw_landmarks[LandmarkIndex.FOREHEAD]
        face_l = raw_landmarks[LandmarkIndex.FACE_LEFT]
        face_r = raw_landmarks[LandmarkIndex.FACE_RIGHT]
        eye_l = raw_landmarks[LandmarkIndex.LEFT_EYE_INNER]
        eye_r = raw_landmarks[LandmarkIndex.RIGHT_EYE_INNER]

        # Face width in normalized frame units
        width_norm = math.hypot(face_r[0] - face_l[0], face_r[1] - face_l[1])

        # Compute face quality
        quality = self.compute_face_quality(
            landmarks=raw_landmarks,
            width_norm=width_norm,
            chin=chin,
            forehead=forehead,
            eye_l=eye_l,
            eye_r=eye_r,
            nose=nose,
        )

        # Gate on quality threshold
        if quality < self.quality_threshold:
            return FaceMeshResult.create_null(process_ms, reason="quality_below_threshold")

        # Key anchor points mapped for downstream calibration/gesture logic
        key_points: Dict[str, Tuple[float, float]] = {
            "nose_tip": (nose[0], nose[1]),
            "forehead": (forehead[0], forehead[1]),
            "chin": (chin[0], chin[1]),
            "face_left": (face_l[0], face_l[1]),
            "face_right": (face_r[0], face_r[1]),
            "left_eye_center": (
                (raw_landmarks[LandmarkIndex.LEFT_EYE_OUTER][0] + eye_l[0]) / 2.0,
                (raw_landmarks[LandmarkIndex.LEFT_EYE_OUTER][1] + eye_l[1]) / 2.0,
            ),
            "right_eye_center": (
                (raw_landmarks[LandmarkIndex.RIGHT_EYE_OUTER][0] + eye_r[0]) / 2.0,
                (raw_landmarks[LandmarkIndex.RIGHT_EYE_OUTER][1] + eye_r[1]) / 2.0,
            ),
            "mouth_top": (
                raw_landmarks[LandmarkIndex.LIP_TOP_INNER][0],
                raw_landmarks[LandmarkIndex.LIP_TOP_INNER][1],
            ),
            "mouth_bottom": (
                raw_landmarks[LandmarkIndex.LIP_BOTTOM_INNER][0],
                raw_landmarks[LandmarkIndex.LIP_BOTTOM_INNER][1],
            ),
            "mouth_corner_left": (
                raw_landmarks[LandmarkIndex.MOUTH_CORNER_LEFT][0],
                raw_landmarks[LandmarkIndex.MOUTH_CORNER_LEFT][1],
            ),
            "mouth_corner_right": (
                raw_landmarks[LandmarkIndex.MOUTH_CORNER_RIGHT][0],
                raw_landmarks[LandmarkIndex.MOUTH_CORNER_RIGHT][1],
            ),
            "left_brow_mid": (
                raw_landmarks[LandmarkIndex.LEFT_BROW_MID][0],
                raw_landmarks[LandmarkIndex.LEFT_BROW_MID][1],
            ),
            "right_brow_mid": (
                raw_landmarks[LandmarkIndex.RIGHT_BROW_MID][0],
                raw_landmarks[LandmarkIndex.RIGHT_BROW_MID][1],
            ),
        }

        # Head center x, y in normalized [0, 1]
        center_x = (face_l[0] + face_r[0]) / 2.0
        center_y = (forehead[1] + chin[1]) / 2.0

        return FaceMeshResult(
            detected=True,
            quality=round(quality, 2),
            width_norm=round(width_norm, 4),
            center_x=round(center_x, 4),
            center_y=round(center_y, 4),
            process_ms=round(process_ms, 2),
            landmarks=raw_landmarks,
            blendshapes=blendshapes_dict,
            key_points=key_points,
            metadata={
                "landmark_count": len(raw_landmarks),
                "width_norm": width_norm,
            },
        )

    def compute_face_quality(
        self,
        landmarks: List[Tuple[float, float, float]],
        width_norm: float,
        chin: Tuple[float, float, float],
        forehead: Tuple[float, float, float],
        eye_l: Tuple[float, float, float],
        eye_r: Tuple[float, float, float],
        nose: Tuple[float, float, float],
    ) -> float:
        """
        Calculates face.quality in [0.0, 1.0].

        Combines size score (multiplicative gate), pose sanity, and viewport containment.
        """
        # 1. Face Size Score: Optimal width_norm is ~0.35
        if width_norm < 0.10:
            size_score = 0.0
        elif width_norm < 0.20:
            size_score = (width_norm - 0.10) / 0.10
        elif width_norm <= 0.65:
            size_score = 1.0
        elif width_norm <= 0.85:
            size_score = 1.0 - (width_norm - 0.65) / 0.20
        else:
            size_score = 0.0

        # 2. Pose Sanity (Tilt & Pitch)
        dx_eyes = eye_r[0] - eye_l[0]
        dy_eyes = eye_r[1] - eye_l[1]
        tilt_angle_rad = abs(math.atan2(dy_eyes, dx_eyes)) if abs(dx_eyes) > 1e-5 else 0.0
        tilt_score = max(0.0, min(1.0, 1.0 - (tilt_angle_rad / (math.pi / 4.0))))

        pitch_score = 1.0 if chin[1] > forehead[1] else 0.0
        pose_score = (tilt_score * 0.7) + (pitch_score * 0.3)

        # 3. Viewport Containment
        inside_box = (
            0.02 <= nose[0] <= 0.98
            and 0.02 <= nose[1] <= 0.98
            and 0.02 <= chin[1] <= 0.98
            and 0.02 <= forehead[1] <= 0.98
        )
        boundary_score = 1.0 if inside_box else 0.2

        base_quality = (0.60 * pose_score) + (0.40 * boundary_score)
        final_quality = size_score * base_quality
        return float(np.clip(final_quality, 0.0, 1.0))

    def draw_debug_landmarks(
        self,
        frame: np.ndarray,
        result: FaceMeshResult,
        show_keypoints: bool = True,
    ) -> np.ndarray:
        """Renders debug visual feedback directly on the OpenCV frame."""
        if frame is None or not result.detected:
            return frame

        h, w = frame.shape[:2]

        if show_keypoints and result.key_points:
            for name, (nx, ny) in result.key_points.items():
                px, py = int(nx * w), int(ny * h)
                color = (0, 255, 0) if "eye" in name else (255, 100, 0)
                if "nose" in name:
                    color = (0, 0, 255)
                    cv2.circle(frame, (px, py), 5, color, -1)
                else:
                    cv2.circle(frame, (px, py), 3, color, -1)

        quality_str = f"Quality: {result.quality:.2f}"
        q_color = (0, 255, 0) if result.quality >= 0.7 else (0, 165, 255) if result.quality >= 0.5 else (0, 0, 255)
        cv2.putText(frame, quality_str, (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.6, q_color, 2)
        cv2.putText(frame, f"Proc: {result.process_ms:.1f}ms", (10, 85), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 200, 200), 1)

        return frame

    def close(self) -> None:
        if self._landmarker is not None:
            try:
                self._landmarker.close()
            except Exception:
                pass
            self._landmarker = None
        if self._legacy_mesh is not None:
            try:
                self._legacy_mesh.close()
            except Exception:
                pass
            self._legacy_mesh = None
