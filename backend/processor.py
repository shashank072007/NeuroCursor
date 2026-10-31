"""Central Signal Processor and Event Dispatcher for FLUX.
Reference: Section B1, B5, B7, B8.
Runs the main ~30 Hz frame loop and 1 Hz periodic adaptation / effort timers.
"""

import time
import threading
import queue
from typing import Optional, Dict, Any, Callable
from .bus import bus, make_msg
from .sources import FrameSource, MockFrameSource
from .os_control import os_controller
from .safety import safety_manager
from .intent_guard import IntentGuard
from .effort import EffortMeter
from .adapt import AdaptiveEngine
from .channels import ChannelManager
from .profiles import profile_mgr
from .calibration import calibration_engine
from .config import Q_MIN


class ProcessorPipeline:
    """Orchestrates real-time frame ingestion, guard checks, OS dispatch, and timers."""

    def __init__(
        self,
        frame_source: Optional[FrameSource] = None,
        control_q: Optional[queue.Queue] = None,
        simulate_os: bool = False
    ):
        self.frame_source = frame_source or MockFrameSource()
        self.control_q = control_q or queue.Queue(maxsize=10)
        if hasattr(self.frame_source, "control_q"):
            self.frame_source.control_q = self.control_q

        # Wire subsystems
        self.os_controller = os_controller
        self.os_controller.simulate = simulate_os

        self.safety = safety_manager
        self.intent_guard = IntentGuard(self.os_controller)
        self.effort = EffortMeter()
        self.adapt = AdaptiveEngine(on_vision_params=self._send_vision_params)
        self.control_mode = "head"
        self.channels = ChannelManager()
        self.calibration = calibration_engine
        self.calibration.control_q = self.control_q

        # Wire status change listener
        self.safety.add_status_listener(self.emit_status)

        # Performance monitoring
        self.fps: float = 30.0
        self._frame_count = 0
        self._fps_window_start = time.time()
        self._last_status_ts = 0.0

        # State flags
        self.running = False
        self._processor_thread: Optional[threading.Thread] = None
        self._timer_thread: Optional[threading.Thread] = None

    def _send_vision_params(self, vp: Dict[str, Any]) -> None:
        """Push vision_params message to control_q for vision module."""
        try:
            if self.control_q.full():
                try:
                    self.control_q.get_nowait()
                except queue.Empty:
                    pass
            self.control_q.put_nowait(vp)
        except Exception:
            pass

    def start(self) -> None:
        """Start the frame processing and timer threads."""
        self.running = True
        self.frame_source.start()

        # Emit initial status & ui_state snapshot
        self.emit_status()
        initial_ui, _ = self.adapt.compute_ui_state(
            self.effort.current_level, self.effort.range_now, profile_mgr.active_profile
        )
        bus.broadcast(initial_ui)

        self._processor_thread = threading.Thread(target=self._process_loop, daemon=True)
        self._processor_thread.start()

        self._timer_thread = threading.Thread(target=self._timer_loop, daemon=True)
        self._timer_thread.start()
        print("[Processor] Real-time FLUX pipeline online.")

    def stop(self) -> None:
        """Stop threads cleanly."""
        self.running = False
        self.frame_source.stop()
        self.safety.stop()
        if self._processor_thread:
            self._processor_thread.join(timeout=1.0)
        if self._timer_thread:
            self._timer_thread.join(timeout=1.0)
        print("[Processor] Pipeline stopped.")

    def _process_loop(self) -> None:
        """Main high-frequency loop processing each frame from frame_source (~30 Hz)."""
        while self.running:
            frame = self.frame_source.get_frame(timeout=0.05)
            if not frame:
                continue

            now = time.time()
            msg_type = frame.get("type")

            # Route internal calibration result from vision
            if msg_type == "calib_result":
                self.calibration.execute_step(
                    frame.get("step", ""),
                    frame.get("rep", 1),
                    incoming_result=frame
                )
                continue

            # Update FPS tracking
            self._frame_count += 1
            if (now - self._fps_window_start) >= 2.0:
                elapsed = now - self._fps_window_start
                self.fps = round(self._frame_count / elapsed, 1)
                self._frame_count = 0
                self._fps_window_start = now

            # 1. Check face tracking and safety
            face = frame.get("face") or {}
            detected = bool(frame.get("detected", face.get("detected", False)))
            was_lost = self.safety.face_lost
            is_lost = self.safety.update_face_tracking(detected, now)

            if was_lost and not is_lost:
                # Tracking recovered
                loss_duration = (now - self.safety.last_face_time)
                self.effort.notify_tracking_loss(loss_duration, now)

            # 2. Update pointer if tracking and safety allow
            head = frame.get("head") or frame.get("pointer") or {}
            raw_motion = frame.get("raw_motion") or {}
            if detected and head and self.safety.can_move_pointer() and self.control_mode in ("head", "hybrid"):
                nx = head.get("nx", 0.5)
                ny = head.get("ny", 0.5)
                self.os_controller.move_pointer(nx, ny)

                # Evaluate drift re-centring
                raw_dx = head.get("raw_dx", raw_motion.get("raw_dx", 0.0))
                raw_dy = head.get("raw_dy", raw_motion.get("raw_dy", 0.0))
                drift_shifted = self.adapt.update_drift(
                    nx, ny, raw_dx, raw_dy, self.intent_guard.last_action_ts, now
                )
                if drift_shifted:
                    # Push updated neutral shift
                    profile = profile_mgr.active_profile
                    params = self.adapt.compute_ui_state(self.effort.current_level, self.effort.range_now, profile)[0]
                    self.adapt._emit_vision_params(params["smoothing_alpha"], params["gain"], profile)

            # 3. IntentGuard evaluation
            profile = profile_mgr.active_profile
            cached_ui = bus.get_latest("ui_state") or self.adapt._last_ui_state or {}

            guard_msg, action_msg, dwell_pending_msg = self.intent_guard.process_frame(
                frame=frame,
                ui_state=cached_ui,
                profile=profile,
                paused=self.safety.paused,
                locked=self.safety.locked,
                face_lost=self.safety.face_lost,
                control_enabled=self.control_mode in ("head", "hybrid")
            )

            if dwell_pending_msg:
                bus.broadcast(dwell_pending_msg)

            if guard_msg:
                bus.broadcast(guard_msg)
                # Feed guard decision to effort friction & channels
                is_struggle = (guard_msg.get("decision") == "reject" and
                               guard_msg.get("reason") in ("pointer_fast", "gesture_short", "low_confidence"))
                self.effort.record_attempt(is_struggle, now)

                # Feed channel reliability
                ch = guard_msg.get("channel", "gesture")
                if guard_msg.get("decision") == "allow":
                    self.channels.record_attempt(ch, success=True, ts=now)
                elif is_struggle:
                    self.channels.record_attempt(ch, success=False, ts=now)

            if action_msg:
                bus.broadcast(action_msg)

            # 4. Shadow dwell tracking
            if head and detected:
                nx = head.get("nx", 0.5)
                ny = head.get("ny", 0.5)
                p_speed = self.intent_guard._pointer_history[-1][1] if self.intent_guard._pointer_history else 0.0
                dwell_target = cached_ui.get("dwell_ms", 1000)
                self.channels.update_shadow_dwell(nx, ny, p_speed, dwell_target, now)

            # 5. Feed effort meter if quality >= Q_MIN
            if detected and face.get("quality", 0.0) >= Q_MIN:
                self.effort.feed_frame(frame)

            # 6. Relay frame over SSE (G1)
            bus.broadcast(frame)

    def _timer_loop(self) -> None:
        """Periodic 1 Hz and 5 s background timer."""
        while self.running:
            time.sleep(1.0)
            if not self.running:
                break

            now = time.time()
            profile = profile_mgr.active_profile

            # 1. Effort meter 1 Hz tick
            effort_msg = self.effort.tick(profile, now)
            bus.broadcast(effort_msg)

            # 2. Adaptation 1 Hz evaluation
            ui_state, changed = self.adapt.compute_ui_state(
                effort_msg["level"], effort_msg["range_now"], profile
            )
            if changed:
                bus.broadcast(ui_state)

            # 3. Channel reliability 1 Hz tick
            channels_msg = self.channels.tick(now)
            bus.broadcast(channels_msg)

            # Check if channel switch recommendation changed ui_state
            if self.channels.suggest_channel != self.adapt.suggest_channel:
                self.adapt.suggest_channel = self.channels.suggest_channel
                ui_state, _ = self.adapt.compute_ui_state(
                    effort_msg["level"], effort_msg["range_now"], profile
                )
                bus.broadcast(ui_state)

            # 4. Status emission every 5 s (C.7)
            if (now - self._last_status_ts) >= 5.0:
                self.emit_status()

    def emit_status(self) -> None:
        """Emit status message (on change and every 5 s)."""
        now = time.time()
        self._last_status_ts = now
        profile = profile_mgr.active_profile
        source = self.frame_source
        producer = getattr(source, "producer", None)
        if producer is None:
            camera_state = "mock" if isinstance(source, MockFrameSource) else "off"
        elif producer.use_mock:
            camera_state = "mock"
        else:
            has_recent_frame = (
                producer.last_success_ts > 0
                and (time.monotonic() - producer.last_success_ts) < 1.0
            )
            camera_state = "on" if producer.camera.is_open and has_recent_frame else "off"

        status_msg = make_msg(
            "status",
            paused=self.safety.paused,
            locked=self.safety.locked,
            camera=camera_state,
            mic="off",
            fps=self.fps,
            profile_id=profile.get("profile_id", "demo_profile"),
            mode=self.adapt.mode
        )
        bus.broadcast(status_msg)

    def handle_undo(self) -> Dict[str, Any]:
        """Trigger action undo: re-emits same action with undone: True."""
        undone_action = self.intent_guard.handle_undo()
        if undone_action:
            # Re-emit with same seq
            bus.broadcast(undone_action)
            # Count against channel reliability
            ch = undone_action.get("channel", "gesture")
            self.channels.record_undo(ch)
            return {"ok": True, "undone": True}
        return {"ok": True, "undone": False}
