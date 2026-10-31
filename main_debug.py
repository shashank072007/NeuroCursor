"""
Interactive debug visualizer for FLUX / NeuroCursor.

Provides a live OpenCV HUD overlay showing detected face landmarks, tracking crosshair,
real FPS, capture/process latencies, face quality bar, active expression banner,
and interactive calibration controls.

Usage:
    python main_debug.py                # Uses real webcam index 0
    python main_debug.py --mock         # Runs with synthetic mock stream (no camera needed)
    python main_debug.py --camera 1     # Selects camera index 1
"""

from __future__ import annotations

import argparse
import os
import sys
import time

# Ensure project root in sys.path
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import cv2
import numpy as np

from vision.calibration import CalibrationManager, CalibrationStep
from vision.camera import CameraManager
from vision.gestures import GestureDetector, GestureEnum
from vision.landmarks import FaceMeshExtractor
from vision.mock import MockFrameGenerator
from vision.tracking import PointerTracker


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="FLUX / NeuroCursor - Vision Debug HUD")
    parser.add_argument("--camera", type=int, default=0, help="Camera device index (default: 0)")
    parser.add_argument("--mock", action="store_true", help="Run with synthetic mock frame generator")
    parser.add_argument("--width", type=int, default=640, help="Camera width (default: 640)")
    parser.add_argument("--height", type=int, default=480, help="Camera height (default: 480)")
    parser.add_argument("--profile", type=str, default=None, help="Path to custom calibration.json")
    return parser.parse_args()


