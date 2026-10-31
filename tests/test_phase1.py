"""
Unit and integration tests for Phase 1 of FLUX / NeuroCursor.
Verifies camera manager, landmark extraction, quality metrics, mock frame schema,
and the strict null-out contract.
"""

import json
import os
import sys
import unittest
import numpy as np

# Add project root to sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from vision.camera import CameraManager
from vision.landmarks import FaceMeshExtractor, FaceMeshResult
from vision.mock import MockFrameGenerator


class TestMockFrames(unittest.TestCase):
    """Verifies mock_frames.json schema against team contract."""

    def test_mock_frames_schema(self):
        mock_path = os.path.join(PROJECT_ROOT, "mock_frames.json")
        self.assertTrue(os.path.isfile(mock_path), "mock_frames.json must exist in project root")

        with open(mock_path, "r", encoding="utf-8") as f:
            frames = json.load(f)

        self.assertEqual(len(frames), 10, "mock_frames.json must contain exactly 10 frames")

        valid_gestures = {"none", "mouth_open", "brow_raise", "smile", "wink_left", "wink_right"}

        for frame in frames:
            self.assertIn("frame_index", frame)
            self.assertIn("timestamp", frame)
            self.assertIn("detected", frame)
            self.assertIn("timing", frame)
            self.assertIn("fps", frame["timing"])
            self.assertIn("capture_ms", frame["timing"])
            self.assertIn("process_ms", frame["timing"])

            if frame["detected"]:
                self.assertIsNotNone(frame["face"])
                self.assertIsNotNone(frame["pointer"])
                self.assertIsNotNone(frame["raw_motion"])
                self.assertIn("nx", frame["pointer"])
                self.assertIn("ny", frame["pointer"])
                self.assertTrue(0.0 <= frame["pointer"]["nx"] <= 1.0)
                self.assertTrue(0.0 <= frame["pointer"]["ny"] <= 1.0)
                self.assertIn("raw_dx", frame["raw_motion"])
                self.assertIn("raw_dy", frame["raw_motion"])
                self.assertIn(frame["gesture"]["name"], valid_gestures)
            else:
                # Null-out contract when face is lost
                self.assertIsNone(frame["face"], "face must be null when detected=false")
                self.assertIsNone(frame["pointer"], "pointer must be null when detected=false")
                self.assertIsNone(frame["raw_motion"], "raw_motion must be null when detected=false")
                self.assertEqual(frame["gesture"]["name"], "none")
                self.assertEqual(frame["gesture"]["score"], 0.0)
                self.assertEqual(frame["gesture"]["held_ms"], 0)

    def test_mock_frame_generator(self):
        generator = MockFrameGenerator(loop=False)
        streamed = list(generator.stream_frames(max_frames=5, realtime=False))
        self.assertEqual(len(streamed), 5)
        self.assertEqual(streamed[0]["frame_index"], 1)


class TestCameraManager(unittest.TestCase):
    """Verifies CameraManager error handling and utilities."""

    def test_camera_offline_graceful_handling(self):
        # Open an unlikely camera index to verify it fails gracefully without throwing
        cam = CameraManager(camera_index=999)
        opened = cam.open()
        self.assertFalse(opened, "Invalid camera index should return False")

        success, frame, capture_ms, meta = cam.read_frame()
        self.assertFalse(success)
        self.assertIsNone(frame)
        self.assertFalse(meta["camera_connected"])
        cam.release()

    def test_lighting_estimation(self):
        cam = CameraManager()
        # Test synthetic bright frame
        bright_frame = np.full((100, 100, 3), 180, dtype=np.uint8)
        brightness, is_low = cam.estimate_lighting(bright_frame)
        self.assertAlmostEqual(brightness, 180.0, places=1)
        self.assertFalse(is_low)

        # Test synthetic dark frame
        dark_frame = np.full((100, 100, 3), 20, dtype=np.uint8)
        brightness, is_low = cam.estimate_lighting(dark_frame)
        self.assertAlmostEqual(brightness, 20.0, places=1)
        self.assertTrue(is_low)


class TestLandmarks(unittest.TestCase):
    """Verifies FaceMeshExtractor null-out contract and quality scoring."""

    def test_null_contract_on_empty_frame(self):
        extractor = FaceMeshExtractor()
        result = extractor.process_frame(None)
        self.assertFalse(result.detected)
        self.assertEqual(result.quality, 0.0)
        self.assertIsNone(result.center_x)
        self.assertIsNone(result.center_y)
        self.assertIsNone(result.width_norm)
        extractor.close()

    def test_face_quality_computation(self):
        extractor = FaceMeshExtractor()
        # Test size scoring
        dummy_landmarks = [(0.5, 0.5, 0.0)] * 468
        chin = (0.5, 0.8, 0.0)
        forehead = (0.5, 0.2, 0.0)
        eye_l = (0.4, 0.4, 0.0)
        eye_r = (0.6, 0.4, 0.0)
        nose = (0.5, 0.5, 0.0)

        # Optimal size width_norm = 0.35
        q_optimal = extractor.compute_face_quality(
            landmarks=dummy_landmarks,
            width_norm=0.35,
            chin=chin,
            forehead=forehead,
            eye_l=eye_l,
            eye_r=eye_r,
            nose=nose,
        )
        self.assertGreaterEqual(q_optimal, 0.8)

        # Extreme small face width_norm = 0.05
        q_small = extractor.compute_face_quality(
            landmarks=dummy_landmarks,
            width_norm=0.05,
            chin=chin,
            forehead=forehead,
            eye_l=eye_l,
            eye_r=eye_r,
            nose=nose,
        )
        self.assertLess(q_small, 0.5)
        extractor.close()


if __name__ == "__main__":
    unittest.main()
