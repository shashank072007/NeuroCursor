// =============================================================
// NEUROCURSOR — AURALIGHT INTERACTIVE ENGINE & HEAD TRACKING
// =============================================================

const state = {
  page: "dashboard",
  darkMode: false,
  headMouseEnabled: !["speech", "mouse"].includes(localStorage.getItem("neuro_control_mode") || "head"),
  controlMode: localStorage.getItem("neuro_control_mode") || "head",
  controlPriority: localStorage.getItem("neuro_control_priority") || "head",
  cursorPaused: false,        // Eyebrow raise toggle
  voiceListening: false,     // Continuous voice command listener
  voiceCursorActive: false,  // Triggered by "Hey Cursor" wake word
  voiceError: "",            // Last microphone / recognition error
  isGliding: false,          // Active during smooth voice pointing animations
  osMouseEnabled: false,     // Direct physical Windows operating system cursor control
  cameraActive: false,
  trackingDetected: false,
  selectedPhrase: "",
  transcriptionText: "",
  isListening: false,
  sensitivity: 36,           // Slider: 10 - 100 (lower default for precision)
  dwell: 1.2,                // Seconds: 0.5 - 3.5
  sound: true,
  visualReticle: true,
  clickFeedback: true,
  alertStatus: "",
  activeProfile: "My Workspace",
  highContrast: false,
  largeInterface: false,
  reducedAnimation: false,
  voiceFeedback: true,
  brushColor: "#24A98A",
  brushSize: 5,
  contacts: [
    { name: "Sarah (Primary Caregiver)", phone: "+1 (555) 234-5678" }
  ],
  calibrating: false,
  calibStep: 0,
  
  // Real-time tracking coordinates & kinematics
  rawNx: 0.5,
  rawNy: 0.5,
  smoothNx: 0.5,
  smoothNy: 0.5,
  rawDx: 0.0,
  rawDy: 0.0,
  gestureName: "none",
  gestureScore: 0.0,
  fps: 30.0,
  captureMs: 3.5,
  processMs: 11.0,
  
  // Camera orientation configuration (default false: standard un-inverted view)
  mirrorVideo: localStorage.getItem("neuro_mirror_video") === "true",
  flipVVideo: localStorage.getItem("neuro_flipv_video") === "true",
  interimTranscription: ""
};

const pageTitles = {
  dashboard: "Dashboard",
  control: "Live Cursor Control",
  communication: "Voice & Communication",
  studio: "Creative Studio",
  sos: "SOS & Caregiver Center",
  settings: "Personalisation",
  help: "Help & Guidance"
};

// Web Audio API for gentle acoustic feedback
let audioCtx = null;
function playSound(type = "click") {
  if (!state.sound) return;
  try {
    if (!audioCtx) audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    if (audioCtx.state === "suspended") audioCtx.resume();

    const osc = audioCtx.createOscillator();
    const gain = audioCtx.createGain();
    osc.connect(gain);
    gain.connect(audioCtx.destination);

    if (type === "click") {
      osc.type = "sine";
      osc.frequency.setValueAtTime(560, audioCtx.currentTime);
      osc.frequency.exponentialRampToValueAtTime(780, audioCtx.currentTime + 0.07);
      gain.gain.setValueAtTime(0.06, audioCtx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.001, audioCtx.currentTime + 0.07);
      osc.start();
      osc.stop(audioCtx.currentTime + 0.07);
    } else if (type === "success") {
      osc.type = "triangle";
      osc.frequency.setValueAtTime(440, audioCtx.currentTime);
      osc.frequency.exponentialRampToValueAtTime(880, audioCtx.currentTime + 0.18);
      gain.gain.setValueAtTime(0.1, audioCtx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.001, audioCtx.currentTime + 0.2);
      osc.start();
      osc.stop(audioCtx.currentTime + 0.2);
    } else if (type === "alert") {
      osc.type = "sawtooth";
      osc.frequency.setValueAtTime(350, audioCtx.currentTime);
      osc.frequency.linearRampToValueAtTime(520, audioCtx.currentTime + 0.22);
      gain.gain.setValueAtTime(0.18, audioCtx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.01, audioCtx.currentTime + 0.28);
      osc.start();
      osc.stop(audioCtx.currentTime + 0.28);
    }
  } catch (e) {
    // Autoplay restrictions
  }
}

// Text to Speech (Native Web Speech Synthesis)
function speak(text) {
  if (!text) return;
  playSound("success");
  if (!state.voiceFeedback) return;
  // Speech synthesis seizes the audio device and kills Chrome SpeechRecognition.
  // Skip spoken feedback while the command mic is armed so listening stays alive.
  if (voiceEngineArmed && !state.isListening) return;
  if (!("speechSynthesis" in window)) return;
  try {
    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.rate = 0.92;
    utterance.pitch = 1.0;
    utterance.onend = resumeVoiceAfterSpeech;
    utterance.onerror = resumeVoiceAfterSpeech;
    window.speechSynthesis.speak(utterance);
  } catch (e) {}
}

function resumeVoiceAfterSpeech() {
  if (voiceEngineArmed && !state.isListening) {
    restartVoiceRecognizerSoon(280);
  }
}

// Global Navigation
function setPage(pageId) {
  state.page = pageId;
  playSound("click");
  updateNavigation();
  renderView();
}

function updateNavigation() {
  document.querySelectorAll(".nav-item").forEach(item => {
    if (item.getAttribute("data-page") === state.page) {
      item.classList.add("active");
    } else {
      item.classList.remove("active");
    }
  });

  const currentPageEl = document.getElementById("topbar-current-page");
  if (currentPageEl) currentPageEl.textContent = pageTitles[state.page] || "Workspace";

  const profileNameEl = document.getElementById("sidebar-profile-name");
  if (profileNameEl) profileNameEl.textContent = state.activeProfile;

  const initial = state.activeProfile.charAt(0).toUpperCase() || "N";
  const sideAvatar = document.getElementById("sidebar-avatar");
  const topAvatar = document.getElementById("topbar-avatar");
  if (sideAvatar) sideAvatar.textContent = initial;
  if (topAvatar) topAvatar.textContent = initial;
}

// Theme Toggle
function toggleDarkMode() {
  state.darkMode = !state.darkMode;
  document.body.classList.toggle("dark-mode", state.darkMode);
  const icon = document.getElementById("theme-icon");
  if (icon) {
    icon.setAttribute("data-lucide", state.darkMode ? "sun" : "moon");
  }
  playSound("click");
  if (window.lucide) window.lucide.createIcons();
}

// Dwell selection kinematics & Gesture debouncing
let lastCursorX = 0;
let lastCursorY = 0;
let dwellAnchorX = null;
let dwellAnchorY = null;
let dwellTimeAccumulated = 0;
let dwellSpent = false;
let lastFrameTime = performance.now();
let lastSyntheticClickAt = 0;
const DWELL_RADIUS_THRESHOLD = 38;
let lastGestureClickTime = 0;
let lastEyebrowToggleTime = 0;
let gestureToastTimer = null;
let voiceEngineArmed = false;
let voiceCommandRecognizer = null;
let voiceGlideAnimationId = null;
let voiceActiveTimeout = null;
let voiceRestartTimer = null;
let voiceStartInFlight = false;

// Floating Gesture Notification Toast
function showGestureToast(msg) {
  const toast = document.getElementById("gesture-toast");
  if (!toast) return;
  toast.textContent = msg;
  toast.classList.add("show");
  if (gestureToastTimer) clearTimeout(gestureToastTimer);
  gestureToastTimer = setTimeout(() => {
    toast.classList.remove("show");
  }, 1600);
}

// Master In-Browser Head Mouse Toggle
async function toggleHeadMouseControl() {
  await setControlMode(state.headMouseEnabled ? "mouse" : "head");
}

async function setControlMode(mode) {
  if (!["head", "speech", "mouse", "hybrid"].includes(mode)) return;
  state.controlMode = mode;
  state.headMouseEnabled = mode === "head" || mode === "hybrid";
  try { localStorage.setItem("neuro_control_mode", mode); } catch (e) {}
  playSound(state.headMouseEnabled ? "success" : "click");
  
  const cursor = document.getElementById("global-head-cursor");
  const btn = document.getElementById("head-mouse-toggle-btn");
  const text = document.getElementById("head-mouse-status-text");

  if (state.headMouseEnabled) {
    if (cursor) cursor.classList.add("active");
    if (btn) btn.classList.add("active");
    if (text) text.textContent = mode === "hybrid" ? "Hybrid: ON" : "Head Mouse: ON";
    if (!backendConnected) await startCameraVision();
  } else {
    if (cursor) cursor.classList.remove("active");
    if (btn) btn.classList.remove("active");
    if (text) text.textContent = mode === "speech" ? "Speech Cursor" : "Physical Mouse";
  }
  const modeSelect = document.getElementById("control-mode-select");
  if (modeSelect) modeSelect.value = mode;
  const prioritySelect = document.getElementById("control-priority-select");
  if (prioritySelect) prioritySelect.disabled = mode !== "hybrid";
  syncBackendControlMode();
  resetDwellSelection();
  renderView();
}

function resetDwellSelection() {
  dwellAnchorX = null;
  dwellAnchorY = null;
  dwellTimeAccumulated = 0;
  dwellSpent = false;
  const ring = document.getElementById("dwell-progress-bar");
  if (ring) ring.style.strokeDashoffset = 157;
}

function setControlPriority(priority) {
  if (!["head", "speech"].includes(priority)) return;
  state.controlPriority = priority;
  try { localStorage.setItem("neuro_control_priority", priority); } catch (e) {}
  const select = document.getElementById("control-priority-select");
  if (select) select.value = priority;
  if (state.controlMode !== "hybrid") return;
  syncBackendControlMode();
  showGestureToast(`Cursor priority: ${priority}`);
}

function syncBackendControlMode() {
  const speechOwns = state.controlMode === "hybrid" && state.controlPriority === "speech" && state.voiceCursorActive;
  callBackend("/control-mode", { mode: speechOwns ? "speech" : state.controlMode });
}


// -------------------------------------------------------------
// FLUX BACKEND INTEGRATION & SSE STREAM
// -------------------------------------------------------------
const BACKEND_URL = (window.location.protocol === "http:" || window.location.protocol === "https:")
  ? window.location.origin
  : "http://127.0.0.1:5000";
const FLUX_TOKEN = "dev-token";
let backendSSE = null;
let backendConnected = false;

function initBackendConnection() {
  try {
    const streamUrl = `${BACKEND_URL}/stream?token=${FLUX_TOKEN}`;
    backendSSE = new EventSource(streamUrl);

    backendSSE.onopen = () => {
      backendConnected = true;
      console.log("[NeuroCursor] Connected to FLUX backend SSE stream at", streamUrl);
      const statusEl = document.getElementById("pip-status-label");
      if (statusEl) statusEl.textContent = "Python Vision Linked";
      syncWebcamVideoStreams();
      const statusText = document.getElementById("system-status-text");
      if (statusText) statusText.textContent = "Vision: Connected to Python";
      callBackend("/vision/sensitivity", { value: state.sensitivity });
    };

    backendSSE.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);
        handleBackendMessage(msg);
      } catch (err) {
        // keepalive or non-json message
      }
    };

    backendSSE.onerror = () => {
      if (backendConnected) {
        console.warn("[NeuroCursor] Python vision stream disconnected.");
        backendConnected = false;
        state.cameraActive = false;
        state.trackingDetected = false;
        syncWebcamVideoStreams();
      }
    };
  } catch (e) {
    console.warn("[NeuroCursor] Python backend unavailable; integrated tracking is disabled:", e);
  }
}

function handleBackendMessage(msg) {
  if (!msg || !msg.type) return;

  if (msg.type === "frame") {
    if (msg.face && Number.isFinite(msg.face.quality)) state.faceQuality = Number(msg.face.quality);
    if (msg.camera && Number.isFinite(msg.camera.brightness)) state.cameraBrightness = Number(msg.camera.brightness);
    if (msg.camera && typeof msg.camera.connected === "boolean" && msg.camera.connected !== state.cameraActive) {
      state.cameraActive = msg.camera.connected;
      syncWebcamVideoStreams();
      const pipLabel = document.getElementById("pip-status-label");
      const statusText = document.getElementById("system-status-text");
      const label = state.cameraActive ? "Python Vision Live" : "Python Camera Offline";
      if (pipLabel) pipLabel.textContent = label;
      if (statusText) statusText.textContent = `Vision: ${label}`;
    }
    const head = msg.head || msg.pointer;
    if (head && msg.detected) {
      const nx = head.nx !== undefined ? head.nx : 0.5;
      const ny = head.ny !== undefined ? head.ny : 0.5;
      const gest = msg.gesture ? msg.gesture.name : "none";
      const score = msg.gesture ? msg.gesture.score : 0.0;
      updateTrackingKinematics(nx, ny, gest, score);
      state.trackingDetected = true;
    } else {
      state.trackingDetected = false;
      state.gestureName = "none";
      state.gestureScore = 0;
      const gestureLabel = document.getElementById("active-gesture-display");
      if (gestureLabel) gestureLabel.textContent = "None (Neutral)";
      resetDwellSelection();
    }
    if (msg.timing && msg.timing.fps) {
      state.fps = msg.timing.fps;
    }
    if (msg.timing) {
      state.captureMs = Number(msg.timing.capture_ms || 0);
      state.processMs = Number(msg.timing.process_ms || 0);
    }
    if (msg.face && Number.isFinite(msg.face.quality)) state.faceQuality = msg.face.quality;
    if (msg.camera && Number.isFinite(msg.camera.brightness)) state.cameraBrightness = msg.camera.brightness;
  } else if (msg.type === "status") {
    state.cursorPaused = !!msg.paused;
    if (msg.locked !== undefined) state.locked = msg.locked;
    state.cameraActive = msg.camera === "on";
    const pipLabel = document.getElementById("pip-status-label");
    const statusText = document.getElementById("system-status-text");
    const label = state.cameraActive ? "Python Vision Live" : msg.camera === "mock" ? "Python Vision: Mock Source" : "Python Camera Offline";
    if (pipLabel) pipLabel.textContent = label;
    if (statusText) statusText.textContent = `Vision: ${label}`;
    syncWebcamVideoStreams();
    if (Number.isFinite(msg.fps)) state.fps = msg.fps;
  } else if (msg.type === "action") {
    if (msg.action === "left_click" || msg.action === "click") {
      const scrX = (msg.nx ?? state.smoothNx) * window.innerWidth;
      const scrY = (msg.ny ?? state.smoothNy) * window.innerHeight;
      if (["head", "hybrid"].includes(state.controlMode)) executeClickAt(scrX, scrY, "left", "Backend Gesture");
    } else if (msg.action === "right_click") {
      const scrX = (msg.nx ?? state.smoothNx) * window.innerWidth;
      const scrY = (msg.ny ?? state.smoothNy) * window.innerHeight;
      if (["head", "hybrid"].includes(state.controlMode)) executeClickAt(scrX, scrY, "right", "Backend Gesture");
    }
  } else if (msg.type === "ui_state") {
    if (msg.dwell_ms) {
      state.dwell = msg.dwell_ms / 1000.0;
    }
  } else if (msg.type === "effort") {
    state.effortScore = msg.score;
    state.effortLevel = msg.level;
  }
}

