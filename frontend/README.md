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
- **Startup Mode Choice**: On launch, choose Head Cursor or Voice Cursor. The voice listener remains available for spoken mode switching: `"Hey Cursor, switch to voice cursor now"` and `"Hey Cursor, switch to head cursor mode"`.
- **Directional Speech Navigation**: With voice enabled, say `"Hey Cursor, move cursor left"`, `"move cursor up"`, or `"point to center"`; say `"click [option]"` to select a named UI control.
- **Speech-to-Text & Transcriber**: Browser Web Speech Recognition with selectable language, contextual NeuroCursor command hints, alternative transcript selection, interim text, punctuation, and guarded reconnects. Lower-confidence recognized speech is retained rather than silently discarded.
- **Text-to-Speech Communication**: Browser-native Web Speech Synthesis with customizable voice profiles.
- **Auralight Design System**: High-contrast, glassmorphic UI with customizable light/dark themes and responsive typography.

### How to Run Locally
From the repository root, start the integrated Python application:

```bash
python main.py --source live --open-browser
```

Open the local Flask page at `http://127.0.0.1:5000/`. If the camera is unavailable, the UI reports that Python vision is offline; it does not silently switch to browser capture or synthetic frames. Use `python main.py --source mock` only for simulation.

Voice control requires a supported browser with its microphone permission enabled. On the Voice & Communication page, select your speaking language for both dictation and cursor commands. Choose a cursor mode at launch and allow microphone access, then say `"Hey Cursor"` followed by a command. If voice listening is off, toggle the Voice pill. In Hybrid mode, the selected priority arbitrates cursor movement while speech is active. The browser supplies the speech model; microphone gain and acoustic capture are controlled by the browser, operating system, and microphone.
