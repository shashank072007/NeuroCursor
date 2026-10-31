"""FLUX Backend Package.
Hands-free adaptive accessibility system.
"""

from .config import *
from .bus import bus, make_msg, next_seq
from .sources import MockFrameSource, ReplayFrameSource, LiveFrameSource
from .os_control import os_controller
from .safety import safety_manager
from .intent_guard import IntentGuard
from .effort import EffortMeter
from .adapt import AdaptiveEngine
from .channels import ChannelManager
from .profiles import profile_mgr
from .calibration import calibration_engine
from .bench import bench_storage
from .processor import ProcessorPipeline