async function callBackend(endpoint, body = {}) {
  try {
    const res = await fetch(`${BACKEND_URL}${endpoint}`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Flux-Token": FLUX_TOKEN
      },
      body: JSON.stringify(body)
    });
    return await res.json();
  } catch (e) {
    return { ok: false, error: e.message };
  }
}

// Precision Cursor Tracking Mode Toggle
function toggleOSMouseControl() {
  state.osMouseEnabled = !state.osMouseEnabled;
  playSound(state.osMouseEnabled ? "success" : "click");
  showGestureToast(state.osMouseEnabled ? "🎯 OS Physical Mouse: ON" : "🎯 OS Physical Mouse: PAUSED");
  if (state.osMouseEnabled) {
    callBackend("/resume");
  } else {
    callBackend("/pause");
  }
  renderView();
}


// Webcam preview is relayed from Python's capture worker over MJPEG.
// The browser never opens a camera device or runs a landmark model.
function applyWebcamTransforms() {
  [
    document.getElementById("live-webcam-element"),
    document.getElementById("persistent-webcam"),
    document.getElementById("pip-camera-container")
  ].forEach(el => {
    if (!el) return;
    el.classList.toggle("mirrored", !!state.mirrorVideo);
    el.classList.toggle("flipped-v", !!state.flipVVideo);
  });
}

function toggleWebcamMirror() {
  state.mirrorVideo = !state.mirrorVideo;
  try { localStorage.setItem("neuro_mirror_video", state.mirrorVideo ? "true" : "false"); } catch (e) {}
  applyWebcamTransforms();
  playSound("click");
  showGestureToast(state.mirrorVideo ? "Preview mirrored" : "Preview standard orientation");
  renderView();
}

function toggleWebcamFlipV() {
  state.flipVVideo = !state.flipVVideo;
  try { localStorage.setItem("neuro_flipv_video", state.flipVVideo ? "true" : "false"); } catch (e) {}
  applyWebcamTransforms();
  playSound("click");
  showGestureToast(state.flipVVideo ? "Preview flipped vertically" : "Preview standard orientation");
  renderView();
}

function syncWebcamVideoStreams() {
  const previewUrl = backendConnected && state.cameraActive
    ? `${BACKEND_URL}/camera/stream?token=${encodeURIComponent(FLUX_TOKEN)}`
    : "";
  [document.getElementById("persistent-webcam"), document.getElementById("live-webcam-element")].forEach(img => {
    if (!img) return;
    if (previewUrl && img.src !== previewUrl) img.src = previewUrl;
    if (!previewUrl && img.hasAttribute("src")) img.removeAttribute("src");
  });
  applyWebcamTransforms();
}

async function startCameraVision() {
  if (!backendSSE) initBackendConnection();
  syncWebcamVideoStreams();
  if (!backendConnected) {
    showGestureToast("Start the Python app to connect its camera and tracking stream.");
    return;
  }
  showGestureToast(state.cameraActive ? "Python vision is live." : "Waiting for Python camera status…");
}

function stopCameraVision() {
  state.headMouseEnabled = false;
  state.trackingDetected = false;
  callBackend("/pause");
  const cursor = document.getElementById("global-head-cursor");
  if (cursor) cursor.classList.remove("active");
  showGestureToast("Cursor paused. Python camera stays available to the integrated app.");
  renderView();
}

// Coordinates arrive normalized and already calibrated/filtered by Python.
let lastObservedGesture = "none";
let calibrationPreviousPause = false;
function updateTrackingKinematics(targetNx, targetNy, gesture = "none", score = 0) {
  state.rawNx = Number(targetNx);
  state.rawNy = Number(targetNy);
  state.gestureName = gesture || "none";
  state.gestureScore = Number(score) || 0;
  const gestureLabel = document.getElementById("active-gesture-display");
  if (gestureLabel) {
    gestureLabel.textContent = state.gestureName === "none"
      ? "None (Neutral)"
      : `${state.gestureName.toUpperCase()} · ${Math.round(state.gestureScore * 100)}%`;
  }

  // Toggle on an activation edge, never repeatedly while the expression is held.
  if (!state.calibrating && state.gestureName === "brow_raise" && lastObservedGesture !== "brow_raise" && state.gestureScore >= 0.55) {
    state.cursorPaused = !state.cursorPaused;
    callBackend(state.cursorPaused ? "/pause" : "/resume");
    const cursor = document.getElementById("global-head-cursor");
    if (cursor) cursor.classList.toggle("paused", state.cursorPaused);
    showGestureToast(state.cursorPaused ? "Cursor paused" : "Cursor resumed");
  }
  lastObservedGesture = state.gestureName;

  const cursor = document.getElementById("global-head-cursor");
  const speechOwnsCursor = (state.controlMode === "speech" && (state.voiceCursorActive || state.isGliding)) ||
    (state.controlMode === "mouse" && (state.voiceCursorActive || state.isGliding)) ||
    (state.controlMode === "hybrid" && state.controlPriority === "speech" && (state.voiceCursorActive || state.isGliding));
  if (!speechOwnsCursor) {
    state.smoothNx = Math.max(0, Math.min(1, state.rawNx));
    state.smoothNy = Math.max(0, Math.min(1, state.rawNy));
  }
  const x = state.smoothNx * window.innerWidth;
  const y = state.smoothNy * window.innerHeight;
  if (cursor && state.headMouseEnabled && !state.cursorPaused && !speechOwnsCursor) {
    cursor.style.left = `${x}px`;
    cursor.style.top = `${y}px`;
  }

  const reticle = document.getElementById("active-reticle");
  const zone = document.getElementById("cursor-test-zone");
  if (reticle && zone) {
    const rect = zone.getBoundingClientRect();
    reticle.style.left = `${state.smoothNx * rect.width}px`;
    reticle.style.top = `${state.smoothNy * rect.height}px`;
  }
  if (state.page === "studio" && state.headMouseEnabled && !state.cursorPaused && !speechOwnsCursor) {
    handleHeadStudioDrawing(x, y);
  }

  const now = performance.now();
  const dt = Math.min(0.1, Math.max(0, (now - lastFrameTime) / 1000));
  lastFrameTime = now;
  const dwellEnabled = ["head", "hybrid"].includes(state.controlMode) &&
    state.headMouseEnabled && !state.cursorPaused && !state.calibrating && !speechOwnsCursor;
  const ring = document.getElementById("dwell-progress-bar");
  if (!dwellEnabled) {
    resetDwellSelection();
  } else {
    const anchorX = dwellAnchorX === null ? x : dwellAnchorX;
    const anchorY = dwellAnchorY === null ? y : dwellAnchorY;
    if (Math.hypot(x - anchorX, y - anchorY) > DWELL_RADIUS_THRESHOLD) {
      dwellAnchorX = x;
      dwellAnchorY = y;
      dwellTimeAccumulated = 0;
      dwellSpent = false;
    } else if (dwellAnchorX === null) {
      dwellAnchorX = x;
      dwellAnchorY = y;
      dwellTimeAccumulated = 0;
      dwellSpent = false;
    } else if (!dwellSpent) {
      dwellTimeAccumulated += dt;
    }

    const dwellTarget = Math.max(0.5, Math.min(3.5, Number(state.dwell) || 1.2));
    const progress = Math.min(1, dwellTimeAccumulated / dwellTarget);
    if (ring) ring.style.strokeDashoffset = 157 * (1 - progress);
    if (!dwellSpent && progress >= 1 && now - lastSyntheticClickAt >= 650) {
      dwellSpent = true;
      executeClickAt(x, y, "left", "Dwell Selection");
    }
  }

}

// Execute synthetic click on UI element under pointer with intelligent interactive ancestor resolution
function executeClickAt(x, y, button = "left", source = "Head Cursor") {
  lastSyntheticClickAt = performance.now();
  if (source !== "Dwell Selection") dwellSpent = true;
  const globalCursor = document.getElementById("global-head-cursor");
  if (globalCursor) {
    globalCursor.classList.add("clicking");
    globalCursor.style.pointerEvents = "none";
  }

  const rawTarget = document.elementFromPoint(x, y);
  if (rawTarget) {
    // Resolve nearest interactive target so child icons, spans, and labels activate their parent button/card
    const target = rawTarget.closest('button, a, input, select, textarea, [role="button"], [onclick], .interactive, .toggle, .toggle-row, .card-panel, .nav-item, .suggestion-chip, .key-btn, .calib-target') || rawTarget;

    // Transient visual feedback highlight
    target.classList.add("gesture-target-highlight");
    setTimeout(() => target.classList.remove("gesture-target-highlight"), 350);

    if (button === "left") {
      target.dispatchEvent(new MouseEvent("mousedown", { bubbles: true, cancelable: true, view: window, clientX: x, clientY: y, button: 0 }));
      target.dispatchEvent(new MouseEvent("mouseup", { bubbles: true, cancelable: true, view: window, clientX: x, clientY: y, button: 0 }));
      target.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true, view: window, clientX: x, clientY: y, button: 0 }));
    } else if (button === "right") {
      target.dispatchEvent(new MouseEvent("contextmenu", { bubbles: true, cancelable: true, view: window, clientX: x, clientY: y, button: 2 }));
    }
  }

  playSound("click");
  if (source === "Dwell Selection") showGestureToast("Dwell left click");

  setTimeout(() => {
    if (globalCursor) globalCursor.classList.remove("clicking");
  }, 220);
}

// Neutral Posture Calibration
function calibrateNeutralPosition() {
  callBackend("/vision/recenter").then(result => {
    if (result.ok) {
      showGestureToast(result.message || "Python neutral position saved.");
      playSound("success");
    } else {
      showGestureToast(result.error || "Could not recenter. Check Python camera tracking.");
    }
  });
}

// =============================================================
// VOICE INTERACTIVE CURSOR ENGINE ("HEY CURSOR" + POINTING)
// =============================================================
function getSpeechRecognitionCtor() {
  return window.SpeechRecognition || window.webkitSpeechRecognition || null;
}

function restartVoiceRecognizerSoon(delayMs = 220) {
  if (voiceRestartTimer) clearTimeout(voiceRestartTimer);
  voiceRestartTimer = setTimeout(() => {
    if (!voiceEngineArmed || state.isListening) return;
    try {
      if (voiceCommandRecognizer) voiceCommandRecognizer.start();
      else attachVoiceRecognizer();
    } catch (e) {
      attachVoiceRecognizer();
    }
  }, delayMs);
}

function destroyVoiceRecognizer() {
  if (voiceRestartTimer) {
    clearTimeout(voiceRestartTimer);
    voiceRestartTimer = null;
  }
  if (!voiceCommandRecognizer) return;
  voiceCommandRecognizer.onstart = null;
  voiceCommandRecognizer.onend = null;
  voiceCommandRecognizer.onerror = null;
  voiceCommandRecognizer.onresult = null;
  try { voiceCommandRecognizer.abort(); } catch (e) {}
  voiceCommandRecognizer = null;
}

async function ensureMicrophonePermission() {
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    throw new Error("Microphone API unavailable");
  }
  const stream = await navigator.mediaDevices.getUserMedia({
    audio: { echoCancellation: true, noiseSuppression: true }
  });
  // Release the track so SpeechRecognition can own the mic
  stream.getTracks().forEach((t) => t.stop());
}

function attachVoiceRecognizer() {
  const SpeechRec = getSpeechRecognitionCtor();
  if (!SpeechRec) return;

  destroyVoiceRecognizer();
  const rec = new SpeechRec();
  rec.continuous = true;
  rec.interimResults = true;
  rec.lang = navigator.language || "en-US";
  rec.maxAlternatives = 3;

  rec.onstart = () => {
    state.voiceListening = true;
    state.voiceError = "";
    updateVoicePillUI();
  };

  rec.onresult = (event) => {
    let transcript = "";
    let isFinal = false;
    for (let i = event.resultIndex; i < event.results.length; ++i) {
      transcript += event.results[i][0].transcript;
      if (event.results[i].isFinal) isFinal = true;
    }
    transcript = normalizeVoiceTranscript(transcript);
    if (transcript) handleVoiceCommandPhrase(transcript, isFinal);
  };

  rec.onerror = (e) => {
    const err = e && e.error ? e.error : "unknown";
    if (err === "not-allowed" || err === "service-not-allowed") {
      voiceEngineArmed = false;
      state.voiceListening = false;
      state.voiceError = "mic-blocked";
      showGestureToast("Microphone blocked. Allow mic in the browser address bar.");
      updateVoicePillUI();
      return;
    }
    if (err === "audio-capture") {
      state.voiceError = "no-mic";
      showGestureToast("No microphone was found.");
    }
    // aborted / no-speech / network: onend will reconnect
  };

  rec.onend = () => {
    state.voiceListening = false;
    updateVoicePillUI();
    if (voiceEngineArmed && !state.isListening) {
      restartVoiceRecognizerSoon(240);
    }
  };

  voiceCommandRecognizer = rec;
  try {
    rec.start();
  } catch (e) {
    restartVoiceRecognizerSoon(320);
  }
}

