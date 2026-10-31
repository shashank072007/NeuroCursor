"""Comprehensive Test Suite for FLUX Backend.
Validates all modules against FLUX-CONTRACT v1.1.
"""

import os
import sys
import time
import json
import unittest

# Ensure backend package can be imported
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

import backend
from backend.config import (
    FRAME_HZ, FACE_LOST_MS, Q_MIN, COOLDOWN_MS,
    UNDO_WINDOW_MS, BENCH_COLUMNS
)
from backend.bus import bus, next_seq, make_msg
from backend.profiles import profile_mgr
from backend.calibration import calibration_engine
from backend.safety import safety_manager
from backend.os_control import os_controller
from backend.intent_guard import IntentGuard
from backend.effort import EffortMeter
from backend.adapt import AdaptiveEngine, ADAPTATION_TABLE
from backend.channels import ChannelManager
from backend.bench import bench_storage
from backend.sources import MockFrameSource
from backend.app import create_app, SERVER_TOKEN


class TestBusAndMessages(unittest.TestCase):
    def test_sequence_counters(self):
        s1 = next_seq("test_msg")
        s2 = next_seq("test_msg")
        self.assertEqual(s2, s1 + 1)

        f1 = next_seq("frame")
        f2 = next_seq("frame")
        self.assertEqual(f2, f1 + 1)

    def test_make_msg_envelope(self):
        msg = make_msg("test_type", foo="bar")
        self.assertEqual(msg["v"], 1)
        self.assertEqual(msg["type"], "test_type")
        self.assertIn("seq", msg)
        self.assertIn("ts", msg)
        self.assertEqual(msg["foo"], "bar")

    def test_bus_snapshot_and_broadcast(self):
        m1 = make_msg("status", paused=False, locked=False)
        bus.broadcast(m1)

        q, snapshot = bus.subscribe()
        try:
            # Snapshot should contain the cached status
            types = [s["type"] for s in snapshot]
            self.assertIn("status", types)

            # Broadcast another message
            m2 = make_msg("effort", score=10)
            bus.broadcast(m2)

            received = q.get(timeout=0.5)
            self.assertEqual(received["type"], "effort")
        finally:
            bus.unsubscribe(q)


class TestProfilesAndCalibration(unittest.TestCase):
    def test_default_profiles_exist(self):
        profiles = profile_mgr.list_profiles()
        self.assertIn("demo_profile", profiles)
        demo = profile_mgr.get_profile("demo_profile")
        self.assertIsNotNone(demo)
        self.assertEqual(demo["v"], 1)
        self.assertIn("neutral", demo)
        self.assertIn("range", demo)
        self.assertIn("gesture_thresholds", demo)

    def test_calibration_orchestration(self):
        calib = calibration_engine
        start_res = calib.start("test_calib_user")
        self.assertTrue(start_res["ok"])
        self.assertEqual(start_res["profile_id"], "test_calib_user")

        # Execute neutral step
        step_res = calib.execute_step("neutral", 1)
        self.assertTrue(step_res["ok"])

        # Execute directional steps
        calib.execute_step("right", 1)
        calib.execute_step("left", 1)
        calib.execute_step("up", 1)
        calib.execute_step("down", 1)

        # Execute gesture steps
        for g in ("mouth_open", "brow_raise", "smile"):
            for rep in (1, 2, 3):
                calib.execute_step(f"gesture:{g}", rep)

        # Commit profile
        commit_res = calib.commit()
        self.assertTrue(commit_res["ok"])
        p = commit_res["profile"]
        self.assertEqual(p["profile_id"], "test_calib_user")
        # Formula: range.x = 0.8 * (0.11 + 0.11) = 0.176
        self.assertAlmostEqual(p["range"]["x"], 0.176, places=2)
        # Check gesture thresholds in [0.40, 0.70]
        for g, thresh in p["gesture_thresholds"].items():
            self.assertGreaterEqual(thresh, 0.40)
            self.assertLessEqual(thresh, 0.70)


class TestSafety(unittest.TestCase):
    def test_pause_and_lock(self):
        safety = safety_manager
        safety.face_lost = False
        safety.resume()
        safety.unlock()
        self.assertFalse(safety.paused)
        self.assertFalse(safety.locked)

        safety.pause()
        self.assertTrue(safety.paused)
        self.assertTrue(safety.can_move_pointer())  # Pointer still moves when paused
        self.assertFalse(safety.can_execute_action())

        safety.lock()
        self.assertTrue(safety.locked)
        self.assertFalse(safety.can_move_pointer())  # Pointer stops when locked
        self.assertFalse(safety.can_execute_action())

        safety.unlock()
        safety.resume()
        self.assertFalse(safety.paused)
        self.assertFalse(safety.locked)

    def test_face_lost_timeout(self):
        safety = safety_manager
        now = time.time()
        # Detected
        lost = safety.update_face_tracking(True, now)
        self.assertFalse(lost)

        # 100 ms missing -> not yet lost
        lost = safety.update_face_tracking(False, now + 0.1)
        self.assertFalse(lost)

        # 250 ms missing -> lost (FACE_LOST_MS = 200)
        lost = safety.update_face_tracking(False, now + 0.25)
        self.assertTrue(lost)
        self.assertFalse(safety.can_move_pointer())


