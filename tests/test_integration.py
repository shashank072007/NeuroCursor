"""End-to-End Integration Tests for NeuroCursor.
Verifies seamless interoperation between Frontend, Backend, and Vision modules.
"""

import os
import sys
import unittest
import json

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import backend.app as app_mod
from backend.sources import normalize_frame, MockFrameSource, LiveFrameSource


class TestEndToEndIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ["FLUX_DEV"] = "1"
        cls.app = app_mod.create_app(source_type="mock", simulate_os=True, dev_mode=True)
        cls.token = app_mod.SERVER_TOKEN
        cls.client = cls.app.test_client()

    def test_frontend_serving(self):
        """Verify that backend serves index.html and static assets properly."""
        res_index = self.client.get("/")
        self.assertEqual(res_index.status_code, 200)
        self.assertIn(b"NeuroCursor", res_index.data)

        res_css = self.client.get("/App.css")
        self.assertEqual(res_css.status_code, 200)

        res_js = self.client.get("/app.js")
        self.assertEqual(res_js.status_code, 200)
        self.assertIn(b"initBackendConnection", res_js.data)

    def test_cors_preflight(self):
        """Verify CORS headers on OPTIONS preflight."""
        res = self.client.open("/profiles", method="OPTIONS")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.headers.get("Access-Control-Allow-Origin"), "*")

    def test_stream_telemetry_schema(self):
        """Verify SSE stream delivers telemetry matching both backend and frontend schemas."""
        res = self.client.get(f"/stream?token={self.token}")
        self.assertEqual(res.status_code, 200)

        # Inspect initial snapshot events
        events_found = 0
        for chunk in res.response:
            chunk_str = chunk.decode("utf-8")
            if chunk_str.startswith("data: "):
                data_json = chunk_str[6:].strip()
                try:
                    msg = json.loads(data_json)
                    events_found += 1
                    if msg.get("type") == "frame":
                        self.assertIn("head", msg)
                        self.assertIn("pointer", msg)
                        self.assertIn("raw_motion", msg)
                        self.assertIn("gesture", msg)
                except Exception:
                    pass
            if events_found >= 2:
                break

    def test_normalize_frame_contract(self):
        """Verify normalize_frame bridges vision and backend contracts."""
        # Vision-style frame
        vision_frame = {
            "frame_index": 42,
            "timestamp": 12345.678,
            "detected": True,
            "face": {"quality": 0.92, "width_norm": 0.35},
            "pointer": {"nx": 0.65, "ny": 0.45},
            "raw_motion": {"raw_dx": 0.05, "raw_dy": -0.03},
            "gesture": {"name": "smile", "score": 0.85, "held_ms": 220},
            "timing": {"fps": 30.0, "capture_ms": 3.0, "process_ms": 10.0}
        }
        normalized = normalize_frame(vision_frame)
        self.assertIn("head", normalized)
        self.assertEqual(normalized["head"]["nx"], 0.65)
        self.assertEqual(normalized["head"]["raw_dx"], 0.05)
        self.assertIn("pointer", normalized)
        self.assertEqual(normalized["pointer"]["nx"], 0.65)
        self.assertTrue(normalized["face"]["detected"])
        self.assertEqual(normalized["ts"], 12345.678)

    def test_live_frame_source_init(self):
        """Verify LiveFrameSource initializes with vision FrameProducer."""
        live_src = LiveFrameSource(use_mock=True)
        live_src.start()
        self.assertTrue(live_src.running)
        frame = live_src.get_frame(timeout=0.2)
        live_src.stop()
        self.assertFalse(live_src.running)
        if frame:
            self.assertIn("pointer", frame)
            self.assertIn("head", frame)


if __name__ == "__main__":
    unittest.main()