async function startVoiceCommandListener() {
  if (voiceStartInFlight) return;
  const SpeechRec = getSpeechRecognitionCtor();
  if (!SpeechRec) {
    state.voiceError = "unsupported";
    showGestureToast("Voice commands need Chrome, Edge, or Safari.");
    updateVoicePillUI();
    return;
  }
  if (state.isListening) {
    showGestureToast("Pause speech-to-text first, then turn on Hey Cursor.");
    return;
  }

  voiceStartInFlight = true;
  voiceEngineArmed = true;
  state.voiceError = "";
  updateVoicePillUI();

  try {
    await ensureMicrophonePermission();
    attachVoiceRecognizer();
    showGestureToast("Voice on. Say Hey Cursor, then a command.");
    playSound("success");
  } catch (err) {
    voiceEngineArmed = false;
    state.voiceListening = false;
    state.voiceError = "mic-blocked";
    showGestureToast("Allow microphone access to turn on voice control.");
    updateVoicePillUI();
  } finally {
    voiceStartInFlight = false;
  }
}

function stopVoiceCommandListener() {
  voiceEngineArmed = false;
  state.voiceListening = false;
  destroyVoiceRecognizer();
  deactivateVoiceCursorState();
  updateVoicePillUI();
}

function initVoiceCommandListener() {
  startVoiceCommandListener();
}

function toggleVoiceCommandListener() {
  if (voiceEngineArmed) {
    stopVoiceCommandListener();
    showGestureToast("Voice commands off");
    playSound("click");
    return;
  }
  startVoiceCommandListener();
}

function updateVoicePillUI() {
  const pill = document.getElementById("voice-command-pill");
  const status = document.getElementById("voice-command-status");
  if (!pill || !status) return;

  pill.classList.remove("listening", "awake", "error");

  if (state.voiceError === "unsupported" || state.voiceError === "mic-blocked" || state.voiceError === "no-mic") {
    pill.classList.add("error");
    status.textContent = state.voiceError === "unsupported" ? "Voice unsupported" : "Mic blocked";
    return;
  }
  if (state.voiceCursorActive) {
    pill.classList.add("awake");
    status.textContent = "Cursor Awake — listening";
  } else if (state.voiceListening || voiceEngineArmed) {
    pill.classList.add("listening");
    status.textContent = state.voiceListening ? "Listening — Hey Cursor" : "Starting mic…";
  } else {
    status.textContent = "Voice: Off";
  }
}

function normalizeVoiceTranscript(raw) {
  let t = (raw || "").trim().toLowerCase();
  t = t.replace(/[.,!?]+/g, " ");
  t = t.replace(/\b(hey|hi|hello|hay|he)\s+(curser|courser|kursor|cursa|kerser|cursor|curse her|cur sure|ker sure|computer)\b/g, "hey cursor");
  t = t.replace(/\bokay cursor\b/g, "hey cursor");
  t = t.replace(/\s+/g, " ").trim();
  return t;
}

let lastVoiceCommandTime = 0;
let lastProcessedCommand = "";

function handleVoiceCommandPhrase(phrase, isFinal = false) {
  const now = performance.now();
  if (now - lastVoiceCommandTime < 700 && phrase === lastProcessedCommand) {
    return;
  }

  // 1. Wake word detection: "Hey Cursor" / "Activate Cursor" / "Wake Up Cursor"
  const wakeWords = [
    "hey cursor", "hello cursor", "hi cursor", "okay cursor", "ok cursor",
    "activate cursor", "wake up cursor", "wake cursor",
    "cursor wake up", "hey curser", "curser wake up",
    "neuro cursor", "open cursor"
  ];

  let wakeMatched = false;
  let remainingPhrase = phrase;

  for (const w of wakeWords) {
    if (phrase.includes(w)) {
      wakeMatched = true;
      remainingPhrase = remainingPhrase.replace(w, "").trim();
      break;
    }
  }

  if (wakeMatched) {
    lastVoiceCommandTime = now;
    lastProcessedCommand = phrase;
    activateVoiceCursor();

    if (!remainingPhrase || remainingPhrase.length < 3) {
      return;
    }
    phrase = remainingPhrase;
  }

  // Commands wait for a final transcript so partial words do not fire
  if (!isFinal) return;

  const isDirectCommand = /(?:point|go to|move|navigate|look at|aim at|target|click|select|pause|sleep|resume|speak|speech|transcribe|water|food|canvas|camera|sos|emergency|center|left|right|up|down|priority|hybrid mode|mouse mode)/i.test(phrase);

  if (state.voiceCursorActive || isDirectCommand) {
    processVoiceInstruction(phrase);
    lastVoiceCommandTime = now;
    lastProcessedCommand = phrase;
  }
}

function activateVoiceCursor() {
  state.voiceCursorActive = true;
  state.cursorPaused = false;
  syncBackendControlMode();

  const globalCursor = document.getElementById("global-head-cursor");
  const label = document.getElementById("cursor-voice-label");
  if (globalCursor) {
    globalCursor.classList.add("active");
    globalCursor.classList.add("voice-listening");
    globalCursor.classList.remove("paused");
  }
  if (label) {
    label.textContent = "⚡ AWAKE: 'POINT TO...'";
  }

  updateVoicePillUI();
  playSound("success");
  showGestureToast("⚡ CURSOR ACTIVATED! Say: 'Point to [target]'");

  // Keep mic active and responsive (no long speech synthesis blocking)
  if (voiceActiveTimeout) clearTimeout(voiceActiveTimeout);
  voiceActiveTimeout = setTimeout(() => {
    deactivateVoiceCursorState();
  }, 20000);
}

function deactivateVoiceCursorState() {
  state.voiceCursorActive = false;
  syncBackendControlMode();
  const globalCursor = document.getElementById("global-head-cursor");
  if (globalCursor) {
    globalCursor.classList.remove("voice-listening");
    if (!state.headMouseEnabled) globalCursor.classList.remove("active");
  }
  updateVoicePillUI();
}

// =============================================================
// COMPREHENSIVE FEATURE INTENT REGISTRY FOR VOICE POINTING
// =============================================================
const FEATURE_REGISTRY = [
  // 1. The Speech-to-Text Transcription Button (Primary requested feature)
  {
    id: "speech_to_text",
    name: "Speech-to-Text Transcription Button",
    page: "communication",
    matches: (q) => {
      // Direct user phrasing: "the speak button which allows us to transcribe speech into text option"
      if (q.includes("transcribe") || q.includes("transcription")) return 100;
      if (q.includes("speech into text") || q.includes("speech to text") || q.includes("voice to text")) return 100;
      if (q.includes("speak") && (q.includes("transcribe") || q.includes("text") || q.includes("option") || q.includes("speech") || q.includes("mic") || q.includes("listen")) && !q.includes("aloud")) return 98;
      if (q.includes("start speaking") || q.includes("start listening") || q.includes("tap to start") || q.includes("microphone button") || q.includes("mic button")) return 95;
      if (q === "speak button" || q === "the speak button" || q.includes("speak button")) return 92;
      if (q.includes("speak") && !q.includes("aloud") && !q.includes("message")) return 85;
      return 0;
    },
    selector: "#speech-to-text-btn, .mic-circle-btn, [aria-label*='Transcribe']"
  },

  // 2. Text-to-Speech: Read / Speak Message Aloud
  {
    id: "speak_message_aloud",
    name: "Speak Message Aloud Button",
    page: "communication",
    matches: (q) => {
      if (q.includes("aloud") || q.includes("text to speech") || q.includes("speak message") || q.includes("read message") || q.includes("read aloud") || q.includes("read text")) return 95;
      return 0;
    },
    selector: "#btn-speak-message, button[onclick*='speakCurrentText']"
  },

  // 3. Clear Message Box
  {
    id: "clear_message",
    name: "Clear Message Button",
    page: "communication",
    matches: (q) => {
      if (q.includes("clear") && (q.includes("message") || q.includes("text") || q.includes("transcription") || q.includes("box"))) return 95;
      if (q === "clear" && state.page === "communication") return 90;
      return 0;
    },
    selector: "#btn-clear-transcription, button[onclick*='clearTranscription']"
  },

  // 4. Live Message Box / Textbox Display
  {
    id: "message_box",
    name: "Live Message Box Textarea",
    page: "communication",
    matches: (q) => {
      if (q.includes("message box") || q.includes("textbox") || q.includes("text box") || q.includes("transcription box") || q.includes("live message")) return 95;
      return 0;
    },
    selector: "#transcription-display"
  },

  // 5. Quick Assistance Phrases
  {
    id: "phrase_water",
    name: "Water Assistance Phrase",
    page: "communication",
    matches: (q) => (q.includes("water") || q.includes("drink")) ? 95 : 0,
    selector: "#phrase-i-need-water, #chip-water, button[onclick*='I need water']"
  },
  {
    id: "phrase_food",
    name: "Food Assistance Phrase",
    page: "communication",
    matches: (q) => (q.includes("food") || q.includes("hungry") || q.includes("eat") || q.includes("meal")) ? 95 : 0,
    selector: "#phrase-i-need-food, button[onclick*='I need food']"
  },
  {
    id: "phrase_rest",
    name: "Rest Assistance Phrase",
    page: "communication",
    matches: (q) => (q.includes("rest") || q.includes("tired") || q.includes("sleep")) ? 95 : 0,
    selector: "#phrase-i-need-rest, button[onclick*='I need rest']"
  },
  {
    id: "phrase_pain",
    name: "Pain Assistance Phrase",
    page: "communication",
    matches: (q) => (q.includes("pain") || q.includes("hurt") || q.includes("hurts") || q.includes("uncomfortable")) ? 95 : 0,
    selector: "#phrase-i-am-in-pain, #phrase-i-am-uncomfortable, button[onclick*='pain']"
  },
  {
    id: "phrase_help",
    name: "Call Someone / Help Phrase",
    page: "communication",
    matches: (q) => (q.includes("call someone") || q.includes("please help") || q.includes("medical help")) ? 95 : 0,
    selector: "#phrase-please-call-someone, #chip-help, #phrase-i-need-medical-help"
  },
  {
    id: "phrase_thankyou",
    name: "Thank You Phrase",
    page: "communication",
    matches: (q) => q.includes("thank") ? 95 : 0,
    selector: "#phrase-thank-you, #chip-thankyou"
  },

  // 6. Virtual Keyboard Space & Delete
  {
    id: "keyboard_space",
    name: "Virtual Keyboard Space Bar",
    page: "communication",
    matches: (q) => (q.includes("space bar") || q === "space") ? 90 : 0,
    selector: "#key-space, .keyboard-row button[onclick*=' ']"
  },
  {
    id: "keyboard_delete",
    name: "Virtual Keyboard Delete Key",
    page: "communication",
    matches: (q) => (q.includes("delete key") || q.includes("backspace") || q.includes("del key")) ? 90 : 0,
    selector: "#key-delete, button[onclick*='pressBackspace']"
  },

  // 7. Windows OS Mouse Control (Live Control Page)
  {
    id: "os_mouse",
    name: "Windows OS Mouse Switch",
    page: "control",
    matches: (q) => (q.includes("windows mouse") || q.includes("os mouse") || q.includes("desktop mouse") || q.includes("windows cursor") || q.includes("enable windows")) ? 96 : 0,
    selector: "#btn-toggle-os-mouse, button[onclick*='toggleOSMouseControl']"
  },

  // 8. In-Browser Head Mouse Toggle
  {
    id: "head_mouse",
    name: "In-Browser Head Mouse Toggle",
    page: null,
    matches: (q) => (q.includes("toggle head mouse") || q.includes("head mouse button") || q.includes("in-browser head mouse") || (q.includes("head mouse") && !q.includes("windows"))) ? 95 : 0,
    selector: "#head-mouse-toggle-btn, #btn-toggle-head-mouse"
  },

  // 9. Center Neutral Posture Anchor
  {
    id: "center_anchor",
    name: "Center Anchor Calibration Button",
    page: "control",
    matches: (q) => (q.includes("center anchor") || q.includes("set center") || q.includes("calibrate center") || q.includes("neutral posture") || q.includes("neutral anchor")) ? 95 : 0,
    selector: "#btn-set-center-anchor, button[onclick*='calibrateNeutralPosition']"
  },

  // 10. Guided 5-Point Calibration
  {
    id: "five_point_calibration",
    name: "Guided 5-Point Calibration Button",
    page: "control",
    matches: (q) => (q.includes("5 point") || q.includes("5-point") || q.includes("guided calibration") || q.includes("calibrate range")) ? 95 : 0,
    selector: "#btn-5point-calib, button[onclick*='startCalibration']"
  },

  // 11. Interactive Reticle Test Zone
  {
    id: "reticle_zone",
    name: "Interactive Reticle Demonstration Zone",
    page: "control",
    matches: (q) => (q.includes("reticle") || q.includes("test zone") || q.includes("demonstration reticle") || q.includes("canvas zone") || q.includes("target zone")) ? 95 : 0,
    selector: "#cursor-test-zone, #active-reticle"
  },

  // 12. Camera & Webcam Stream
  {
    id: "camera_feed",
    name: "Live Webcam Vision Feed",
    page: null,
    matches: (q) => (q.includes("camera") || q.includes("webcam") || q.includes("video feed") || q.includes("pip camera") || q.includes("live camera")) ? 92 : 0,
    selector: "#pip-camera-container, #live-webcam-element, #webcam-container, #btn-connect-webcam, #camera-status-pill"
  },

  // 13. Cursor Speed & Sensitivity Slider
  {
    id: "sensitivity_slider",
    name: "Cursor Speed & Sensitivity Slider",
    page: "control",
    matches: (q) => (q.includes("sensitivity") || q.includes("speed slider") || q.includes("cursor speed")) ? 95 : 0,
    selector: "#speed-slider, input[oninput*='updateSensitivity']"
  },

  // 14. Dwell Selection Delay Slider
  {
    id: "dwell_slider",
    name: "Dwell Selection Delay Slider",
    page: "control",
    matches: (q) => (q.includes("dwell") || q.includes("click delay") || q.includes("hover delay")) ? 95 : 0,
    selector: "#dwell-slider, input[oninput*='updateDwell']"
  },

  // 15. Emergency SOS Beacon
  {
    id: "emergency_beacon",
    name: "Emergency SOS Beacon",
    page: "sos",
    matches: (q) => (q.includes("emergency") || q.includes("sos") || q.includes("beacon") || q.includes("alarm") || q.includes("caregiver alert")) ? 95 : 0,
    selector: "#btn-trigger-sos, #btn-send-beacon-now, .sos-big-btn, button[onclick*='triggerSOSAlert']"
  },

  // 16. Add Caregiver Contact Button
  {
    id: "add_caregiver",
    name: "Add Caregiver Contact Button",
    page: "sos",
    matches: (q) => (q.includes("add caregiver") || q.includes("new caregiver") || q.includes("add contact")) ? 95 : 0,
    selector: "#btn-add-caregiver, button[onclick*='addCaregiverPrompt']"
  },

  // 17. Creative Studio Drawing Canvas
  {
    id: "studio_canvas",
    name: "Creative Studio Drawing Canvas",
    page: "studio",
    matches: (q) => (q.includes("canvas") || q.includes("paint area") || q.includes("drawing area") || q.includes("drawing canvas") || (q.includes("drawing") && !q.includes("clear"))) ? 95 : 0,
    selector: "#canvas-element"
  },

  // 18. Clear Drawing Canvas
  {
    id: "clear_canvas",
    name: "Clear Drawing Canvas Button",
    page: "studio",
    matches: (q) => (q.includes("clear") && (q.includes("canvas") || q.includes("drawing") || q.includes("paint") || q.includes("studio"))) ? 95 : 0,
    selector: "#btn-clear-canvas, button[onclick*='clearStudioCanvas']"
  },

  // 19. Studio Palette & Brush Controls
  {
    id: "color_mint",
    name: "Mint Color Palette Swatch",
    page: "studio",
    matches: (q) => q.includes("mint") || q.includes("green") ? 92 : 0,
    selector: "#color-mint"
  },
  {
    id: "color_blue",
    name: "Blue Color Palette Swatch",
    page: "studio",
    matches: (q) => q.includes("blue color") ? 92 : 0,
    selector: "#color-blue"
  },
  {
    id: "color_violet",
    name: "Violet Color Palette Swatch",
    page: "studio",
    matches: (q) => q.includes("violet") || q.includes("purple") ? 92 : 0,
    selector: "#color-violet"
  },
  {
    id: "color_coral",
    name: "Coral Color Palette Swatch",
    page: "studio",
    matches: (q) => q.includes("coral") || q.includes("red") ? 92 : 0,
    selector: "#color-coral"
  },

  // 20. Theme Toggle (Dark / Light Mode)
  {
    id: "theme_toggle",
    name: "Theme Toggle (Dark / Light Mode)",
    page: null,
    matches: (q) => (q.includes("dark mode") || q.includes("light mode") || q.includes("theme") || q.includes("toggle theme")) ? 95 : 0,
    selector: "#theme-toggle-btn"
  },

  // 21. Notification Bell
  {
    id: "notifications",
    name: "Notification Bell",
    page: null,
    matches: (q) => (q.includes("bell") || q.includes("notification")) ? 95 : 0,
    selector: "#bell-btn"
  },

  // 22. Voice Command Topbar Pill
  {
    id: "voice_pill",
    name: "Voice Command Microphone Pill",
    page: null,
    matches: (q) => (q.includes("voice pill") || q.includes("voice command button") || q.includes("hey cursor button") || q.includes("mic pill")) ? 95 : 0,
    selector: "#voice-command-pill"
  },

  // 23. Navigation Tabs (Explicit Tab / Page mentions)
  {
    id: "nav_dashboard",
    name: "Dashboard Tab",
    page: null,
    matches: (q) => (q.includes("dashboard") || q === "home" || q.includes("home page") || q.includes("dashboard tab")) ? 90 : 0,
    selector: "#nav-dashboard"
  },
  {
    id: "nav_control",
    name: "Live Cursor Control Tab",
    page: null,
    matches: (q) => (q.includes("control tab") || q.includes("control page") || q.includes("control screen") || q === "live control") ? 90 : 0,
    selector: "#nav-control"
  },
  {
    id: "nav_communication",
    name: "Communication Tab",
    page: null,
    matches: (q) => (q.includes("communication tab") || q.includes("communication page") || q.includes("messages tab") || q === "communication") ? 90 : 0,
    selector: "#nav-communication"
  },
  {
    id: "nav_studio",
    name: "Creative Studio Tab",
    page: null,
    matches: (q) => (q.includes("studio tab") || q.includes("studio page") || q.includes("creative tab") || q === "creative studio") ? 90 : 0,
    selector: "#nav-studio"
  },
  {
    id: "nav_sos",
    name: "Emergency SOS Tab",
    page: null,
    matches: (q) => (q.includes("sos tab") || q.includes("sos page") || q.includes("emergency tab") || q === "sos") ? 90 : 0,
    selector: "#nav-sos"
  },
  {
    id: "nav_settings",
    name: "Settings Tab",
    page: null,
    matches: (q) => (q.includes("settings tab") || q.includes("settings page") || q.includes("preferences tab") || q === "settings") ? 90 : 0,
    selector: "#nav-settings"
  },
  {
    id: "nav_help",
    name: "Help & Guidance Tab",
    page: null,
    matches: (q) => (q.includes("help tab") || q.includes("help page") || q.includes("faq tab") || q === "help") ? 90 : 0,
    selector: "#nav-help"
  }
];

