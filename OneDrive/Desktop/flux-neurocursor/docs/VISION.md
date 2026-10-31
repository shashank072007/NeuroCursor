# FLUX / NeuroCursor — Vision Subsystem Specification & Team Handoff

**Shared Team Contract v1**  
**Author:** Vision Pipeline Team  
**Deliverables Scope:** `vision/camera.py`, `vision/landmarks.py`, `vision/calibration.py`, `vision/tracking.py`, `vision/gestures.py`, `vision/producer.py`, `main_debug.py`, `simulator.py`, `mock_frames.json`.

---

## 1. System Overview & Architecture

The **Vision Subsystem** provides hands-free cursor control and physical expression detection for assistive navigation. It operates at $\ge 25\text{ FPS}$ (30 FPS target), acquiring standard RGB camera frames, detecting 478 3D facial landmarks via MediaPipe Tasks, computing One Euro Filtered normalized coordinates and raw scale-invariant ability signals, debouncing physical expressions, and publishing frame events to a non-blocking queue.

```
 Webcam Capture (CameraManager)
         │
         ▼
 Landmark & Quality Inference (FaceMeshExtractor)
         │
         ├───► [Quality < 0.45 or Lost] ──► Strict Null-Out (coordinates = None)
         │
         ▼ [Quality >= 0.45]
 Coordinate Mapping & Filtering (PointerTracker)
         ├───► Smoothed (nx, ny) ∈ [0, 1] ────────► Virtual Cursor
         └───► Unsmoothed (raw_dx, raw_dy) ───────► Effort Proxy (Jitter / Range Loss)
         │
 Debounced Gesture Engine (GestureDetector)
         ├───► Bilateral Blink Suppression ───────► Natural Blinks -> "none"
         └───► Debounce & Continuous hold_ms ─────► {mouth_open, brow_raise, smile, wink_l/r}
         │
         ▼
 Threaded Producer & Queue (FrameProducer)
         ├───► Bounded Drop-Oldest Queue (Maxsize 10)
         └───► Samrudh (Backend Consumer) & Sampada (Frontend UI)
```

---

## 2. Landmark Indices & Geometry Choices

MediaPipe FaceLandmarker provides 478 normalized 3D landmarks $(x, y, z)$. We anchor tracking and expressions to the following specific anatomical landmarks:

| Landmark Region | MediaPipe Indices | Purpose |
|---|---|---|
| **Nose Tip** | `1` | Primary tracking center for head position. |
| **Forehead & Chin** | `10` (Forehead), `152` (Chin) | Vertical face height and pitch sanity check. |
| **Face Left & Right** | `234` (Left), `454` (Right) | Horizontal face width (`width_norm`), scale-invariance reference. |
| **Left Eye** | `33` (Outer), `133` (Inner), `159` (Top), `145` (Bottom), `468` (Iris) | Eye Aspect Ratio (EAR), blink detection, roll tilt angle. |
| **Right Eye** | `362` (Inner), `263` (Outer), `386` (Top), `374` (Bottom), `473` (Iris) | Eye Aspect Ratio (EAR), blink detection, roll tilt angle. |
| **Mouth Corners** | `61` (Left Corner), `291` (Right Corner) | Mouth width expansion for `smile`. |
| **Lips (Inner)** | `13` (Upper Inner), `14` (Lower Inner) | Inner mouth gap for `mouth_open`. |
| **Eyebrows** | Left: `70, 63, 105, 66, 107` \| Right: `300, 293, 334, 296, 336` | Vertical elevation above eyes for `brow_raise`. |

---

## 3. Mathematical Formulas

### A. Face Quality Metric (`face.quality ∈ [0.0, 1.0]`)
Face quality gates whether coordinates and expressions may be trusted:
$$\text{Quality} = S_{\text{size}} \times \left(0.60 \cdot S_{\text{pose}} + 0.40 \cdot S_{\text{boundary}}\right)$$

1. **Size Gating ($S_{\text{size}}$):**
   * Optimal normalized face width $w_{\text{norm}} \approx 0.35$.
   * $S_{\text{size}} = 0$ if $w_{\text{norm}} < 0.10$ or $w_{\text{norm}} > 0.85$.
   * Multiplicative gating ensures that a face too far away or filling the entire lens cannot pass quality checks even if upright.
