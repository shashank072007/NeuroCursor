"""
Unit and integration tests for Phase 2 of FLUX / NeuroCursor.
Verifies calibration profile persistence, guided calibration workflow with skip/retry,
pointer tracking coordinate mapping, One Euro Filter smoothing, raw offsets, and null-out safety.
"""

import os
import sys
import tempfile
import unittest

# Add project root to sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from vision.calibration import CalibrationManager, CalibrationProfile, CalibrationStep
from vision.landmarks import FaceMeshResult
from vision.tracking import PointerTracker, TrackingResult


class TestCalibration(unittest.TestCase):
    """Verifies CalibrationProfile and CalibrationManager."""

    def test_profile_serialization(self):
        profile = CalibrationProfile(
            neutral_x=0.48,
            neutral_y=0.52,
            face_width_ref=0.38,
            range_left=0.22,
            range_right=0.28,
            range_up=0.18,
            range_down=0.21,
            is_calibrated=True,
        )

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
            tmp_path = tmp.name

        try:
            profile.save(tmp_path)
            loaded = CalibrationProfile.load(tmp_path)
            self.assertIsNotNone(loaded)
            self.assertAlmostEqual(loaded.neutral_x, 0.48)
            self.assertAlmostEqual(loaded.range_right, 0.28)
            self.assertTrue(loaded.is_calibrated)
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    def test_calibration_skip_and_retry(self):
        manager = CalibrationManager(profile_path="non_existent.json")
        manager.start_range("left", duration_sec=10.0)
        self.assertEqual(manager.step, CalibrationStep.RANGE_LEFT)

        # Test retry
        msg_retry = manager.retry_step()
        self.assertIn("Retrying", msg_retry)
        self.assertEqual(manager.step, CalibrationStep.RANGE_LEFT)

        # Test skip
        msg_skip = manager.skip_step()
        self.assertIn("skipped", msg_skip)
        self.assertEqual(manager.step, CalibrationStep.IDLE)
        self.assertAlmostEqual(manager.profile.range_left, 0.25)

    def test_neutral_collection(self):
        import time
        manager = CalibrationManager()
        manager.start_neutral(duration_sec=0.01)

        # Feed neutral frames
        res = FaceMeshResult(
            detected=True,
            quality=0.95,
            width_norm=0.36,
            center_x=0.50,
            center_y=0.49,
            process_ms=10.0,
        )
        time.sleep(0.02)
        done, _ = manager.add_frame(res)
        self.assertTrue(done)

        self.assertAlmostEqual(manager.profile.neutral_x, 0.50, places=2)
        self.assertAlmostEqual(manager.profile.neutral_y, 0.49, places=2)
        self.assertAlmostEqual(manager.profile.face_width_ref, 0.36, places=2)


class TestPointerTracker(unittest.TestCase):
    """Verifies PointerTracker coordinate translation, smoothing, and ability offsets."""

    def setUp(self):
        self.profile = CalibrationProfile(
            neutral_x=0.50,
            neutral_y=0.50,
            face_width_ref=0.40,
            range_left=0.25,
            range_right=0.25,
            range_up=0.20,
            range_down=0.20,
        )
        self.tracker = PointerTracker(profile=self.profile)

    def test_neutral_pose_maps_to_center(self):
        # Resting center frame
        face = FaceMeshResult(
            detected=True,
            quality=0.92,
            width_norm=0.40,
            center_x=0.50,
            center_y=0.50,
            process_ms=10.0,
        )
        res = self.tracker.update(face, timestamp=1.0)
        self.assertTrue(res.detected)
        self.assertAlmostEqual(res.nx, 0.50, delta=0.05)
        self.assertAlmostEqual(res.ny, 0.50, delta=0.05)
        self.assertAlmostEqual(res.raw_dx, 0.0, delta=0.01)
        self.assertAlmostEqual(res.raw_dy, 0.0, delta=0.01)

    def test_rightward_movement(self):
        # Move right by 0.10 in viewport (0.10 / 0.40 = 0.25 face-width units = full right range)
        face = FaceMeshResult(
            detected=True,
            quality=0.90,
            width_norm=0.40,
            center_x=0.60,
            center_y=0.50,
            process_ms=10.0,
        )
        res = self.tracker.update(face, timestamp=2.0)
        self.assertTrue(res.detected)
        self.assertGreater(res.nx, 0.70)
        self.assertAlmostEqual(res.raw_dx, 0.25, delta=0.02)
        self.assertAlmostEqual(res.raw_dy, 0.0, delta=0.02)

    def test_boundary_clamping(self):
        # Extreme excursion beyond comfortable range
        face = FaceMeshResult(
            detected=True,
            quality=0.85,
            width_norm=0.40,
            center_x=0.95,
            center_y=0.95,
            process_ms=10.0,
        )
        res = self.tracker.update(face, timestamp=3.0)
        self.assertTrue(0.0 <= res.nx <= 1.0)
        self.assertTrue(0.0 <= res.ny <= 1.0)

    def test_strict_null_on_face_loss(self):
        face_lost = FaceMeshResult.create_null(process_ms=5.0)
        res = self.tracker.update(face_lost)
        self.assertFalse(res.detected)
        self.assertIsNone(res.nx)
        self.assertIsNone(res.ny)
        self.assertIsNone(res.raw_dx)
        self.assertIsNone(res.raw_dy)


if __name__ == "__main__":
    unittest.main()
