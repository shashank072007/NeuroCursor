"""
QA Test Harness & Chaos Simulator for FLUX / NeuroCursor.

Allows Shashank (QA / Testing) to synthetically inject:
  1. Jitter / Tremor (Gaussian noise on raw_dx, raw_dy) -> verifies backend interaction-effort proxy.
  2. Range Loss (compressed excursion reach) -> verifies backend adaptive sensitivity.
  3. Tracking Loss / Occlusion (periodic detected=False bursts) -> verifies fail-safe null-out handling.
  4. Expression Spikes (1-frame expression glitches) -> verifies debounce stability.

Usage:
    python simulator.py --mode jitter --duration 3
    python simulator.py --mode low_range --duration 3
    python simulator.py --mode occlusion --duration 3
    python simulator.py --mode all --duration 5 --output test_run.json
"""

from __future__ import annotations

import argparse
import json
import math
import os
import random
import sys
import time
from typing import Any, Dict, Generator, List, Optional


class VisionChaosSimulator:
    """Generates synthetic frame events with controllable anomaly injection."""

    def __init__(
        self,
        mode: str = "all",
        jitter_sigma: float = 0.06,        # Significant tremor on raw displacement
        range_compression: float = 0.20,   # User only able to move 20% of normal range
        occlusion_interval: int = 25,      # Drop tracking every 25 frames
        occlusion_length: int = 5,         # Face lost for 5 consecutive frames (~160ms)
        target_fps: float = 30.0,
    ) -> None:
        self.mode = mode
        self.jitter_sigma = jitter_sigma
        self.range_compression = range_compression
        self.occlusion_interval = occlusion_interval
        self.occlusion_length = occlusion_length
        self.target_fps = target_fps

    def generate_stream(
        self,
        duration_sec: float = 3.0,
        realtime: bool = False,
    ) -> Generator[Dict[str, Any], None, None]:
        """Yields synthetic frame events matching the team contract with injected chaos."""
        total_frames = int(duration_sec * self.target_fps)
        interval = 1.0 / self.target_fps
        t_start = time.time()

        for frame_idx in range(1, total_frames + 1):
            t_now = t_start + (frame_idx * interval)

            # Check if this frame is an occlusion event
            is_occluded = False
            if self.mode in ("occlusion", "all"):
                cycle_pos = frame_idx % self.occlusion_interval
                if 0 <= cycle_pos < self.occlusion_length:
                    is_occluded = True

            if is_occluded:
                # STRICT NULL-OUT CONTRACT: face is lost
                event = {
                    "frame_index": frame_idx,
                    "timestamp": round(t_now, 3),
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
                        "capture_ms": 3.2,
                        "process_ms": 3.8,
                        "fps": round(self.target_fps, 1),
                    },
                    "chaos_metadata": {"injected_fault": "occlusion_loss"},
                }
            else:
                # Synthesize smooth base motion (circular trajectory)
                angle = (frame_idx / 30.0) * (2.0 * math.pi)
                base_dx = 0.15 * math.cos(angle)
                base_dy = 0.12 * math.sin(angle)

                # 1. Apply range compression (simulating low mobility / range loss)
                if self.mode in ("low_range", "all"):
                    base_dx *= self.range_compression
                    base_dy *= self.range_compression

                # 2. Inject tremor / jitter into raw offsets
                raw_dx = base_dx
                raw_dy = base_dy
                if self.mode in ("jitter", "all"):
                    raw_dx += random.gauss(0.0, self.jitter_sigma)
                    raw_dy += random.gauss(0.0, self.jitter_sigma)

                # Derive pointer coordinates
                nx = max(0.0, min(1.0, 0.50 + base_dx * 2.0))
                ny = max(0.0, min(1.0, 0.50 + base_dy * 2.0))

                # 3. Inject gesture spikes or held expressions
                gesture_name = "none"
                gesture_score = 0.0
                gesture_held = 0

                if self.mode in ("spikes", "all") and frame_idx % 40 == 15:
                    # 1-frame glitch spike (should be ignored by debounce)
                    gesture_name = "mouth_open"
                    gesture_score = 0.88
                    gesture_held = 0
                elif 50 <= (frame_idx % 80) <= 65:
                    # Sustained deliberate gesture
                    gesture_name = "smile"
                    gesture_score = 0.82
                    gesture_held = int(((frame_idx % 80) - 50) * interval * 1000)

                event = {
                    "frame_index": frame_idx,
                    "timestamp": round(t_now, 3),
                    "detected": True,
                    "face": {
                        "quality": round(random.uniform(0.85, 0.96), 2),
                        "width_norm": 0.36,
                    },
                    "pointer": {
                        "nx": round(nx, 3),
                        "ny": round(ny, 3),
                    },
                    "raw_motion": {
                        "raw_dx": round(raw_dx, 4),
                        "raw_dy": round(raw_dy, 4),
                    },
                    "gesture": {
                        "name": gesture_name,
                        "score": round(gesture_score, 2),
                        "held_ms": gesture_held,
                    },
                    "timing": {
                        "capture_ms": round(random.uniform(3.0, 4.2), 2),
                        "process_ms": round(random.uniform(9.5, 12.0), 2),
                        "fps": round(self.target_fps, 1),
                    },
                    "chaos_metadata": {
                        "injected_fault": self.mode,
                        "raw_dx_true": round(base_dx, 4),
                        "raw_dy_true": round(base_dy, 4),
                    },
                }

            yield event

            if realtime:
                time.sleep(interval)


def main() -> None:
    parser = argparse.ArgumentParser(description="FLUX / NeuroCursor - QA Chaos Simulator (for Shashank)")
    parser.add_argument(
        "--mode",
        choices=["jitter", "low_range", "occlusion", "spikes", "all"],
        default="all",
        help="Type of synthetic fault to inject (default: all)",
    )
    parser.add_argument("--duration", type=float, default=2.0, help="Test duration in seconds (default: 2.0)")
    parser.add_argument("--output", type=str, default=None, help="Save generated frames to JSON file")
    parser.add_argument("--realtime", action="store_true", help="Pace output to 30 FPS")
    args = parser.parse_args()

    simulator = VisionChaosSimulator(mode=args.mode)
    print(f"[ChaosSimulator] Generating {args.duration}s of mode='{args.mode}'...")

    frames: List[Dict[str, Any]] = []
    for event in simulator.generate_stream(duration_sec=args.duration, realtime=args.realtime):
        frames.append(event)
        # Print summary line to stdout
        detected_flag = "[OK]" if event["detected"] else "[LOST]"
        if event["detected"]:
            nx, ny = event["pointer"]["nx"], event["pointer"]["ny"]
            rdx, rdy = event["raw_motion"]["raw_dx"], event["raw_motion"]["raw_dy"]
            g_name = event["gesture"]["name"]
            print(f"[{event['frame_index']:03d}] {detected_flag} | pos=({nx:.2f}, {ny:.2f}) | raw=({rdx:+.3f}, {rdy:+.3f}) | gest={g_name}")
        else:
            print(f"[{event['frame_index']:03d}] {detected_flag} | [STRICT NULL: coordinates cleared]")

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(frames, f, indent=2)
        print(f"[ChaosSimulator] Exported {len(frames)} frames to '{args.output}'.")


if __name__ == "__main__":
    main()
