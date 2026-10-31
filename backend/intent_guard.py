"""IntentGuard Safety Gate and Action Execution.
Reference: Section B5 & Section G.
Enforces the 8-stage state machine: IDLE -> CANDIDATE -> VALIDATED -> EXECUTED -> COOLDOWN.
Guarantees: one decision per episode, rejections have explicit reasons,
an allow is always followed by exactly one action, and latency_ms is accurately measured.
"""

import time
import math
from typing import Optional, Dict, Any, Tuple, List
from .config import (
    Q_MIN, EMIT_FLOOR_FACTOR, STILL_SPEED, COOLDOWN_MS,
    DWELL_STILL_RADIUS
)
from .bus import make_msg


class IntentGuard:
    """The bouncer: validates user intent before executing OS actions."""

    def __init__(self, os_controller):
        self.os_controller = os_controller

        # Pointer speed tracking (last 200 ms)
        self._pointer_history: List[Tuple[float, float, float]] = []  # (ts, nx, ny)

        # Gesture episode tracking
        self.current_gesture_name: Optional[str] = None
        self.episode_in_progress: bool = False
        self.episode_spent: bool = False  # If rejected or executed, cannot fire again until released
        self.episode_max_score: float = 0.0
        self.episode_max_held_ms: float = 0.0

        # Dwell episode tracking
        self.dwell_in_progress: bool = False
        self.dwell_start_time: float = 0.0
        self.dwell_anchor_nx: float = 0.5
        self.dwell_anchor_ny: float = 0.5
        self.dwell_spent: bool = False

        # Last executed action timestamp for cooldown
        self.last_action_ts: float = 0.0

        # Undo tracking
        self.last_executed_action: Optional[Dict[str, Any]] = None

    def update_pointer_history(self, nx: float, ny: float, ts: float) -> float:
        """Record pointer coordinate and return pointer speed in screen-widths/s over last 200 ms."""
        self._pointer_history.append((ts, nx, ny))
        # Purge older than 200 ms
        cutoff = ts - 0.200
        while self._pointer_history and self._pointer_history[0][0] < cutoff:
            self._pointer_history.pop(0)

        if len(self._pointer_history) < 2:
            return 0.0

        t0, x0, y0 = self._pointer_history[0]
        t1, x1, y1 = self._pointer_history[-1]
        dt = t1 - t0
        if dt <= 0.001:
            return 0.0

        # Calculate path distance in normalized screen units
        dist = math.hypot(x1 - x0, y1 - y0)
        speed = dist / dt
        return round(speed, 3)

    def process_frame(
        self,
        frame: Dict[str, Any],
        ui_state: Dict[str, Any],
        profile: Dict[str, Any],
        paused: bool,
        locked: bool,
        face_lost: bool
    ) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
        """Process a frame through IntentGuard.
        Returns: (guard_msg, action_msg, dwell_pending_msg)
        """
        ts = frame.get("ts", frame.get("timestamp", time.time()))
        face = frame.get("face") or {}
        head = frame.get("head") or frame.get("pointer") or {}
        gesture = frame.get("gesture") or {}
        detected = bool(frame.get("detected", face.get("detected", False)))

        nx = head.get("nx", 0.5) if head else 0.5
        ny = head.get("ny", 0.5) if head else 0.5
        pointer_speed = self.update_pointer_history(nx, ny, ts)

        now = time.time()
        in_cooldown = ((now - self.last_action_ts) * 1000.0) < COOLDOWN_MS

        primary_channel = ui_state.get("primary_channel", "gesture")

        guard_msg = None
        action_msg = None
        dwell_pending_msg = None

        # -------------------------------------------------------------
        # 1. GESTURE PROCESSING
        # -------------------------------------------------------------
        g_name = gesture.get("name") if gesture else None
        g_score = float(gesture.get("score", 0.0)) if gesture else 0.0
        g_held_ms = float(gesture.get("held_ms", 0.0)) if gesture else 0.0

        is_real_gesture = (g_name is not None and g_name != "none")

        base_threshold = profile.get("gesture_thresholds", {}).get(g_name, 0.50) if is_real_gesture else 0.50
        emit_floor = base_threshold * EMIT_FLOOR_FACTOR

        # Check if gesture channel is active
        channel_enabled = (primary_channel == "gesture")
        # Action mapped to gesture (mouth_open -> left_click, etc.)
        gesture_action = profile.get("gesture_bindings", {}).get(g_name, "left_click")

        # Thresholds modified by adaptation ui_state
        thresh_mult = ui_state.get("gesture_threshold_mult", 1.0)
        required_score = base_threshold * thresh_mult
        required_hold_ms = ui_state.get("gesture_hold_ms", 180)

        if is_real_gesture and g_score >= emit_floor:
            # Entering or continuing an episode
            if not self.episode_in_progress or self.current_gesture_name != g_name:
                self.episode_in_progress = True
                self.episode_spent = False
                self.current_gesture_name = g_name
                self.episode_max_score = g_score
                self.episode_max_held_ms = g_held_ms
            else:
                self.episode_max_score = max(self.episode_max_score, g_score)
                self.episode_max_held_ms = max(self.episode_max_held_ms, g_held_ms)

            # If not yet spent, evaluate checks in section G order
            if not self.episode_spent:
                # Check 1: paused or locked
                if paused or locked:
                    self.episode_spent = True
                    guard_msg = make_msg("guard", state="CANDIDATE", action=gesture_action, channel="gesture",
                                         decision="reject", reason="paused", pointer_speed=pointer_speed)
                # Check 2: face_lost
                elif face_lost or not detected:
                    self.episode_spent = True
                    guard_msg = make_msg("guard", state="CANDIDATE", action=gesture_action, channel="gesture",
                                         decision="reject", reason="face_lost", pointer_speed=pointer_speed)
                # Check 3: channel_disabled
                elif not channel_enabled:
                    self.episode_spent = True
                    guard_msg = make_msg("guard", state="CANDIDATE", action=gesture_action, channel="gesture",
                                         decision="reject", reason="channel_disabled", pointer_speed=pointer_speed)
                # Check 4: cooldown
                elif in_cooldown:
                    self.episode_spent = True
                    guard_msg = make_msg("guard", state="CANDIDATE", action=gesture_action, channel="gesture",
                                         decision="reject", reason="cooldown", pointer_speed=pointer_speed)
                # Check 5: low_quality
                elif face.get("quality", 1.0) < Q_MIN:
                    self.episode_spent = True
                    guard_msg = make_msg("guard", state="CANDIDATE", action=gesture_action, channel="gesture",
                                         decision="reject", reason="low_quality", pointer_speed=pointer_speed)
                else:
                    # Moment the hold is satisfied
                    if g_held_ms >= required_hold_ms:
                        # Check 6: pointer_fast
                        if pointer_speed > STILL_SPEED:
                            self.episode_spent = True
                            guard_msg = make_msg("guard", state="CANDIDATE", action=gesture_action, channel="gesture",
                                                 decision="reject", reason="pointer_fast", pointer_speed=pointer_speed)
                        # Check 7: low_confidence
                        elif self.episode_max_score < required_score:
                            self.episode_spent = True
                            guard_msg = make_msg("guard", state="CANDIDATE", action=gesture_action, channel="gesture",
                                                 decision="reject", reason="low_confidence", pointer_speed=pointer_speed)
                        else:
                            # -----------------------------------------
                            # ALLOW & EXECUTE GESTURE ACTION
                            # -----------------------------------------
                            self.episode_spent = True
                            self.last_action_ts = now
                            guard_msg = make_msg("guard", state="VALIDATED", action=gesture_action, channel="gesture",
                                                 decision="allow", reason=None, pointer_speed=pointer_speed)

                            px, py = self.os_controller.last_px, self.os_controller.last_py
                            if gesture_action == "left_click":
                                self.os_controller.left_click(px, py)
                            elif gesture_action == "right_click":
                                self.os_controller.right_click(px, py)
                            elif gesture_action == "double_click":
                                self.os_controller.double_click(px, py)

                            latency_ms = max(1.0, round((time.time() - ts) * 1000.0, 1))
                            action_msg = make_msg("action", action=gesture_action, channel="gesture",
                                                  px={"x": px, "y": py}, latency_ms=latency_ms, undone=False)
                            self.last_executed_action = action_msg
                    else:
                        # Hold in progress: emit pending candidate message
                        guard_msg = make_msg("guard", state="CANDIDATE", action=gesture_action, channel="gesture",
                                             decision="pending", reason=None, pointer_speed=pointer_speed)
        else:
            # Gesture released / below floor
            if self.episode_in_progress:
                # If released before reaching required_hold_ms without firing, reject as gesture_short
                if not self.episode_spent:
                    self.episode_spent = True
                    action_name = profile.get("gesture_bindings", {}).get(self.current_gesture_name, "left_click")
                    if self.episode_max_held_ms < required_hold_ms:
                        guard_msg = make_msg("guard", state="CANDIDATE", action=action_name, channel="gesture",
                                             decision="reject", reason="gesture_short", pointer_speed=pointer_speed)
                    elif self.episode_max_score < required_score:
                        guard_msg = make_msg("guard", state="CANDIDATE", action=action_name, channel="gesture",
                                             decision="reject", reason="low_confidence", pointer_speed=pointer_speed)

                # Reset episode
                self.episode_in_progress = False
                self.episode_spent = False
                self.current_gesture_name = None
                self.episode_max_score = 0.0
                self.episode_max_held_ms = 0.0

        # -------------------------------------------------------------
        # 2. DWELL PROCESSING (when primary is dwell)
        # -------------------------------------------------------------
        if primary_channel == "dwell" and head and not face_lost and detected:
            dist_from_anchor = math.hypot(nx - self.dwell_anchor_nx, ny - self.dwell_anchor_ny)
            dwell_target_ms = ui_state.get("dwell_ms", 1000)

            if not self.dwell_in_progress:
                if pointer_speed <= STILL_SPEED:
                    self.dwell_in_progress = True
                    self.dwell_start_time = now
                    self.dwell_anchor_nx = nx
                    self.dwell_anchor_ny = ny
                    self.dwell_spent = False
                    # Send pending message for frontend ring
                    dwell_pending_msg = make_msg("guard", state="CANDIDATE", action="left_click", channel="dwell",
                                                 decision="pending", reason=None, pointer_speed=pointer_speed)
            else:
                if dist_from_anchor > DWELL_STILL_RADIUS:
                    # Moved out of radius -> dwell cancelled
                    self.dwell_in_progress = False
                    self.dwell_spent = False
                elif not self.dwell_spent:
                    elapsed_dwell_ms = (now - self.dwell_start_time) * 1000.0
                    if elapsed_dwell_ms >= dwell_target_ms:
                        # Dwell completed: check safety
                        self.dwell_spent = True
                        if paused or locked:
                            guard_msg = make_msg("guard", state="CANDIDATE", action="left_click", channel="dwell",
                                                 decision="reject", reason="paused", pointer_speed=pointer_speed)
                        elif in_cooldown:
                            guard_msg = make_msg("guard", state="CANDIDATE", action="left_click", channel="dwell",
                                                 decision="reject", reason="cooldown", pointer_speed=pointer_speed)
                        elif pointer_speed > STILL_SPEED:
                            guard_msg = make_msg("guard", state="CANDIDATE", action="left_click", channel="dwell",
                                                 decision="reject", reason="pointer_fast", pointer_speed=pointer_speed)
                        else:
                            # ALLOW & EXECUTE DWELL
                            self.last_action_ts = now
                            guard_msg = make_msg("guard", state="VALIDATED", action="left_click", channel="dwell",
                                                 decision="allow", reason=None, pointer_speed=pointer_speed)
                            px, py = self.os_controller.last_px, self.os_controller.last_py
                            self.os_controller.left_click(px, py)
                            latency_ms = max(1.0, round((time.time() - ts) * 1000.0, 1))
                            action_msg = make_msg("action", action="left_click", channel="dwell",
                                                  px={"x": px, "y": py}, latency_ms=latency_ms, undone=False)
                            self.last_executed_action = action_msg

        return guard_msg, action_msg, dwell_pending_msg

    def handle_undo(self) -> Optional[Dict[str, Any]]:
        """If an action occurred within UNDO_WINDOW_MS (2000ms), re-emit the same action with undone: True."""
        if not self.last_executed_action:
            return None

        action_ts = self.last_executed_action.get("ts", 0.0)
        if (time.time() - action_ts) <= 2.0:
            undone_action = dict(self.last_executed_action)
            undone_action["undone"] = True
            self.last_executed_action = None
            return undone_action
        return None