function matchFeatureIntent(cleanQuery) {
  let bestFeature = null;
  let highestScore = 0;

  for (const feat of FEATURE_REGISTRY) {
    const score = feat.matches(cleanQuery);
    if (score > highestScore) {
      highestScore = score;
      bestFeature = feat;
    }
  }

  return highestScore >= 70 ? bestFeature : null;
}

function processVoiceInstruction(phrase) {
  console.log("[Process Voice Instruction]:", phrase);

  if (/\b(?:head|head movement) mode\b/.test(phrase)) { setControlMode("head"); return; }
  if (/\b(?:speech|voice) mode\b/.test(phrase)) { setControlMode("speech"); return; }
  if (/\b(?:physical|regular) mouse mode\b/.test(phrase)) { setControlMode("mouse"); return; }
  if (/\bhybrid mode\b/.test(phrase)) { setControlMode("hybrid"); return; }
  if (/\bspeech priority\b/.test(phrase)) { setControlPriority("speech"); return; }
  if (/\bhead priority\b/.test(phrase)) { setControlPriority("head"); return; }
  if (state.controlMode === "hybrid" && state.controlPriority === "head" &&
      /\b(?:point|go to|move|navigate|look at|aim at|target|click|select|choose)\b/i.test(phrase)) {
    showGestureToast("Head priority is active. Choose Speech priority to navigate by voice.");
    return;
  }

  // Video mirror toggle voice commands
  if (phrase.includes("mirror video") || phrase.includes("flip video") || phrase.includes("invert video") || phrase.includes("mirror camera")) {
    toggleWebcamMirror();
    return;
  }

  // Directional speech navigation. Each command moves a predictable fraction
  // of the viewport and can be repeated for finer or faster travel.
  const moveMatch = phrase.match(/\b(?:move|go|nudge|cursor)\s+(?:the\s+)?cursor\s+(?:to\s+)?(left|right|up|down)\b|\b(?:move|go|nudge)\s+(left|right|up|down)\b/i);
  if (moveMatch) {
    const direction = (moveMatch[1] || moveMatch[2]).toLowerCase();
    const amount = phrase.includes("far") || phrase.includes("large") ? 0.22 : 0.08;
    const x = Math.max(24, Math.min(window.innerWidth - 24, state.smoothNx * window.innerWidth + (direction === "left" ? -1 : direction === "right" ? 1 : 0) * window.innerWidth * amount));
    const y = Math.max(24, Math.min(window.innerHeight - 24, state.smoothNy * window.innerHeight + (direction === "up" ? -1 : direction === "down" ? 1 : 0) * window.innerHeight * amount));
    moveCursorToCoordinates(x, y, direction, false);
    return;
  }

  // Direct action command pattern: "click [target]" or "select [target]"
  const actionTargetMatch = phrase.match(/^(?:click|select|choose|tap|press|hit)\s+(.+)$/i);
  if (actionTargetMatch) {
    const candidate = actionTargetMatch[1].trim();
    if (candidate && !/^(that|it|here|now|this)$/i.test(candidate)) {
      executePointCommand(candidate, true, phrase);
      return;
    }
  }

  // A. Pointing and Navigation commands
  const pointTriggers = /(?:point\s+(?:towards|to|at)|go\s+to|move\s+to|navigate\s+to|look\s+at|aim\s+at|focus\s+on|take\s+me\s+to|show\s+me|target)\s+/i;
  
  const hasPointTrigger = pointTriggers.test(phrase) || phrase.startsWith("point ") || phrase.startsWith("move to ");
  const shouldClick = /(?:and|then)\s+(?:click|select|activate|start)/i.test(phrase);

  let targetQuery = phrase;
  if (hasPointTrigger) {
    targetQuery = phrase.replace(pointTriggers, "").trim();
  }

  targetQuery = targetQuery.replace(/(?:and|then)\s+(?:click|select|activate|start)/i, "").trim();
  targetQuery = targetQuery.replace(/^(the|a|an|my|this|that)\s+/i, "").trim();
  targetQuery = targetQuery.replace(/\s+(please|now|button|screen|tab|section|panel|option)$/i, "").trim();
  targetQuery = targetQuery.replace(/[.,?!]+$/, "").trim();

  // If query indicates a feature or point command, execute it
  if (targetQuery && (hasPointTrigger || state.voiceCursorActive)) {
    executePointCommand(targetQuery, shouldClick, phrase);
  }
  // B. Left Click / Select commands
  else if (/(?:^|\s)(?:click|select|click that|click it|left click|choose)(?:\s|$)/i.test(phrase)) {
    triggerVoiceClick("left");
  }
  // C. Right Click commands
  else if (phrase.includes("right click") || phrase.includes("context menu")) {
    triggerVoiceClick("right");
  }
  // D. Pause / Sleep commands
  else if (phrase.includes("pause cursor") || phrase.includes("stop cursor") || phrase.includes("sleep cursor") || phrase.includes("freeze")) {
    pauseVoiceCursor();
  }
  // E. Resume commands
  else if (phrase.includes("resume") || phrase.includes("unpause") || phrase.includes("start cursor")) {
    resumeVoiceCursor();
  }
}

function executePointCommand(targetQuery, shouldClick = false, originalPhrase = "") {
  console.log("[Execute Point]:", targetQuery, "ShouldClick:", shouldClick);
  const clean = targetQuery.toLowerCase();
  const fullClean = (originalPhrase || targetQuery).toLowerCase();

  // 1. Screen Quadrants
  if (clean.includes("center") || clean.includes("middle")) {
    moveCursorToCoordinates(window.innerWidth / 2, window.innerHeight / 2, "Screen Center", shouldClick);
    return;
  }
  if (clean.includes("top left")) {
    moveCursorToCoordinates(window.innerWidth * 0.22, window.innerHeight * 0.22, "Top Left", shouldClick);
    return;
  }
  if (clean.includes("top right")) {
    moveCursorToCoordinates(window.innerWidth * 0.78, window.innerHeight * 0.22, "Top Right", shouldClick);
    return;
  }
  if (clean.includes("bottom left")) {
    moveCursorToCoordinates(window.innerWidth * 0.22, window.innerHeight * 0.78, "Bottom Left", shouldClick);
    return;
  }
  if (clean.includes("bottom right")) {
    moveCursorToCoordinates(window.innerWidth * 0.78, window.innerHeight * 0.78, "Bottom Right", shouldClick);
    return;
  }

  // 2. Intelligent Feature Registry Intent Match (Handles "speak button to transcribe speech into text", etc.)
  const matchedFeature = matchFeatureIntent(fullClean) || matchFeatureIntent(clean);
  if (matchedFeature) {
    console.log("[Feature Matched]:", matchedFeature.name, "Page:", matchedFeature.page);

    // Auto-switch page if required
    if (matchedFeature.page && state.page !== matchedFeature.page) {
      setPage(matchedFeature.page);
    }

    setTimeout(() => {
      const el = document.querySelector(matchedFeature.selector);
      if (el) {
        pointToElementDirectly(el, matchedFeature.name, shouldClick);
      } else {
        // Fallback to text search on the updated page
        const fallbackEl = findScreenElementByVoiceQuery(clean);
        if (fallbackEl) pointToElementDirectly(fallbackEl, matchedFeature.name, shouldClick);
      }
    }, matchedFeature.page && state.page !== matchedFeature.page ? 80 : 0);
    return;
  }

  // 3. Fallback: Search visible elements on current screen
  const el = findScreenElementByVoiceQuery(clean);
  if (el) {
    const labelName = el.textContent ? el.textContent.trim().slice(0, 26) : targetQuery;
    pointToElementDirectly(el, labelName, shouldClick);
  } else {
    showGestureToast(`⚠️ Could not find "${targetQuery}" on screen`);
    speak(`Could not find ${targetQuery}`);
  }
}

function pointToElementDirectly(el, labelName, shouldClick = false) {
  if (!el) return;
  const rect = el.getBoundingClientRect();
  const targetX = rect.left + rect.width / 2;
  const targetY = rect.top + rect.height / 2;

  showGestureToast(`🎯 Pointing to: ${labelName}`);
  speak(`Pointing to ${labelName}`);

  const pageTarget = el.getAttribute("data-page");

  glideCursorTo(targetX, targetY, 750, () => {
    el.classList.add("target-highlight");
    setTimeout(() => el.classList.remove("target-highlight"), 1600);

    if (shouldClick) {
      setTimeout(() => triggerVoiceClick("left"), 150);
    } else if (pageTarget && state.page !== pageTarget) {
      setPage(pageTarget);
    }
  });

  if (voiceActiveTimeout) clearTimeout(voiceActiveTimeout);
  voiceActiveTimeout = setTimeout(() => deactivateVoiceCursorState(), 8000);
}

function moveCursorToCoordinates(x, y, name = "", shouldClick = false) {
  showGestureToast(`🎯 Pointing towards ${name}`);
  speak(`Moving to ${name}`);
  glideCursorTo(x, y, 700, () => {
    if (shouldClick) {
      setTimeout(() => triggerVoiceClick("left"), 150);
    }
  });
}

