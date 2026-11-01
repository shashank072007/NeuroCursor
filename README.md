# NeuroCursor (FLUX) — Assistive Hands-Free Interface & OS Controller

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

### First-time setup on another laptop

The steps below use the GitHub `test1` branch, which contains the integrated Python camera pipeline and cursor controls. Each laptop needs its own camera calibration; the generated `calibration.json` is intentionally local and is not shared through GitHub.

1. Install **Git**, **Python 3.10 or newer**, and a webcam. Install Chrome or Edge if you plan to use speech commands.

2. Clone the branch and enter the project directory:

   ```bash
   git clone --branch test1 --single-branch https://github.com/shashank072007/NeuroCursor.git
   cd NeuroCursor
   ```

3. Create and activate a virtual environment, then install the Python packages.

   **Windows PowerShell:**

   ```powershell
   py -3 -m venv .venv
   .\.venv\Scripts\Activate.ps1
   python -m pip install --upgrade pip
   python -m pip install -r requirements.txt
   ```

   **macOS / Linux:**

   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   python -m pip install --upgrade pip
   python -m pip install -r requirements.txt
   ```

4. Close other apps using the webcam, then launch a safe first run:

   ```bash
   python main.py --source live --camera-index 0 --simulate --open-browser
   ```

   If camera index `0` is unavailable, stop the app with **Ctrl+C** and retry with `--camera-index 1`. The browser page is `http://127.0.0.1:5000/`; the camera preview should say **Python Vision Live**. Grant camera permission to Python/the terminal in the operating system if prompted. The browser itself does not access the webcam.

5. In the app, open **Live Cursor Control** and select **5-Point Calibration**. Follow the prompts: neutral pose, comfortable right, left, up, and down positions. Keep your face visible and hold each pose until the next prompt. The calibration is saved locally for that laptop.

6. Try **Head + gestures** with `--simulate` still enabled. Smile or left wink performs a left click; mouth open or right wink performs a right click. The green dwell circle also performs one in-app left click when it completes. Move away from a target to rearm dwell clicking.

7. To enable native desktop cursor control on a supported system, stop the app with **Ctrl+C** and restart without `--simulate`:

   ```bash
   python main.py --source live --camera-index 0 --open-browser
   ```

8. Choose a mode in the startup dialog and allow microphone access when the browser asks. Say **“Hey Cursor”** followed by a command. If microphone access was denied, use the top-bar Voice button to retry. In **Head + speech** mode, choose which input has priority.

At app startup, a mode chooser asks whether to use **Head Cursor** or **Voice Cursor**. The microphone listener is armed after choosing so you can switch later by saying **“Hey Cursor, switch to voice cursor now”** or **“Hey Cursor, switch to head cursor mode.”** You can also change the mode with the top-bar selector.

**Platform notes:** Windows 10/11 is the primary desktop-control target. On macOS, grant camera and Accessibility permissions to the terminal/Python. On Linux, the camera may require access to `/dev/video0`, and native mouse control can depend on the desktop session (X11/Wayland). The in-browser controls can be used with a supported browser even when native desktop permissions are unavailable.

### Hosted web interface with local Python companion

The web interface is published at **https://shashank072007.github.io/NeuroCursor/**. Each user still runs the Python companion on their own laptop; it is the only process that opens the webcam and it performs native cursor actions locally. Camera frames are streamed from that laptop to the browser and are not sent to GitHub Pages.

1. Start the companion from the project folder with Python and the requirements installed:

   ```bash
   python main.py --source live --camera-index 0 --simulate
   ```

   Keep this terminal open. It prints a random local connection token for this run. `--simulate` keeps native OS cursor movement and clicks disabled for a safe first connection. Remove `--simulate` only after verifying the tracking and calibration.

2. Open **https://shashank072007.github.io/NeuroCursor/** in Chrome or Edge. Paste the token printed by Python into **Connect Python**. The browser may ask to allow the website to contact the local device; allow it for NeuroCursor. The connection uses `127.0.0.1:5000`, which is available only on that same laptop.

3. After the Python status shows connected, choose Head Cursor or Voice Cursor. Calibrate each laptop separately; profiles and calibration remain local.

The companion binds to `127.0.0.1` and uses a fresh token at each launch. The token is held in the browser tab session and should not be shared. To use a fork or another hosted domain, add that site's origin (scheme and host only) to the `FLUX_ALLOWED_ORIGINS` environment variable before launching Python, separated by commas if needed.

GitHub Pages deploys the `frontend/` directory from the `test1` branch using `.github/workflows/pages.yml`. In repository **Settings → Pages**, set the source to **GitHub Actions** once; pushes that change the frontend then publish automatically.

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
| **"Hey Cursor, switch to voice cursor now"** | Frontend Voice | Switches from head tracking to voice cursor control |
| **"Hey Cursor, switch to head cursor mode"** | Frontend Voice | Returns to head tracking |
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
   - **Language Selection:** Choose English (India/US/UK), Hindi, Bengali, Tamil, Telugu, or Urdu; the choice is saved for both dictation and cursor commands.
   - **Better Recovery of Quiet Speech:** Dictation no longer discards recognized results just because the browser assigned low confidence; it compares available alternatives and keeps interim text visible.
   - **Contextual Command Hints:** Supported browsers receive NeuroCursor wake-word, mode-switch, navigation, and click phrases as recognition hints.
   - **Reliable Reconnection:** Recognition restarts once at a time after pauses or service disconnects, with clearer microphone and language errors.
   - **Expanded Voice Intent Dictionary:** Direct "Click [target]" or "Select [option]" voice commands automatically glide the cursor and trigger selection.

   The speech model is provided by the browser. NeuroCursor improves language selection, phrase context, result handling, and recovery; actual microphone gain and recognition acoustics remain controlled by the user's browser, operating system, and microphone.

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
The test suite validates:
1. REST endpoints, token auth, CORS headers, and frontend asset delivery.
2. Dual schema normalization bridging Vision (`pointer`, `raw_motion`, `detected`) and Backend (`head`, `face.detected`, `ts`).
3. Landmark quality gating and strict null-out fail-safes.
4. Bilateral blink suppression and debounced continuous gesture progression.
5. Effort meter EMA smoothing, warmup guards, and fatigue hysteresis.
