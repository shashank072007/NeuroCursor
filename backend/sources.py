"""FrameSource implementations for FLUX.
Reference: Section B1.
Three versions:
  - mock: sine-wave head motion, scripted periodic gestures, ~30 Hz
  - replay: reads recorded JSONL frames
  - live: reads from live vision FrameProducer or injected frame_q
"""

import time
import math
import json
import queue
import threading
from typing import Optional, Dict, Any
from .config import FRAME_HZ, FRAME_Q_MAX
from .bus import make_msg


def normalize_frame(frame: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Harmonizes frame dictionary between Vision subsystem and Backend processor."""
    if not frame:
        return frame
    f = dict(frame)

    # Version & type
    if "v" not in f:
        f["v"] = 1
    if "type" not in f:
        f["type"] = "frame"

    # Timestamp synchronization
    now_ts = round(time.time(), 3)
    ts = f.get("ts", f.get("timestamp", now_ts))
    f["ts"] = round(float(ts), 3)
    f["timestamp"] = f["ts"]

    # Detected flag and face object
    face_in = f.get("face")
    face = dict(face_in) if isinstance(face_in, dict) else {}
    detected = f.get("detected", face.get("detected", False))
    detected = bool(detected)
    f["detected"] = detected
    face["detected"] = detected
    if "quality" not in face:
        face["quality"] = 0.95 if detected else 0.0
    if "width_norm" not in face:
        face["width_norm"] = 0.35 if detected else 0.0
    f["face"] = face

    # Pointer and head coordinates
    pointer_in = f.get("pointer")
    pointer = dict(pointer_in) if isinstance(pointer_in, dict) else {}
    head_in = f.get("head")
    head = dict(head_in) if isinstance(head_in, dict) else {}
    raw_motion_in = f.get("raw_motion")
    raw_motion = dict(raw_motion_in) if isinstance(raw_motion_in, dict) else {}

    nx = pointer.get("nx", head.get("nx", 0.5))
    ny = pointer.get("ny", head.get("ny", 0.5))
    raw_dx = raw_motion.get("raw_dx", head.get("raw_dx", 0.0))
    raw_dy = raw_motion.get("raw_dy", head.get("raw_dy", 0.0))
    sm_dx = head.get("sm_dx", round(nx - 0.5, 4))
    sm_dy = head.get("sm_dy", round(ny - 0.5, 4))

    f["pointer"] = {"nx": round(nx, 3), "ny": round(ny, 3)}
    f["raw_motion"] = {"raw_dx": round(raw_dx, 4), "raw_dy": round(raw_dy, 4)}
    f["head"] = {
        "nx": round(nx, 3),
        "ny": round(ny, 3),
        "raw_dx": round(raw_dx, 4),
        "raw_dy": round(raw_dy, 4),
        "sm_dx": round(sm_dx, 4),
        "sm_dy": round(sm_dy, 4)
    }

    # Gesture
    gesture_in = f.get("gesture")
    gesture = dict(gesture_in) if isinstance(gesture_in, dict) else {}
    if "name" not in gesture:
        gesture["name"] = "none"
    if "score" not in gesture:
        gesture["score"] = 0.0
    if "held_ms" not in gesture:
        gesture["held_ms"] = 0
    f["gesture"] = gesture

    # Timing
    timing_in = f.get("timing")
    timing = dict(timing_in) if isinstance(timing_in, dict) else {}
    if "capture_ms" not in timing:
        timing["capture_ms"] = 5.0
    if "process_ms" not in timing:
        timing["process_ms"] = 12.0
    if "fps" not in timing:
        timing["fps"] = float(FRAME_HZ)
    f["timing"] = timing

    return f


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
            gesture_score = min(0.88, 0.50 + held_s * 1.5)
        # Between 7.0s and 7.4s of cycle, trigger smile gesture
        elif 7.0 <= cycle_pos <= 7.4:
            gesture_name = "smile"
            held_s = cycle_pos - 7.0
            gesture_held_ms = int(held_s * 1000)
            gesture_score = min(0.85, 0.50 + held_s * 1.5)

        raw_msg = make_msg(
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
        return normalize_frame(raw_msg)


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
        f = normalize_frame(frame)
        f["ts"] = round(time.time(), 3)
        f["timestamp"] = f["ts"]
        return f


class LiveFrameSource(FrameSource):
    """Reads real-time frames delivered by vision pipeline FrameProducer on frame_q."""

    def __init__(self, frame_q: Optional[queue.Queue] = None, camera_index: int = 0, use_mock: bool = False):
        self.frame_q = frame_q if frame_q is not None else queue.Queue(maxsize=FRAME_Q_MAX)
        self.camera_index = camera_index
        self.use_mock = use_mock
        self.control_q: Optional[queue.Queue] = None
        self.producer = None
        self.running = False

    def start(self) -> None:
        self.running = True
        try:
            from vision.producer import FrameProducer
            self.producer = FrameProducer(
                camera_index=self.camera_index,
                queue_size=FRAME_Q_MAX,
                use_mock=self.use_mock
            )
            self.producer.control_q = self.control_q
            # Route frames directly into our shared queue
            self.producer.frame_queue = self.frame_q
            self.producer.start()
            print(f"[LiveFrameSource] FrameProducer running (camera={self.camera_index}, mock={self.producer.use_mock})")
        except Exception as e:
            print(f"[LiveFrameSource] Notice: FrameProducer could not start ({e}). Waiting on frame_q.")

    def stop(self) -> None:
        self.running = False
        if self.producer:
            try:
                self.producer.stop()
            except Exception:
                pass

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
            if msg:
                return normalize_frame(msg)
            return None
        except queue.Empty:
            return None