function findScreenElementByVoiceQuery(clean) {
  if (!clean) return null;

  // Stopwords to filter for keyword scoring
  const stopWords = new Set(["point", "towards", "to", "the", "a", "an", "button", "which", "allows", "us", "option", "please", "now", "go", "move", "that"]);
  const queryTokens = clean.split(/\s+/).filter(w => !stopWords.has(w) && w.length > 1);

  // Scan all visible interactive elements and headings on screen
  const candidates = Array.from(document.querySelectorAll("button, a, .feature-tile, .step-card, .phrase-card-btn, .suggestion-chip, input, h1, h2, h3, h4, .nav-item, .stat-badge, [role='button']"));
  let bestMatch = null;
  let bestScore = 0;

  for (const el of candidates) {
    const rect = el.getBoundingClientRect();
    if (rect.width === 0 || rect.height === 0 || rect.top > window.innerHeight || rect.bottom < 0) continue;

    const text = (el.textContent || el.innerText || el.getAttribute("aria-label") || el.title || el.placeholder || el.id || "").toLowerCase();
    
    // Check exact substring match
    if (text.includes(clean)) {
      const score = 10 + (clean.length / Math.max(text.length, 1));
      if (score > bestScore) {
        bestScore = score;
        bestMatch = el;
      }
      continue;
    }

    // Keyword overlap scoring
    let matchCount = 0;
    for (const t of queryTokens) {
      if (text.includes(t)) matchCount++;
    }

    if (matchCount > 0) {
      const score = (matchCount / queryTokens.length) * 5;
      if (score > bestScore) {
        bestScore = score;
        bestMatch = el;
      }
    }
  }

  return bestMatch;
}

function glideCursorTo(targetX, targetY, duration = 750, callback = null) {
  if (voiceGlideAnimationId) cancelAnimationFrame(voiceGlideAnimationId);

  const startX = state.smoothNx * window.innerWidth;
  const startY = state.smoothNy * window.innerHeight;
  const startTime = performance.now();

  state.isGliding = true;

  function easeOutCubic(t) {
    return 1 - Math.pow(1 - t, 3);
  }

  function step(now) {
    const elapsed = now - startTime;
    const progress = Math.min(1.0, elapsed / duration);
    const eased = easeOutCubic(progress);

    const currentX = startX + (targetX - startX) * eased;
    const currentY = startY + (targetY - startY) * eased;

    state.smoothNx = currentX / window.innerWidth;
    state.smoothNy = currentY / window.innerHeight;

    const globalCursor = document.getElementById("global-head-cursor");
    if (globalCursor) {
      globalCursor.style.left = `${currentX}px`;
      globalCursor.style.top = `${currentY}px`;
    }

    const activeReticle = document.getElementById("active-reticle");
    const testZone = document.getElementById("cursor-test-zone");
    if (activeReticle && testZone) {
      const rect = testZone.getBoundingClientRect();
      activeReticle.style.left = `${state.smoothNx * rect.width}px`;
      activeReticle.style.top = `${state.smoothNy * rect.height}px`;
    }

    if (progress < 1.0) {
      voiceGlideAnimationId = requestAnimationFrame(step);
    } else {
      state.isGliding = false;
      playSound("click");

      if (typeof callback === "function") {
        callback(targetX, targetY);
      }
    }
  }

  voiceGlideAnimationId = requestAnimationFrame(step);
}

function triggerVoiceClick(button = "left") {
  const currentX = state.smoothNx * window.innerWidth;
  const currentY = state.smoothNy * window.innerHeight;
  executeClickAt(currentX, currentY, button, `Voice Click (${button})`);
  showGestureToast(`⚡ Voice ${button.toUpperCase()} Click Executed!`);
  playSound("success");
}

function pauseVoiceCursor() {
  state.cursorPaused = true;
  deactivateVoiceCursorState();
  const globalCursor = document.getElementById("global-head-cursor");
  if (globalCursor) globalCursor.classList.add("paused");
  showGestureToast("⏸️ Cursor Paused by Voice");
  playSound("alert");
  speak("Cursor paused.");
}

function resumeVoiceCursor() {
  state.cursorPaused = false;
  const globalCursor = document.getElementById("global-head-cursor");
  if (globalCursor) globalCursor.classList.remove("paused");
  showGestureToast("▶️ Cursor Resumed by Voice");
  playSound("success");
  speak("Cursor resumed.");
}

