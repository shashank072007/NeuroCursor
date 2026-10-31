# GSD Project State: FLUX / NeuroCursor (Vision Subsystem)

## Current Status
- **Milestone:** v1.0 Complete (100% of Phases Delivered and Verified)
- **Completed Phases:** 4 / 4
- **Active Phase:** None (All Phases Complete)
- **Last Summary:** `.planning/phases/04-threaded-producer-debug-visualizer-qa-handoff/04-SUMMARY.md`

## Completed Deliverables
- `vision/camera.py`: Robust camera capture, capture_ms measurement, sliding-window FPS, lighting monitoring.
- `vision/landmarks.py`: MediaPipe FaceLandmarker, quality metric, 52 blendshapes, null-out contract.
- `vision/calibration.py`: Guided neutral & range calibration, skip/retry safeguards, `calibration.json` persistence.
- `vision/tracking.py`: Normalized `nx, ny ∈ [0, 1]` with One Euro Filter smoothing, separate raw `raw_dx, raw_dy` ability signals.
- `vision/gestures.py`: Debounced expressions strictly matching the 6-value enum, bilateral blink suppression, continuous `held_ms` tracking.
- `vision/producer.py`: Threaded non-blocking producer with drop-oldest bounded queue.
- `main_debug.py`: Interactive OpenCV HUD with live landmarks, cursor reticle, FPS, quality bar, and gesture feedback.
- `simulator.py`: Chaos test harness for Shashank (jitter, range loss, occlusion testing).
- `mock_frames.json`: 10-frame realistic handoff sample unblocking Samrudh and Sampada.
- `docs/VISION.md`: Complete team handoff specification & DoD compliance matrix.
- `tests/`: 23 automated unit tests passing at 100%.

## Definition of Done Verification
- Target $\ge 25$ FPS on demo hardware; report actual FPS: ✅ Verified
- `nx, ny` numeric and clamped $[0, 1]$ when valid; `null` when face lost: ✅ Verified
- `raw_dx, raw_dy` unsmoothed in face-width units: ✅ Verified
- Strict gesture enum; vision never maps to clicks: ✅ Verified
- Emit once per hold with stable `held_ms` progression: ✅ Verified
- Queue producer never blocks camera loop (drop-oldest queue): ✅ Verified