2. **Pose Sanity ($S_{\text{pose}}$):**
   * Computes roll tilt angle $\theta = |\arctan2(\Delta y_{\text{eyes}}, \Delta x_{\text{eyes}})|$. Penalizes tilts exceeding $25^\circ$.
   * Pitch sanity: Chin must lie below forehead ($\text{chin}_y > \text{forehead}_y$).
3. **Boundary Containment ($S_{\text{boundary}}$):**
   * Verifies that anchor points lie within $[0.02, 0.98]$ of viewport bounds.
* **Strict Null-Out Threshold:** If $\text{Quality} < 0.45$, `detected = False` and coordinates are cleared to `None`.

### B. Normalized Coordinates & Scale-Invariant Raw Offsets
* **Raw Displacement in Face-Width Units (Unsmoothed):**
  $$\text{raw\_dx} = \frac{x_{\text{center}} - x_{\text{neutral}}}{w_{\text{ref}}}, \quad \text{raw\_dy} = \frac{y_{\text{center}} - y_{\text{neutral}}}{w_{\text{ref}}}$$
  *Scale-invariant:* If the user leans closer or farther, raw motion remains measured in units of their own face width.
* **Cursor Normalization (`nx, ny ∈ [0, 1]`):**
  $$nx = 0.50 + 0.50 \cdot \left(\frac{\text{raw\_dx}}{\text{range\_right}}\right) \quad (\text{if raw\_dx} \ge 0)$$
  Clamped strictly to $[0.0, 1.0]$.
* **One Euro Filter Smoothing:**
  Adaptive low-pass cutoff frequency:
  $$f_c = f_{c,\min} + \beta |\dot{x}| \quad (\text{default: } f_{c,\min} = 1.2\text{ Hz}, \beta = 0.02)$$
  Completely eliminates hand/head tremor at rest while introducing zero phase lag during intentional fast sweeps.

### C. Bilateral Blink Suppression
To prevent natural, involuntary blinks from triggering false winks:
$$\text{IsBlink} = \left(\text{blink}_L > 0.40 \land \text{blink}_R > 0.40 \land |\text{blink}_L - \text{blink}_R| < 0.28\right)$$
If $\text{IsBlink} = \text{True}$, `wink_left` and `wink_right` are forced to $0.0$, emitting `name = "none"`.
Winks require deliberate asymmetric closure ($\text{blink}_{\text{active}} > 0.50 \land \text{blink}_{\text{opposite}} < 0.35$).

---

## 4. Calibration Instructions

Calibration takes $\approx 10$ seconds and persists to `calibration.json`:
1. **Resting Pose:** User sits comfortably and looks straight ahead for 1.5s. Stores $(x_{\text{neutral}}, y_{\text{neutral}})$, reference face width $w_{\text{ref}}$, and baseline expression ratios.
2. **Comfortable Range:** Prompts the user to gently tilt Left, Right, Up, and Down. Estimates usable reach using the 90th percentile peak excursion.
3. **Safety Controls:**
   * Pressing `'s'` skips the active direction and applies safe conservative defaults ($0.25$ horizontal, $0.20$ vertical).
   * Pressing `'r'` retries the direction without restarting the entire calibration.
   * Users are **never** forced into uncomfortable or extreme movements.

---

## 5. Teammate Handoff Protocols

### To Samrudh (Backend Consumer)
* **Frame Producer API:**
  ```python
  from vision.producer import FrameProducer

  with FrameProducer(camera_index=0, queue_size=10) as producer:
      for event in producer.get_events(timeout=0.1):
          # event matches standardized JSON contract
          if event["detected"]:
              handle_cursor(event["pointer"]["nx"], event["pointer"]["ny"])
              handle_effort(event["raw_motion"]["raw_dx"], event["raw_motion"]["raw_dy"])
              handle_gesture(event["gesture"]["name"], event["gesture"]["held_ms"])
  ```
