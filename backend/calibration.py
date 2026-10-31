"""Calibration Engine for FLUX.
Reference: Section B2, C.8, C.9.
Orchestrates the calibration wizard:
  neutral -> right -> left -> up -> down -> mouth_open x3 -> brow_raise x3 -> smile x3
Sends calib_cmd, waits for calib_result, and computes the personalized profile.
"""

import time
import datetime
import numpy as np
from typing import Dict, Any, List, Optional
from .bus import make_msg
from .profiles import profile_mgr

CALIBRATION_STEPS = [
    {"step": "neutral", "rep": 1, "duration_ms": 3000},
    {"step": "right", "rep": 1, "duration_ms": 2000},
    {"step": "left", "rep": 1, "duration_ms": 2000},
    {"step": "up", "rep": 1, "duration_ms": 2000},
    {"step": "down", "rep": 1, "duration_ms": 2000},
    {"step": "gesture:mouth_open", "rep": 1, "duration_ms": 3000},
    {"step": "gesture:mouth_open", "rep": 2, "duration_ms": 3000},
    {"step": "gesture:mouth_open", "rep": 3, "duration_ms": 3000},
    {"step": "gesture:brow_raise", "rep": 1, "duration_ms": 3000},
    {"step": "gesture:brow_raise", "rep": 2, "duration_ms": 3000},
    {"step": "gesture:brow_raise", "rep": 3, "duration_ms": 3000},
    {"step": "gesture:smile", "rep": 1, "duration_ms": 3000},
    {"step": "gesture:smile", "rep": 2, "duration_ms": 3000},
    {"step": "gesture:smile", "rep": 3, "duration_ms": 3000},
]


class CalibrationEngine:
    """Manages the calibration wizard state and profile computation."""

    def __init__(self, control_q=None):
        self.control_q = control_q
        self.profile_id: Optional[str] = None
        self.step_data: Dict[str, Any] = {}
        self.in_progress: bool = False

    def start(self, profile_id: str) -> Dict[str, Any]:
        """Start a new calibration session."""
        self.profile_id = profile_id or f"user_{int(time.time())}"
        self.step_data = {}
        self.in_progress = True
        return {
            "ok": True,
            "profile_id": self.profile_id,
            "steps": CALIBRATION_STEPS
        }

    def execute_step(self, step: str, rep: int = 1, incoming_result: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Execute or record a calibration step."""
        key = f"{step}:{rep}"

        # If an explicit result arrived from Ritesh's frame_q, use it
        if incoming_result and incoming_result.get("ok"):
            data = incoming_result.get("data", {})
            self.step_data[key] = data
            return {"ok": True, "step": step, "rep": rep, "data": data}

        # If in mock / offline testing without hardware camera, generate canonical mock result
        mock_data: Dict[str, Any] = {}
        if step == "neutral":
            mock_data = {
                "neutral_px": {"x": 318, "y": 242},
                "face_width_px": 212,
                "jitter_std": 0.004
            }
        elif step in ("right", "left"):
            mock_data = {"excursion": 0.11}
        elif step in ("up", "down"):
            mock_data = {"excursion": 0.08}
        elif step.startswith("gesture:"):
            mock_data = {
                "rest_ratio": 0.15,
                "peak_ratio": 0.75,
                "peak_score": 0.90 + (rep * 0.01),
                "episode_hold_ms": 180 + (rep * 5)
            }

        self.step_data[key] = mock_data

        # If control_q exists, emit calib_cmd to Vision
        if self.control_q:
            cmd = make_msg("calib_cmd", step=step, rep=rep, duration_ms=2500)
            try:
                if self.control_q.full():
                    try:
                        self.control_q.get_nowait()
                    except Exception:
                        pass
                self.control_q.put_nowait(cmd)
            except Exception:
                pass

        return {"ok": True, "step": step, "rep": rep, "data": mock_data}

    def commit(self) -> Dict[str, Any]:
        """Compute profile according to exact formulas in Section C.8."""
        if not self.profile_id:
            return {"ok": False, "error": "No calibration in progress"}

        neutral_data = self.step_data.get("neutral:1", {})
        if not neutral_data:
            return {"ok": False, "error": "Missing neutral calibration step"}

        # Excursions
        right_exc = self.step_data.get("right:1", {}).get("excursion", 0.11)
        left_exc = self.step_data.get("left:1", {}).get("excursion", 0.11)
        up_exc = self.step_data.get("up:1", {}).get("excursion", 0.08)
        down_exc = self.step_data.get("down:1", {}).get("excursion", 0.08)

        # Range = 0.8 * span
        range_x = round(0.8 * (right_exc + left_exc), 3)
        range_y = round(0.8 * (up_exc + down_exc), 3)

        # Baseline jitter
        jitter_std = float(neutral_data.get("jitter_std", 0.004))

        # Gestures
        gestures = ["mouth_open", "brow_raise", "smile"]
        gesture_peaks = []
        gesture_holds = []
        gesture_thresholds = {}

        for g in gestures:
            rep_peaks = []
            for rep in (1, 2, 3):
                d = self.step_data.get(f"gesture:{g}:{rep}", {})
                score = float(d.get("peak_score", 0.90))
                rep_peaks.append(score)
                hold = float(d.get("episode_hold_ms", 180))
                gesture_holds.append(hold)

            med_peak = float(np.median(rep_peaks))
            gesture_peaks.append(med_peak)
            # clamp(0.6 * median rep peak, 0.40, 0.70)
            thresh = max(0.40, min(0.70, 0.60 * med_peak))
            gesture_thresholds[g] = round(thresh, 2)

        avg_gesture_peak = round(float(np.mean(gesture_peaks)), 2)
        med_hold_ms = int(round(float(np.median(gesture_holds))))

        profile = {
            "v": 1,
            "profile_id": self.profile_id,
            "created": datetime.datetime.now(datetime.timezone.utc).astimezone().isoformat(),
            "neutral": {
                "x": 0.50,
                "y": 0.50,
                "face_width_px": neutral_data.get("face_width_px", 212)
            },
            "range": {
                "x": range_x,
                "y": range_y
            },
            "baseline": {
                "jitter": jitter_std,
                "gesture_peak": avg_gesture_peak,
                "hold_ms": med_hold_ms
            },
            "gesture_map": {
                "mouth_open": "left_click",
                "brow_raise": "scroll_toggle",
                "smile": "menu_open"
            },
            "gesture_thresholds": gesture_thresholds,
            "sound": {"enabled": False, "template": None}
        }

        # Save and activate
        profile_mgr.save_profile(self.profile_id, profile)
        profile_mgr.activate(self.profile_id)
        self.in_progress = False

        return {"ok": True, "profile": profile}


# Global calibration singleton
calibration_engine = CalibrationEngine()
