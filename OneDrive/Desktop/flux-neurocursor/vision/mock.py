"""
Mock frame generator for FLUX / NeuroCursor.

Provides synthetic frame streaming and replay of mock_frames.json,
unblocking backend (Samrudh) and frontend (Sampada) development without webcam access.
"""

from __future__ import annotations

import json
import os
import time
from typing import Any, Dict, Generator, List, Optional


class MockFrameGenerator:
    """Replays or synthetically generates frame payloads matching the vision contract."""

    def __init__(
        self,
        mock_file_path: Optional[str] = None,
        loop: bool = True,
        frame_interval_sec: float = 0.033,  # ~30 FPS
    ) -> None:
        self.loop = loop
        self.frame_interval_sec = frame_interval_sec

        if mock_file_path is None:
            # Look for mock_frames.json in project root
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            mock_file_path = os.path.join(base_dir, "mock_frames.json")

        self.mock_file_path = mock_file_path
        self.frames: List[Dict[str, Any]] = self._load_mock_frames()

    def _load_mock_frames(self) -> List[Dict[str, Any]]:
        """Loads static frames from JSON file if available, otherwise generates defaults."""
        if os.path.isfile(self.mock_file_path):
            with open(self.mock_file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        return self._generate_default_frames()

    def _generate_default_frames(self) -> List[Dict[str, Any]]:
        """Fallback synthetic frames if JSON file is missing."""
        frames = []
        for i in range(1, 11):
            if i == 9:
                # Occlusion / face lost frame
                frames.append({
                    "frame_index": i,
                    "timestamp": time.time(),
                    "detected": False,
                    "face": None,
                    "pointer": None,
                    "raw_motion": None,
                    "gesture": {"name": "none", "score": 0.0, "held_ms": 0},
                    "timing": {"capture_ms": 3.5, "process_ms": 4.0, "fps": 30.0},
                })
            else:
                frames.append({
                    "frame_index": i,
                    "timestamp": time.time(),
                    "detected": True,
                    "face": {"quality": 0.92, "width_norm": 0.35},
                    "pointer": {"nx": 0.50 + (i * 0.01), "ny": 0.50 - (i * 0.01)},
                    "raw_motion": {"raw_dx": 0.01 * i, "raw_dy": -0.01 * i},
                    "gesture": {
                        "name": "mouth_open" if 6 <= i <= 7 else "none",
                        "score": 0.85 if 6 <= i <= 7 else 0.0,
                        "held_ms": (i - 5) * 120 if 6 <= i <= 7 else 0,
                    },
                    "timing": {"capture_ms": 3.8, "process_ms": 11.2, "fps": 29.5},
                })
        return frames

    def stream_frames(
        self,
        max_frames: Optional[int] = None,
        realtime: bool = True,
    ) -> Generator[Dict[str, Any], None, None]:
        """
        Yields frame dictionaries with updated current timestamps.

        Args:
            max_frames: Maximum number of frames to emit (None for infinite if loop=True)
            realtime: If True, sleeps between frames to match target frame rate.
        """
        emitted_count = 0
        while True:
            for base_frame in self.frames:
                frame = dict(base_frame)
                frame["timestamp"] = round(time.time(), 3)
                frame["frame_index"] = emitted_count + 1

                yield frame
                emitted_count += 1

                if max_frames is not None and emitted_count >= max_frames:
                    return

                if realtime:
                    time.sleep(self.frame_interval_sec)

            if not self.loop:
                break


if __name__ == "__main__":
    print("[MockFrameGenerator] Streaming 5 mock frames to stdout:")
    generator = MockFrameGenerator()
    for f in generator.stream_frames(max_frames=5, realtime=False):
        print(json.dumps(f, indent=2))
