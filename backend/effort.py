"""Effort Meter and Fatigue Estimation for FLUX.
Reference: Section B6 & Section F.
Combines 4 physiological/behavioral tiredness components:
  1. range_loss (0.30)
  2. jitter (0.25)
  3. gesture_strain (0.25)
  4. friction (0.20)
Applies warmup (20s), tracking loss rearm (10s), EMA smoothing,
and level hysteresis with a 10s minimum hold.
"""

import time
import math
import numpy as np
from typing import Dict, Any, List, Optional, Tuple
from .config import (
    Q_MIN, WARMUP_S, REARM_S, MIN_LEVEL_HOLD_S,
    EFFORT_EMA_ALPHA, MIN_MOTION
)
from .bus import make_msg


class EffortMeter:
    """Computes real-time effort score and discrete adaptation level."""

    LEVEL_ORDER = ["fresh", "moderate", "high", "rest"]

    def __init__(self, start_time: Optional[float] = None):
        self.start_time = start_time or time.time()
        self.last_loss_recovery_time: Optional[float] = None
        self.last_tracking_loss_duration: float = 0.0

        # Rolling frame records: (ts, raw_dx, raw_dy, sm_dx, sm_dy, nx, ny)
        self._frame_window: List[Tuple[float, float, float, float, float, float, float]] = []

        # Rolling episode records (last 60s): (ts, peak_score, episode_hold_ms)
        self._episode_window: List[Tuple[float, float, float]] = []

        # Rolling attempt / reject records (last 60s): (ts, is_struggle)
        self._attempt_window: List[Tuple[float, bool]] = []

        # State
        self.current_score: float = 0.0
        self.current_level: str = "fresh"
        self.last_level_change_ts: float = self.start_time
        self.range_now: float = 1.0

        # Dev overrides
        self.dev_score_override: Optional[float] = None
        self.dev_level_override: Optional[str] = None
        self.simulated: bool = False

    def feed_frame(self, frame: Dict[str, Any]) -> None:
        """Ingest a valid frame (only frames with quality >= Q_MIN are retained)."""
        face = frame.get("face") or {}
        head = frame.get("head") or frame.get("pointer") or {}
        raw_motion = frame.get("raw_motion") or {}
        detected = bool(frame.get("detected", face.get("detected", False)))
        if not detected or face.get("quality", 0.0) < Q_MIN:
            return
        if not head:
            return

        ts = frame.get("ts", frame.get("timestamp", time.time()))
        raw_dx = head.get("raw_dx", raw_motion.get("raw_dx"))
        raw_dy = head.get("raw_dy", raw_motion.get("raw_dy"))
        nx = head.get("nx", 0.5)
        ny = head.get("ny", 0.5)
        sm_dx = head.get("sm_dx", round(nx - 0.5, 4))
        sm_dy = head.get("sm_dy", round(ny - 0.5, 4))

        if raw_dx is not None and raw_dy is not None:
            self._frame_window.append((ts, float(raw_dx), float(raw_dy), float(sm_dx), float(sm_dy), float(nx), float(ny)))

        # Retain up to 25s for range and jitter
        cutoff = ts - 25.0
        while self._frame_window and self._frame_window[0][0] < cutoff:
            self._frame_window.pop(0)

    def record_episode(self, peak_score: float, hold_ms: float, ts: Optional[float] = None) -> None:
        """Record completed gesture episode for gesture strain metric."""
        t = ts or time.time()
        self._episode_window.append((t, peak_score, hold_ms))
        cutoff = t - 60.0
        while self._episode_window and self._episode_window[0][0] < cutoff:
            self._episode_window.pop(0)

    def record_attempt(self, is_struggle_reject: bool, ts: Optional[float] = None) -> None:
        """Record attempt for friction metric."""
        t = ts or time.time()
        self._attempt_window.append((t, is_struggle_reject))
        cutoff = t - 60.0
        while self._attempt_window and self._attempt_window[0][0] < cutoff:
            self._attempt_window.pop(0)

    def notify_tracking_loss(self, duration_s: float, recovery_ts: float) -> None:
        """Called when tracking recovers after loss."""
        if duration_s > 1.0:
            self.last_loss_recovery_time = recovery_ts
            self.last_tracking_loss_duration = duration_s

    def compute_range_loss(self, now: float, profile: Dict[str, Any]) -> Tuple[float, float]:
        """Compute range_loss (0..1) and range_now ratio over last 20 s."""
        cutoff_20s = now - 20.0
        pts_20s = [p for p in self._frame_window if p[0] >= cutoff_20s]
        if len(pts_20s) < 10:
            return 0.0, self.range_now

        # Check total path motion
        motion = 0.0
        for i in range(1, len(pts_20s)):
            motion += math.hypot(pts_20s[i][5] - pts_20s[i-1][5], pts_20s[i][6] - pts_20s[i-1][6])

        if motion < MIN_MOTION:
            # User was idle / resting, freeze previous range_loss
            return 0.0, self.range_now

        # Calculate bounding box of raw excursions
        dxs = [p[1] for p in pts_20s]
        dys = [p[2] for p in pts_20s]
        actual_range_x = max(dxs) - min(dxs)
        actual_range_y = max(dys) - min(dys)

        prof_range = profile.get("range", {"x": 0.22, "y": 0.16})
        rx_calib = max(0.01, float(prof_range.get("x", 0.22)))
        ry_calib = max(0.01, float(prof_range.get("y", 0.16)))

        # Normalized range fraction
        rx_ratio = actual_range_x / rx_calib
        ry_ratio = actual_range_y / ry_calib
        self.range_now = max(0.05, min(1.0, float((rx_ratio + ry_ratio) / 2.0)))

        # Invert to loss: 1.0 means full loss, 0.0 means normal range
        range_loss = max(0.0, min(1.0, 1.0 - self.range_now))
        return round(range_loss, 3), self.range_now

    def compute_jitter(self, now: float, profile: Dict[str, Any]) -> float:
        """Compute jitter metric (0..1) over last 2 s."""
        cutoff_2s = now - 2.0
        pts_2s = [p for p in self._frame_window if p[0] >= cutoff_2s]
        if len(pts_2s) < 5:
            return 0.0

        diff_x = [p[1] - p[3] for p in pts_2s]
        diff_y = [p[2] - p[4] for p in pts_2s]

        std_x = np.std(diff_x)
        std_y = np.std(diff_y)
        j = float((std_x + std_y) / 2.0)

        base_jitter = profile.get("baseline", {}).get("jitter", 0.004)
        base_jitter = max(0.0001, float(base_jitter))

        jitter_metric = max(0.0, min(1.0, (j / base_jitter - 1.0) / 2.0))
        return round(jitter_metric, 3)

    def compute_gesture_strain(self, now: float, profile: Dict[str, Any]) -> float:
        """Compute gesture_strain metric (0..1) over last 60 s."""
        cutoff_60s = now - 60.0
        eps = [e for e in self._episode_window if e[0] >= cutoff_60s]
        if not eps:
            return 0.0

        scores = [e[1] for e in eps]
        holds = [e[2] for e in eps]

        peak_now = float(np.median(scores))
        median_hold = float(np.median(holds))

        base_peak = max(0.1, float(profile.get("baseline", {}).get("gesture_peak", 0.91)))
        base_hold = max(50.0, float(profile.get("baseline", {}).get("hold_ms", 180)))

        strain_base = max(0.0, min(1.0, 1.0 - (peak_now / base_peak)))

        hold_penalty = 0.0
        if median_hold > base_hold:
            hold_penalty = 0.2 * max(0.0, min(1.0, (median_hold / base_hold - 1.0) / 0.5))

        return round(min(1.0, strain_base + hold_penalty), 3)

    def compute_friction(self, now: float) -> float:
        """Compute friction metric (0..1) over last 60 s."""
        cutoff_60s = now - 60.0
        atts = [a for a in self._attempt_window if a[0] >= cutoff_60s]
        if not atts:
            return 0.0

        struggles = sum(1 for a in atts if a[1])
        struggle_rate = struggles / len(atts)
        return round(max(0.0, min(1.0, struggle_rate)), 3)

    def is_samples_ok(self, now: float) -> bool:
        """Returns True if warmup has expired and recovery hold has completed."""
        # 1. Warmup check: 20 seconds
        if (now - self.start_time) < WARMUP_S:
            return False

        # 2. Tracking loss rearm check: 10 seconds after recovery
        if self.last_loss_recovery_time is not None:
            if (now - self.last_loss_recovery_time) < REARM_S:
                return False

        return True

    def update_level_hysteresis(self, score: float, now: float) -> str:
        """Applies level threshold hysteresis and 10 s minimum dwell per level."""
        if (now - self.last_level_change_ts) < MIN_LEVEL_HOLD_S:
            return self.current_level

        lvl = self.current_level
        new_lvl = lvl

        if lvl == "fresh":
            if score >= 40:
                new_lvl = "moderate"
        elif lvl == "moderate":
            if score < 30:
                new_lvl = "fresh"
            elif score >= 65:
                new_lvl = "high"
        elif lvl == "high":
            if score < 55:
                new_lvl = "moderate"
            elif score >= 85:
                new_lvl = "rest"
        elif lvl == "rest":
            if score < 75:
                new_lvl = "high"

        if new_lvl != lvl:
            self.current_level = new_lvl
            self.last_level_change_ts = now

        return self.current_level

    def tick(self, profile: Dict[str, Any], current_time: Optional[float] = None) -> Dict[str, Any]:
        """Perform 1 Hz evaluation and return effort message."""
        now = current_time or time.time()
        samples_ok = self.is_samples_ok(now)

        if self.dev_score_override is not None:
            self.current_score = float(self.dev_score_override)
            self.simulated = True
            self.current_level = self.update_level_hysteresis(self.current_score, now)
            comp = {"range_loss": 0.0, "jitter": 0.0, "gesture_strain": 0.0, "friction": 0.0}
        elif not samples_ok:
            # Freeze score and level during warmup or recovery
            comp = {"range_loss": 0.0, "jitter": 0.0, "gesture_strain": 0.0, "friction": 0.0}
        else:
            self.simulated = False
            r_loss, _ = self.compute_range_loss(now, profile)
            jit = self.compute_jitter(now, profile)
            strain = self.compute_gesture_strain(now, profile)
            fric = self.compute_friction(now)

            comp = {
                "range_loss": r_loss,
                "jitter": jit,
                "gesture_strain": strain,
                "friction": fric
            }

            raw_score = 100.0 * (0.30 * r_loss + 0.25 * jit + 0.25 * strain + 0.20 * fric)
            # EMA alpha 0.1 per second
            self.current_score = (1.0 - EFFORT_EMA_ALPHA) * self.current_score + EFFORT_EMA_ALPHA * raw_score
            self.current_score = round(self.current_score, 1)
            self.current_level = self.update_level_hysteresis(self.current_score, now)

        if self.dev_level_override:
            self.current_level = self.dev_level_override

        return make_msg(
            "effort",
            score=int(round(self.current_score)),
            level=self.current_level,
            components=comp,
            range_now=self.range_now,
            samples_ok=samples_ok,
            simulated=self.simulated
        )
