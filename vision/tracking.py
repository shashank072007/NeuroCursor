"""
Pointer tracking and ability signal module for FLUX / NeuroCursor.

Translates facial displacement relative to neutral calibration into:
1. Stable normalized pointer coordinates (nx, ny in [0, 1]) with One Euro Filter smoothing.
2. Separate, unsmoothed raw offsets (raw_dx, raw_dy in face-width units) for the backend's
   interaction-effort proxy (jitter and range-loss detection).
Coordinates are strictly normalized and never converted to screen pixels.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass
from typing import Optional, Tuple

import numpy as np

from vision.calibration import CalibrationProfile
from vision.landmarks import FaceMeshResult


class OneEuroFilter1D:
    """
    Adaptive low-pass filter (Casiez et al., CHI 2012).
    Reduces jitter at low speeds while eliminating lag during fast movements.
    """

    def __init__(
        self,
        min_cutoff: float = 1.0,
        beta: float = 0.007,
        d_cutoff: float = 1.0,
    ) -> None:
        self.min_cutoff = min_cutoff
        self.beta = beta
        self.d_cutoff = d_cutoff

        self.x_prev: Optional[float] = None
        self.dx_prev: float = 0.0
        self.t_prev: Optional[float] = None

    def filter(self, x: float, timestamp: Optional[float] = None) -> float:
        t = timestamp if timestamp is not None else time.time()

        if self.t_prev is None or self.x_prev is None:
            self.x_prev = x
            self.dx_prev = 0.0
            self.t_prev = t
            return x

        dt = max(1e-4, t - self.t_prev)

        # Estimate derivative (speed)
        dx = (x - self.x_prev) / dt
        edx = self._alpha(dt, self.d_cutoff) * dx + (1.0 - self._alpha(dt, self.d_cutoff)) * self.dx_prev

        # Dynamic cutoff frequency based on speed
        cutoff = self.min_cutoff + self.beta * abs(edx)

        # Filtered output value
        a = self._alpha(dt, cutoff)
        x_filtered = a * x + (1.0 - a) * self.x_prev

        # Update state
        self.x_prev = x_filtered
        self.dx_prev = edx
        self.t_prev = t

        return x_filtered

    def reset(self) -> None:
        self.x_prev = None
        self.dx_prev = 0.0
        self.t_prev = None

    @staticmethod
    def _alpha(dt: float, cutoff: float) -> float:
        tau = 1.0 / (2.0 * math.pi * cutoff)
        return 1.0 / (1.0 + tau / dt)


@dataclass
class TrackingResult:
    """Encapsulates normalized pointer coordinates and raw motion ability signals."""
    detected: bool
    nx: Optional[float]
    ny: Optional[float]
    raw_dx: Optional[float]
    raw_dy: Optional[float]
    filtered_dx: Optional[float] = None
    filtered_dy: Optional[float] = None

    @classmethod
    def create_null(cls) -> TrackingResult:
        """Strict null contract when face tracking is lost or poor quality."""
        return cls(
            detected=False,
            nx=None,
            ny=None,
            raw_dx=None,
            raw_dy=None,
            filtered_dx=None,
            filtered_dy=None,
        )


class PointerTracker:
    """
    Translates head displacement to normalized cursor coordinates and raw ability signals.
    """

    def __init__(
        self,
        profile: Optional[CalibrationProfile] = None,
        min_cutoff: float = 0.65,
        beta: float = 0.004,
    ) -> None:
        self.profile = profile or CalibrationProfile()
        self.manual_gain = 1.0
        self.adaptive_gain = 1.0

        # Independent One Euro Filters for X and Y coordinates
        self.filter_x = OneEuroFilter1D(min_cutoff=min_cutoff, beta=beta)
        self.filter_y = OneEuroFilter1D(min_cutoff=min_cutoff, beta=beta)

    def set_profile(self, profile: CalibrationProfile) -> None:
        self.profile = profile
        self.reset_filters()

    def set_user_sensitivity(self, value: float) -> None:
        """Set user gain from the UI's 10..100 sensitivity scale."""
        normalized = float(np.clip((float(value) - 10.0) / 90.0, 0.0, 1.0))
        self.manual_gain = 0.60 + normalized * 1.50

    def set_adaptation(self, gain: float, smoothing_alpha: float) -> None:
        """Apply backend adaptation parameters to the Python tracking filters."""
        new_gain = float(np.clip(gain, 0.75, 1.6))
        alpha = float(np.clip(smoothing_alpha, 0.08, 0.65))
        cutoff = (alpha / (1.0 - alpha)) * (30.0 / (2.0 * math.pi))
        changed = abs(new_gain - self.adaptive_gain) > 0.01 or abs(cutoff - self.filter_x.min_cutoff) > 0.05
        self.adaptive_gain = new_gain
        self.filter_x.min_cutoff = cutoff
        self.filter_y.min_cutoff = cutoff
        if changed:
            self.reset_filters()

    def reset_filters(self) -> None:
        self.filter_x.reset()
        self.filter_y.reset()

    def update(
        self,
        face_result: FaceMeshResult,
        timestamp: Optional[float] = None,
    ) -> TrackingResult:
        """
        Updates pointer state from latest FaceMeshResult.

        Strict contract:
        - If face_result.detected == False: returns create_null() and resets filter state.
        - nx, ny are smoothed and strictly clamped to [0.0, 1.0].
        - raw_dx, raw_dy remain unsmoothed in scale-invariant face-width units.
        - Never converts to screen pixels.
        """
        if not face_result.detected or face_result.center_x is None or face_result.center_y is None:
            self.reset_filters()
            return TrackingResult.create_null()

        t = timestamp if timestamp is not None else time.time()

        # 1. Calculate raw displacement relative to calibrated neutral pose
        dx_viewport = face_result.center_x - self.profile.neutral_x
        dy_viewport = face_result.center_y - self.profile.neutral_y

        # Scale by reference face width for scale-invariant displacement units
        ref_w = max(0.1, self.profile.face_width_ref)
        raw_dx = dx_viewport / ref_w
        raw_dy = dy_viewport / ref_w

        # 2. Map displacement to normalized viewport [0.0, 1.0] using calibrated ranges
        # Neutral center maps to (0.5, 0.5)
        # Horizontal mapping
        r_left = max(0.05, self.profile.range_left)
        r_right = max(0.05, self.profile.range_right)
        # Invert camera-frame X so a user's rightward head movement moves the
        # cursor right, matching the face-to-screen interaction convention.
        if raw_dx >= 0.0:
            target_nx = 0.50 - 0.50 * (raw_dx / r_right)
        else:
            target_nx = 0.50 + 0.50 * (abs(raw_dx) / r_left)

        # Vertical mapping
        r_up = max(0.05, self.profile.range_up)
        r_down = max(0.05, self.profile.range_down)
        if raw_dy >= 0.0:
            target_ny = 0.50 + 0.50 * (raw_dy / r_down)
        else:
            target_ny = 0.50 - 0.50 * (abs(raw_dy) / r_up)

        # Clamp target before smoothing
        combined_gain = self.manual_gain * self.adaptive_gain
        target_nx = float(np.clip(0.5 + (target_nx - 0.5) * combined_gain, 0.0, 1.0))
        target_ny = float(np.clip(0.5 + (target_ny - 0.5) * combined_gain, 0.0, 1.0))

        # 3. Apply One Euro Filter to eliminate jitter
        smoothed_nx = self.filter_x.filter(target_nx, t)
        smoothed_ny = self.filter_y.filter(target_ny, t)

        # Final boundary clamp
        final_nx = float(np.clip(smoothed_nx, 0.0, 1.0))
        final_ny = float(np.clip(smoothed_ny, 0.0, 1.0))

        return TrackingResult(
            detected=True,
            nx=round(final_nx, 3),
            ny=round(final_ny, 3),
            raw_dx=round(raw_dx, 4),
            raw_dy=round(raw_dy, 4),
        )
