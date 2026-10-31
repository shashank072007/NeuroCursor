# NeuroCursor (FLUX) — Assistive Hands-Free Interface & OS Controller

> **Unified Integration Branch (`integration`)**  
> An adaptive, accessible hands-free platform that bridges **computer vision head tracking**, an **intelligent intent & fatigue adaptation backend**, and a modern **interactive web UI suite**.

---

## 1. System Architecture

```
                  ┌──────────────────────────────────────────────┐
                  │                 USER WEBCAM                  │
                  └──────────────────────┬───────────────────────┘
                                         │
                                         ▼
                  ┌──────────────────────────────────────────────┐
                  │          VISION SUBSYSTEM (`vision/`)        │
                  │  • MediaPipe Tasks (478 3D Landmarks)        │
                  │  • One Euro Filter Smoothing (nx, ny)        │
                  │  • Debounced Expression Engine               │
                  │  • Drop-Oldest Threaded FrameProducer        │
                  └──────────────────────┬───────────────────────┘
                                         │
                                         ▼ ~30 Hz Normalized Frames
                  ┌──────────────────────────────────────────────┐
                  │          BACKEND PIPELINE (`backend/`)       │
                  │  • IntentGuard 8-Stage State Machine         │
                  │  • Effort Meter & Fatigue Detection          │
                  │  • Adaptive Sensitivity & Dwell Engine       │
                  │  • Safety Gate & Hotkeys (F9/F10)            │
                  │  • OS Mouse Controller (pynput / pywin32)    │
                  └──────────────┬───────────────────────────────┘
                                 │
                     ┌───────────┴───────────┐
                     │ SSE Stream / REST API │ (Port 5000)
                     ▼                       ▼
      ┌─────────────────────────────┐ ┌─────────────────────────────┐
                     │     DESKTOP OS CURSOR       │ │    FRONTEND UI (`frontend/`)│
      │  Native Windows OS Clicks   │ │  • Real-time HUD & Cursor    │
      │  & Coordinated Movement     │ │  • Voice-Interactive Engine │
      └─────────────────────────────┘ │  • Python SSE / MJPEG Client  │
                                      └─────────────────────────────┘
```

---

## 2. Directory Structure

- **`frontend/`**: The web application suite. High-contrast UI, voice command engine ("Hey Cursor"), Flask SSE telemetry client, and Python-served MJPEG preview. It does not open the webcam or run a landmark model.
- **`backend/`**: Central controller and Flask REST/SSE server. Hosts `bus.py`, `processor.py`, `intent_guard.py`, `effort.py`, `adapt.py`, `channels.py`, `os_control.py`, and `safety.py`.
- **`vision/`**: Vision subsystem modules. Standard RGB camera acquisition (`camera.py`), landmark extraction (`landmarks.py`), pointer tracking (`tracking.py`), facial expression debounce (`gestures.py`), calibration manager (`calibration.py`), and threaded producer (`producer.py`).
- **`models/`**: MediaPipe model asset (`face_landmarker.task`).
- **`tests/`**: Unit, contract, and integration tests across all subsystems.
- **`main.py` / `run.py`**: Unified multi-mode application launcher.
- **`simulator.py`**: QA chaos injection simulator for jitter, range loss, occlusion, and expression spikes.
- **`main_debug.py`**: OpenCV live HUD visualizer for tuning and debugging landmarks.

---

## 3. Quickstart

### Prerequisites
- Python 3.10+
- Webcam (for live tracking mode)

```bash
pip install -r requirements.txt
```

### Running the Application

#### Option A: Unified Live Mode (Recommended)
Launches the Flask backend, captures webcam frames with OpenCV + MediaPipe Tasks, activates IntentGuard OS mouse control, and serves the frontend:
```bash
python main.py --source live --camera-index 0 --simulate --open-browser
```
The command above uses OS simulation for a safe first run. When tracking is calibrated and you want native OS mouse input, restart without `--simulate`.
* **Web UI:** Open `http://127.0.0.1:5000/` in Chrome, Edge, or Brave.
* **SSE Telemetry:** `http://127.0.0.1:5000/stream?token=dev-token`

#### Option B: Mock Simulation Mode (No Camera Required)
Runs synthetic ~30 Hz head trajectories and scripted gestures for testing without camera hardware:
```bash
python main.py --source mock --open-browser
```

#### Option C: Vision OpenCV Debug Visualizer
Launches the standalone OpenCV HUD displaying real-time landmarks, iris gaze, and expression debouncers:
```bash
python main.py --debug-vision
# or:
python main_debug.py
```