class TestIntentGuard(unittest.TestCase):
    def setUp(self):
        os_controller.simulate = True
        self.guard = IntentGuard(os_controller)
        self.profile = profile_mgr.get_profile("demo_profile")
        self.ui_state = {
            "level": "fresh",
            "gesture_threshold_mult": 1.0,
            "gesture_hold_ms": 150,
            "dwell_ms": 800,
            "primary_channel": "gesture"
        }

    def test_pointer_fast_reject(self):
        now = time.time()
        # Simulate fast moving pointer
        self.guard.update_pointer_history(0.1, 0.1, now - 0.1)
        self.guard.update_pointer_history(0.8, 0.8, now)

        frame = make_msg(
            "frame",
            face={"detected": True, "quality": 0.95},
            head={"nx": 0.8, "ny": 0.8, "raw_dx": 0.05, "raw_dy": 0.05, "sm_dx": 0.05, "sm_dy": 0.05},
            gesture={"name": "mouth_open", "score": 0.90, "held_ms": 200}
        )

        guard_msg, action_msg, _ = self.guard.process_frame(
            frame, self.ui_state, self.profile, paused=False, locked=False, face_lost=False
        )

        self.assertIsNotNone(guard_msg)
        self.assertEqual(guard_msg["decision"], "reject")
        self.assertEqual(guard_msg["reason"], "pointer_fast")
        self.assertIsNone(action_msg)  # Reject NEVER produces action

    def test_successful_gesture_execution(self):
        now = time.time()
        # Still pointer
        self.guard.update_pointer_history(0.5, 0.5, now - 0.1)
        self.guard.update_pointer_history(0.5, 0.5, now)

        frame = make_msg(
            "frame",
            face={"detected": True, "quality": 0.95},
            head={"nx": 0.5, "ny": 0.5, "raw_dx": 0.01, "raw_dy": 0.01, "sm_dx": 0.01, "sm_dy": 0.01},
            gesture={"name": "mouth_open", "score": 0.90, "held_ms": 180}
        )

        guard_msg, action_msg, _ = self.guard.process_frame(
            frame, self.ui_state, self.profile, paused=False, locked=False, face_lost=False
        )

        self.assertIsNotNone(guard_msg)
        self.assertEqual(guard_msg["decision"], "allow")
        self.assertIsNone(guard_msg["reason"])
        self.assertIsNotNone(action_msg)
        self.assertEqual(action_msg["action"], "left_click")
        self.assertFalse(action_msg["undone"])
        self.assertGreater(action_msg["latency_ms"], 0)

    def test_undo_action(self):
        now = time.time()
        self.guard.update_pointer_history(0.5, 0.5, now)
        frame = make_msg(
            "frame",
            face={"detected": True, "quality": 0.95},
            head={"nx": 0.5, "ny": 0.5, "raw_dx": 0.01, "raw_dy": 0.01, "sm_dx": 0.01, "sm_dy": 0.01},
            gesture={"name": "mouth_open", "score": 0.90, "held_ms": 180}
        )
        _, action_msg, _ = self.guard.process_frame(
            frame, self.ui_state, self.profile, paused=False, locked=False, face_lost=False
        )
        self.assertIsNotNone(action_msg)
        orig_seq = action_msg["seq"]

        # Call undo
        undone = self.guard.handle_undo()
        self.assertIsNotNone(undone)
        self.assertEqual(undone["seq"], orig_seq)  # Same seq (G8)
        self.assertTrue(undone["undone"])


