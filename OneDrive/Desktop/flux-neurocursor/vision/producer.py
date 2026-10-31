"""
Threaded frame producer module for FLUX / NeuroCursor.

Runs the camera acquisition and vision processing loop in a dedicated background worker,
enqueuing standardized frame events onto a bounded, drop-oldest queue.
Ensures the camera acquisition loop never blocks or stutters even if downstream consumers lag.
"""

from __future__ import annotations

import os
import queue
import sys
import threading
import time
from typing import Any, Dict, Generator, Optional, Tuple

import cv2
import numpy as np

from vision.calibration import CalibrationManager, CalibrationProfile
from vision.camera import CameraManager
from vision.gestures import GestureDetector, GestureResult
from vision.landmarks import FaceMeshExtractor, FaceMeshResult
from vision.tracking import PointerTracker, TrackingResult


class FrameProducer:
    """
    Spawns a background worker thread that continuously processes camera frames
    and publishes structured events to a bounded thread-safe queue.
    """

    def __init__(
        self,
        camera_index: int = 0,
        camera_width: int = 640,
        camera_height: int = 480,
        target_fps: int = 30,
        queue_size: int = 10,
        profile_path: Optional[str] = None,
        use_mock: bool = False,
    ) -> None:
        self.camera_index = camera_index
        self.camera_width = camera_width
        self.camera_height = camera_height
        self.target_fps = target_fps
        self.queue_size = queue_size
        self.use_mock = use_mock

        # Shared bounded queue
        self.frame_queue: queue.Queue[Dict[str, Any]] = queue.Queue(maxsize=queue_size)

        # Threading controls
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

        # Vision pipeline components
        self.calibration_mgr = CalibrationManager(profile_path=profile_path)
        self.profile = self.calibration_mgr.profile

        self.camera = CameraManager(
            camera_index=camera_index,
            width=camera_width,
            height=camera_height,
            target_fps=target_fps,
        )
        self.extractor = FaceMeshExtractor()
        self.tracker = PointerTracker(profile=self.profile)
        self.detector = GestureDetector(profile=self.profile)

        # Performance and status tracking
        self.frame_count: int = 0
        self.dropped_frame_count: int = 0
        self.last_frame: Optional[np.ndarray] = None
        self.is_running: bool = False

    def start(self) -> bool:
        """Starts the camera acquisition and processing thread."""
        if self.is_running:
            return True

        if not self.use_mock:
            if not self.camera.open():
                # Attempt to run in mock mode if physical camera is busy or unavailable
                self.use_mock = True

        self._stop_event.clear()
        self.is_running = True
        self._thread = threading.Thread(target=self._worker_loop, daemon=True, name="VisionProducerThread")
        self._thread.start()
        return True

    def stop(self, timeout: float = 2.0) -> None:
        """Signals shutdown, waits for the background thread, and releases resources."""
        if not self.is_running:
            return

        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=timeout)

        self.camera.release()
        self.extractor.close()
        self.is_running = False

    def _worker_loop(self) -> None:
        """Continuous background loop processing frames at target FPS."""
        frame_interval = 1.0 / max(1, self.target_fps)

        while not self._stop_event.is_set():
            loop_start = time.perf_counter()

            if self.use_mock:
                success, frame, capture_ms, meta = self._generate_synthetic_frame()
            else:
                success, frame, capture_ms, meta = self.camera.read_frame()

            t_now = time.time()
            self.frame_count += 1

            if not success or frame is None:
                # Camera read dropped or offline
                event = self._build_event(
                    timestamp=t_now,
                    detected=False,
                    face_res=FaceMeshResult.create_null(0.0, reason="camera_offline"),
                    track_res=TrackingResult.create_null(),
                    gest_res=GestureResult.create_none(),
                    capture_ms=capture_ms,
                    fps=self.camera.current_fps,
                )
            else:
                self.last_frame = frame

                # 1. Landmark extraction & quality scoring
                face_res = self.extractor.process_frame(frame)

                # 2. Feed calibration manager if calibration is active
                if self.calibration_mgr.step.value != "idle" and self.calibration_mgr.step.value != "complete":
                    self.calibration_mgr.add_frame(face_res)
                    if self.calibration_mgr.profile.is_calibrated:
                        self.profile = self.calibration_mgr.profile
                        self.tracker.set_profile(self.profile)
                        self.detector.set_profile(self.profile)

                # 3. Pointer tracking & ability signals
                track_res = self.tracker.update(face_res, timestamp=t_now)

                # 4. Debounced expression detection
                gest_res = self.detector.update(face_res, timestamp=t_now)

                # 5. Assemble agreed frame event payload
                event = self._build_event(
                    timestamp=t_now,
                    detected=face_res.detected,
                    face_res=face_res,
                    track_res=track_res,
                    gest_res=gest_res,
                    capture_ms=capture_ms,
                    fps=self.camera.current_fps,
                )

            # 6. Push to bounded queue with drop-oldest policy
            self._enqueue_drop_oldest(event)

            # Pace loop to match target FPS
            elapsed = time.perf_counter() - loop_start
            sleep_needed = frame_interval - elapsed
            if sleep_needed > 0:
                time.sleep(sleep_needed)

    def _enqueue_drop_oldest(self, event: Dict[str, Any]) -> None:
        """
        Guarantees that the camera loop never blocks:
        If queue is full, discard the oldest item before placing the newest.
        """
        if self.frame_queue.full():
            try:
                self.frame_queue.get_nowait()
                self.dropped_frame_count += 1
            except queue.Empty:
                pass

        try:
            self.frame_queue.put_nowait(event)
        except queue.Full:
            pass

    def _build_event(
        self,
        timestamp: float,
        detected: bool,
        face_res: FaceMeshResult,
        track_res: TrackingResult,
        gest_res: GestureResult,
        capture_ms: float,
        fps: float,
    ) -> Dict[str, Any]:
        """Constructs standardized frame dictionary conforming to the team contract."""
        if not detected:
            return {
                "frame_index": self.frame_count,
                "timestamp": round(timestamp, 3),
                "detected": False,
                "face": None,
                "pointer": None,
                "raw_motion": None,
                "gesture": {
                    "name": "none",
                    "score": 0.0,
                    "held_ms": 0,
                },
                "timing": {
                    "capture_ms": round(capture_ms, 2),
                    "process_ms": round(face_res.process_ms, 2),
                    "fps": round(fps, 1),
                },
            }

        return {
            "frame_index": self.frame_count,
            "timestamp": round(timestamp, 3),
            "detected": True,
            "face": {
                "quality": face_res.quality,
                "width_norm": face_res.width_norm,
            },
            "pointer": {
                "nx": track_res.nx,
                "ny": track_res.ny,
            },
            "raw_motion": {
                "raw_dx": track_res.raw_dx,
                "raw_dy": track_res.raw_dy,
            },
            "gesture": {
                "name": gest_res.name,
                "score": gest_res.score,
                "held_ms": gest_res.held_ms,
            },
            "timing": {
                "capture_ms": round(capture_ms, 2),
                "process_ms": round(face_res.process_ms, 2),
                "fps": round(fps, 1),
            },
        }

    def _generate_synthetic_frame(self) -> Tuple[bool, np.ndarray, float, Dict[str, Any]]:
        """Generates a blank test image if running in mock mode."""
        frame = np.full((self.camera_height, self.camera_width, 3), 120, dtype=np.uint8)
        return True, frame, 3.2, {"fps": 30.0, "camera_connected": False, "brightness": 120.0, "low_light": False}

    def get_events(self, timeout: float = 0.1) -> Generator[Dict[str, Any], None, None]:
        """Generator allowing consumer to iterate through incoming frame events."""
        while self.is_running:
            try:
                event = self.frame_queue.get(timeout=timeout)
                yield event
            except queue.Empty:
                if self._stop_event.is_set():
                    break

    def __enter__(self) -> FrameProducer:
        self.start()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.stop()
