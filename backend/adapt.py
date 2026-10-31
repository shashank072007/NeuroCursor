"""Adaptation Engine, UI State Generation, and Drift Re-centring.
Reference: Section B7 & Section F.
Maps discrete fatigue levels to UI and control parameters.
Manages continuous gain, static/flux modes, drift correction,
and pushes internal vision_params to control_q.
"""

import time
import math
from typing import Dict, Any, Optional, Tuple, Callable
from .config import (
    DRIFT_EDGE_MARGIN, DRIFT_HOLD_S, DRIFT_RATE
)
from .bus import make_msg

ADAPTATION_TABLE = {
    "fresh": {
        "target_scale": 1.0,
        "dwell_ms": 800,
        "radial_bubbles": 6,
        "smoothing_alpha": 0.35,
        "gesture_threshold_mult": 1.0,
        "gesture_hold_ms": 150
    },
    "moderate": {
        "target_scale": 1.25,
        "dwell_ms": 1000,
        "radial_bubbles": 6,
        "smoothing_alpha": 0.28,
        "gesture_threshold_mult": 0.95,
        "gesture_hold_ms": 180
    },
    "high": {
        "target_scale": 1.5,
        "dwell_ms": 1300,
        "radial_bubbles": 4,
        "smoothing_alpha": 0.20,
        "gesture_threshold_mult": 0.90,
        "gesture_hold_ms": 220
    },
    "rest": {
        "target_scale": 1.8,
        "dwell_ms": 1600,
        "radial_bubbles": 3,
        "smoothing_alpha": 0.15,
        "gesture_threshold_mult": 0.85,
        "gesture_hold_ms": 260
    }
}


class AdaptiveEngine:
    """Computes ui_state adaptations and neutral drift re-centring."""

    def __init__(self, on_vision_params: Optional[Callable[[Dict[str, Any]], None]] = None):
        self.on_vision_params = on_vision_params
        self.mode: str = "flux"  # flux | static
        self.primary_channel: str = "gesture"
        self.suggest_channel: Optional[str] = None

        # Continuous gain & drift
        self.gain: float = 1.0
        self.neutral_shift = {"dx": 0.0, "dy": 0.0}

        # Drift tracking
        self._drift_edge_start: Optional[float] = None
        self._last_head_dx: float = 0.0
        self._last_head_dy: float = 0.0

        # Last emitted ui_state cache for change-detection
        self._last_ui_state: Optional[Dict[str, Any]] = None

    def set_mode(self, new_mode: str) -> None:
        if new_mode in ("flux", "static"):
            self.mode = new_mode

    def update_drift(self, nx: float, ny: float, raw_dx: float, raw_dy: float, last_click_time: float, now: float) -> bool:
        """Evaluate drift re-centring: pointer within 3% of edge for 5s with no clicks."""
        is_near_edge = (nx <= DRIFT_EDGE_MARGIN or nx >= (1.0 - DRIFT_EDGE_MARGIN) or
                        ny <= DRIFT_EDGE_MARGIN or ny >= (1.0 - DRIFT_EDGE_MARGIN))

        no_click_recently = (now - last_click_time) >= DRIFT_HOLD_S

        self._last_head_dx = raw_dx
        self._last_head_dy = raw_dy

        if is_near_edge and no_click_recently:
            if self._drift_edge_start is None:
                self._drift_edge_start = now
            elif (now - self._drift_edge_start) >= DRIFT_HOLD_S:
                # Shift neutral 1% per second towards head offset
                step = DRIFT_RATE * 0.033  # per-frame step (~30Hz)
                if abs(raw_dx) > 0.001:
                    self.neutral_shift["dx"] = round(self.neutral_shift["dx"] + math.copysign(step, raw_dx), 4)
                if abs(raw_dy) > 0.001:
                    self.neutral_shift["dy"] = round(self.neutral_shift["dy"] + math.copysign(step, raw_dy), 4)
                return True
        else:
            self._drift_edge_start = None

        return False

    def compute_ui_state(self, level: str, range_now: float, profile: Dict[str, Any]) -> Tuple[Dict[str, Any], bool]:
        """Compute the current ui_state and determine if it meaningfully changed."""
        effective_level = "fresh" if self.mode == "static" else level
        params = ADAPTATION_TABLE.get(effective_level, ADAPTATION_TABLE["fresh"])

        # Continuous gain = clamp(1 / range_now, 1.0, 1.35) — capped to avoid hypersensitive pointing
        r_now = max(0.01, range_now)
        new_gain = round(max(1.0, min(1.35, 1.0 / r_now)), 2)

        # In static mode, lens is disabled and suggest_channel is never sent
        if self.mode == "static":
            lens_block = {"enabled": False, "slow_speed": 0.05, "dwell_to_open_ms": 400}
            suggest = None
        else:
            lens_block = {"enabled": True, "slow_speed": 0.05, "dwell_to_open_ms": 400}
            suggest = self.suggest_channel

        ui_state = make_msg(
            "ui_state",
            level=effective_level,
            target_scale=params["target_scale"],
            dwell_ms=params["dwell_ms"],
            radial_bubbles=params["radial_bubbles"],
            smoothing_alpha=params["smoothing_alpha"],
            gain=new_gain,
            gesture_threshold_mult=params["gesture_threshold_mult"],
            gesture_hold_ms=params["gesture_hold_ms"],
            lens=lens_block,
            primary_channel=self.primary_channel,
            suggest_channel=suggest
        )

        changed = False
        if self._last_ui_state is None:
            changed = True
        else:
            # Compare fields
            old = self._last_ui_state
            if (old.get("level") != ui_state["level"] or
                old.get("target_scale") != ui_state["target_scale"] or
                old.get("dwell_ms") != ui_state["dwell_ms"] or
                old.get("radial_bubbles") != ui_state["radial_bubbles"] or
                old.get("smoothing_alpha") != ui_state["smoothing_alpha"] or
                old.get("gesture_threshold_mult") != ui_state["gesture_threshold_mult"] or
                old.get("gesture_hold_ms") != ui_state["gesture_hold_ms"] or
                old.get("primary_channel") != ui_state["primary_channel"] or
                old.get("suggest_channel") != ui_state["suggest_channel"] or
                old.get("lens", {}).get("enabled") != ui_state["lens"]["enabled"] or
                abs(old.get("gain", 1.0) - ui_state["gain"]) >= 0.02):
                changed = True

        if changed:
            self._last_ui_state = ui_state
            self.gain = new_gain
            # Push internal vision_params to Vision
            self._emit_vision_params(params["smoothing_alpha"], new_gain, profile)

        return ui_state, changed

    def _emit_vision_params(self, alpha: float, gain: float, profile: Dict[str, Any]) -> None:
        if self.on_vision_params:
            thresholds = profile.get("gesture_thresholds", {
                "mouth_open": 0.55, "brow_raise": 0.60, "smile": 0.50
            })
            vp = make_msg(
                "vision_params",
                alpha=alpha,
                gain=gain,
                neutral_shift=self.neutral_shift,
                thresholds=thresholds,
                mirror=True
            )
            self.on_vision_params(vp)