class TestEffortAndAdaptation(unittest.TestCase):
    def test_effort_meter_warmup(self):
        now = time.time()
        meter = EffortMeter(start_time=now)
        profile = profile_mgr.get_profile("demo_profile")

        # 5 seconds in -> warmup active (WARMUP_S = 20)
        msg = meter.tick(profile, current_time=now + 5.0)
        self.assertFalse(msg["samples_ok"])
        self.assertEqual(msg["level"], "fresh")

        # 25 seconds in -> warmup cleared
        msg = meter.tick(profile, current_time=now + 25.0)
        self.assertTrue(msg["samples_ok"])

    def test_adaptation_table_values(self):
        adapt = AdaptiveEngine()
        profile = profile_mgr.get_profile("demo_profile")

        for level in ("fresh", "moderate", "high", "rest"):
            ui, _ = adapt.compute_ui_state(level, range_now=1.0, profile=profile)
            expected = ADAPTATION_TABLE[level]
            self.assertEqual(ui["target_scale"], expected["target_scale"])
            self.assertEqual(ui["dwell_ms"], expected["dwell_ms"])
            self.assertEqual(ui["radial_bubbles"], expected["radial_bubbles"])
            self.assertEqual(ui["smoothing_alpha"], expected["smoothing_alpha"])
            self.assertEqual(ui["gesture_threshold_mult"], expected["gesture_threshold_mult"])
            self.assertEqual(ui["gesture_hold_ms"], expected["gesture_hold_ms"])

    def test_static_mode(self):
        adapt = AdaptiveEngine()
        adapt.set_mode("static")
        profile = profile_mgr.get_profile("demo_profile")

        # In static mode, even if level is rest, UI state is frozen at fresh and lens is disabled
        ui, _ = adapt.compute_ui_state("rest", range_now=0.5, profile=profile)
        self.assertEqual(ui["level"], "fresh")
        self.assertEqual(ui["target_scale"], 1.0)
        self.assertFalse(ui["lens"]["enabled"])
        self.assertIsNone(ui["suggest_channel"])


class TestChannelsAndBench(unittest.TestCase):
    def test_channels_reliability(self):
        ch = ChannelManager()
        # Less than 3 attempts -> None
        self.assertIsNone(ch.get_reliability("gesture"))

        # Add 3 successful attempts
        ch.record_attempt("gesture", True)
        ch.record_attempt("gesture", True)
        ch.record_attempt("gesture", True)
        self.assertEqual(ch.get_reliability("gesture"), 1.0)

        # Add 1 failed attempt -> 3/4 = 0.75
        ch.record_attempt("gesture", False)
        self.assertEqual(ch.get_reliability("gesture"), 0.75)

    def test_bench_csv_columns(self):
        row = {
            "session_id": "test_s1",
            "tester": "Samrudh",
            "condition": "flux",
            "fatigue": "rested",
            "task": "A",
            "target_id": "btn_1",
            "target_size_px": 48,
            "t_start": 100.0,
            "t_end": 102.5,
            "time_ms": 2500,
            "hit": 1,
            "error_dist_px": 5.2,
            "false_click_flag": 0,
            "guard_rejects": 1,
            "effort_score": 35,
            "level": "moderate"
        }
        ok = bench_storage.log_trial(row)
        self.assertTrue(ok)

        csv_text = bench_storage.export_csv("test_s1")
        header = csv_text.splitlines()[0]
        expected_header = ",".join(BENCH_COLUMNS)
        self.assertEqual(header, expected_header)


class TestAppEndpoints(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = create_app(source_type="mock", simulate_os=True)
        cls.client = cls.app.test_client()

    @classmethod
    def tearDownClass(cls):
        import backend.app as app_mod
        if app_mod.pipeline:
            app_mod.pipeline.stop()
        safety_manager.stop()

    def test_unauthorized_without_token(self):
        res = self.client.get("/profiles")
        self.assertEqual(res.status_code, 401)

    def test_authorized_with_token(self):
        headers = {"X-Flux-Token": SERVER_TOKEN}
        res = self.client.get("/profiles", headers=headers)
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertIn("profiles", data)

    def test_pause_resume_endpoints(self):
        headers = {"X-Flux-Token": SERVER_TOKEN}
        res = self.client.post("/pause", headers=headers)
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.get_json()["paused"])

        res = self.client.post("/resume", headers=headers)
        self.assertEqual(res.status_code, 200)
        self.assertFalse(res.get_json()["paused"])

    def test_dev_effort_override(self):
        headers = {"X-Flux-Token": SERVER_TOKEN}
        res = self.client.post("/dev/effort", headers=headers, json={"score": 75})
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.get_json()["simulated"])

    def test_stream_connect_snapshot(self):
        res = self.client.get(f"/stream?token={SERVER_TOKEN}")
        self.assertEqual(res.status_code, 200)
        gen = res.response
        first_chunk = next(gen)
        self.assertIn(b"data: ", first_chunk)
        res.close()


if __name__ == "__main__":
    res = unittest.main(exit=False)
    safety_manager.stop()
    os._exit(0 if res.result.wasSuccessful() else 1)
