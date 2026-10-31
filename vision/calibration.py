"""
Calibration module for FLUX / NeuroCursor.

Provides guided neutral pose collection, comfortable range estimation
with skip/retry options, and profile persistence to calibration.json.
"""

from __future__ import annotations

import json
import math
import os
import time
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from vision.landmarks import FaceMeshResult, LandmarkIndex


@dataclass
class CalibrationProfile:
    """Stores calibrated resting head pose, face width, and comfortable movement ranges."""
    neutral_x: float = 0.50
    neutral_y: float = 0.50
    face_width_ref: float = 0.35

    # Comfortable excursion ranges in face-width units
    range_left: float = 0.25
    range_right: float = 0.25
    range_up: float = 0.20
    range_down: float = 0.20

    # Baseline expression ratios collected during neutral rest
    neutral_mouth_ratio: float = 0.05
    neutral_brow_ratio: float = 0.22
    neutral_left_ear: float = 0.28
    neutral_right_ear: float = 0.28

    timestamp: float = field(default_factory=time.time)
    is_calibrated: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> CalibrationProfile:
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})

    def save(self, filepath: str) -> None:
        """Persists profile to disk as JSON."""
        os.makedirs(os.path.dirname(os.path.abspath(filepath)), exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2)

    @classmethod
    def load(cls, filepath: str) -> Optional[CalibrationProfile]:
        """Loads profile from JSON file if it exists."""
        if not os.path.isfile(filepath):
            return None
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
            return cls.from_dict(data)
        except Exception:
            return None


class CalibrationStep(str, Enum):
    IDLE = "idle"
    COLLECTING_NEUTRAL = "collecting_neutral"
    RANGE_LEFT = "range_left"
    RANGE_RIGHT = "range_right"
    RANGE_UP = "range_up"
    RANGE_DOWN = "range_down"
    COMPLETE = "complete"


