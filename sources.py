"""FrameSource implementations for FLUX.
Reference: Section B1.
Three versions:
  - mock: sine-wave head motion, scripted periodic gestures, ~30 Hz
  - replay: reads recorded JSONL frames
  - live: reads from Ritesh's frame_q
"""

import time
import math
import json
import queue
import threading
from typing import Optional, Dict, Any
from .config import FRAME_HZ, FRAME_Q_MAX
from .bus import make_msg


class FrameSource:
    """Abstract base class for all frame sources."""

    def start(self) -> None:
        pass

    def stop(self) -> None:
        pass

    def get_frame(self, timeout: float = 0.05) -> Optional[Dict[str, Any]]:
        raise NotImplementedError


class MockFrameSource(FrameSource):
    """Generates synthetic 30 Hz head motion and scripted gestures for testing and dev."""

    def __init__(self):
        self.running = False
        self.start_time = time.time()
        self.frame_interval = 1.0 / FRAME_HZ
        self._last_frame_time = time.time()

        # Scripted gesture state
        self._gesture_cycle_period = 8.0  # seconds per cycle
        self._active_gesture = "none"
        self._gesture_start_time = 0.0

    def start(self) -> None:
        self.running = True
        self.start_time = time.time()
        self._last_frame_time = time.time()

    def stop(self) -> None:
        self.running = False

    def get_frame(self, timeout: float = 0.05) -> Optional[Dict[str, Any]]:
        if not self.running:
            return None

        now = time.time()
        elapsed_since_last = now - self._last_frame_time
        if elapsed_since_last < self.frame_interval:
            time.sleep(max(0.001, self.frame_interval - elapsed_since_last))
            now = time.time()

        self._last_frame_time = now
        t = now - self.start_time

        # Sine wave head movement
        raw_dx = 0.04 * math.sin(0.8 * t) + 0.002 * math.sin(5.0 * t)
        raw_dy = 0.03 * math.cos(0.6 * t) + 0.002 * math.cos(4.0 * t)
        sm_dx = 0.04 * math.sin(0.8 * t)
        sm_dy = 0.03 * math.cos(0.6 * t)

        nx = max(0.0, min(1.0, 0.5 + sm_dx * 3.0))
        ny = max(0.0, min(1.0, 0.5 + sm_dy * 3.0))

        # Scripted gesture episode every 8 seconds
        cycle_pos = t % self._gesture_cycle_period
        gesture_name = "none"
        gesture_score = 0.0
        gesture_held_ms = 0

        # Between 4.0s and 4.6s of cycle, trigger mouth_open gesture
        if 4.0 <= cycle_pos <= 4.5:
            gesture_name = "mouth_open"
            held_s = cycle_pos - 4.0
            gesture_held_ms = int(held_s * 1000)
            # Ramp score up quickly to 0.88
            gesture_score = min(0.88, 0.50 + held_s * 1.5)
        # Between 7.0s and 7.4s of cycle, trigger smile gesture
        elif 7.0 <= cycle_pos <= 7.4:
            gesture_name = "smile"
            held_s = cycle_pos - 7.0
            gesture_held_ms = int(held_s * 1000)
            gesture_score = min(0.85, 0.50 + held_s * 1.5)

        return make_msg(
            "frame",
            ts=round(now, 3),
            face={
                "detected": True,
                "quality": 0.95
            },
            head={
                "nx": round(nx, 3),
                "ny": round(ny, 3),
                "raw_dx": round(raw_dx, 4),
                "raw_dy": round(raw_dy, 4),
                "sm_dx": round(sm_dx, 4),
                "sm_dy": round(sm_dy, 4)
            },
            gesture={
                "name": gesture_name,
                "score": round(gesture_score, 2),
                "held_ms": gesture_held_ms
            },
            timing={
                "capture_ms": 8,
                "process_ms": 14
            }
        )


class ReplayFrameSource(FrameSource):
    """Replays frames from a pre-recorded JSONL file."""

    def __init__(self, jsonl_path: str):
        self.jsonl_path = jsonl_path
        self.frames = []
        self.current_idx = 0
        self.running = False
        self._load_frames()

    def _load_frames(self) -> None:
        try:
            with open(self.jsonl_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        self.frames.append(json.loads(line))
        except Exception as e:
            print(f"[ReplaySource] Error loading {self.jsonl_path}: {e}")

    def start(self) -> None:
        self.running = True
        self.current_idx = 0

    def stop(self) -> None:
        self.running = False

    def get_frame(self, timeout: float = 0.05) -> Optional[Dict[str, Any]]:
        if not self.running or not self.frames:
            return None

        frame = self.frames[self.current_idx]
        self.current_idx = (self.current_idx + 1) % len(self.frames)
        time.sleep(1.0 / FRAME_HZ)
        # Update timestamp to now so it flows seamlessly
        f = dict(frame)
        f["ts"] = round(time.time(), 3)
        return f


class LiveFrameSource(FrameSource):
    """Reads real-time frames delivered by Ritesh's vision pipeline on frame_q."""

    def __init__(self, frame_q: queue.Queue):
        self.frame_q = frame_q
        self.running = False

    def start(self) -> None:
        self.running = True

    def stop(self) -> None:
        self.running = False

    def get_frame(self, timeout: float = 0.05) -> Optional[Dict[str, Any]]:
        if not self.running:
            return None
        try:
            # Drain queue if older frames are buffered beyond FRAME_Q_MAX (drop oldest)
            while self.frame_q.qsize() > FRAME_Q_MAX:
                try:
                    self.frame_q.get_nowait()
                except queue.Empty:
                    break

            msg = self.frame_q.get(timeout=timeout)
            return msg
        except queue.Empty:
            return None