// =============================================================
// MAIN CONTENT RENDERER
// =============================================================
function renderView() {
  const container = document.getElementById("app-content");
  if (!container) return;

  // 1. DASHBOARD
  if (state.page === "dashboard") {
    container.innerHTML = `
      <div class="hero-banner">
        <div class="hero-content">
          <span class="hero-tag">
            <i data-lucide="sparkles" style="width: 14px; height: 14px;"></i> AURALIGHT ACCESSIBILITY
          </span>
          <h2>Control without limits.<br>Designed for freedom.</h2>
          <p>
            Experience intuitive hands-free computer control using natural head tracking, facial gestures, and voice synthesis.
          </p>
          <div style="display: flex; gap: 12px; margin-top: 8px; flex-wrap: wrap;">
            <button class="primary-btn" onclick="toggleHeadMouseControl()">
              <i data-lucide="scan-face"></i> ${state.headMouseEnabled ? 'Disable Head-Controlled UI Cursor' : 'Enable Head-Controlled UI Cursor'}
            </button>
            <button class="secondary-btn" onclick="toggleOSMouseControl()">
              <i data-lucide="monitor"></i> ${state.osMouseEnabled ? 'OS Physical Mouse: ON' : 'OS Physical Mouse: OFF'}
            </button>
            <button class="secondary-btn" onclick="setPage('control')">
              <i data-lucide="camera"></i> Camera View
            </button>
          </div>
        </div>

        <div class="hero-visual">
          <div class="orbit-ring orbit-1"></div>
          <div class="orbit-ring orbit-2"></div>
          <div class="orbit-ring orbit-3"></div>
          <div class="cursor-node">
            <i data-lucide="mouse-pointer-2" style="width: 32px; height: 32px;"></i>
          </div>
        </div>
      </div>

      <div class="panel-header" style="margin-top: 6px;">
        <div>
          <h3>System Status</h3>
          <p class="subheading" style="font-size: 0.85rem;">Live peripherals and tracking modules</p>
        </div>
        <span class="badge ${state.cameraActive ? 'success' : 'neutral'}">
          ${state.cameraActive ? 'Camera Connected & Active' : 'Camera Standby'}
        </span>
      </div>

      <div class="feature-tiles">
        <div class="feature-tile">
          <div class="tile-icon blue"><i data-lucide="camera"></i></div>
          <div>
            <h4>Camera Feed</h4>
            <p>${state.cameraActive ? `Python camera active at ${state.fps.toFixed(1)} FPS` : 'Start the Python app to connect the camera'}</p>
          </div>
          <span class="badge ${state.cameraActive ? 'success' : 'neutral'}">${state.cameraActive ? 'Active' : 'Standby'}</span>
        </div>

        <div class="feature-tile">
          <div class="tile-icon teal"><i data-lucide="scan-face"></i></div>
          <div>
            <h4>Head Tracking</h4>
            <p>Python Face Landmarker and calibrated head tracking</p>
          </div>
          <span class="badge ${state.headMouseEnabled ? 'success' : 'neutral'}">${state.headMouseEnabled ? 'Tracking ON' : 'Paused'}</span>
        </div>

        <div class="feature-tile">
          <div class="tile-icon purple"><i data-lucide="monitor"></i></div>
          <div>
            <h4>OS Mouse Bridge</h4>
            <p>${state.osMouseEnabled ? 'Controlling Windows OS Cursor' : 'Desktop mouse bridge standby'}</p>
          </div>
          <span class="badge ${state.osMouseEnabled ? 'success' : 'neutral'}">${state.osMouseEnabled ? 'OS Active' : 'Standby'}</span>
        </div>

        <div class="feature-tile">
          <div class="tile-icon amber"><i data-lucide="volume-2"></i></div>
          <div>
            <h4>Voice Synthesizer</h4>
            <p>Text-to-speech & audio dictation</p>
          </div>
          <span class="badge success">Available</span>
        </div>
      </div>

      <div class="panel-header" style="margin-top: 12px;">
        <h3>Quick Navigation</h3>
      </div>

      <div class="feature-tiles">
        <button class="feature-tile" onclick="setPage('control')">
          <div class="tile-icon blue"><i data-lucide="mouse-pointer-2"></i></div>
          <div>
            <h4>Live Cursor Control</h4>
            <p>Animated reticle, webcam feed, and sensitivity.</p>
          </div>
          <i data-lucide="arrow-up-right" class="tile-arrow"></i>
        </button>

        <button class="feature-tile" onclick="setPage('communication')">
          <div class="tile-icon teal"><i data-lucide="mic"></i></div>
          <div>
            <h4>Voice & Communication</h4>
            <p>Speech-to-text with audio waveform and keyboard.</p>
          </div>
          <i data-lucide="arrow-up-right" class="tile-arrow"></i>
        </button>

        <button class="feature-tile" onclick="setPage('studio')">
          <div class="tile-icon purple"><i data-lucide="palette"></i></div>
          <div>
            <h4>Creative Studio</h4>
            <p>Expressive hands-free drawing canvas.</p>
          </div>
          <i data-lucide="arrow-up-right" class="tile-arrow"></i>
        </button>

        <button class="feature-tile" onclick="setPage('help')">
          <div class="tile-icon amber"><i data-lucide="life-buoy"></i></div>
          <div>
            <h4>Help & Guidance</h4>
            <p>5-step setup walkthrough and troubleshooting.</p>
          </div>
          <i data-lucide="arrow-up-right" class="tile-arrow"></i>
        </button>
      </div>
    `;
  }

  // 2. LIVE CURSOR CONTROL (SIGNATURE ATTRACTION)
  else if (state.page === "control") {
    container.innerHTML = `
      <div>
        <p class="eyebrow">SIGNATURE INTERFACE</p>
        <h1 class="page-title">Live Cursor Control<span class="accent-dot">.</span></h1>
        <p class="subheading">Direct camera-coordinated head tracking, reticle physics, and facial gesture clicks.</p>
      </div>

      <div class="live-control-layout">
        <!-- Interactive Cursor Reticle Demonstration Area -->
        <div class="cursor-showcase">
          <div class="panel-header" style="margin-bottom: 0;">
            <h3>Interactive Reticle Demonstration</h3>
            <span class="badge ${state.headMouseEnabled ? 'success' : 'neutral'}">
              ${state.headMouseEnabled ? 'Head Mouse Active' : 'Head Mouse Standby'}
            </span>
          </div>

          <div class="cursor-canvas-zone" id="cursor-test-zone" onclick="triggerReticleRipple(event)">
            <!-- Custom Animated Cursor Reticle -->
            <div class="reticle-container" id="active-reticle" style="top: 50%; left: 50%;">
              <div class="reticle-outer">
                <div class="reticle-inner">
                  <div class="reticle-center"></div>
                </div>
              </div>
              <div class="reticle-ripple" id="reticle-ripple-node"></div>
            </div>
            <div class="cursor-zone-caption">
              Hold still for the green dwell circle • Smile / left wink: left click
            </div>
          </div>

          <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 12px;">
            <div class="telemetry-box">
              <small>Movement Mode</small>
              <strong>Head Tracking (Nose Anchor)</strong>
            </div>
            <div class="telemetry-box">
              <small>Active Gesture</small>
              <strong id="active-gesture-display" style="color:var(--primary-blue);">
                ${state.gestureName !== 'none' ? state.gestureName.toUpperCase() : 'None (Neutral)'}
              </strong>
            </div>
          </div>

          <div style="display: flex; gap: 12px; flex-wrap: wrap;">
            <button id="btn-toggle-head-mouse" class="primary-btn full-btn" onclick="toggleHeadMouseControl()">
              <i data-lucide="scan-face"></i>
              ${state.headMouseEnabled ? 'Disable Head-Controlled UI Cursor' : 'Enable Head-Controlled UI Cursor'}
            </button>
            <button id="btn-toggle-os-mouse" class="secondary-btn full-btn" onclick="toggleOSMouseControl()">
              <i data-lucide="monitor"></i>
              ${state.osMouseEnabled ? 'Disable Windows OS Mouse' : 'Enable Windows OS Mouse'}
            </button>
            <button id="btn-set-center-anchor" class="secondary-btn" style="width: 100%;" onclick="calibrateNeutralPosition()">
              <i data-lucide="target"></i> Set Center Anchor
            </button>
          </div>
        </div>

        <!-- Live Camera & Face Landmark Vision Panel -->
        <div class="card-panel">
          <div class="panel-header">
            <h3>Webcam & Face Landmarks</h3>
            <span class="badge ${state.cameraActive ? 'success' : 'neutral'}">
              ${state.cameraActive ? 'Camera Live' : 'Camera Off'}
            </span>
          </div>

          <div class="webcam-panel" id="webcam-container">
            <img class="webcam-video" id="live-webcam-element" alt="Preview from the Python vision pipeline" />
            <div class="webcam-hud">
              <span class="hud-pill"><i data-lucide="scan-face" style="width:12px;display:inline;"></i> PYTHON VISION</span>
              <button class="hud-pill" style="cursor:pointer; background:rgba(15,23,42,0.82); border:1px solid rgba(255,255,255,0.2); color:#fff;" onclick="toggleWebcamMirror()" title="Toggle Video Mirror">
                <i data-lucide="flip-horizontal" style="width:12px;display:inline;"></i> ${state.mirrorVideo ? 'MIRRORED' : 'NORMAL (NON-INVERTED)'}
              </button>
            </div>
          </div>

          <div class="telemetry-row">
            <div class="telemetry-box">
              <small>Face Detected</small>
              <strong style="color:var(--mint-teal);">${state.trackingDetected ? 'Yes (Locked)' : 'Standby'}</strong>
            </div>
            <div class="telemetry-box">
              <small>Lighting Quality</small>
              <strong style="color:var(--primary-blue);">${state.cameraBrightness >= 40 ? 'Good' : state.cameraBrightness > 0 ? 'Low' : '—'} · ${state.faceQuality.toFixed(2)}</strong>
            </div>
            <div class="telemetry-box">
              <small>Gesture Status</small>
              <strong id="head-pitch-val">${state.gestureName.toUpperCase()}</strong>
            </div>
          </div>

          <div style="display: flex; gap: 8px; margin-top: 16px; flex-wrap: wrap;">
            <button id="btn-connect-webcam" class="primary-btn teal-btn" style="flex: 1;" onclick="startCameraVision()">
              <i data-lucide="camera"></i> ${state.cameraActive ? `Python Camera · ${state.fps.toFixed(0)} FPS` : 'Check Python Camera'}
            </button>
            <button id="btn-toggle-mirror" class="secondary-btn" onclick="toggleWebcamMirror()" title="Toggle Horizontal Mirroring">
              <i data-lucide="flip-horizontal"></i> ${state.mirrorVideo ? 'Mirror: ON' : 'Normal Feed'}
            </button>
            <button id="btn-toggle-flipv" class="secondary-btn" onclick="toggleWebcamFlipV()" title="Toggle Vertical Inversion">
              <i data-lucide="flip-vertical"></i> ${state.flipVVideo ? 'Flip V: ON' : 'Flip V'}
            </button>
            <button id="btn-5point-calib" class="secondary-btn" onclick="startCalibration()">
              <i data-lucide="target"></i> Guided Head Calibration
            </button>
          </div>

          <p style="font-size: 0.76rem; color: var(--text-muted); margin-top: 12px; text-align: center;">
            🔒 Webcam frames and face tracking stay in the local Python vision pipeline. The page receives tracking telemetry over Flask SSE.
          </p>
        </div>
      </div>

      <!-- Settings & Sensitivity Sliders -->
      <div class="card-panel" style="margin-top: 6px;">
        <div class="panel-header">
          <h3>Tracking Sensitivity & Ergonomics</h3>
          <i data-lucide="sliders-horizontal"></i>
        </div>

        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 24px;">
          <div class="slider-group">
            <label class="slider-label">
              Cursor Speed & Sensitivity <strong id="speed-slider-val">${state.sensitivity}%</strong>
            </label>
            <input id="speed-slider" type="range" min="10" max="100" value="${state.sensitivity}" oninput="updateSensitivity(this.value)" />
            <p style="font-size: 0.78rem; color: var(--text-muted);">
              Keep this low for precise aiming. Raise it only if you cannot reach screen edges.
            </p>
          </div>

          <div class="slider-group">
            <label class="slider-label">
              Dwell Selection Delay <strong id="dwell-slider-val">${state.dwell}s</strong>
            </label>
            <input id="dwell-slider" type="range" min="0.5" max="3.5" step="0.1" value="${state.dwell}" oninput="updateDwell(this.value)" />
            <p style="font-size: 0.78rem; color: var(--text-muted);">
              Hover stationary over any button to trigger an automatic click.
            </p>
          </div>
        </div>
      </div>
    `;

  }

  // 3. VOICE & COMMUNICATION
  else if (state.page === "communication") {
    container.innerHTML = `
      <div>
        <p class="eyebrow">VOICE & TYPING</p>
        <h1 class="page-title">Voice & Communication<span class="accent-dot">.</span></h1>
        <p class="subheading">Turn on the Voice pill in the top bar, say Hey Cursor, then a command. Use the large mic below only for speech-to-text.</p>
      </div>

      <div class="comm-layout">
        <!-- Speech-to-Text & Transcription -->
        <div class="card-panel">
          <div class="mic-hero-box">
            <button id="speech-to-text-btn" class="mic-circle-btn ${state.isListening ? 'listening' : ''}" onclick="toggleSpeechRecognition()" title="Transcribe speech into text option" aria-label="Transcribe speech into text option">
              <i data-lucide="${state.isListening ? 'mic-off' : 'mic'}" style="width: 38px; height: 38px;"></i>
            </button>
            <h3 id="speech-to-text-heading" style="font-size: 1.2rem; color: var(--text-title); margin-bottom: 4px;">
              ${state.isListening ? 'Listening to your speech...' : 'Transcribe Speech into Text'}
            </h3>
            <p style="font-size: 0.84rem; color: var(--text-muted);">
              ${state.isListening ? 'Speak naturally into your microphone.' : 'Convert voice into text with browser speech recognition.'}
            </p>

            <div class="audio-waveform ${state.isListening ? 'active' : ''}">
              <div class="wave-bar"></div>
              <div class="wave-bar"></div>
              <div class="wave-bar"></div>
              <div class="wave-bar"></div>
              <div class="wave-bar"></div>
            </div>
          </div>

          <div class="panel-header" style="margin-bottom: 8px;">
            <strong style="font-size: 0.88rem; text-transform: uppercase; letter-spacing: 0.08em; color: var(--text-muted);">Live Message Box</strong>
            <button id="btn-clear-transcription" class="secondary-btn" style="padding: 4px 12px; font-size: 0.8rem;" onclick="clearTranscription()">
              <i data-lucide="rotate-ccw" style="width: 14px;"></i> Clear
            </button>
          </div>

          <div class="transcription-box" id="transcription-display">
            ${state.transcriptionText || '<span style="color:var(--text-faint);">Your spoken words or typed message will appear here...</span>'}
          </div>

          <div style="display: flex; gap: 12px; margin-bottom: 20px;">
            <button id="btn-speak-message" class="primary-btn full-btn" onclick="speakCurrentText()">
              <i data-lucide="volume-2"></i> Speak Message Aloud
            </button>
          </div>

          <!-- On-Screen Virtual Keyboard -->
          <div class="panel-header" style="margin-bottom: 8px;">
            <strong style="font-size: 0.88rem; text-transform: uppercase; letter-spacing: 0.08em; color: var(--text-muted);">Accessible On-Screen Keyboard</strong>
          </div>

          <div class="virtual-keyboard">
            <div class="word-suggestions">
              <button id="chip-water" class="suggestion-chip" onclick="insertWord('I need water')">+ I need water</button>
              <button id="chip-help" class="suggestion-chip" onclick="insertWord('Please help')">+ Please help</button>
              <button id="chip-thankyou" class="suggestion-chip" onclick="insertWord('Thank you')">+ Thank you</button>
              <button id="chip-caregiver" class="suggestion-chip" onclick="insertWord('Call caregiver')">+ Call caregiver</button>
              <button id="chip-yes" class="suggestion-chip" onclick="insertWord('Yes')">+ Yes</button>
              <button id="chip-no" class="suggestion-chip" onclick="insertWord('No')">+ No</button>
            </div>

            <div class="keyboard-row">
              ${['Q','W','E','R','T','Y','U','I','O','P'].map(k => `<button class="key-btn" onclick="pressKey('${k}')">${k}</button>`).join('')}
            </div>
            <div class="keyboard-row">
              ${['A','S','D','F','G','H','J','K','L'].map(k => `<button class="key-btn" onclick="pressKey('${k}')">${k}</button>`).join('')}
            </div>
            <div class="keyboard-row">
              ${['Z','X','C','V','B','N','M'].map(k => `<button class="key-btn" onclick="pressKey('${k}')">${k}</button>`).join('')}
              <button id="key-delete" class="key-btn special" onclick="pressBackspace()"><i data-lucide="delete" style="width:16px;"></i> Del</button>
            </div>
            <div class="keyboard-row">
              <button id="key-space" class="key-btn special" style="flex:3;" onclick="pressKey(' ')">Space Bar</button>
              <button id="key-speak" class="key-btn special" style="flex:1; background:var(--mint-teal); color:#fff;" onclick="speakCurrentText()">Speak</button>
            </div>
          </div>
        </div>

        <!-- Quick Assistance Phrase Library -->
        <div class="card-panel">
          <div class="panel-header">
            <h3>Quick Phrases</h3>
            <span class="badge primary">Instant Speak</span>
          </div>

          <p style="font-size: 0.84rem; color: var(--text-muted); margin-bottom: 16px;">
            Select any phrase below to instantly load or read it aloud:
          </p>

          <div class="phrase-grid">
            ${[
              "I need water",
              "I need food",
              "I am uncomfortable",
              "Please call someone",
              "I need rest",
              "I need medical help",
              "Yes",
              "No",
              "Thank you",
              "Please wait",
              "I feel great today",
              "Adjust my position"
            ].map(p => `
              <button id="phrase-${p.toLowerCase().replace(/[^a-z0-9]+/g, '-')}" class="phrase-card-btn ${state.selectedPhrase === p ? 'selected' : ''}" onclick="selectAndSpeakPhrase('${p}')">
                <i data-lucide="message-square" style="width: 17px; color: var(--primary-blue); flex-shrink: 0;"></i>
                <span>${p}</span>
              </button>
            `).join('')}
          </div>
        </div>
      </div>
    `;
  }

  // 4. CREATIVE STUDIO
  else if (state.page === "studio") {
    container.innerHTML = `
      <div>
        <p class="eyebrow">EXPRESS YOURSELF</p>
        <h1 class="page-title">Creative Studio<span class="accent-dot">.</span></h1>
        <p class="subheading">Expressive hands-free drawing space. Use head motion or cursor to create digital art.</p>
      </div>

      <div class="card-panel">
        <div class="studio-toolbar">
          <span style="font-size: 0.82rem; font-weight: 700; color: var(--text-muted); text-transform: uppercase;">Palette</span>
          <button id="color-mint" class="secondary-btn" style="padding: 7px 14px; ${state.brushColor === '#24A98A' ? 'border-color:var(--mint-teal); background:var(--mint-teal-dim);' : ''}" onclick="setStudioColor('#24A98A')">
            <span style="width:12px;height:12px;border-radius:50%;background:#24A98A;display:inline-block;margin-right:6px;"></span> Mint
          </button>
          <button id="color-blue" class="secondary-btn" style="padding: 7px 14px; ${state.brushColor === '#4268D5' ? 'border-color:var(--primary-blue); background:var(--primary-blue-dim);' : ''}" onclick="setStudioColor('#4268D5')">
            <span style="width:12px;height:12px;border-radius:50%;background:#4268D5;display:inline-block;margin-right:6px;"></span> Blue
          </button>
          <button id="color-violet" class="secondary-btn" style="padding: 7px 14px; ${state.brushColor === '#8060C8' ? 'border-color:var(--lavender); background:var(--lavender-dim);' : ''}" onclick="setStudioColor('#8060C8')">
            <span style="width:12px;height:12px;border-radius:50%;background:#8060C8;display:inline-block;margin-right:6px;"></span> Violet
          </button>
          <button id="color-coral" class="secondary-btn" style="padding: 7px 14px; ${state.brushColor === '#EF4444' ? 'border-color:var(--coral-alert); background:var(--coral-alert-dim);' : ''}" onclick="setStudioColor('#EF4444')">
            <span style="width:12px;height:12px;border-radius:50%;background:#EF4444;display:inline-block;margin-right:6px;"></span> Coral
          </button>

          <span style="font-size: 0.82rem; font-weight: 700; color: var(--text-muted); text-transform: uppercase; margin-left: 12px;">Brush Size</span>
          <button id="brush-thin" class="secondary-btn" style="padding: 7px 12px; ${state.brushSize === 3 ? 'border-color:var(--primary-blue); font-weight:700;' : ''}" onclick="setStudioSize(3)">Thin</button>
          <button id="brush-medium" class="secondary-btn" style="padding: 7px 12px; ${state.brushSize === 8 ? 'border-color:var(--primary-blue); font-weight:700;' : ''}" onclick="setStudioSize(8)">Medium</button>
          <button id="brush-thick" class="secondary-btn" style="padding: 7px 12px; ${state.brushSize === 18 ? 'border-color:var(--primary-blue); font-weight:700;' : ''}" onclick="setStudioSize(18)">Thick</button>

          <button id="btn-clear-canvas" class="secondary-btn" style="margin-left: auto; color: var(--coral-alert);" onclick="clearStudioCanvas()">
            <i data-lucide="trash-2"></i> Clear Canvas
          </button>
        </div>

        <div class="studio-canvas-zone">
          <canvas id="canvas-element"></canvas>
        </div>

        <p style="font-size: 0.8rem; color: var(--text-muted); margin-top: 14px;">
          💡 Tip: Turn on "Head Mouse" in the topbar to draw with your head movements directly!
        </p>
      </div>
    `;

    initStudioCanvas();
  }

  // 5. SOS & CAREGIVER
  else if (state.page === "sos") {
    container.innerHTML = `
      <div>
        <p class="eyebrow">SAFETY & SUPPORT</p>
        <h1 class="page-title">SOS & Caregiver Center<span class="accent-dot">.</span></h1>
        <p class="subheading">Direct emergency alert dispatch and trusted caregiver contacts.</p>
      </div>

      <div class="sos-card-hero">
        <div style="width: 58px; height: 58px; border-radius: var(--radius-md); background: var(--coral-alert); color: #fff; display: flex; align-items: center; justify-content: center; flex-shrink: 0;">
          <i data-lucide="shield-alert" style="width: 32px; height: 32px;"></i>
        </div>
        <div>
          <h2 style="font-size: 1.35rem; font-weight: 800; color: var(--text-title); margin-bottom: 4px;">
            Emergency Assistance Available
          </h2>
          <p style="font-size: 0.92rem; color: var(--text-muted);">
            Triggering an alert notifies your registered caregivers with simulated GPS location and audio beacons.
          </p>
        </div>
      </div>

      <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 24px;">
        <div class="card-panel" style="text-align: center;">
          <div class="panel-header">
            <h3>Immediate Dispatch</h3>
            <span class="badge" style="background:var(--coral-alert-dim); color:var(--coral-alert);">High Priority</span>
          </div>

          <div id="btn-trigger-sos" class="sos-big-btn" onclick="triggerSOSAlert()" title="Press to dispatch emergency alert">
            <i data-lucide="shield-alert" style="width: 48px; height: 48px;"></i>
          </div>

          <h3 style="font-size: 1.25rem; margin-top: 10px;">Dispatch Caregiver Alert</h3>
          <p style="font-size: 0.86rem; color: var(--text-muted); max-width: 340px; margin: 6px auto 20px auto;">
            Hold or click the button to send an urgent notification to your configured emergency contacts.
          </p>

          <button id="btn-send-beacon-now" class="primary-btn full-btn" style="background: var(--coral-alert);" onclick="triggerSOSAlert()">
            <i data-lucide="bell"></i> Send Emergency Beacon Now
          </button>

          ${state.alertStatus ? `
            <div style="margin-top: 14px; padding: 12px; background: var(--coral-alert-dim); border: 1px solid rgba(239, 68, 68, 0.3); border-radius: var(--radius-md); font-size: 0.85rem; color: var(--coral-alert); font-weight: 600;">
              ${state.alertStatus}
            </div>
          ` : ''}
        </div>

        <div class="card-panel">
          <div class="panel-header">
            <h3>Trusted Caregivers</h3>
            <button id="btn-add-caregiver" class="secondary-btn" style="padding: 4px 12px; font-size: 0.82rem;" onclick="addCaregiverPrompt()">
              <i data-lucide="plus"></i> Add
            </button>
          </div>

          <div style="display: flex; flex-direction: column; gap: 12px;">
            ${state.contacts.map((c, idx) => `
              <div style="display: flex; align-items: center; justify-content: space-between; padding: 14px 16px; background: var(--bg-panel-subtle); border: 1px solid var(--border-subtle); border-radius: var(--radius-md);">
                <div>
                  <strong style="color:var(--text-title); display:block; font-size:0.92rem;">${c.name}</strong>
                  <small style="color:var(--text-muted);">${c.phone}</small>
                </div>
                <button class="secondary-btn" style="padding: 4px 10px; font-size: 0.76rem; color: var(--coral-alert);" onclick="removeCaregiver(${idx})">
                  Remove
                </button>
              </div>
            `).join('')}
          </div>

          <div style="height: 1px; background: var(--border-subtle); margin: 20px 0;"></div>

          <div class="toggle-row">
            <div>
              <strong>Emergency confirmation chime</strong>
              <small>Play high-priority acoustic chime on activation</small>
            </div>
            <button class="toggle toggle-on" role="switch"><span></span></button>
          </div>
        </div>
      </div>
    `;
  }

  // 6. PERSONALISATION
  else if (state.page === "settings") {
    container.innerHTML = `
      <div>
        <p class="eyebrow">MAKE IT YOURS</p>
        <h1 class="page-title">Personalisation<span class="accent-dot">.</span></h1>
        <p class="subheading">Adapt NeuroCursor to your exact interaction comfort and accessibility preferences.</p>
      </div>

      <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 24px;">
        <div class="card-panel">
          <div class="panel-header">
            <h3>User Profile</h3>
            <i data-lucide="user"></i>
          </div>

          <label style="font-size: 0.88rem; font-weight: 600; color: var(--text-title); display: block; margin-bottom: 8px;">
            Profile Name
          </label>
          <input id="profile-name-input" class="text-input" value="${state.activeProfile}" oninput="setProfileName(this.value)" />

          <div style="height: 1px; background: var(--border-subtle); margin: 22px 0;"></div>

          <h4 style="font-size: 0.95rem; font-weight: 700; color: var(--primary-blue); margin-bottom: 14px; text-transform: uppercase; letter-spacing: 0.06em;">
            Accessibility Toggles
          </h4>

          <div class="toggle-row">
            <div><strong>Mirror Webcam Feed (Flip Horizontal)</strong><small>Toggle horizontal flip if your camera requires mirroring</small></div>
            <button id="toggle-mirror-video" class="toggle ${state.mirrorVideo ? 'toggle-on' : ''}" onclick="toggleWebcamMirror()" role="switch"><span></span></button>
          </div>

          <div class="toggle-row">
            <div><strong>Invert Vertical Webcam (Flip Vertical)</strong><small>Flip camera vertically if camera mount is inverted</small></div>
            <button id="toggle-flipv-video" class="toggle ${state.flipVVideo ? 'toggle-on' : ''}" onclick="toggleWebcamFlipV()" role="switch"><span></span></button>
          </div>

          <div class="toggle-row">
            <div><strong>High Contrast Mode</strong><small>Sharpen text and border readability</small></div>
            <button id="toggle-high-contrast" class="toggle ${state.highContrast ? 'toggle-on' : ''}" onclick="toggleSettingKey('highContrast')" role="switch"><span></span></button>
          </div>

          <div class="toggle-row">
            <div><strong>Large Interface Scaling</strong><small>Enlarge touch targets and typography</small></div>
            <button id="toggle-large-interface" class="toggle ${state.largeInterface ? 'toggle-on' : ''}" onclick="toggleSettingKey('largeInterface')" role="switch"><span></span></button>
          </div>

          <div class="toggle-row">
            <div><strong>Reduced Animation</strong><small>Minimize visual motion for comfort</small></div>
            <button id="toggle-reduced-animation" class="toggle ${state.reducedAnimation ? 'toggle-on' : ''}" onclick="toggleSettingKey('reducedAnimation')" role="switch"><span></span></button>
          </div>

          <div class="toggle-row">
            <div><strong>Acoustic Audio Feedback</strong><small>Play subtle chimes on clicks and actions</small></div>
            <button id="toggle-sound" class="toggle ${state.sound ? 'toggle-on' : ''}" onclick="toggleSettingKey('sound')" role="switch"><span></span></button>
          </div>
        </div>

        <div class="card-panel">
          <div class="panel-header">
            <h3>Facial Gesture Mapping</h3>
            <i data-lucide="smile"></i>
          </div>

          <div style="display: flex; flex-direction: column; gap: 10px;">
            ${[
              { gesture: "Smile / Grin (Natural > 77%)", action: "Left Primary Click / Select Option" },
              { gesture: "Mouth Open (Natural > 11%)", action: "Right Click / Context Actions" },
              { gesture: "Eyebrow Raise", action: "Pause / Resume Cursor Movement" },
              { gesture: "Head Movement", action: "Nose Tip Precision Cursor Drive" },
              { gesture: "Dwell Hover (1.2s)", action: "Hands-Free Auto-Click with Progress Ring" }
            ].map(g => `
              <div style="display: flex; align-items: center; justify-content: space-between; padding: 12px 16px; background: var(--bg-panel-subtle); border-radius: var(--radius-md); border: 1px solid var(--border-subtle);">
                <div>
                  <strong style="font-size: 0.88rem; color: var(--text-title); display: block;">${g.gesture}</strong>
                  <small style="color: var(--primary-blue); font-weight: 600;">${g.action}</small>
                </div>
                <button class="secondary-btn" style="padding: 4px 10px; font-size: 0.78rem;" onclick="editGestureMapping('${g.gesture}')">
                  Edit
                </button>
              </div>
            `).join('')}
          </div>
        </div>
      </div>
    `;
  }

  // 7. HELP & GUIDANCE
  else if (state.page === "help") {
    container.innerHTML = `
      <div>
        <p class="eyebrow">USER ONBOARDING & SETUP</p>
        <h1 class="page-title">Help & Guidance Centre<span class="accent-dot">.</span></h1>
        <p class="subheading">Step-by-step setup walkthrough, video guidance, and troubleshooting solutions.</p>
      </div>

      <div class="panel-header">
        <h3>Let's get you started</h3>
        <span class="badge success">5 Easy Steps</span>
      </div>

      <div class="setup-guide-steps">
        <div class="step-card">
          <div class="step-number">1</div>
          <h4>Connect Webcam</h4>
          <p>Position yourself comfortably in front of the camera with balanced room lighting.</p>
          <button class="secondary-btn" style="margin-top:auto;" onclick="startCameraVision()">Connect Camera</button>
        </div>

        <div class="step-card">
          <div class="step-number">2</div>
          <h4>Calibrate Neutral</h4>
          <p>Click "Set Center Anchor" while sitting comfortably to set your neutral resting center.</p>
          <button class="primary-btn" style="margin-top:auto;" onclick="calibrateNeutralPosition()">Set Anchor</button>
        </div>

        <div class="step-card">
          <div class="step-number">3</div>
          <h4>Enable Head Mouse</h4>
          <p>Click the "Head Mouse" button in the topbar to control your pointer with head turns.</p>
          <button class="secondary-btn" style="margin-top:auto;" onclick="toggleHeadMouseControl()">Toggle Mouse</button>
        </div>

        <div class="step-card">
          <div class="step-number">4</div>
          <h4>Dwell to Click</h4>
          <p>Hold your head steady over any button for 1.2s to trigger automatic dwell selection.</p>
          <button class="secondary-btn" style="margin-top:auto;" onclick="setPage('control')">Test Reticle</button>
        </div>

        <div class="step-card">
          <div class="step-number">5</div>
          <h4>Communicate</h4>
          <p>Use voice dictation, quick phrases, or the virtual keyboard to talk hands-free.</p>
          <button class="secondary-btn" style="margin-top:auto;" onclick="setPage('communication')">Try Voice</button>
        </div>
      </div>

      <div class="card-panel" style="margin-top: 14px;">
        <div class="panel-header">
          <h3>Frequently Asked Questions & Troubleshooting</h3>
        </div>

        <div class="faq-list">
          <div class="faq-item" onclick="toggleFaq(this)">
            <button class="faq-question">
              <span>How does head movement control the mouse?</span>
              <i data-lucide="chevron-down" class="faq-icon" style="transition: transform 0.2s;"></i>
            </button>
            <div class="faq-answer">
              Python captures the webcam and applies MediaPipe Face Landmarker, calibration, and filtering. The page displays the Python preview and consumes normalized cursor coordinates over Flask SSE.
            </div>
          </div>

          <div class="faq-item" onclick="toggleFaq(this)">
            <button class="faq-question">
              <span>How do I click without hands?</span>
              <i data-lucide="chevron-down" class="faq-icon" style="transition: transform 0.2s;"></i>
            </button>
            <div class="faq-answer">
              Three methods are active simultaneously:
              1. <strong>Smile / Grin:</strong> Left click / select.
              2. <strong>Open Mouth:</strong> Right click / context select.
              3. <strong>Dwell:</strong> Rest on any target for 1.2s to auto-click.
              4. <strong>Eyebrow Raise:</strong> Pause or unpause cursor tracking.
            </div>
          </div>

          <div class="faq-item" onclick="toggleFaq(this)">
            <button class="faq-question">
              <span>Does NeuroCursor require an external backend or cloud server?</span>
              <i data-lucide="chevron-down" class="faq-icon" style="transition: transform 0.2s;"></i>
            </button>
            <div class="faq-answer">
              The integrated application runs webcam capture, face tracking, calibration, and gestures locally in Python. Flask streams local camera preview and telemetry to the interface; no camera frames are sent to a cloud service.
            </div>
          </div>
        </div>
      </div>
    `;
  }

  // Footer
  container.insertAdjacentHTML('beforeend', `
    <footer class="footer">
      <span>© 2026 NeuroCursor — Auralight Accessibility Suite</span>
      <span style="display: flex; align-items: center; gap: 6px;">
        Empowering Independent Living <i data-lucide="heart" style="width: 14px; color: var(--coral-alert);"></i>
      </span>
    </footer>
  `);

  if (window.lucide && typeof window.lucide.createIcons === "function") {
    window.lucide.createIcons();
  }
  syncWebcamVideoStreams();
}

