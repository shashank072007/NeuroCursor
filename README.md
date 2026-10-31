# FLUX · Backend & OS Layer (`backend/`)

**Author:** Samrudh (Backend / OS)  
**Contract Version:** FLUX-CONTRACT v1.1  
**Project:** FLUX — An interface that adapts to the user's body, minute by minute.

---

## 1. Overview & Architecture

The FLUX backend serves as the brain and safety net for the hands-free accessibility platform:
- **Event Bus & SSE (`bus.py`, `app.py`):** Serves `GET /stream?token=...` at ~30 Hz. Bounded queue per client, latest-of-each-type snapshot on connect (G14), and `: keepalive` every 15 s.
- **IntentGuard (`intent_guard.py`):** Strict 8-stage state machine (`IDLE -> CANDIDATE -> VALIDATED -> EXECUTED -> COOLDOWN`). One decision per episode, explicit rejection reasons, measured `latency_ms`.
- **Effort Meter (`effort.py`):** Four movement-strain components (`range_loss`, `jitter`, `gesture_strain`, `friction`), EMA smoothing, warmup & rearm guards, and level hysteresis (`fresh`, `moderate`, `high`, `rest`).
- **Adaptation Engine (`adapt.py`):** Translates effort levels to `ui_state` parameters (`target_scale`, `dwell_ms`, `radial_bubbles`, `smoothing_alpha`, `gesture_threshold_mult`, `gesture_hold_ms`, `lens`), continuous gain compensation, and neutral drift re-centring.
- **Channel Fusion (`channels.py`):** Monitors rolling reliability across `gesture`, `dwell`, and `sound`. Dwell runs in shadow mode during gesture primary; triggers `suggest_channel` on degradation.
- **OS Control (`os_control.py`):** Windows DPI-aware normalized-to-pixel coordinate conversion and failsafe-free cursor movement and clicks.
- **Safety & Panic Keys (`safety.py`):** Hardware-free panic hotkeys (**F9 = pause/resume**, **F10 = lock/unlock**) and tracking-loss jump prevention.
- **Calibration & Profiles (`calibration.py`, `profiles.py`):** Orchestrates the calibration wizard and saves personalized profile formulas (C.8).
- **Benchmark Storage (`bench.py`):** Records trial metrics and exports exact 16-column CSVs.

---

## 2. Quickstart

### Prerequisites
- Python 3.10+
- Dependencies: `flask`, `numpy`, `pynput`, `pywin32`

```bash
pip install -r requirements.txt
```

### Running the Backend

#### Mock Mode (Default for Dev & Frontend Testing)
```bash
python app.py --source mock --dev
```
- Binds to `http://127.0.0.1:5000`
- Token is set to `dev-token`
- Relays simulated ~30 Hz head movement and periodic scripted gestures

#### Replay Mode (Demo Backup)
```bash
python app.py --source replay --replay-file session.jsonl --dev
```

#### Live Mode (Connected to Ritesh's Vision Queue)
```bash
python app.py --source live
```

---

## 3. REST API Reference

All REST endpoints require the `X-Flux-Token` header.

| Endpoint | Method | Body | Description |
|---|---|---|---|
| `/stream?token=<token>` | GET | — | SSE stream. Sends snapshot on connect, then live messages. |
| `/calibrate/start` | POST | `{"profile_id": "name"}` | Starts calibration sequence. |
| `/calibrate/step` | POST | `{"step": "neutral", "rep": 1}` | Captures/records step data. |
| `/calibrate/commit` | POST | `{}` | Computes and saves profile per C.8 formulas. |
| `/profiles` | GET | — | Lists stored user profiles. |
| `/profile/<id>` | GET / PUT | Profile JSON | Reads or writes a profile JSON. |
| `/profile/<id>/activate` | POST | `{}` | Activates profile & emits `vision_params`. |
| `/pause`, `/resume` | POST | `{}` | Pauses or resumes click execution. |
| `/lock`, `/unlock` | POST | `{}` | Locks/unlocks clicks and cursor movement. |
| `/mode` | POST | `{"mode": "flux"\|"static"}` | Switches adaptive flux or static mode. |
| `/channel/accept` | POST | `{"channel": "dwell"}` | Accepts recommended channel switch. |
| `/undo` | POST | `{}` | Undoes action within 2000 ms, re-emits with `undone: true`. |
| `/bench/log` | POST | JSON trial row | Appends trial row to CSV. |
| `/bench/export` | GET | `?session_id=...` | Exports CSV text. |
| `/dev/effort` | POST | `{"score": 0-100\|null}` | Overrides effort score (`simulated: true`). |
| `/dev/level` | POST | `{"level": "fresh"\|"moderate"\|"high"\|"rest"\|null}` | Overrides level for false-click testing. |
| `/pointer/snap` | POST | `{"nx": 0.5, "ny": 0.5}` | Adjusts neutral point so pointer lands at target. |

---

## 4. Hotkeys
- **F9:** Toggle Pause / Resume (cursor moves, clicks disabled)
- **F10:** Toggle Lock / Unlock (cursor and clicks disabled)
