# NeuroCursor — Integrated Frontend

**NeuroCursor (FLUX)** is an accessible, hands-free assistive interface designed for full autonomy.

### Architecture
- The Python vision worker is the sole webcam owner and runs MediaPipe Face Landmarker, calibration, filtering, and gesture detection.
- Flask relays normalized tracking events and performance telemetry over Server-Sent Events (SSE).
- The camera preview is an MJPEG stream encoded by the Python capture worker. The browser does not request webcam access or run a MediaPipe model.

### Features
- **Hands-Free Head Tracking**: Python Face Landmarker tracking with calibrated, filtered pointer coordinates.
- **Facial Gesture Triggers**:
  - **Smile**: Synthetic Left Click / Select.
  - **Open Mouth**: Synthetic Right Click / Context Action.
  - **Eyebrow Raise**: Pause / Resume Head Tracking.
- **Voice-Interactive Cursor Engine**: Wake-word recognition for `"Hey Cursor"` + 27-feature target registry for spoken hands-free navigation (`"point towards speak button"`, `"point towards dashboard"`, etc.).
- **Selectable Cursor Modes**: Head + gestures, Speech cursor, Physical mouse, or Hybrid. Hybrid mode lets the user choose whether head or speech input owns browser cursor navigation.
- **Directional Speech Navigation**: With voice enabled, say `"Hey Cursor, move cursor left"`, `"move cursor up"`, or `"point to center"`; say `"click [option]"` to select a named UI control.
- **Speech-to-Text & Transcriber**: Native Web Speech Recognition for dictation and communication cards.
- **Text-to-Speech Communication**: Browser-native Web Speech Synthesis with customizable voice profiles.
- **Auralight Design System**: High-contrast, glassmorphic UI with customizable light/dark themes and responsive typography.

### How to Run Locally
From the repository root, start the integrated Python application:

```bash
python main.py --source live --open-browser
```

Open the local Flask page at `http://127.0.0.1:5000/`. If the camera is unavailable, the UI reports that Python vision is offline; it does not silently switch to browser capture or synthetic frames. Use `python main.py --source mock` only for simulation.

Voice control requires a supported browser with its microphone permission enabled. Turn on the Voice pill, then say `"Hey Cursor"` followed by a command. In Hybrid mode, the selected priority arbitrates cursor movement while speech is active. In Head or Hybrid mode, holding the cursor steady fills a green ring and performs one left click when complete; move away from the target to rearm it.
