"""
Unit and integration tests for Phase 3 of FLUX / NeuroCursor.
Verifies expression detection, bilateral blink suppression, single-frame debounce filtering,
continuous held_ms progression, strict enum adherence, and null-out safety.
"""

import os
import sys
import unittest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from vision.calibration import CalibrationProfile
from vision.gestures import GestureDetector, GestureEnum, GestureResult
from vision.landmarks import FaceMeshResult


class TestGestures(unittest.TestCase):
    """Verifies GestureDetector adherence to the team contract."""

    def setUp(self):
        self.profile = CalibrationProfile(
            neutral_mouth_ratio=0.05,
            neutral_brow_ratio=0.20,
            neutral_left_ear=0.28,
            neutral_right_ear=0.28,
        )
        self.detector = GestureDetector(profile=self.profile, activation_frames=2, release_frames=2)
        self.allowed_enums = {e.value for e in GestureEnum}

    def _create_face(self, blendshapes=None, detected=True):
        return FaceMeshResult(
            detected=detected,
            quality=0.92 if detected else 0.0,
            width_norm=0.35 if detected else None,
            center_x=0.50 if detected else None,
            center_y=0.50 if detected else None,
            process_ms=10.0,
            blendshapes=blendshapes or {},
        )

    def test_strict_enum_adherence(self):
        face = self._create_face({"jawOpen": 0.80})
        res = self.detector.update(face, timestamp=1.0)
        self.assertIn(res.name, self.allowed_enums)

    def test_bilateral_blink_suppression(self):
        """REQ-EXP-02: Ordinary involuntary blinks must NEVER be emitted as winks."""
        # Both eyes close simultaneously
        blink_face = self._create_face({"eyeBlinkLeft": 0.88, "eyeBlinkRight": 0.85})

        for i in range(5):
            res = self.detector.update(blink_face, timestamp=1.0 + (i * 0.033))
            self.assertEqual(
                res.name,
                GestureEnum.NONE.value,
                f"Bilateral blink must emit 'none', got '{res.name}'",
            )
            self.assertEqual(res.held_ms, 0)

    def test_asymmetric_winks(self):
        # Left eye closed, right eye open -> wink_left after 2 debounce frames
        wink_l_face = self._create_face({"eyeBlinkLeft": 0.85, "eyeBlinkRight": 0.05})

        # Frame 1: Candidate detected but debounced (stays none)
        res1 = self.detector.update(wink_l_face, timestamp=1.000)
        self.assertEqual(res1.name, GestureEnum.NONE.value)

        # Frame 2: Sustained activation threshold met -> transitions to active!
        res2 = self.detector.update(wink_l_face, timestamp=1.033)
        self.assertEqual(res2.name, GestureEnum.WINK_LEFT.value)
        self.assertGreaterEqual(res2.score, 0.45)

        # Right eye closed, left eye open -> wink_right
        self.detector.reset()
        wink_r_face = self._create_face({"eyeBlinkRight": 0.85, "eyeBlinkLeft": 0.05})
        self.detector.update(wink_r_face, timestamp=2.000)
        res_r2 = self.detector.update(wink_r_face, timestamp=2.033)
        self.assertEqual(res_r2.name, GestureEnum.WINK_RIGHT.value)

    def test_single_frame_glitch_debouncing(self):
        """REQ-EXP-04: Single-frame expression spikes must not become active gestures."""
        spike_face = self._create_face({"jawOpen": 0.95})
        neutral_face = self._create_face({})

        # Frame 1: Glitch spike
        res1 = self.detector.update(spike_face, timestamp=1.000)
        self.assertEqual(res1.name, GestureEnum.NONE.value, "1-frame spike must be suppressed")

        # Frame 2: Immediately returns to neutral
        res2 = self.detector.update(neutral_face, timestamp=1.033)
        self.assertEqual(res2.name, GestureEnum.NONE.value, "Must remain none after spike clears")

    def test_continuous_held_ms_progression(self):
        """REQ-EXP-04: Sustained gestures must exhibit continuous held_ms progression."""
        smile_face = self._create_face({"mouthSmileLeft": 0.75, "mouthSmileRight": 0.75})

        # Frame 1: Candidate frame
        self.detector.update(smile_face, timestamp=1.000)

        # Frame 2: Activated at t=1.033
        res2 = self.detector.update(smile_face, timestamp=1.033)
        self.assertEqual(res2.name, GestureEnum.SMILE.value)
        self.assertEqual(res2.held_ms, 0)

        # Frame 3: Held for 100ms
        res3 = self.detector.update(smile_face, timestamp=1.133)
        self.assertEqual(res3.name, GestureEnum.SMILE.value)
        self.assertAlmostEqual(res3.held_ms, 100, delta=5)

        # Frame 4: Held for 250ms
        res4 = self.detector.update(smile_face, timestamp=1.283)
        self.assertEqual(res4.name, GestureEnum.SMILE.value)
        self.assertAlmostEqual(res4.held_ms, 250, delta=5)

    def test_strict_reset_on_face_loss(self):
        # Establish active mouth_open gesture
        open_face = self._create_face({"jawOpen": 0.85})
        self.detector.update(open_face, timestamp=1.000)
        self.detector.update(open_face, timestamp=1.033)
        self.assertEqual(self.detector.current_active, GestureEnum.MOUTH_OPEN.value)

        # Face suddenly lost
        lost_face = FaceMeshResult.create_null(process_ms=4.0)
        res = self.detector.update(lost_face, timestamp=1.066)
        self.assertEqual(res.name, GestureEnum.NONE.value)
        self.assertEqual(res.score, 0.0)
        self.assertEqual(res.held_ms, 0)
        self.assertEqual(self.detector.current_active, GestureEnum.NONE.value)


if __name__ == "__main__":
    unittest.main()
