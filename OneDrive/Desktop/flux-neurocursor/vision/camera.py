"""
Camera acquisition module for FLUX / NeuroCursor.

Provides robust webcam capture, actual FPS calculation, capture latency tracking,
ambient lighting estimation, and graceful error handling.
"""

from __future__ import annotations

import time
from collections import deque
from typing import Any, Dict, Optional, Tuple

import cv2
import numpy as np


class CameraManager:
    """Manages webcam capture lifecycle, performance tracking, and health checks."""

    def __init__(
        self,
        camera_index: int = 0,
        width: int = 640,
        height: int = 480,
        target_fps: int = 30,
        low_light_threshold: float = 40.0,
    ) -> None:
        self.camera_index = camera_index
        self.width = width
        self.height = height
        self.target_fps = target_fps
        self.low_light_threshold = low_light_threshold

        self.cap: Optional[cv2.VideoCapture] = None
        self.is_open: bool = False
        self._frame_timestamps: deque[float] = deque(maxlen=30)
        self._last_capture_ms: float = 0.0
        self._current_fps: float = 0.0

    def open(self) -> bool:
        """
        Attempts to open the webcam. On Windows, tries DirectShow (CAP_DSHOW)
        first for faster startup and lower latency, falling back to CAP_ANY.
        """
        self.release()

        # Try DirectShow first on Windows
        try:
            self.cap = cv2.VideoCapture(self.camera_index, cv2.CAP_DSHOW)
            if not self.cap or not self.cap.isOpened():
                self.cap = cv2.VideoCapture(self.camera_index, cv2.CAP_ANY)
        except Exception:
            self.cap = cv2.VideoCapture(self.camera_index, cv2.CAP_ANY)

        if not self.cap or not self.cap.isOpened():
            self.is_open = False
            return False

        # Set requested resolution and frame rate
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        self.cap.set(cv2.CAP_PROP_FPS, self.target_fps)

        self.is_open = True
        self._frame_timestamps.clear()
        return True

    def read_frame(self) -> Tuple[bool, Optional[np.ndarray], float, Dict[str, Any]]:
        """
        Reads a single frame from the camera.

        Returns:
            Tuple of:
            - success (bool)
            - frame (Optional[np.ndarray]): BGR frame image
            - capture_ms (float): elapsed time spent acquiring the frame
            - metadata (dict): contains actual fps, brightness, low_light flag, and dimensions
        """
        if not self.is_open or self.cap is None:
            return False, None, 0.0, {
                "fps": 0.0,
                "brightness": 0.0,
                "low_light": True,
                "camera_connected": False,
            }

        start_time = time.perf_counter()
        try:
            ret, frame = self.cap.read()
        except Exception:
            ret, frame = False, None
        end_time = time.perf_counter()

        capture_ms = (end_time - start_time) * 1000.0
        self._last_capture_ms = capture_ms

        now = time.time()
        self._frame_timestamps.append(now)
        self._update_fps()

        if not ret or frame is None:
            return False, None, capture_ms, {
                "fps": self._current_fps,
                "brightness": 0.0,
                "low_light": True,
                "camera_connected": False,
            }

        brightness, is_low_light = self.estimate_lighting(frame)
        h, w = frame.shape[:2]

        metadata: Dict[str, Any] = {
            "fps": round(self._current_fps, 1),
            "brightness": round(brightness, 1),
            "low_light": is_low_light,
            "camera_connected": True,
            "width": w,
            "height": h,
        }

        return True, frame, round(capture_ms, 2), metadata

    def _update_fps(self) -> None:
        """Calculates rolling FPS based on recent frame intervals."""
        if len(self._frame_timestamps) < 2:
            self._current_fps = 0.0
            return
        elapsed = self._frame_timestamps[-1] - self._frame_timestamps[0]
        if elapsed > 0:
            self._current_fps = (len(self._frame_timestamps) - 1) / elapsed
        else:
            self._current_fps = 0.0

    def estimate_lighting(self, frame: np.ndarray) -> Tuple[float, bool]:
        """
        Estimates ambient lighting level via mean grayscale brightness.

        Returns:
            Tuple of (mean_brightness, is_low_light)
        """
        if frame is None or frame.size == 0:
            return 0.0, True

        # Quick brightness estimate on downsampled grayscale
        try:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            mean_brightness = float(np.mean(gray))
            is_low_light = mean_brightness < self.low_light_threshold
            return mean_brightness, is_low_light
        except Exception:
            return 0.0, True

    @property
    def current_fps(self) -> float:
        return round(self._current_fps, 1)

    @property
    def last_capture_ms(self) -> float:
        return round(self._last_capture_ms, 2)

    def release(self) -> None:
        """Safely releases the webcam capture resource."""
        if self.cap is not None:
            try:
                self.cap.release()
            except Exception:
                pass
            self.cap = None
        self.is_open = False

    def __enter__(self) -> CameraManager:
        self.open()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.release()
