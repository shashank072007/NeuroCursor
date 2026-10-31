"""OS Pointer and Mouse Control for FLUX.
Reference: Section B3.
Only place that converts normalized (0..1) coordinates to screen pixels.
DPI-aware and handles failsafe-free cursor movement and clicks.
"""

import ctypes
from typing import Tuple, Dict, Any, Optional

# Enable Windows DPI Awareness so normalized coordinates map accurately to physical pixels
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)  # Per-monitor DPI aware
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

# Optional Win32 API for ultra-fast, failsafe-free mouse control
HAS_WIN32 = False
try:
    import win32api
    import win32con
    HAS_WIN32 = True
except ImportError:
    pass

# Fallback to pynput if win32 not available
HAS_PYNPUT = False
try:
    from pynput.mouse import Controller as MouseController, Button
    _pynput_mouse = MouseController()
    HAS_PYNPUT = True
except ImportError:
    pass


class OSController:
    """Controls OS cursor movement and button clicks."""

    def __init__(self, simulate: bool = False):
        self.simulate = simulate
        self.screen_w, self.screen_h = self._get_screen_resolution()
        self.last_px = self.screen_w // 2
        self.last_py = self.screen_h // 2
        self.scroll_mode_active = False

    def _get_screen_resolution(self) -> Tuple[int, int]:
        """Detect primary monitor resolution in physical pixels."""
        try:
            w = ctypes.windll.user32.GetSystemMetrics(0)
            h = ctypes.windll.user32.GetSystemMetrics(1)
            if w > 0 and h > 0:
                return w, h
        except Exception:
            pass
        return 1920, 1080

    def move_pointer(self, nx: float, ny: float) -> Tuple[int, int]:
        """Convert normalized (0..1) coordinates to pixels and move cursor.
        Returns clamped pixel coordinates (px, py).
        """
        px = max(0, min(self.screen_w - 1, int(round(nx * self.screen_w))))
        py = max(0, min(self.screen_h - 1, int(round(ny * self.screen_h))))

        self.last_px = px
        self.last_py = py

        if not self.simulate:
            if HAS_WIN32:
                try:
                    win32api.SetCursorPos((px, py))
                except Exception:
                    pass
            elif HAS_PYNPUT:
                try:
                    _pynput_mouse.position = (px, py)
                except Exception:
                    pass

        # Handle scroll toggle mode if pointer is in top/bottom 15%
        if self.scroll_mode_active and not self.simulate:
            if ny < 0.15:
                self.scroll(1)   # scroll up
            elif ny > 0.85:
                self.scroll(-1)  # scroll down

        return px, py

    def execute_action(self, action_name: str, px: Optional[int] = None, py: Optional[int] = None) -> bool:
        """Execute the requested OS action (e.g. left_click, scroll_toggle).
        menu_open is handled purely by frontend, so backend does not click.
        """
        if px is None:
            px = self.last_px
        if py is None:
            py = self.last_py

        if action_name == "left_click":
            return self.left_click(px, py)
        elif action_name == "scroll_toggle":
            self.scroll_mode_active = not self.scroll_mode_active
            return True
        elif action_name == "menu_open":
            # Handled by frontend, no OS click
            return True
        return False

    def left_click(self, px: int, py: int) -> bool:
        """Execute a single left mouse click at given pixel coords."""
        if self.simulate:
            return True

        if HAS_WIN32:
            try:
                win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, px, py, 0, 0)
                win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, px, py, 0, 0)
                return True
            except Exception:
                pass
        if HAS_PYNPUT:
            try:
                _pynput_mouse.position = (px, py)
                _pynput_mouse.click(Button.left, 1)
                return True
            except Exception:
                pass
        return False

    def scroll(self, steps: int) -> None:
        """Scroll the mouse wheel."""
        if self.simulate:
            return
        if HAS_WIN32:
            try:
                # 120 units per notch
                win32api.mouse_event(win32con.MOUSEEVENTF_WHEEL, 0, 0, steps * 120, 0)
            except Exception:
                pass
        elif HAS_PYNPUT:
            try:
                _pynput_mouse.scroll(0, steps)
            except Exception:
                pass


# Global OS Controller singleton
os_controller = OSController()
