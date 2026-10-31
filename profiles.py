"""User Profile Storage and Management for FLUX.
Reference: Section B2 & C.8.
Profiles are stored in backend/profiles/<id>.json.
"""

import os
import json
import time
from typing import Dict, Any, List, Optional
from .config import PROFILES_DIR

DEFAULT_DEMO_PROFILE: Dict[str, Any] = {
    "v": 1,
    "profile_id": "demo_profile",
    "created": "2026-10-31T11:40:00+05:30",
    "neutral": { "x": 0.50, "y": 0.50, "face_width_px": 212 },
    "range": { "x": 0.18, "y": 0.12 },
    "baseline": { "jitter": 0.004, "gesture_peak": 0.91, "hold_ms": 180 },
    "gesture_map": {
        "mouth_open": "left_click",
        "brow_raise": "scroll_toggle",
        "smile": "menu_open"
    },
    "gesture_thresholds": {
        "mouth_open": 0.55,
        "brow_raise": 0.60,
        "smile": 0.50
    },
    "sound": { "enabled": False, "template": None }
}

DEFAULT_RITESH_PROFILE: Dict[str, Any] = {
    "v": 1,
    "profile_id": "ritesh_v1",
    "created": "2026-10-31T11:40:00+05:30",
    "neutral": { "x": 0.50, "y": 0.50, "face_width_px": 212 },
    "range": { "x": 0.18, "y": 0.12 },
    "baseline": { "jitter": 0.004, "gesture_peak": 0.91, "hold_ms": 180 },
    "gesture_map": {
        "mouth_open": "left_click",
        "brow_raise": "scroll_toggle",
        "smile": "menu_open"
    },
    "gesture_thresholds": {
        "mouth_open": 0.55,
        "brow_raise": 0.60,
        "smile": 0.50
    },
    "sound": { "enabled": False, "template": None }
}


class ProfileManager:
    """Manages loading, saving, listing, and activating user profiles."""

    def __init__(self, profiles_dir: str = PROFILES_DIR):
        self.profiles_dir = profiles_dir
        os.makedirs(self.profiles_dir, exist_ok=True)
        self._ensure_default_profiles()
        self._active_profile: Dict[str, Any] = self.get_profile("demo_profile") or DEFAULT_DEMO_PROFILE

    def _ensure_default_profiles(self) -> None:
        """Seed demo_profile and ritesh_v1 if missing."""
        demo_path = os.path.join(self.profiles_dir, "demo_profile.json")
        if not os.path.exists(demo_path):
            self.save_profile("demo_profile", DEFAULT_DEMO_PROFILE)

        ritesh_path = os.path.join(self.profiles_dir, "ritesh_v1.json")
        if not os.path.exists(ritesh_path):
            self.save_profile("ritesh_v1", DEFAULT_RITESH_PROFILE)

    def list_profiles(self) -> List[str]:
        """Return list of profile IDs found on disk."""
        profiles = []
        for filename in os.listdir(self.profiles_dir):
            if filename.endswith(".json"):
                profiles.append(filename[:-5])
        return sorted(profiles)

    def get_profile(self, profile_id: str) -> Optional[Dict[str, Any]]:
        """Load and return profile data by ID."""
        path = os.path.join(self.profiles_dir, f"{profile_id}.json")
        if not os.path.exists(path):
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None

    def save_profile(self, profile_id: str, data: Dict[str, Any]) -> bool:
        """Save a profile to disk."""
        path = os.path.join(self.profiles_dir, f"{profile_id}.json")
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            return True
        except Exception:
            return False

    @property
    def active_profile(self) -> Dict[str, Any]:
        return self._active_profile

    def activate(self, profile_id: str) -> Optional[Dict[str, Any]]:
        """Set the active profile."""
        profile = self.get_profile(profile_id)
        if profile is not None:
            self._active_profile = profile
            return profile
        return None


# Global profile manager singleton
profile_mgr = ProfileManager()
