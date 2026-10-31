# Project Charter: FLUX / NeuroCursor (Vision Subsystem)

## Executive Summary
FLUX / NeuroCursor is an assistive, hands-free pointer control system designed for users with limited motor function. The **Vision Subsystem** captures user head position and facial expressions using standard laptop webcams via OpenCV and MediaPipe Face Mesh, translating physical movements into stable normalized coordinates, raw ability signals, and debounced physical gestures.

## Team Contract & Interfaces
- **Our Subsystem (Vision):** Captures webcam, extracts Face Mesh landmarks, executes calibration, computes normalized coordinates `(nx, ny)` and raw displacement `(raw_dx, raw_dy)`, detects physical expressions, and pushes frames to a bounded, non-blocking queue.
- **Samrudh (Backend):** Consumes frame events from the queue, calculates jitter/range-loss as an interaction-effort proxy, executes guard rejection, and maps expressions to user clicks/actions.
- **Sampada (Frontend):** Consumes pointer events and UI states to render the assistive cursor and user interface. Requires mock frame JSON.
- **Shashank (QA & Simulation):** Tests pipeline stability, edge-case recovery, and simulates low range, jitter, and tracking loss.

## Core Responsibilities (Part 1)
1. **Webcam & Landmark Pipeline:** Robust webcam reader with OpenCV, MediaPipe 468+ landmark tracking, debug visualization (landmarks, FPS, quality), and graceful recovery from lighting drops or camera disconnection.
2. **Neutral Calibration & Movement Range:** Guided resting-pose calibration (neutral x/y, face width) followed by comfortable range estimation (left/right/up/down) with skip/retry without forcing user motion.
3. **Stable Normalized Pointer Coordinates:** Maps movement to normalized `nx, ny ∈ [0, 1]` with smoothing and clamping. Keeps `raw_dx, raw_dy` separate in face-width units. Never converts to screen pixels.
4. **Physical Expression Detection:** Emits strictly `none`, `mouth_open`, `brow_raise`, `smile`, `wink_left`, `wink_right`. Never emits ordinary blinks or maps expressions to clicks. Emits once per hold with continuous `held_ms`.
5. **Face Quality & Timing:** Calculates `face.quality ∈ [0, 1]`, measures `capture_ms` and `process_ms`. If face is lost or quality is bad, emits `detected=false` and nulls all coordinate/gesture fields (never repeats stale frames).
6. **Live Ability Signal Support:** Emits raw displacement so the backend can estimate range loss and jitter (effort proxy) without medically labeling the user.

## Deliverables & Handoff (Part 2)
- `vision/camera.py`: Camera capture, verification, and error recovery.
- `vision/landmarks.py`: Landmark extraction and face quality metrics.
- `vision/calibration.py`: Neutral and comfortable range calibration.
- `vision/tracking.py`: Smoothing, normalized mapping `(nx, ny)`, and raw offsets `(raw_dx, raw_dy)`.
- `vision/gestures.py`: Expression detection, scoring, and held duration.
- `vision/producer.py`: Threaded non-blocking producer with drop-oldest bounded queue.
- `docs/VISION.md`: Architecture, landmark IDs, mathematical formulas, calibration instructions, and limits.
- `mock_frames.json`: 10-frame synthetic test frames for backend and frontend.
- `simulator.py`: Test harness for Shashank to simulate tracking loss, jitter, and low range.

## Definition of Done
- Target $\ge 25$ FPS on demo hardware; report actual FPS.
- `nx, ny` strictly numeric and clamped when valid; `null` when face lost.
- `raw_dx, raw_dy` unsmoothed in face-width units.
- Strict enum adherence for expressions; no click mappings in vision.
- Stable debounced `held_ms` progression.
- Non-blocking camera loop via drop-oldest queue.
