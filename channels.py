"""Channel Fusion and Reliability Scoring for FLUX.
Reference: Section B8 & Section C.5.
Channels: gesture, dwell, sound.
Maintains last 10 attempts per channel, tracks dwell shadow mode,
evaluates switch rule, and generates 1 Hz channels message.
"""

import time
import math
from typing import Dict, Any, List, Optional, Tuple
from .config import (
    SWITCH_RULE_LOW, SWITCH_RULE_HIGH, SWITCH_RULE_HOLD_S,
    DWELL_STILL_RADIUS, STILL_SPEED
)
from .bus import make_msg


class ChannelManager:
    """Tracks channel reliability and offers smart modal transitions."""

    def __init__(self):
        self.primary_channel: str = "gesture"

        # Attempt histories (last 10 attempts per channel): list of (ts, success: bool)
        self._history: Dict[str, List[Tuple[float, bool]]] = {
            "gesture": [],
            "dwell": [],
            "sound": []
        }

        # Dwell shadow tracking
        self._shadow_dwell_start: Optional[float] = None
        self._shadow_anchor_nx: float = 0.5
        self._shadow_anchor_ny: float = 0.5

        # Switch rule tracking
        self._switch_condition_start: Optional[float] = None
        self.suggest_channel: Optional[str] = None

    def record_attempt(self, channel: str, success: bool, ts: Optional[float] = None) -> None:
        """Record an action attempt for a channel."""
        if channel not in self._history:
            return
        t = ts or time.time()
        self._history[channel].append((t, success))
        # Keep last 10 attempts
        if len(self._history[channel]) > 10:
            self._history[channel].pop(0)

    def record_undo(self, channel: str) -> None:
        """When an action is undone, mark the most recent attempt as failed."""
        if channel in self._history and self._history[channel]:
            # Replace the last attempt with failure
            last_ts, _ = self._history[channel][-1]
            self._history[channel][-1] = (last_ts, False)

    def get_reliability(self, channel: str) -> Optional[float]:
        """Compute channel reliability over the last 10 attempts.
        Returns None if fewer than 3 attempts have been recorded.
        """
        attempts = self._history.get(channel, [])
        if len(attempts) < 3:
            return None
        successes = sum(1 for _, ok in attempts if ok)
        return round(float(successes / len(attempts)), 2)

    def update_shadow_dwell(self, nx: float, ny: float, pointer_speed: float, dwell_target_ms: float, now: float) -> None:
        """Run dwell in shadow mode while gesture is primary to estimate dwell reliability."""
        if self.primary_channel == "dwell":
            return

        dist = math.hypot(nx - self._shadow_anchor_nx, ny - self._shadow_anchor_ny)

        if self._shadow_dwell_start is None:
            if pointer_speed <= STILL_SPEED:
                self._shadow_dwell_start = now
                self._shadow_anchor_nx = nx
                self._shadow_anchor_ny = ny
        else:
            if dist > DWELL_STILL_RADIUS:
                # Cancelled or drifted out
                self._shadow_dwell_start = None
            else:
                elapsed_ms = (now - self._shadow_dwell_start) * 1000.0
                if elapsed_ms >= dwell_target_ms:
                    # Successful shadow dwell completion
                    self.record_attempt("dwell", success=True, ts=now)
                    self._shadow_dwell_start = None

    def evaluate_switch_rule(self, now: float) -> Optional[str]:
        """Rule: primary < 0.5 and another > 0.75 for 10 s -> suggest_channel."""
        primary_rel = self.get_reliability(self.primary_channel)
        if primary_rel is None:
            self._switch_condition_start = None
            return None

        # Check alternative channels
        candidate = None
        for ch in ("dwell", "gesture", "sound"):
            if ch != self.primary_channel:
                rel = self.get_reliability(ch)
                if rel is not None and rel > SWITCH_RULE_HIGH:
                    candidate = ch
                    break

        if primary_rel < SWITCH_RULE_LOW and candidate:
            if self._switch_condition_start is None:
                self._switch_condition_start = now
            elif (now - self._switch_condition_start) >= SWITCH_RULE_HOLD_S:
                self.suggest_channel = candidate
                return candidate
        else:
            self._switch_condition_start = None

        return None

    def accept_channel(self, channel: str) -> bool:
        """User accepted a channel switch."""
        if channel in ("gesture", "dwell", "sound"):
            self.primary_channel = channel
            self.suggest_channel = None
            self._switch_condition_start = None
            return True
        return False

    def tick(self, now: Optional[float] = None) -> Dict[str, Any]:
        """Generate 1 Hz channels message."""
        t = now or time.time()
        self.evaluate_switch_rule(t)

        return make_msg(
            "channels",
            gesture={
                "enabled": True,
                "reliability": self.get_reliability("gesture"),
                "attempts": len(self._history["gesture"])
            },
            dwell={
                "enabled": True,
                "reliability": self.get_reliability("dwell"),
                "attempts": len(self._history["dwell"])
            },
            sound={
                "enabled": False,
                "reliability": None,
                "attempts": 0
            }
        )
