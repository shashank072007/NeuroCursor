"""
Unit and integration tests for Phase 4 of FLUX / NeuroCursor.
Verifies threaded frame producer, drop-oldest bounded queue, clean shutdown,
and the QA chaos simulator.
"""

import os
import queue
import sys
import time
import unittest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from simulator import VisionChaosSimulator
from vision.producer import FrameProducer


class TestFrameProducer(unittest.TestCase):
    """Verifies FrameProducer threading, queue drop-oldest policy, and shutdown."""

    def test_producer_lifecycle_and_event_schema(self):
        producer = FrameProducer(use_mock=True, queue_size=5, target_fps=60)
        started = producer.start()
        self.assertTrue(started)
        self.assertTrue(producer.is_running)

        # Collect 3 events from queue
        events = []
        for _ in range(5):
            try:
                ev = producer.frame_queue.get(timeout=1.0)
                events.append(ev)
                if len(events) >= 3:
                    break
            except queue.Empty:
                pass

        producer.stop()
        self.assertFalse(producer.is_running)
        self.assertGreaterEqual(len(events), 3)

        # Verify event schema
        ev0 = events[0]
        self.assertIn("frame_index", ev0)
        self.assertIn("timestamp", ev0)
        self.assertIn("detected", ev0)
        self.assertIn("gesture", ev0)
        self.assertIn("timing", ev0)
        self.assertIn("fps", ev0["timing"])

    def test_drop_oldest_queue_policy(self):
        """Producer must never block on a full queue; it drops the oldest frame."""
        producer = FrameProducer(use_mock=True, queue_size=3)

        # Manually fill the queue
        for i in range(3):
            producer._enqueue_drop_oldest({"dummy_id": i})

        self.assertEqual(producer.frame_queue.qsize(), 3)
        self.assertEqual(producer.dropped_frame_count, 0)

        # Enqueue a 4th event when queue is already full
        producer._enqueue_drop_oldest({"dummy_id": 999})

        # Queue size must still be 3, dropped count must increment
        self.assertEqual(producer.frame_queue.qsize(), 3)
        self.assertEqual(producer.dropped_frame_count, 1)

        # First item out should be dummy_id 1 (since 0 was dropped)
        item1 = producer.frame_queue.get_nowait()
        self.assertEqual(item1["dummy_id"], 1)


class TestChaosSimulator(unittest.TestCase):
    """Verifies Shashank's chaos test harness."""

    def test_occlusion_strict_null(self):
        sim = VisionChaosSimulator(mode="occlusion", occlusion_interval=10, occlusion_length=3)
        events = list(sim.generate_stream(duration_sec=0.5, realtime=False))

        occluded = [e for e in events if not e["detected"]]
        self.assertGreater(len(occluded), 0, "Occlusion events must be generated")

        for ev in occluded:
            self.assertIsNone(ev["pointer"])
            self.assertIsNone(ev["raw_motion"])
            self.assertIsNone(ev["face"])
            self.assertEqual(ev["gesture"]["name"], "none")

    def test_jitter_injection(self):
        sim_clean = VisionChaosSimulator(mode="none", jitter_sigma=0.0)
        sim_noisy = VisionChaosSimulator(mode="jitter", jitter_sigma=0.15)

        events_clean = list(sim_clean.generate_stream(duration_sec=0.5, realtime=False))
        events_noisy = list(sim_noisy.generate_stream(duration_sec=0.5, realtime=False))

        diffs = [
            abs(n["raw_motion"]["raw_dx"] - c["raw_motion"]["raw_dx"])
            for c, n in zip(events_clean, events_noisy)
            if c["detected"] and n["detected"]
        ]
        avg_diff = sum(diffs) / max(1, len(diffs))
        self.assertGreater(avg_diff, 0.05, "Jitter must produce measurable variance on raw_dx")


if __name__ == "__main__":
    unittest.main()
