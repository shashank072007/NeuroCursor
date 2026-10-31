# NeuroCursor — Frontend Suite

**NeuroCursor (FLUX)** is an accessible, hands-free assistive interface designed for full autonomy.

### Features
- **Hands-Free In-Browser Head Tracking**: Real-time facial landmark detection powered by Google MediaPipe FaceMesh (WASM), requiring zero external backend installation.
- **Facial Gesture Triggers**:
  - **Smile**: Synthetic Left Click / Select.
  - **Open Mouth**: Synthetic Right Click / Context Action.
  - **Eyebrow Raise**: Pause / Resume Head Tracking.
- **Voice-Interactive Cursor Engine**: Wake-word recognition for `"Hey Cursor"` + 27-feature target registry for spoken hands-free navigation (`"point towards speak button"`, `"point towards dashboard"`, etc.).
- **Speech-to-Text & Transcriber**: Native Web Speech Recognition for dictation and communication cards.
- **Text-to-Speech Communication**: Browser-native Web Speech Synthesis with customizable voice profiles.
- **Auralight Design System**: High-contrast, glassmorphic UI with customizable light/dark themes and responsive typography.

### How to Run Locally
1. Serve this folder with any static web server:
   ```bash
   # Using Python
   python -m http.server 5173

   # Or using Node / npx
   npx serve .
   ```
2. Open `http://localhost:5173` in Google Chrome, Microsoft Edge, or Brave.
3. Grant camera and microphone permissions when prompted.