* **Frame Frequency:** 30 Hz nominal ($\ge 25\text{ FPS}$ target).
* **Queue Name & Strategy:** Bounded thread-safe queue (`producer.frame_queue`, default size 10). Employs a **drop-oldest** policy—if the backend consumer lags, the oldest frame is discarded so your processing always aligns with real-time state without blocking the camera loop.
* **Shutdown Behavior:** Call `producer.stop()` or exit context manager. It signals a `threading.Event`, joins the daemon thread, releases `cv2.VideoCapture`, and destroys the MediaPipe landmarker.
* **10-Frame Sample:** Available at [`mock_frames.json`](file:///c:/Users/rites/Downloads/symposium_final/flux-neurocursor/mock_frames.json). Notice Frame 9 demonstrates the strict null-out behavior (`detected: false`, coordinates `null`).

### To Sampada (Frontend UI)
* **Sample Frame for Mock Data:**
  ```json
  {
    "frame_index": 7,
    "timestamp": 1730370000.200,
    "detected": true,
    "face": { "quality": 0.88, "width_norm": 0.35 },
    "pointer": { "nx": 0.728, "ny": 0.342 },
    "raw_motion": { "raw_dx": 0.282, "raw_dy": -0.192 },
    "gesture": { "name": "mouth_open", "score": 0.89, "held_ms": 250 },
    "timing": { "capture_ms": 3.9, "process_ms": 11.9, "fps": 28.9 }
  }
  ```
* **Streaming Mock Frames:**
  You can stream continuous mock frames at 30 FPS without opening a camera:
  ```python
  from vision.mock import MockFrameGenerator
  generator = MockFrameGenerator()
  for frame in generator.stream_frames(realtime=True):
      update_cursor_ui(frame["pointer"]["nx"], frame["pointer"]["ny"])
  ```

### To Shashank (QA & Simulation)
Run `simulator.py` to test backend robustness without needing a live webcam:
* **Test Tremor / Effort Proxy:**
  ```bash
  python simulator.py --mode jitter --duration 5 --output jitter_test.json
  ```
* **Test Motor Range Loss:**
  ```bash
  python simulator.py --mode low_range --duration 5
  ```
* **Test Occlusion / Face Recovery:**
  ```bash
  python simulator.py --mode occlusion --duration 5
  ```
* **Test 1-Frame Expression Spikes:**
  ```bash
  python simulator.py --mode spikes --duration 5
  ```

---

## 6. Known Hardware Limitations & Safeguards

1. **Poor Ambient Lighting:** If mean grayscale brightness drops below 40.0, `metadata["low_light"]` flags `True` on the camera stream to alert the user before tracking degrades.
2. **Extreme Backlighting:** Windows or bright lights directly behind the user will darken facial landmarks. The quality metric will automatically decrease below 0.45 and trigger fail-safe coordinate nulling.
3. **Thick Eyewear:** Glare on prescription glasses can occasionally occlude eye landmarks; MediaPipe Tasks blendshapes with iris refinement minimize iris drift.
4. **Camera Indices:** Windows DirectShow (`cv2.CAP_DSHOW`) is used first to minimize camera startup lag; falls back to `cv2.CAP_ANY` if unindexable.

---

## 7. Definition of Done Compliance Matrix

| DoD Requirement | Implementation Evidence | Status |
|---|---|---|
| Target $\ge 25\text{ FPS}$ on laptop; report actual FPS | Rolling 30-frame window in `CameraManager._update_fps()`, reported live in every frame event and debug HUD. | ✅ Met |
| `nx, ny` numeric and clamped $[0, 1]$ when valid; `null` when face lost | Enforced in `PointerTracker.update()` via `np.clip()`; returns `create_null()` on loss. | ✅ Met |
| `raw_dx, raw_dy` unsmoothed in face-width units | Computed as $(x - x_{\text{neutral}}) / w_{\text{ref}}$ without filtering in `PointerTracker`. | ✅ Met |
| Strict gesture enum; vision never maps to clicks | Strictly `GestureEnum` (`none`, `mouth_open`, `brow_raise`, `smile`, `wink_left`, `wink_right`). No OS mouse calls in vision. | ✅ Met |
| Emit once per hold with stable `held_ms` progression | Debounce state machine in `GestureDetector` requires 2 activation frames and tracks continuous `(t - t_{\text{start}}) \times 1000`. | ✅ Met |
| Queue producer never blocks camera loop | Bounded `queue.Queue(maxsize=10)` with drop-oldest `get_nowait()` pattern in `FrameProducer._enqueue_drop_oldest()`. | ✅ Met |