def render_hud(
    frame: np.ndarray,
    face_res,
    track_res,
    gest_res,
    calib_mgr: CalibrationManager,
    fps: float,
    capture_ms: float,
) -> np.ndarray:
    """Renders all diagnostic overlays directly on the frame."""
    h, w = frame.shape[:2]

    # 1. Dark semi-transparent header bar
    overlay = frame.copy()
    cv2.rectangle(overlay, (0, 0), (w, 55), (20, 20, 20), -1)
    cv2.addWeighted(overlay, 0.75, frame, 0.25, 0, frame)

    # 2. Performance & Timing Metrics
    fps_color = (0, 255, 0) if fps >= 25 else (0, 165, 255) if fps >= 15 else (0, 0, 255)
    cv2.putText(frame, f"FPS: {fps:.1f}", (15, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.6, fps_color, 2)
    cv2.putText(frame, f"Cap: {capture_ms:.1f}ms", (130, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)
    proc_ms = face_res.process_ms if face_res else 0.0
    cv2.putText(frame, f"Proc: {proc_ms:.1f}ms", (230, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)

    # 3. Quality Gauge Bar
    quality = face_res.quality if (face_res and face_res.detected) else 0.0
    q_color = (0, 255, 0) if quality >= 0.7 else (0, 165, 255) if quality >= 0.45 else (0, 0, 255)
    cv2.putText(frame, f"Qual: {quality:.2f}", (340, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.5, q_color, 1)

    # Mini quality bar
    bar_x, bar_y, bar_w, bar_h = 440, 15, 80, 12
    cv2.rectangle(frame, (bar_x, bar_y), (bar_x + bar_w, bar_y + bar_h), (80, 80, 80), 1)
    fill_w = int(bar_w * quality)
    if fill_w > 0:
        cv2.rectangle(frame, (bar_x, bar_y), (bar_x + fill_w, bar_y + bar_h), q_color, -1)

    # Status pill
    status_str = "TRACKING" if (face_res and face_res.detected) else "FACE LOST"
    status_col = (0, 255, 0) if (face_res and face_res.detected) else (0, 0, 255)
    cv2.putText(frame, status_str, (w - 105, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.5, status_col, 2)

    # 4. Virtual Cursor Preview Box (Mini viewport top-right)
    box_w, box_h = 130, 100
    box_x = w - box_w - 15
    box_y = 65

    # Draw box background
    cv2.rectangle(frame, (box_x, box_y), (box_x + box_w, box_y + box_h), (35, 35, 35), -1)
    cv2.rectangle(frame, (box_x, box_y), (box_x + box_w, box_y + box_h), (100, 100, 100), 1)
    cv2.putText(frame, "Cursor [0,1]", (box_x + 5, box_y - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (180, 180, 180), 1)

    # Draw center reticle in preview box
    cx, cy = box_x + box_w // 2, box_y + box_h // 2
    cv2.line(frame, (cx - 5, cy), (cx + 5, cy), (70, 70, 70), 1)
    cv2.line(frame, (cx, cy - 5), (cx, cy + 5), (70, 70, 70), 1)

    if track_res and track_res.detected and track_res.nx is not None and track_res.ny is not None:
        # Crosshair cursor dot
        dot_x = int(box_x + track_res.nx * box_w)
        dot_y = int(box_y + track_res.ny * box_h)
        cv2.circle(frame, (dot_x, dot_y), 4, (0, 255, 255), -1)
        cv2.putText(
            frame,
            f"nx:{track_res.nx:.2f} ny:{track_res.ny:.2f}",
            (box_x + 5, box_y + box_h - 5),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.35,
            (255, 255, 255),
            1,
        )

    # 5. Raw Ability Signal Box
    if track_res and track_res.detected and track_res.raw_dx is not None and track_res.raw_dy is not None:
        cv2.putText(
            frame,
            f"raw_dx: {track_res.raw_dx:+.3f} fw",
            (15, h - 35),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            (180, 220, 255),
            1,
        )
        cv2.putText(
            frame,
            f"raw_dy: {track_res.raw_dy:+.3f} fw",
            (15, h - 15),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            (180, 220, 255),
            1,
        )

    # 6. Active Physical Gesture Banner
    if gest_res and gest_res.name != GestureEnum.NONE.value:
        g_banner_y = h - 60
        g_name_str = gest_res.name.upper()
        g_score_str = f"{gest_res.score:.2f}"
        g_held_str = f"{gest_res.held_ms}ms"

        # Highlight banner
        cv2.rectangle(frame, (w - 240, g_banner_y), (w - 15, g_banner_y + 45), (0, 100, 0), -1)
        cv2.rectangle(frame, (w - 240, g_banner_y), (w - 15, g_banner_y + 45), (0, 255, 0), 2)
        cv2.putText(frame, f"GESTURE: {g_name_str}", (w - 230, g_banner_y + 18), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 2)
        cv2.putText(frame, f"Score:{g_score_str}  Held:{g_held_str}", (w - 230, g_banner_y + 36), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (200, 255, 200), 1)

    # 7. Guided Calibration Overlay (if active)
    if calib_mgr.step != CalibrationStep.IDLE and calib_mgr.step != CalibrationStep.COMPLETE:
        calib_banner_y = 70
        step_str = calib_mgr.step.value.upper()
        cv2.rectangle(frame, (15, calib_banner_y), (350, calib_banner_y + 50), (40, 20, 0), -1)
        cv2.rectangle(frame, (15, calib_banner_y), (350, calib_banner_y + 50), (255, 165, 0), 2)
        cv2.putText(frame, f"CALIBRATION: {step_str}", (25, calib_banner_y + 22), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 2)
        cv2.putText(frame, "[s] Skip  [r] Retry  [c] Restart", (25, calib_banner_y + 42), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (200, 200, 200), 1)

    # 8. Bottom Helper Footer
    cv2.putText(frame, "[c] Calibrate  [s] Skip  [r] Retry  [q] Quit", (w // 2 - 130, h - 15), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (130, 130, 130), 1)

    return frame


def main() -> None:
    args = parse_args()
    print("=" * 60)
    print("  FLUX / NeuroCursor - Vision Subsystem Debug Visualizer")
    print("=" * 60)
    print("  Controls:")
    print("    'c' - Start guided calibration sequence")
    print("    's' - Skip active calibration step (uses safe defaults)")
    print("    'r' - Retry active calibration step")
    print("    'q' / ESC - Quit")
    print("=" * 60)

    # Initialize components
    camera = CameraManager(camera_index=args.camera, width=args.width, height=args.height)
    if not args.mock:
        if not camera.open():
            print(f"[WARN] Camera index {args.camera} unavailable. Falling back to --mock mode.")
            args.mock = True

    mock_gen = MockFrameGenerator() if args.mock else None
    extractor = FaceMeshExtractor()
    calib_mgr = CalibrationManager(profile_path=args.profile)
    tracker = PointerTracker(profile=calib_mgr.profile)
    detector = GestureDetector(profile=calib_mgr.profile)

    window_name = "FLUX / NeuroCursor - Vision Debug HUD"
    cv2.namedWindow(window_name, cv2.WINDOW_AUTOSIZE)

    try:
        while True:
            t_now = time.time()

            if args.mock:
                # Synthetic test frame
                frame = np.full((args.height, args.width, 3), 100, dtype=np.uint8)
                capture_ms = 3.5
                fps = 30.0
                face_res = extractor.process_frame(None)  # Simulates clean null or test
            else:
                success, frame, capture_ms, meta = camera.read_frame()
                if not success or frame is None:
                    time.sleep(0.01)
                    continue
                fps = camera.current_fps
                face_res = extractor.process_frame(frame)

            # Draw landmark dots
            if face_res and face_res.detected:
                extractor.draw_debug_landmarks(frame, face_res)

            # Update calibration if active
            if calib_mgr.step != CalibrationStep.IDLE and calib_mgr.step != CalibrationStep.COMPLETE:
                calib_mgr.add_frame(face_res)
                if calib_mgr.profile.is_calibrated:
                    tracker.set_profile(calib_mgr.profile)
                    detector.set_profile(calib_mgr.profile)

            # Update tracking & gestures
            track_res = tracker.update(face_res, timestamp=t_now)
            gest_res = detector.update(face_res, timestamp=t_now)

            # Render complete HUD
            hud_frame = render_hud(
                frame=frame,
                face_res=face_res,
                track_res=track_res,
                gest_res=gest_res,
                calib_mgr=calib_mgr,
                fps=fps,
                capture_ms=capture_ms,
            )

            cv2.imshow(window_name, hud_frame)

            key = cv2.waitKey(1) & 0xFF
            if key == ord("q") or key == 27:  # 'q' or ESC
                break
            elif key == ord("c"):
                print("[HUD] Starting neutral calibration...")
                calib_mgr.start_neutral(duration_sec=2.0)
            elif key == ord("s"):
                msg = calib_mgr.skip_step()
                print(f"[HUD] {msg}")
            elif key == ord("r"):
                msg = calib_mgr.retry_step()
                print(f"[HUD] {msg}")

    finally:
        camera.release()
        extractor.close()
        cv2.destroyAllWindows()
        print("[HUD] Visualizer closed cleanly.")


if __name__ == "__main__":
    main()
