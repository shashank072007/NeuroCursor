"""Safety Monitor, Pause/Lock Controls, and Keyboard Hotkeys.
Reference: Section B4 & G15.
Registers global panic hotkeys (F9 pause/resume, F10 lock/unlock) and handles tracking loss.
"""

import time
import threading
from typing import Callable, Optional, List
from .config import FACE_LOST_MS

try:
    from pynput import keyboard
    HAS_PYNPUT_KEYBOARD = True
except ImportError:
    HAS_PYNPUT_KEYBOARD = False


class SafetyManager:
    """Manages pause, lock, panic hotkeys, and face loss detection."""

    def __init__(self):
        self.paused: bool = False
        self.locked: bool = False
        self.face_lost: bool = False
        self.last_face_time: float = time.time()
        self.tracking_loss_duration: float = 0.0

        self._on_status_change_callbacks: List[Callable[[], None]] = []
        self._listener: Optional[Any] = None
        self._lock = threading.Lock()
        self._start_hotkey_listener()

    def add_status_listener(self, cb: Callable[[], None]) -> None:
        self._on_status_change_callbacks.append(cb)

    def _notify_change(self) -> None:
        for cb in self._on_status_change_callbacks:
            try:
                cb()
            except Exception:
                pass

    def pause(self) -> None:
        with self._lock:
            self.paused = True
        self._notify_change()

    def resume(self) -> None:
        with self._lock:
            self.paused = False
        self._notify_change()

    def toggle_pause(self) -> None:
        with self._lock:
            self.paused = not self.paused
        self._notify_change()

    def lock(self) -> None:
        with self._lock:
            self.locked = True
        self._notify_change()

    def unlock(self) -> None:
        with self._lock:
            self.locked = False
        self._notify_change()

    def toggle_lock(self) -> None:
        with self._lock:
            self.locked = not self.locked
        self._notify_change()

    def update_face_tracking(self, detected: bool, current_time: Optional[float] = None) -> bool:
        """Update face detection state. Returns True if face is currently considered lost."""
        if current_time is None:
            current_time = time.time()

        with self._lock:
            if detected:
                self.last_face_time = current_time
                self.face_lost = False
                return False
            else:
                elapsed_ms = (current_time - self.last_face_time) * 1000.0
                if elapsed_ms > FACE_LOST_MS:
                    self.face_lost = True
                    return True
                return False

    def can_move_pointer(self) -> bool:
        """Pointer movement is allowed unless system is locked or face is lost."""
        with self._lock:
            return not self.locked and not self.face_lost

    def can_execute_action(self) -> bool:
        """Clicks and actions are forbidden when paused, locked, or face is lost."""
        with self._lock:
            return not self.paused and not self.locked and not self.face_lost

    def stop(self) -> None:
        """Stop hotkey listener and cleanup."""
        if self._listener:
            try:
                self._listener.stop()
            except Exception:
                pass
            self._listener = None

    def _start_hotkey_listener(self) -> None:
        if not HAS_PYNPUT_KEYBOARD:
            print("[Safety] pynput keyboard not available, F9/F10 hotkeys disabled.")
            return

        def on_press(key):
            try:
                if key == keyboard.Key.f9:
                    self.toggle_pause()
                    state = "PAUSED" if self.paused else "RESUMED"
                    print(f"[Safety Hotkey F9] System {state}")
                elif key == keyboard.Key.f10:
                    self.toggle_lock()
                    state = "LOCKED" if self.locked else "UNLOCKED"
                    print(f"[Safety Hotkey F10] System {state}")
            except Exception:
                pass

        try:
            self._listener = keyboard.Listener(on_press=on_press)
            self._listener.daemon = True
            self._listener.start()
            print("[Safety] F9 (pause/resume) and F10 (lock/unlock) hotkeys active.")
        except Exception as e:
            print(f"[Safety] Could not start keyboard listener: {e}")


# Global safety manager singleton
safety_manager = SafetyManager()