#### Option D: Frontend-only Preview
The static UI can be served independently for visual review, but head tracking, camera preview, calibration, and OS controls require the integrated Python app in Option A.

---

## 4. Key Controls & Hotkeys

| Key / Action | Subsystem | Behavior |
|---|---|---|
| **F9** | Backend Safety | Toggle **Pause / Resume** (pointer tracks, clicks disabled) |
| **F10** | Backend Safety | Toggle **Lock / Unlock** (cursor and clicks disabled) |
| **Smile** | Vision / Guard | Left Click after a sustained, still, confident gesture |
| **Dwell circle** | Frontend | A steady hover fills the green circle and performs one left click on completion; move away to rearm |
| **Mouth Open** | Vision / Guard | Right Click after a sustained, still, confident gesture |
| **Left Wink** | Vision / Guard | Left Click after a deliberate wink hold |
| **Right Wink** | Vision / Guard | Right Click after a deliberate wink hold |
| **Eyebrows Raise**| Vision / Frontend | Hands-free cursor pause / resume toggle |
| **Both Eyes Blink** | Vision | Suppressed as a natural blink; it does not click |
| **"Hey Cursor"** | Frontend Voice | Activates voice-directed smooth navigation |
| **"Click [Option]"**| Frontend Voice | Directly targets and activates interactive UI controls |
| **"Move cursor left/right/up/down"** | Frontend Voice | Moves the browser cursor in small steps; repeat or say “move cursor far left” for a larger step |
| **Control mode selector** | Frontend / Backend | Choose Head + gestures, Speech cursor, Physical mouse, or Head + speech |
| **Priority selector** | Frontend / Backend | In Hybrid mode, choose Head or Speech priority; speech priority temporarily suspends head actions while the voice cursor is awake |
| **Flip / Mirror** | Frontend Vision | Quick toggle between standard (non-inverted) & mirrored webcam feed |
| **OS Mouse Toggle** | Frontend / API | Switches OS native cursor control via `/resume` and `/pause` |

Gesture clicks require about 150-260ms of hold depending on the adaptive effort level, adequate face quality, a steady pointer, and a 600ms action cooldown. The wink mapping is asymmetric: left wink clicks left, right wink clicks right.

---

## 5. Fine-Tuned Ergonomics & Speech-to-Text Optimizations

1. **Non-Inverted Webcam Feed & Quick Toggles:**
   - Laptop webcam video feeds render in their natural, un-inverted orientation by default.
   - Quick one-click "Flip / Mirror" and "Invert V" toggles are available directly in the Live Camera HUD and Personalisation settings, persisting preferences to `localStorage`.
   - The landmark mesh overlay dynamically matches CSS transforms for 1:1 face alignment.

2. **Precision Navigation & Gesture Clicks:**
   - **Asymmetric Gain:** 1.35x vertical scaling compensates for human pitch range vs yaw neck rotation, making top and bottom screen targets effortless to reach.
   - **Fixation Deadzone (0.0035):** Prevents micro-tremors from disturbing button targeting.
   - **Velocity-Adaptive Smoothing:** Automatically provides high responsiveness during sweeping motions and steady low-jitter stability during fixation.
   - **Interactive Target Resolution:** Ensures clicking inner icons or text spans accurately triggers the parent button or card action.

3. **Optimized Speech-to-Text Conversion:**
   - **Live Interim Preview:** Real-time visual feedback renders interim spoken phrases in styled italic preview before committing finalized text.
   - **Spoken Punctuation Normalization:** Automatically converts verbalized punctuation ("question mark", "period", "comma", "exclamation point", "new line") to proper symbols and capitalizes sentence beginnings.
   - **Acoustic Noise Filtering:** Low-confidence background acoustic noise (< 0.40) is ignored to prevent hallucinated words.
   - **Continuous Reconnection:** Automatically resumes recognition across pauses without silent dropouts.
   - **Expanded Voice Intent Dictionary:** Direct "Click [target]" or "Select [option]" voice commands automatically glide the cursor and trigger selection.

---

## 6. Verification & Testing

Execute the complete end-to-end integration test suite:
```bash
python main.py --test
```
Or with unittest:
```bash
python -m unittest discover tests
```
All 48 tests validate:
1. REST endpoints, token auth, CORS headers, and frontend asset delivery.
2. Dual schema normalization bridging Vision (`pointer`, `raw_motion`, `detected`) and Backend (`head`, `face.detected`, `ts`).
3. Landmark quality gating and strict null-out fail-safes.
4. Bilateral blink suppression and debounced continuous gesture progression.
5. Effort meter EMA smoothing, warmup guards, and fatigue hysteresis.
