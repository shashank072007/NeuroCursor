"""NeuroCursor — Assistive Hands-Free Interface & OS Controller.
Unified execution entry point for Frontend, Backend, and Vision subsystems.

Usage:
  python main.py                     # Runs live with webcam + backend + frontend UI
  python main.py --source mock       # Runs in mock simulation mode (no camera needed)
  python main.py --open-browser      # Automatically opens UI in default browser
  python main.py --simulate          # Runs OS controller in simulation mode (no actual mouse clicks)
  python main.py --test              # Runs the complete test suite across backend and vision
  python main.py --debug-vision      # Launches the Vision OpenCV debug visualizer HUD
"""

import os
import sys
import argparse
import unittest
import webbrowser

# Ensure project root is in python path
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from backend.config import DEFAULT_HOST, DEFAULT_PORT, DEV_TOKEN
import backend.app as backend_app
from backend.app import create_app


def run_tests():
    """Runs all backend and vision unit/integration tests."""
    print("\n=======================================================")
    print("  Running NeuroCursor Full Integration Test Suite")
    print("=======================================================\n")
    loader = unittest.TestLoader()
    suite = loader.discover(os.path.join(PROJECT_ROOT, "tests"), pattern="test_*.py")
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)


def run_vision_debug(camera_index: int = 0):
    """Launches the OpenCV HUD debug visualizer."""
    print("\n=======================================================")
    print("  Launching Vision Debug Visualizer HUD")
    print("=======================================================\n")
    try:
        from main_debug import run_visualizer
        run_visualizer(camera_index=camera_index)
    except ImportError:
        import subprocess
        subprocess.run([sys.executable, "main_debug.py", "--camera-index", str(camera_index)])


def main():
    parser = argparse.ArgumentParser(description="NeuroCursor Unified Launcher")
    parser.add_argument("--source", default="live", choices=["live", "mock", "replay"],
                        help="Signal source: 'live' (webcam + MediaPipe), 'mock' (synthetic ~30Hz), or 'replay'")
    parser.add_argument("--host", default=DEFAULT_HOST, help=f"Binding host (default {DEFAULT_HOST})")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"Binding port (default {DEFAULT_PORT})")
    parser.add_argument("--camera-index", type=int, default=0, help="Camera device index (default 0)")
    parser.add_argument("--replay-file", default=None, help="Path to JSONL frames file for replay mode")
    parser.add_argument("--simulate", action="store_true", help="Simulate OS mouse actions without moving cursor")
    parser.add_argument("--dev", action="store_true", default=False, help="Use the fixed development token (unsafe for hosted UI connections)")
    parser.add_argument("--no-dev", dest="dev", action="store_false", help="Use a random local agent token (default)")
    parser.add_argument("--open-browser", action="store_true", help="Automatically open web frontend in browser")
    parser.add_argument("--test", action="store_true", help="Run integration tests and exit")
    parser.add_argument("--debug-vision", action="store_true", help="Launch OpenCV vision debug visualizer window")

    args = parser.parse_args()

    if args.test:
        run_tests()
        return

    if args.debug_vision:
        run_vision_debug(args.camera_index)
        return

    # Create and start Flask app with selected source
    app = create_app(
        source_type=args.source,
        replay_file=args.replay_file,
        simulate_os=args.simulate,
        camera_index=args.camera_index,
        dev_mode=args.dev
    )

    url = f"http://{args.host}:{args.port}"
    token = DEV_TOKEN if args.dev else backend_app.SERVER_TOKEN

    print(f"\n=======================================================")
    print(f"  🧠 NeuroCursor (FLUX) Integration Platform Online")
    print(f"  ---------------------------------------------------")
    print(f"  🌐 Frontend UI:    {url}/")
    print(f"  📡 SSE Stream:     {url}/stream?token={token}")
    print(f"  🔑 Security Token: {token}")
    print(f"  📷 Vision Source:  {args.source.upper()}")
    print(f"  ⌨️  Hotkeys:        F9 = Pause/Resume | F10 = Lock/Unlock")
    print(f"=======================================================\n")

    if args.open_browser:
        webbrowser.open(url)

    app.run(host=args.host, port=args.port, threaded=True)


if __name__ == "__main__":
    main()
