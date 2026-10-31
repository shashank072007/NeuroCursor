"""
Facial expression and physical gesture detection module for FLUX / NeuroCursor.

Detects expressions strictly matching the shared enum:
    none, mouth_open, brow_raise, smile, wink_left, wink_right
Filters ordinary involuntary blinks, computes calibration-relative scores,
and enforces debounce stability with continuous held_ms progression.
Vision strictly emits physical expressions and never maps them to clicks.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from vision.calibration import CalibrationProfile
from vision.landmarks import FaceMeshResult, LandmarkIndex


class GestureEnum(str, Enum):
    NONE = "none"
    MOUTH_OPEN = "mouth_open"
    BROW_RAISE = "brow_raise"
    SMILE = "smile"
    WINK_LEFT = "wink_left"
    WINK_RIGHT = "wink_right"


@dataclass
class GestureResult:
    """Encapsulates the detected physical expression and hold duration."""
    name: str  # Strictly one of GestureEnum values
    score: float  # In [0.0, 1.0]
    held_ms: int  # Continuous duration since activation in milliseconds
    raw_scores: Dict[str, float] = field(default_factory=dict)

    @classmethod
    def create_none(cls) -> GestureResult:
        """Null/resting gesture output."""
        return cls(name=GestureEnum.NONE.value, score=0.0, held_ms=0, raw_scores={})


class GestureDetector:
    """
    Detects facial expressions, suppresses bilateral blinks, and debounces gestures.
    """

    # Activation thresholds for expressions
    THRESHOLDS = {
        GestureEnum.MOUTH_OPEN.value: 0.32,
        GestureEnum.BROW_RAISE.value: 0.32,
        GestureEnum.SMILE.value: 0.35,
        GestureEnum.WINK_LEFT.value: 0.38,
        GestureEnum.WINK_RIGHT.value: 0.38,
    }

    # Hysteresis release threshold
    RELEASE_RATIO = 0.70

    def __init__(
        self,
        profile: Optional[CalibrationProfile] = None,
        activation_frames: int = 2,  # ~60ms at 30 FPS to filter single-frame glitches
        release_frames: int = 2,     # ~60ms to prevent release flutter
    ) -> None:
        self.profile = profile or CalibrationProfile()
        self.activation_frames = activation_frames
        self.release_frames = release_frames

        # State machine tracking
        self.current_active: str = GestureEnum.NONE.value
        self.active_start_time: Optional[float] = None
        self.active_score: float = 0.0

        self.candidate_name: str = GestureEnum.NONE.value
        self.candidate_frame_count: int = 0
        self.release_frame_count: int = 0

    def set_profile(self, profile: CalibrationProfile) -> None:
        self.profile = profile
        self.reset()

    def reset(self) -> None:
        """Resets the debounce state machine."""
        self.current_active = GestureEnum.NONE.value
        self.active_start_time = None
        self.active_score = 0.0
        self.candidate_name = GestureEnum.NONE.value
        self.candidate_frame_count = 0
        self.release_frame_count = 0

    def update(
        self,
        face_result: FaceMeshResult,
        timestamp: Optional[float] = None,
    ) -> GestureResult:
        """
        Updates gesture state from latest FaceMeshResult.

        Strict contract:
        - If face_result.detected == False: reset state, return create_none().
        - Involuntary bilateral blinks are strictly suppressed (never emit as winks).
        - Filter 1-frame spikes via activation debounce.
        - Track continuous held_ms while active.
        """
        if not face_result.detected or face_result.quality < 0.45:
            self.reset()
            return GestureResult.create_none()

        t = timestamp if timestamp is not None else time.time()

        # 1. Compute raw expression scores from blendshapes and landmark ratios
        raw_scores = self._compute_expression_scores(face_result)

        # 2. Select the top candidate expression exceeding threshold
        candidate, candidate_score = self._select_candidate(raw_scores)

        # 3. Apply debounce state machine
        if self.current_active == GestureEnum.NONE.value:
            # Currently idle: look for sustained activation
            if candidate != GestureEnum.NONE.value:
                if candidate == self.candidate_name:
                    self.candidate_frame_count += 1
                else:
                    self.candidate_name = candidate
                    self.candidate_frame_count = 1

                if self.candidate_frame_count >= self.activation_frames:
                    # Transition to active gesture!
                    self.current_active = candidate
                    self.active_start_time = t
                    self.active_score = candidate_score
                    self.candidate_name = GestureEnum.NONE.value
                    self.candidate_frame_count = 0
                    self.release_frame_count = 0
            else:
                self.candidate_name = GestureEnum.NONE.value
                self.candidate_frame_count = 0

        else:
            # Currently active gesture: track hold or release
            threshold = self.THRESHOLDS.get(self.current_active, 0.40) * self.RELEASE_RATIO
            current_score = raw_scores.get(self.current_active, 0.0)

            if current_score >= threshold:
                # Still being held
                self.active_score = current_score
                self.release_frame_count = 0
            else:
                # Expression dropped below release threshold
                self.release_frame_count += 1
                if self.release_frame_count >= self.release_frames:
                    # Transition back to none
                    self.current_active = GestureEnum.NONE.value
                    self.active_start_time = None
                    self.active_score = 0.0
                    self.release_frame_count = 0

        # 4. Compute held_ms progression
        if self.current_active != GestureEnum.NONE.value and self.active_start_time is not None:
            held_ms = int(max(0.0, (t - self.active_start_time) * 1000.0))
            return GestureResult(
                name=self.current_active,
                score=round(self.active_score, 2),
                held_ms=held_ms,
                raw_scores={k: round(v, 2) for k, v in raw_scores.items()},
            )

        return GestureResult(
            name=GestureEnum.NONE.value,
            score=0.0,
            held_ms=0,
            raw_scores={k: round(v, 2) for k, v in raw_scores.items()},
        )

    def _select_candidate(self, raw_scores: Dict[str, float]) -> Tuple[str, float]:
        """Finds candidate with highest score meeting its activation threshold."""
        best_name = GestureEnum.NONE.value
        best_score = 0.0

        for name, thresh in self.THRESHOLDS.items():
            score = raw_scores.get(name, 0.0)
            if score >= thresh and score > best_score:
                best_name = name
                best_score = score

        return best_name, best_score

    def _compute_expression_scores(self, face_result: FaceMeshResult) -> Dict[str, float]:
        """
        Fuses MediaPipe blendshapes and calibrated landmark geometry.
        Strictly enforces bilateral blink suppression.
        """
        scores: Dict[str, float] = {
            GestureEnum.MOUTH_OPEN.value: 0.0,
            GestureEnum.BROW_RAISE.value: 0.0,
            GestureEnum.SMILE.value: 0.0,
            GestureEnum.WINK_LEFT.value: 0.0,
            GestureEnum.WINK_RIGHT.value: 0.0,
        }

        blend = face_result.blendshapes
        landmarks = face_result.landmarks

        # A. Eye blink & Wink calculations
        blink_l = blend.get("eyeBlinkLeft", 0.0) if blend else 0.0
        blink_r = blend.get("eyeBlinkRight", 0.0) if blend else 0.0

        if landmarks and not blend:
            # Fallback to Eye Aspect Ratio from landmarks
            ear_l, ear_r = self._calc_ears(landmarks)
            ref_ear_l = max(0.1, self.profile.neutral_left_ear)
            ref_ear_r = max(0.1, self.profile.neutral_right_ear)
            # Invert EAR to get blink score
            blink_l = float(np.clip(1.0 - (ear_l / ref_ear_l), 0.0, 1.0))
            blink_r = float(np.clip(1.0 - (ear_r / ref_ear_r), 0.0, 1.0))

        # --- BILATERAL BLINK SUPPRESSION (REQ-EXP-02) ---
        # When both eyes close simultaneously (ordinary involuntary blink):
        # Asymmetry is low and both blink scores are significant.
        asymmetry = abs(blink_l - blink_r)
        is_bilateral_blink = (blink_l > 0.40 and blink_r > 0.40 and asymmetry < 0.28)

        if not is_bilateral_blink:
            # True asymmetric wink: one eye closed (>0.50), other eye open (<0.35)
            if blink_l > 0.50 and blink_r < 0.35:
                scores[GestureEnum.WINK_LEFT.value] = float(np.clip(blink_l * (1.0 - blink_r * 1.5), 0.0, 1.0))
            elif blink_r > 0.50 and blink_l < 0.35:
                scores[GestureEnum.WINK_RIGHT.value] = float(np.clip(blink_r * (1.0 - blink_l * 1.5), 0.0, 1.0))

        # B. Mouth Open Calculation
        if blend and "jawOpen" in blend:
            scores[GestureEnum.MOUTH_OPEN.value] = blend["jawOpen"]
        elif landmarks:
            m_ratio = self._calc_mouth_ratio(landmarks)
            ref_m = max(0.02, self.profile.neutral_mouth_ratio)
            # Relative increase over resting mouth ratio
            if m_ratio > ref_m:
                scores[GestureEnum.MOUTH_OPEN.value] = float(np.clip((m_ratio - ref_m) / (ref_m * 3.0), 0.0, 1.0))

        # C. Brow Raise Calculation
        if blend and ("browInnerUp" in blend or "browOuterUpLeft" in blend):
            inner = blend.get("browInnerUp", 0.0)
            outer = max(blend.get("browOuterUpLeft", 0.0), blend.get("browOuterUpRight", 0.0))
            scores[GestureEnum.BROW_RAISE.value] = max(inner, outer)
        elif landmarks:
            b_ratio = self._calc_brow_ratio(landmarks)
            ref_b = max(0.1, self.profile.neutral_brow_ratio)
            if b_ratio > ref_b:
                scores[GestureEnum.BROW_RAISE.value] = float(np.clip((b_ratio - ref_b) / (ref_b * 0.40), 0.0, 1.0))

        # D. Smile Calculation
        if blend and ("mouthSmileLeft" in blend and "mouthSmileRight" in blend):
            smile_avg = (blend["mouthSmileLeft"] + blend["mouthSmileRight"]) / 2.0
            scores[GestureEnum.SMILE.value] = smile_avg
        elif landmarks:
            # Check mouth width expansion relative to face width
            corner_l = landmarks[LandmarkIndex.MOUTH_CORNER_LEFT]
            corner_r = landmarks[LandmarkIndex.MOUTH_CORNER_RIGHT]
            mouth_w = math.hypot(corner_r[0] - corner_l[0], corner_r[1] - corner_l[1])
            face_w = max(0.1, face_result.width_norm or self.profile.face_width_ref)
            smile_ratio = mouth_w / face_w
            if smile_ratio > 0.48:
                scores[GestureEnum.SMILE.value] = float(np.clip((smile_ratio - 0.48) / 0.15, 0.0, 1.0))

        return scores

    @staticmethod
    def _calc_mouth_ratio(landmarks: List[Tuple[float, float, float]]) -> float:
        inner_top = landmarks[LandmarkIndex.LIP_TOP_INNER]
        inner_bottom = landmarks[LandmarkIndex.LIP_BOTTOM_INNER]
        corner_l = landmarks[LandmarkIndex.MOUTH_CORNER_LEFT]
        corner_r = landmarks[LandmarkIndex.MOUTH_CORNER_RIGHT]
        h = abs(inner_bottom[1] - inner_top[1])
        w = max(1e-4, math.hypot(corner_r[0] - corner_l[0], corner_r[1] - corner_l[1]))
        return h / w

    @staticmethod
    def _calc_brow_ratio(landmarks: List[Tuple[float, float, float]]) -> float:
        brow_l = landmarks[LandmarkIndex.LEFT_BROW_MID]
        eye_l_top = landmarks[LandmarkIndex.LEFT_EYE_TOP]
        chin = landmarks[LandmarkIndex.CHIN]
        forehead = landmarks[LandmarkIndex.FOREHEAD]
        brow_dist = abs(eye_l_top[1] - brow_l[1])
        face_h = max(1e-4, abs(chin[1] - forehead[1]))
        return brow_dist / face_h

    @staticmethod
    def _calc_ears(landmarks: List[Tuple[float, float, float]]) -> Tuple[float, float]:
        def calc_ear(top_idx: int, bot_idx: int, outer_idx: int, inner_idx: int) -> float:
            h = abs(landmarks[bot_idx][1] - landmarks[top_idx][1])
            w = max(1e-4, math.hypot(landmarks[outer_idx][0] - landmarks[inner_idx][0], landmarks[outer_idx][1] - landmarks[inner_idx][1]))
            return h / w

        l = calc_ear(LandmarkIndex.LEFT_EYE_TOP, LandmarkIndex.LEFT_EYE_BOTTOM, LandmarkIndex.LEFT_EYE_OUTER, LandmarkIndex.LEFT_EYE_INNER)
        r = calc_ear(LandmarkIndex.RIGHT_EYE_TOP, LandmarkIndex.RIGHT_EYE_BOTTOM, LandmarkIndex.RIGHT_EYE_OUTER, LandmarkIndex.RIGHT_EYE_INNER)
        return l, r
