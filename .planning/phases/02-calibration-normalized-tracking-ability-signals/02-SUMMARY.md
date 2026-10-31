---
phase: 02-calibration-normalized-tracking-ability-signals
status: complete
date: 2026-10-31
requirements_satisfied:
  - REQ-CAL-01
  - REQ-CAL-02
  - REQ-CAL-03
  - REQ-TRACK-01
  - REQ-TRACK-02
  - REQ-TRACK-03
---

# Phase 2 Summary: Calibration, Normalized Tracking & Ability Signals

## Accomplishments
1. **Calibration Engine (`vision/calibration.py`)**:
   - Implemented `CalibrationProfile` storing resting pose `(neutral_x, neutral_y)`, reference face width (`face_width_ref`), and comfortable excursion bounds in face-width units.
   - Built guided `CalibrationManager` with step progression: `neutral` -> `left` -> `right` -> `up` -> `down`.
   - Built safety controls: `skip_step()` safely defaults the range without forcing discomfort; `retry_step()` restarts the window cleanly.
   - Profile persistence to `calibration.json` with `save()` and `load()`.
   - Sampled baseline resting expression ratios (`mouth_ratio`, `brow_ratio`, `left_ear`, `right_ear`) for downstream Phase 3 gesture detection.

2. **Pointer Tracking & Ability Signals (`vision/tracking.py`)**:
   - Implemented `PointerTracker` converting displacement to scale-invariant face-width units: `raw_dx = dx / face_width_ref`, `raw_dy = dy / face_width_ref`.
   - Kept `raw_dx, raw_dy` **unsmoothed and separated** to serve as the backend's interaction-effort proxy (detecting user jitter and range loss).
   - Normalized pointer mapping to `nx, ny ∈ [0.0, 1.0]` with strict boundary clamping.
   - Implemented adaptive `OneEuroFilter1D` eliminating static resting jitter while maintaining instantaneous response during deliberate movement.
   - Strictly enforced null-out contract: when face tracking drops, emits `None` for coordinates and resets filter states. Never converts to screen pixels.

3. **MediaPipe Tasks Architecture Upgrade**:
   - Upgraded `vision/landmarks.py` to MediaPipe Tasks `FaceLandmarker` with local asset `models/face_landmarker.task`.
   - Enabled `output_face_blendshapes=True` unlocking 52 high-precision facial blendshapes.

4. **Automated Verification**:
   - Added `tests/test_phase2.py` with 7 automated tests.
   - Total test suite now stands at 13 unit tests across both phases: 100% passing in 0.12s.