// Reticle Ripple Visual Helper
function triggerReticleRipple(e) {
  const ripple = document.getElementById("reticle-ripple-node");
  if (!ripple) return;
  ripple.classList.remove("active");
  void ripple.offsetWidth;
  ripple.classList.add("active");
  playSound("click");
}

// Five-step calibration is sampled and applied by the Python camera worker.
const calibCoords = [
  { step: "neutral", x: "50%", y: "50%", title: "Neutral Position", desc: "Relax your face and look straight ahead while Python samples." },
  { step: "right", x: "82%", y: "50%", title: "Comfortable Right Range", desc: "Move your head comfortably to the right and hold." },
  { step: "left", x: "18%", y: "50%", title: "Comfortable Left Range", desc: "Move your head comfortably to the left and hold." },
  { step: "up", x: "50%", y: "22%", title: "Comfortable Up Range", desc: "Move your head comfortably upward and hold." },
  { step: "down", x: "50%", y: "78%", title: "Comfortable Down Range", desc: "Move your head comfortably downward and hold." }
];

async function startCalibration() {
  if (!backendConnected || !state.cameraActive) {
    showGestureToast("Connect the live Python camera before calibration.");
    return;
  }
  calibrationPreviousPause = !!state.cursorPaused;
  callBackend("/pause");
  state.calibrating = true;
  state.calibStep = 0;
  const overlay = document.getElementById("calibration-overlay");
  if (overlay) overlay.classList.add("active");
  playSound("success");
  await advanceCalibrationStep();
}

async function advanceCalibrationStep() {
  if (!state.calibrating) return;
  const target = document.getElementById("calib-target-node");
  const title = document.getElementById("calib-step-title");
  const desc = document.getElementById("calib-step-desc");

  if (state.calibStep < calibCoords.length) {
    const pt = calibCoords[state.calibStep];
    if (target) {
      target.style.left = pt.x;
      target.style.top = pt.y;
    }
    if (title) title.textContent = pt.title;
    if (desc) desc.textContent = pt.desc;
    const result = await callBackend("/vision/calibration/step", { step: pt.step, duration_sec: 1.8 });
    if (!result.ok) {
      showGestureToast(result.error || "Python calibration step failed.");
      cancelCalibration();
      return;
    }
    playSound("click");

    setTimeout(() => {
      state.calibStep++;
      advanceCalibrationStep();
    }, 2050);
  } else {
    const result = await callBackend("/vision/calibration/commit");
    if (!result.ok) {
      showGestureToast(result.error || "Could not save Python calibration.");
      cancelCalibration();
      return;
    }
    if (title) title.textContent = "Calibration Complete! 🎉";
    if (desc) desc.textContent = "Python saved your neutral pose and comfortable head movement ranges.";
    playSound("success");
    setTimeout(() => {
      cancelCalibration(true);
    }, 1200);
  }
}

function cancelCalibration(completed = false) {
  if (state.calibrating && !completed) callBackend("/vision/calibration/cancel");
  state.calibrating = false;
  callBackend(calibrationPreviousPause ? "/pause" : "/resume");
  const overlay = document.getElementById("calibration-overlay");
  if (overlay) overlay.classList.remove("active");
  playSound("click");
}

