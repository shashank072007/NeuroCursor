# Project Roadmap: FLUX / NeuroCursor (Vision Subsystem)

## Phase 1: Camera, Landmarks & Teammate Handoff Mock
**Status:** Complete
**Goal:** Build rock-solid webcam ingestion, landmark tracking, quality scoring, and immediately generate synthetic JSON frames to unblock Samrudh and Sampada.
- [x] `01-01`: Build `vision/camera.py` (webcam open, capture_ms measurement, auto-reconnect, FPS calculation).
- [x] `01-02`: Build `vision/landmarks.py` (MediaPipe Face Mesh integration, landmark indexing, `face.quality` formula, latency metrics, null-out protocol).
- [x] `01-03`: Build `mock_frames.json` (10-frame realistic sample) and mock-frame mode unblocking backend and frontend.

## Phase 2: Calibration, Normalized Tracking & Ability Signals
**Status:** Complete
**Goal:** Implement guided calibration and coordinate translation separating smoothed normalized cursor coordinates from unsmoothed raw offsets.
- [x] `02-01`: Build `vision/calibration.py` (neutral resting pose, comfortable range estimation with skip/retry, persistence to JSON).
- [x] `02-02`: Build `vision/tracking.py` (One-Euro filter for `nx, ny ∈ [0, 1]`, separate unsmoothed `raw_dx, raw_dy` in face-width units).

## Phase 3: Debounced Physical Expressions & Gesture Engine
**Status:** Complete
**Goal:** Detect expressions strictly matching the shared enum, filtering out ordinary blinks and tracking continuous hold time.
- [x] `03-01`: Build `vision/gestures.py` (facial ratio calculations, bilateral blink suppression, debounce state machine, and continuous `held_ms` progression).

## Phase 4: Threaded Producer, Debug Visualizer & QA Handoff
**Status:** Complete
**Goal:** Deliver non-blocking queue producer, interactive OpenCV debug HUD, test simulator for Shashank, and documentation.
- [x] `04-01`: Build `vision/producer.py` (bounded queue with drop-oldest policy, frame packaging, clean shutdown).
- [x] `04-02`: Build interactive debug visualizer (`main_debug.py`) displaying FPS, landmarks, face quality, active gestures, and tracking box.
- [x] `04-03`: Build `simulator.py` for Shashank to test jitter, low range, and occlusion recovery.
- [x] `04-04`: Write `docs/VISION.md` detailing architecture, landmark IDs, mathematical formulas, calibration instructions, and known limitations.
