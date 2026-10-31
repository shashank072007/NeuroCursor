"""FLUX Backend Configuration and Shared Constants.
Reference: Shared Contract FLUX-CONTRACT v1.1.
"""

import os

# Section E Shared Constants
FRAME_HZ = 30
FACE_LOST_MS = 200
FRAME_Q_MAX = 2
Q_MIN = 0.50
EMIT_FLOOR_FACTOR = 0.85  # Gesture emitted once score >= 0.85 * base threshold (G4)
STILL_SPEED = 0.18        # Max pointer speed (screen-widths / s over last 200ms)
COOLDOWN_MS = 600
UNDO_WINDOW_MS = 2000
DWELL_STILL_RADIUS = 0.02 # Normalized screen units
WARMUP_S = 20
REARM_S = 10
MIN_LEVEL_HOLD_S = 10
EFFORT_EMA_ALPHA = 0.1    # Per second
MIN_MOTION = 0.5          # Screen-widths of pointer path in 20 s needed to update range_now
DRIFT_EDGE_MARGIN = 0.03  # 3% edge
DRIFT_HOLD_S = 5.0        # 5 s hold near edge
DRIFT_RATE = 0.01         # 1% / s shift
SWITCH_RULE_LOW = 0.5     # Primary reliability below 0.5
SWITCH_RULE_HIGH = 0.75   # Alternative reliability above 0.75
SWITCH_RULE_HOLD_S = 10.0 # for 10 s
LENS_MAX_PX = 48          # Targets <= 48 px rendered (G11)

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 5000

# File Paths
BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
PROFILES_DIR = os.path.join(BACKEND_DIR, "profiles")
BENCH_LOGS_DIR = os.path.join(BACKEND_DIR, "bench_logs")

os.makedirs(PROFILES_DIR, exist_ok=True)
os.makedirs(BENCH_LOGS_DIR, exist_ok=True)

# G12: Dev Token override
FLUX_DEV = os.environ.get("FLUX_DEV", "0") == "1"
DEV_TOKEN = "dev-token"

# Benchmark CSV Columns in exact order (Section H)
BENCH_COLUMNS = [
    "session_id", "tester", "condition", "fatigue", "task",
    "target_id", "target_size_px", "t_start", "t_end", "time_ms",
    "hit", "error_dist_px", "false_click_flag", "guard_rejects",
    "effort_score", "level"
]
