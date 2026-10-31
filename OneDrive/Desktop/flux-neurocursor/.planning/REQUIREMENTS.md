# Requirements Matrix: FLUX / NeuroCursor (Vision Subsystem)

## Functional Requirements

### Camera & Capture
- **`REQ-CAM-01`**: Verify laptop camera index and open video stream at $\ge 25$ FPS target via OpenCV.
- **`REQ-CAM-02`**: Gracefully handle camera disconnection, busy device, and failure to read frames without unhandled exceptions.
- **`REQ-CAM-03`**: Measure `capture_ms` for every acquired frame.

### Landmarks & Quality Assessment
- **`REQ-LAND-01`**: Run MediaPipe Face Mesh to extract 468+ 3D face landmarks per frame.
- **`REQ-LAND-02`**: Provide an OpenCV debug overlay displaying face contour, key anchor landmarks (nose tip, eyes, mouth, chin), live FPS, tracking quality score, and active gesture.
- **`REQ-QUAL-01`**: Compute `face.quality ∈ [0.0, 1.0]` factoring landmark visibility, normalized face size against viewport, and pose sanity (yaw/pitch/roll boundaries).
- **`REQ-TIM-01`**: Measure `process_ms` per frame. When face is lost or quality falls below threshold, emit `detected: false` and set `nx, ny, raw_dx, raw_dy` to `null` and `gesture.name` to `"none"`. Stale coordinates must NEVER be repeated.

### Calibration
- **`REQ-CAL-01`**: Guided neutral calibration capturing resting head center `(neutral_x, neutral_y)` and reference face width in normalized units over a short sample window.
- **`REQ-CAL-02`**: Interactive range calibration prompting comfortable left, right, up, down head excursions with skip/retry options. Never force uncomfortable user motion.
- **`REQ-CAL-03`**: Persist and reload calibration profile to disk (`calibration.json`) to allow instant restart.

### Coordinate Mapping & Ability Signals
- **`REQ-TRACK-01`**: Map head displacement from neutral to normalized pointer coordinates `nx, ny ∈ [0.0, 1.0]`, applying configurable smoothing (Exponential Moving Average / One Euro Filter) and boundary clamping.
- **`REQ-TRACK-02`**: Calculate unsmoothed displacement `raw_dx, raw_dy` expressed in face-width units and preserve raw samples for backend jitter and range loss computation.
- **`REQ-TRACK-03`**: Never convert normalized coordinates to screen pixel dimensions.

### Physical Expression Detection
- **`REQ-EXP-01`**: Detect and emit physical expressions strictly from the enum: `["none", "mouth_open", "brow_raise", "smile", "wink_left", "wink_right"]`.
- **`REQ-EXP-02`**: Explicitly filter out ordinary involuntary blinks so they are never emitted as winks.
- **`REQ-EXP-03`**: Compute expression score relative to user's neutral calibration baseline.
- **`REQ-EXP-04`**: Provide debounce logic and continuous `held_ms` progression; emit once per hold and prevent 1-frame spikes from becoming sustained gestures.
- **`REQ-EXP-05`**: Never map expressions to clicks or OS events inside the vision subsystem.

### Producer, Concurrency & Handoff
- **`REQ-PROD-01`**: Implement threaded producer putting structured frame events onto a thread-safe bounded queue with a drop-oldest policy so the camera loop is never blocked.
- **`REQ-PROD-02`**: Implement graceful shutdown signalling and resource cleanup (camera release, thread join).
- **`REQ-MOCK-01`**: Provide a mock frame generator and export a verified 10-frame JSON sample file unblocking Samrudh (backend) and Sampada (frontend).
- **`REQ-TEST-01`**: Provide a simulation script for Shashank allowing synthetic injection of low range, jitter, and intermittent tracking loss.
- **`REQ-DOC-01`**: Create comprehensive `docs/VISION.md` detailing setup, landmark choices, mathematical formulas, calibration instructions, and known limitations.
