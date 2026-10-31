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
      │  Native Windows OS Clicks   │ │  • Real-time HUD & Dwell Ring│
      │  & Coordinated Movement     │ │  • Voice-Interactive Engine │
      └─────────────────────────────┘ │  • In-Browser MediaPipe Fallback│
                                      └─────────────────────────────┘
```

---

## 2. Directory Structure

- **`frontend/`**: The web application suite. High-contrast glassmorphic UI, voice command engine ("Hey Cursor"), in-browser MediaPipe FaceMesh fallback, and live SSE telemetry receiver.
- **`backend/`**: Central controller and Flask REST/SSE server. Hosts `bus.py`, `processor.py`, `intent_guard.py`, `effort.py`, `adapt.py`, `channels.py`, `os_control.py`, and `safety.py`.
- **`vision/`**: Vision subsystem modules. Standard RGB camera acquisition (`camera.py`), landmark extraction (`landmarks.py`), pointer tracking (`tracking.py`), facial expression debounce (`gestures.py`), calibration manager (`calibration.py`), and threaded producer (`producer.py`).
- **`models/`**: MediaPipe model asset (`face_landmarker.task`).
- **`tests/`**: Unified test suite containing 48 unit, contract, and integration tests across all subsystems.
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
python main.py --open-browser
```
Or simply:
```bash
python run.py
```
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

#### Option D: Standalone Frontend
You can also run the frontend independently using any static web server:
```bash
cd frontend
python -m http.server 5173
```

---

## 4. Key Controls & Hotkeys

| Key / Action | Subsystem | Behavior |
|---|---|---|
| **F9** | Backend Safety | Toggle **Pause / Resume** (pointer tracks, clicks disabled) |
| **F10** | Backend Safety | Toggle **Lock / Unlock** (cursor and clicks disabled) |
| **Smile** | Vision / Guard | Left Click / Primary Option Selection (debounced 550ms) |
| **Mouth Open** | Vision / Guard | Context Action / Right Click Trigger |
| **Eyebrows Raise**| Vision / Frontend | Hands-free cursor pause / resume toggle |
| **Dwell Hover** | Frontend Engine | Anchor-based 38px radius hands-free click with radial progress ring |
| **"Hey Cursor"** | Frontend Voice | Activates voice-directed smooth navigation |
| **"Click [Option]"**| Frontend Voice | Directly targets and activates interactive UI controls |
| **Flip / Mirror** | Frontend Vision | Quick toggle between standard (non-inverted) & mirrored webcam feed |
| **OS Mouse Toggle** | Frontend / API | Switches OS native cursor control via `/resume` and `/pause` |

---

## 5. Fine-Tuned Ergonomics & Speech-to-Text Optimizations

1. **Non-Inverted Webcam Feed & Quick Toggles:**
   - Laptop webcam video feeds render in their natural, un-inverted orientation by default.
   - Quick one-click "Flip / Mirror" and "Invert V" toggles are available directly in the Live Camera HUD and Personalisation settings, persisting preferences to `localStorage`.
   - The landmark mesh overlay dynamically matches CSS transforms for 1:1 face alignment.

2. **Precision Navigation & Anchor-Based Dwell Click:**
   - **Asymmetric Gain:** 1.35x vertical scaling compensates for human pitch range vs yaw neck rotation, making top and bottom screen targets effortless to reach.
   - **Fixation Deadzone (0.0035):** Prevents micro-tremors from disturbing button targeting.
   - **Velocity-Adaptive Smoothing:** Automatically provides high responsiveness during sweeping motions and steady low-jitter stability during fixation.
   - **Anchor Dwell Engine:** Progresses within a 38px anchor circle, eliminating drift-resets.
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