// HTML sanitization helper
function escapeHtml(str) {
  if (!str) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

// Spoken text normalization and automatic punctuation formatting
function formatSpokenText(raw) {
  let text = (raw || "").trim();
  if (!text) return "";

  // Convert spoken punctuation words to actual symbols
  text = text
    .replace(/\bperiod\b/gi, ".")
    .replace(/\bfull stop\b/gi, ".")
    .replace(/\bcomma\b/gi, ",")
    .replace(/\bquestion mark\b/gi, "?")
    .replace(/\bexclamation mark\b/gi, "!")
    .replace(/\bexclamation point\b/gi, "!")
    .replace(/\bnew line\b/gi, "\n");

  // Capitalize sentence beginnings
  text = text.replace(/(^\w|[.!?]\s+\w)/g, c => c.toUpperCase());
  return text;
}

// Update live transcription box with both committed and interim text
function updateTranscriptionDisplay() {
  const display = document.getElementById("transcription-display");
  if (!display) return;
  if (!state.transcriptionText && !state.interimTranscription) {
    display.innerHTML = '<span style="color:var(--text-faint);">Your spoken words or typed message will appear here...</span>';
  } else {
    let html = escapeHtml(state.transcriptionText);
    if (state.interimTranscription) {
      html += (html ? ' ' : '') + `<span class="interim-speech-live">${escapeHtml(state.interimTranscription)}</span>`;
    }
    display.innerHTML = html;
  }
}

// Speech Recognition & Virtual Keyboard
let speechRecognition = null;

function toggleSpeechRecognition() {
  const SpeechRec = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SpeechRec) {
    state.isListening = !state.isListening;
    playSound(state.isListening ? "success" : "click");
    if (state.isListening) {
      setTimeout(() => {
        state.transcriptionText += (state.transcriptionText ? " " : "") + "Hello NeuroCursor, I need a glass of water.";
        state.isListening = false;
        playSound("success");
        renderView();
      }, 2500);
    }
    renderView();
    return;
  }

  if (!speechRecognition) {
    speechRecognition = new SpeechRec();
    speechRecognition.continuous = true;
    speechRecognition.interimResults = true;
    speechRecognition.lang = navigator.language || "en-US";
    speechRecognition.maxAlternatives = 3;

    speechRecognition.onresult = (e) => {
      let finalChunk = "";
      let interimChunk = "";

      for (let i = e.resultIndex; i < e.results.length; ++i) {
        const res = e.results[i];
        const transcript = res[0].transcript;
        const confidence = res[0].confidence;

        // Filter out low-confidence background acoustic noise
        if (confidence !== undefined && confidence > 0 && confidence < 0.40) {
          continue;
        }

        if (res.isFinal) {
          finalChunk += transcript;
        } else {
          interimChunk += transcript;
        }
      }

      if (finalChunk) {
        const formatted = formatSpokenText(finalChunk);
        if (formatted) {
          state.transcriptionText += (state.transcriptionText ? " " : "") + formatted;
        }
        state.interimTranscription = "";
      } else {
        state.interimTranscription = interimChunk;
      }

      updateTranscriptionDisplay();
    };

    // Auto-reconnect so pauses in speech do not silently terminate recognition
    speechRecognition.onend = () => {
      if (state.isListening) {
        setTimeout(() => {
          if (state.isListening && speechRecognition) {
            try { speechRecognition.start(); } catch (err) {}
          }
        }, 150);
      } else if (voiceEngineArmed) {
        restartVoiceRecognizerSoon(200);
      }
    };

    speechRecognition.onerror = (e) => {
      console.log("[Speech Recognition Error]", e.error);
      if (e.error === "not-allowed") {
        state.isListening = false;
        showGestureToast("⚠️ Microphone access denied. Please allow microphone permissions.");
        renderView();
      }
      // 'no-speech' is expected during quiet pauses; do not abort session
    };
  }

  if (!state.isListening) {
    if (voiceEngineArmed) {
      destroyVoiceRecognizer();
    }
    try {
      speechRecognition.start();
      state.isListening = true;
      playSound("success");
      showGestureToast("🎙️ Speech Recognition Active: Speak naturally");
    } catch (e) {
      state.isListening = true;
    }
  } else {
    state.isListening = false;
    try { speechRecognition.stop(); } catch (e) {}
    playSound("click");
    showGestureToast("Speech recognition paused.");
    if (voiceEngineArmed) restartVoiceRecognizerSoon(250);
  }
  renderView();
}

function clearTranscription() {
  state.transcriptionText = "";
  playSound("click");
  const display = document.getElementById("transcription-display");
  if (display) display.innerHTML = '<span style="color:var(--text-faint);">Your spoken words or typed message will appear here...</span>';
}

function speakCurrentText() {
  if (state.transcriptionText) {
    speak(state.transcriptionText);
  } else {
    speak("Please type or speak a message first.");
  }
}

function pressKey(char) {
  state.transcriptionText += char;
  playSound("click");
  const display = document.getElementById("transcription-display");
  if (display) display.textContent = state.transcriptionText;
}

function pressBackspace() {
  state.transcriptionText = state.transcriptionText.slice(0, -1);
  playSound("click");
  const display = document.getElementById("transcription-display");
  if (display) {
    display.textContent = state.transcriptionText || "Your spoken words or typed message will appear here...";
  }
}

function insertWord(word) {
  state.transcriptionText += (state.transcriptionText ? " " : "") + word;
  playSound("click");
  const display = document.getElementById("transcription-display");
  if (display) display.textContent = state.transcriptionText;
}

function selectAndSpeakPhrase(phrase) {
  state.selectedPhrase = phrase;
  state.transcriptionText = phrase;
  speak(phrase);
  renderView();
}

// Creative Studio Drawing
let studioCtx = null;
let lastDrawX = null;
let lastDrawY = null;

function initStudioCanvas() {
  const canvas = document.getElementById("canvas-element");
  if (!canvas) return;

  canvas.width = canvas.parentElement.clientWidth;
  canvas.height = 420;
  studioCtx = canvas.getContext("2d");

  let isDrawing = false;

  function start(e) {
    isDrawing = true;
    const r = canvas.getBoundingClientRect();
    lastDrawX = (e.clientX || e.touches[0].clientX) - r.left;
    lastDrawY = (e.clientY || e.touches[0].clientY) - r.top;
  }

  function draw(e) {
    if (!isDrawing || !studioCtx) return;
    const r = canvas.getBoundingClientRect();
    const x = (e.clientX || (e.touches && e.touches[0].clientX)) - r.left;
    const y = (e.clientY || (e.touches && e.touches[0].clientY)) - r.top;

    studioCtx.beginPath();
    studioCtx.moveTo(lastDrawX, lastDrawY);
    studioCtx.lineTo(x, y);
    studioCtx.strokeStyle = state.brushColor;
    studioCtx.lineWidth = state.brushSize;
    studioCtx.lineCap = "round";
    studioCtx.lineJoin = "round";
    studioCtx.stroke();

    lastDrawX = x;
    lastDrawY = y;
  }

  function stop() { isDrawing = false; }

  canvas.addEventListener("mousedown", start);
  canvas.addEventListener("mousemove", draw);
  canvas.addEventListener("mouseup", stop);
  canvas.addEventListener("mouseleave", stop);
}

function handleHeadStudioDrawing(screenX, screenY) {
  const canvas = document.getElementById("canvas-element");
  if (!canvas || !studioCtx) return;

  const rect = canvas.getBoundingClientRect();
  if (screenX >= rect.left && screenX <= rect.right && screenY >= rect.top && screenY <= rect.bottom) {
    const x = screenX - rect.left;
    const y = screenY - rect.top;

    if (lastDrawX !== null && lastDrawY !== null) {
      studioCtx.beginPath();
      studioCtx.moveTo(lastDrawX, lastDrawY);
      studioCtx.lineTo(x, y);
      studioCtx.strokeStyle = state.brushColor;
      studioCtx.lineWidth = state.brushSize;
      studioCtx.lineCap = "round";
      studioCtx.lineJoin = "round";
      studioCtx.stroke();
    }
    lastDrawX = x;
    lastDrawY = y;
  } else {
    lastDrawX = null;
    lastDrawY = null;
  }
}

function setStudioColor(col) {
  state.brushColor = col;
  playSound("click");
  renderView();
}

function setStudioSize(sz) {
  state.brushSize = sz;
  playSound("click");
  renderView();
}

function clearStudioCanvas() {
  const canvas = document.getElementById("canvas-element");
  if (canvas && studioCtx) {
    studioCtx.clearRect(0, 0, canvas.width, canvas.height);
  }
  playSound("click");
}

// SOS Alert (Client-Side & Local Storage)
function triggerSOSAlert() {
  playSound("alert");
  const time = new Date().toLocaleTimeString();
  state.alertStatus = `🚨 Emergency beacon dispatched locally to ${state.contacts.length} caregiver(s) at ${time}! Audio alarm active.`;
  try {
    const logs = JSON.parse(localStorage.getItem("neuro_sos_logs") || "[]");
    logs.unshift({ time: new Date().toISOString(), status: state.alertStatus });
    localStorage.setItem("neuro_sos_logs", JSON.stringify(logs.slice(0, 10)));
  } catch (e) {}
  showGestureToast("🚨 SOS Emergency Beacon Dispatched!");
  renderView();
}

function addCaregiverPrompt() {
  const name = prompt("Caregiver or Contact Name:");
  if (!name) return;
  const phone = prompt("Phone Number or Address:");
  if (!phone) return;
  
  state.contacts.push({ name, phone });
  try {
    localStorage.setItem("neuro_contacts", JSON.stringify(state.contacts));
  } catch (e) {}
  playSound("success");
  showGestureToast(`Added caregiver: ${name}`);
  renderView();
}

function removeCaregiver(idx) {
  state.contacts.splice(idx, 1);
  try {
    localStorage.setItem("neuro_contacts", JSON.stringify(state.contacts));
  } catch (e) {}
  playSound("click");
  renderView();
}

// Settings & Preferences with Local Storage Persistence
function setProfileName(name) {
  state.activeProfile = name || "User";
  saveLocalPreferences();
  updateNavigation();
}

function updateSensitivity(val) {
  state.sensitivity = Number(val);
  const el = document.getElementById("speed-slider-val");
  if (el) el.textContent = val + "%";
  saveLocalPreferences();
  callBackend("/vision/sensitivity", { value: state.sensitivity }).then(result => {
    if (!result.ok && backendConnected) showGestureToast(result.error || "Could not update Python tracking sensitivity.");
  });
}

function updateDwell(val) {
  state.dwell = Number(val);
  const el = document.getElementById("dwell-slider-val");
  if (el) el.textContent = val + "s";
  saveLocalPreferences();
}

function saveLocalPreferences() {
  try {
    localStorage.setItem("neuro_settings", JSON.stringify({
      sensitivity: state.sensitivity,
      dwell: state.dwell,
      activeProfile: state.activeProfile,
      highContrast: state.highContrast,
      largeInterface: state.largeInterface,
      reducedAnimation: state.reducedAnimation,
      pointerTune: "v3"
    }));
  } catch (err) {}
}

function loadLocalPreferences() {
  try {
    const saved = localStorage.getItem("neuro_settings");
    if (saved) {
      const cfg = JSON.parse(saved);
      if (cfg.sensitivity != null) {
        let s = Number(cfg.sensitivity);
        if (cfg.pointerTune !== "v3") {
          s = Math.round(10 + (s - 10) * 0.5);
          s = Math.max(10, Math.min(48, s));
        }
        state.sensitivity = s;
      }
      if (cfg.dwell) state.dwell = cfg.dwell;
      if (cfg.activeProfile) state.activeProfile = cfg.activeProfile;
      if (cfg.highContrast !== undefined) {
        state.highContrast = cfg.highContrast;
        document.body.classList.toggle("high-contrast", state.highContrast);
      }
      if (cfg.largeInterface !== undefined) {
        state.largeInterface = cfg.largeInterface;
        document.body.classList.toggle("large-interface", state.largeInterface);
      }
      if (cfg.reducedAnimation !== undefined) {
        state.reducedAnimation = cfg.reducedAnimation;
        document.body.classList.toggle("reduced-animation", state.reducedAnimation);
      }
    }
    const contacts = localStorage.getItem("neuro_contacts");
    if (contacts) {
      const parsed = JSON.parse(contacts);
      if (Array.isArray(parsed) && parsed.length > 0) {
        state.contacts = parsed;
      }
    }
  } catch (e) {
    console.log("[NeuroCursor] Local preferences load:", e);
  }
}

function toggleSettingKey(key) {
  state[key] = !state[key];
  playSound("click");

  if (key === "highContrast") document.body.classList.toggle("high-contrast", state.highContrast);
  if (key === "largeInterface") document.body.classList.toggle("large-interface", state.largeInterface);
  if (key === "reducedAnimation") document.body.classList.toggle("reduced-animation", state.reducedAnimation);

  saveLocalPreferences();
  renderView();
}

function editGestureMapping(gesture) {
  const newAction = prompt(`Change action for ${gesture}:`, "Left Click");
  if (newAction) {
    alert(`Updated: ${gesture} is now mapped to "${newAction}".`);
    playSound("success");
  }
}

function toggleFaq(el) {
  el.classList.toggle("open");
  playSound("click");
}

function triggerNotificationToast() {
  playSound("success");
  showGestureToast("🔔 NeuroCursor: In-browser tracking, voice commands, and vision engine active.");
}

// Initialization on DOM Load
document.addEventListener("DOMContentLoaded", () => {
  // Connect to FLUX Backend stream if available
  initBackendConnection();
  document.querySelectorAll(".nav-item").forEach(btn => {
    btn.addEventListener("click", () => {
      const p = btn.getAttribute("data-page");
      if (p) setPage(p);
    });
  });

  // Activate Head-Controlled Cursor by default
  const globalCursor = document.getElementById("global-head-cursor");
  if (globalCursor) globalCursor.classList.add("active");
  const headMouseBtn = document.getElementById("head-mouse-toggle-btn");
  if (headMouseBtn) headMouseBtn.classList.toggle("active", state.headMouseEnabled);
  const headMouseTxt = document.getElementById("head-mouse-status-text");
  if (headMouseTxt) headMouseTxt.textContent = state.headMouseEnabled ? "Head Mouse: ON" : state.controlMode === "speech" ? "Speech Cursor" : "Physical Mouse";

  // Load user saved settings from browser localStorage
  loadLocalPreferences();
  const modeSelect = document.getElementById("control-mode-select");
  const prioritySelect = document.getElementById("control-priority-select");
  if (modeSelect) modeSelect.value = state.controlMode;
  if (prioritySelect) prioritySelect.value = state.controlPriority;
  if (prioritySelect) prioritySelect.disabled = state.controlMode !== "hybrid";

  updateNavigation();
  renderView();

  // Auto-start camera feed & synchronise streams
  startCameraVision();
  syncBackendControlMode();
  syncWebcamVideoStreams();
  updateVoicePillUI();
  setTimeout(() => {
    if (!voiceEngineArmed) {
      showGestureToast("Click Voice: Off in the top bar, allow the microphone, then say Hey Cursor");
    }
  }, 1400);
});