class CalibrationManager:
    """Guides the user through neutral pose and range calibration with skip/retry."""

    # Default conservative ranges in face-width units
    DEFAULT_RANGES = {
        "left": 0.25,
        "right": 0.25,
        "up": 0.20,
        "down": 0.20,
    }

    def __init__(self, profile_path: Optional[str] = None) -> None:
        self.profile_path = profile_path or os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "calibration.json"
        )
        self.profile = CalibrationProfile.load(self.profile_path) or CalibrationProfile()
        self.step: CalibrationStep = CalibrationStep.IDLE
        self._step_start_time: float = 0.0
        self._step_duration_sec: float = 2.0

        # Buffers for collecting samples
        self._neutral_samples_x: List[float] = []
        self._neutral_samples_y: List[float] = []
        self._neutral_samples_w: List[float] = []
        self._neutral_mouth_ratios: List[float] = []
        self._neutral_brow_ratios: List[float] = []
        self._neutral_left_ears: List[float] = []
        self._neutral_right_ears: List[float] = []

        self._range_samples: List[float] = []

    def start_neutral(self, duration_sec: float = 1.5) -> None:
        """Begins collecting neutral resting face samples."""
        self.step = CalibrationStep.COLLECTING_NEUTRAL
        self._step_start_time = time.time()
        self._step_duration_sec = duration_sec
        self._clear_neutral_buffers()

    def start_range(self, direction: str, duration_sec: float = 2.0) -> None:
        """Begins collecting excursion range for a specific direction (left/right/up/down)."""
        mapping = {
            "left": CalibrationStep.RANGE_LEFT,
            "right": CalibrationStep.RANGE_RIGHT,
            "up": CalibrationStep.RANGE_UP,
            "down": CalibrationStep.RANGE_DOWN,
        }
        if direction not in mapping:
            raise ValueError(f"Unknown direction: {direction}. Use left, right, up, down.")

        self.step = mapping[direction]
        self._step_start_time = time.time()
        self._step_duration_sec = duration_sec
        self._range_samples.clear()

    def add_frame(self, face_result: FaceMeshResult) -> Tuple[bool, str]:
        """
        Processes a single frame for the current calibration step.

        Returns:
            Tuple of (step_finished: bool, message: str)
        """
        if self.step == CalibrationStep.IDLE:
            return False, "Calibration idle."

        if self.step == CalibrationStep.COMPLETE:
            return True, "Calibration complete."

        elapsed = time.time() - self._step_start_time
        remaining = max(0.0, self._step_duration_sec - elapsed)
        if not face_result.detected or face_result.quality < 0.5:
            if elapsed < self._step_duration_sec:
                return False, "Face not detected or quality too low; please face the camera."
            # Close an expired step even when tracking was lost so the caller can
            # report insufficient samples instead of silently advancing forever.
            if self.step == CalibrationStep.COLLECTING_NEUTRAL and self._neutral_samples_x:
                self._finish_neutral()
            elif self.step in (CalibrationStep.RANGE_LEFT, CalibrationStep.RANGE_RIGHT,
                               CalibrationStep.RANGE_UP, CalibrationStep.RANGE_DOWN) and self._range_samples:
                self._finish_range(self.step.value.replace("range_", ""))
            else:
                self.step = CalibrationStep.IDLE
            return True, "Calibration step ended without a valid face sample."

        if self.step == CalibrationStep.COLLECTING_NEUTRAL:
            if face_result.center_x is not None and face_result.center_y is not None and face_result.width_norm is not None:
                self._neutral_samples_x.append(face_result.center_x)
                self._neutral_samples_y.append(face_result.center_y)
                self._neutral_samples_w.append(face_result.width_norm)

                # Sample baseline ratios if landmarks are available
                if face_result.landmarks:
                    m_ratio, b_ratio, l_ear, r_ear = self._extract_ratios(face_result.landmarks)
                    self._neutral_mouth_ratios.append(m_ratio)
                    self._neutral_brow_ratios.append(b_ratio)
                    self._neutral_left_ears.append(l_ear)
                    self._neutral_right_ears.append(r_ear)

            if elapsed >= self._step_duration_sec:
                self._finish_neutral()
                return True, "Neutral calibration complete."
            return False, f"Keep looking straight ahead ({remaining:.1f}s)..."

        # Range collection steps
        if self.step in (CalibrationStep.RANGE_LEFT, CalibrationStep.RANGE_RIGHT, CalibrationStep.RANGE_UP, CalibrationStep.RANGE_DOWN):
            if face_result.center_x is not None and face_result.center_y is not None:
                ref_w = max(0.1, self.profile.face_width_ref)
                dx_units = (face_result.center_x - self.profile.neutral_x) / ref_w
                dy_units = (face_result.center_y - self.profile.neutral_y) / ref_w

                if self.step == CalibrationStep.RANGE_LEFT:
                    # Moving left on screen corresponds to dx < 0
                    self._range_samples.append(abs(min(0.0, dx_units)))
                elif self.step == CalibrationStep.RANGE_RIGHT:
                    self._range_samples.append(max(0.0, dx_units))
                elif self.step == CalibrationStep.RANGE_UP:
                    # Moving up on screen corresponds to dy < 0
                    self._range_samples.append(abs(min(0.0, dy_units)))
                elif self.step == CalibrationStep.RANGE_DOWN:
                    self._range_samples.append(max(0.0, dy_units))

            if elapsed >= self._step_duration_sec:
                direction_name = self.step.value.replace("range_", "")
                self._finish_range(direction_name)
                return True, f"Range for {direction_name} captured."
            return False, f"Comfortably move {self.step.value.replace('range_', '')} ({remaining:.1f}s)..."

        return False, ""

    def skip_step(self) -> str:
        """Skips the active calibration step and applies conservative safe defaults."""
        if self.step == CalibrationStep.COLLECTING_NEUTRAL:
            self.profile.neutral_x = 0.50
            self.profile.neutral_y = 0.50
            self.profile.face_width_ref = 0.35
            self.step = CalibrationStep.IDLE
            return "Neutral skipped; applied default center."

        if self.step in (CalibrationStep.RANGE_LEFT, CalibrationStep.RANGE_RIGHT, CalibrationStep.RANGE_UP, CalibrationStep.RANGE_DOWN):
            dir_name = self.step.value.replace("range_", "")
            setattr(self.profile, f"range_{dir_name}", self.DEFAULT_RANGES[dir_name])
            self.step = CalibrationStep.IDLE
            return f"Range for {dir_name} skipped; applied default {self.DEFAULT_RANGES[dir_name]}."

        return "No active step to skip."

    def retry_step(self) -> str:
        """Clears current step buffers and restarts timer."""
        if self.step == CalibrationStep.COLLECTING_NEUTRAL:
            self.start_neutral(self._step_duration_sec)
            return "Retrying neutral calibration."

        if self.step in (CalibrationStep.RANGE_LEFT, CalibrationStep.RANGE_RIGHT, CalibrationStep.RANGE_UP, CalibrationStep.RANGE_DOWN):
            dir_name = self.step.value.replace("range_", "")
            self.start_range(dir_name, self._step_duration_sec)
            return f"Retrying range for {dir_name}."

        return "No active step to retry."

    def _finish_neutral(self) -> None:
        """Computes trimmed mean of collected neutral samples."""
        if self._neutral_samples_x:
            self.profile.neutral_x = float(np.median(self._neutral_samples_x))
            self.profile.neutral_y = float(np.median(self._neutral_samples_y))
            self.profile.face_width_ref = float(np.median(self._neutral_samples_w))

        if self._neutral_mouth_ratios:
            self.profile.neutral_mouth_ratio = float(np.median(self._neutral_mouth_ratios))
        if self._neutral_brow_ratios:
            self.profile.neutral_brow_ratio = float(np.median(self._neutral_brow_ratios))
        if self._neutral_left_ears:
            self.profile.neutral_left_ear = float(np.median(self._neutral_left_ears))
        if self._neutral_right_ears:
            self.profile.neutral_right_ear = float(np.median(self._neutral_right_ears))

        self.step = CalibrationStep.IDLE

    def _finish_range(self, direction: str) -> None:
        """Estimates comfortable range from the 90th percentile peak excursion."""
        if self._range_samples:
            # 90th percentile avoids single-frame glitch peaks while capturing true comfortable reach
            peak = float(np.percentile(self._range_samples, 90))
            # Floor at 0.10 to prevent division by zero or hypersensitive cursor
            peak = max(0.10, peak)
        else:
            peak = self.DEFAULT_RANGES[direction]

        setattr(self.profile, f"range_{direction}", round(peak, 3))
        self.step = CalibrationStep.IDLE

    def finish_all_and_save(self) -> CalibrationProfile:
        """Marks profile complete and writes to calibration.json."""
        self.profile.is_calibrated = True
        self.profile.timestamp = time.time()
        self.profile.save(self.profile_path)
        self.step = CalibrationStep.COMPLETE
        return self.profile

    def _clear_neutral_buffers(self) -> None:
        self._neutral_samples_x.clear()
        self._neutral_samples_y.clear()
        self._neutral_samples_w.clear()
        self._neutral_mouth_ratios.clear()
        self._neutral_brow_ratios.clear()
        self._neutral_left_ears.clear()
        self._neutral_right_ears.clear()

    @staticmethod
    def _extract_ratios(landmarks: List[Tuple[float, float, float]]) -> Tuple[float, float, float, float]:
        """Calculates mouth aspect ratio, brow elevation ratio, and left/right EAR."""
        # 1. Mouth ratio: inner lip height / mouth width
        inner_top = landmarks[LandmarkIndex.LIP_TOP_INNER]
        inner_bottom = landmarks[LandmarkIndex.LIP_BOTTOM_INNER]
        corner_l = landmarks[LandmarkIndex.MOUTH_CORNER_LEFT]
        corner_r = landmarks[LandmarkIndex.MOUTH_CORNER_RIGHT]
        lip_height = abs(inner_bottom[1] - inner_top[1])
        lip_width = max(1e-4, math.hypot(corner_r[0] - corner_l[0], corner_r[1] - corner_l[1]))
        mouth_ratio = lip_height / lip_width

        # 2. Brow ratio: vertical distance from brow to eye / face height
        brow_l = landmarks[LandmarkIndex.LEFT_BROW_MID]
        eye_l_top = landmarks[LandmarkIndex.LEFT_EYE_TOP]
        brow_dist = abs(eye_l_top[1] - brow_l[1])
        chin = landmarks[LandmarkIndex.CHIN]
        forehead = landmarks[LandmarkIndex.FOREHEAD]
        face_h = max(1e-4, abs(chin[1] - forehead[1]))
        brow_ratio = brow_dist / face_h

        # 3. Eye Aspect Ratio (EAR) for left & right
        def calc_ear(top_idx: int, bot_idx: int, outer_idx: int, inner_idx: int) -> float:
            h = abs(landmarks[bot_idx][1] - landmarks[top_idx][1])
            w = max(1e-4, math.hypot(landmarks[outer_idx][0] - landmarks[inner_idx][0], landmarks[outer_idx][1] - landmarks[inner_idx][1]))
            return h / w

        left_ear = calc_ear(LandmarkIndex.LEFT_EYE_TOP, LandmarkIndex.LEFT_EYE_BOTTOM, LandmarkIndex.LEFT_EYE_OUTER, LandmarkIndex.LEFT_EYE_INNER)
        right_ear = calc_ear(LandmarkIndex.RIGHT_EYE_TOP, LandmarkIndex.RIGHT_EYE_BOTTOM, LandmarkIndex.RIGHT_EYE_OUTER, LandmarkIndex.RIGHT_EYE_INNER)

        return mouth_ratio, brow_ratio, left_ear, right_ear
