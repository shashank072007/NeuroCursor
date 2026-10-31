"""Flask Application and REST/SSE Server for FLUX Backend.
Reference: Section B1, Section D & Shared Contract.
Binds to 127.0.0.1:5000, enforces token authentication (G12),
serves real-time Server-Sent Events (/stream), serves the frontend UI,
and provides all REST endpoints for calibration, profiles, safety, mode, channels, bench, and dev tools.
"""

import os
import sys
import json
import time
import queue
import secrets
import argparse
import webbrowser
from functools import wraps
from typing import Dict, Any, Generator

from flask import Flask, request, Response, jsonify, send_from_directory

# Ensure backend package can be imported
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

from backend.config import (
    DEFAULT_HOST, DEFAULT_PORT, FLUX_DEV, DEV_TOKEN
)
from backend.bus import bus
from backend.sources import MockFrameSource, ReplayFrameSource, LiveFrameSource
from backend.processor import ProcessorPipeline
from backend.profiles import profile_mgr
from backend.bench import bench_storage

# Token Generation / Auth (G12)
if FLUX_DEV:
    SERVER_TOKEN = DEV_TOKEN
else:
    SERVER_TOKEN = os.environ.get("FLUX_TOKEN", secrets.token_hex(16))

print(f"[FLUX Security] Active Token: {SERVER_TOKEN} (FLUX_DEV={FLUX_DEV})")

# Determine Frontend Directory
FRONTEND_DIR = os.path.abspath(os.path.join(parent_dir, "frontend"))

app = Flask(__name__, static_folder=FRONTEND_DIR, static_url_path="")

# Global pipeline instance (initialized in main / CLI)
pipeline: ProcessorPipeline = None


@app.after_request
def add_cors_headers(response):
    """Enable Cross-Origin Resource Sharing for frontend compatibility."""
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, X-Flux-Token"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
    return response


@app.before_request
def handle_options_preflight():
    """Handle CORS preflight without authentication block."""
    if request.method == "OPTIONS":
        return Response("", status=200)


def require_token(f):
    """Enforce X-Flux-Token header on all REST calls."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if request.method == "OPTIONS":
            return Response("", status=200)
        token = request.headers.get("X-Flux-Token")
        if not token or token != SERVER_TOKEN:
            return jsonify({"ok": False, "error": "Unauthorized: invalid or missing X-Flux-Token"}), 401
        return f(*args, **kwargs)
    return decorated_function


# -------------------------------------------------------------
# FRONTEND STATIC ROUTES
# -------------------------------------------------------------
@app.route("/", methods=["GET"])
def serve_index():
    """Serves NeuroCursor frontend web interface."""
    return send_from_directory(FRONTEND_DIR, "index.html")


@app.route("/<path:path>", methods=["GET"])
def serve_frontend_assets(path):
    """Serves static frontend assets (css, js, assets, etc.)."""
    target = os.path.join(FRONTEND_DIR, path)
    if os.path.isfile(target):
        return send_from_directory(FRONTEND_DIR, path)
    if os.path.isfile(os.path.join(FRONTEND_DIR, "index.html")):
        return send_from_directory(FRONTEND_DIR, "index.html")
    return jsonify({"ok": False, "error": "Not found"}), 404


# -------------------------------------------------------------
# SSE STREAM ENDPOINT (Section D, G1, G14)
# -------------------------------------------------------------
@app.route("/stream", methods=["GET"])
def stream_events():
    """SSE endpoint with token validation, initial snapshot, and 15s keepalive."""
    token = request.args.get("token")
    if not token or token != SERVER_TOKEN:
        return jsonify({"ok": False, "error": "Unauthorized: invalid or missing ?token="}), 401

    client_q, snapshot = bus.subscribe()

    def event_generator() -> Generator[str, None, None]:
        try:
            # 1. Send latest snapshot on connect (G14)
            for snap_msg in snapshot:
                yield f"data: {json.dumps(snap_msg)}\n\n"

            last_keepalive = time.time()

            # 2. Stream live messages from bounded queue
            while True:
                try:
                    msg = client_q.get(timeout=1.0)
                    yield f"data: {json.dumps(msg)}\n\n"
                    last_keepalive = time.time()
                except queue.Empty:
                    pass

                now = time.time()
                if (now - last_keepalive) >= 15.0:
                    yield ": keepalive\n\n"
                    last_keepalive = now

        except GeneratorExit:
            bus.unsubscribe(client_q)
        except Exception as e:
            print(f"[SSE] Client disconnect: {e}")
            bus.unsubscribe(client_q)

    return Response(
        event_generator(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


@app.route("/camera/stream", methods=["GET"])
def stream_camera_preview():
    """Serve a preview encoded by the Python vision worker (never browser-captured)."""
    token = request.args.get("token")
    if not token or token != SERVER_TOKEN:
        return jsonify({"ok": False, "error": "Unauthorized: invalid or missing ?token="}), 401

    def image_generator():
        last_frame_index = -1
        while True:
            current_pipeline = pipeline
            source = getattr(current_pipeline, "frame_source", None)
            producer = getattr(source, "producer", None)
            if producer is not None:
                frame_index = producer.latest_jpeg_frame_index
                jpeg = producer.latest_jpeg
                if jpeg and frame_index != last_frame_index:
                    last_frame_index = frame_index
                    yield (b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: "
                           + str(len(jpeg)).encode("ascii") + b"\r\n\r\n" + jpeg + b"\r\n")
            time.sleep(0.08)

    return Response(image_generator(), mimetype="multipart/x-mixed-replace; boundary=frame",
                    headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})


@app.route("/vision/recenter", methods=["POST"])
@require_token
def vision_recenter():
    """Recenter the Python pointer tracker using its most recent face landmarks."""
    source = getattr(pipeline, "frame_source", None)
    producer = getattr(source, "producer", None)
    if producer is None or producer.use_mock:
        return jsonify({"ok": False, "error": "Live Python camera tracking is not active."}), 503
    ok, message = producer.recenter()
    return jsonify({"ok": ok, "message": message}), (200 if ok else 409)


@app.route("/vision/sensitivity", methods=["POST"])
@require_token
def vision_sensitivity():
    data = request.get_json(silent=True) or {}
    try:
        value = float(data.get("value", 36))
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "Sensitivity must be between 10 and 100."}), 400
    if not 10 <= value <= 100:
        return jsonify({"ok": False, "error": "Sensitivity must be between 10 and 100."}), 400
    source = getattr(pipeline, "frame_source", None)
    producer = getattr(source, "producer", None)
    if producer is None or producer.use_mock:
        return jsonify({"ok": False, "error": "Live Python camera tracking is not active."}), 503
    producer.set_user_sensitivity(value)
    return jsonify({"ok": True, "sensitivity": value})


@app.route("/vision/calibration/step", methods=["POST"])
@require_token
def vision_calibration_step():
    data = request.get_json(silent=True) or {}
    source = getattr(pipeline, "frame_source", None)
    producer = getattr(source, "producer", None)
    if producer is None or producer.use_mock:
        return jsonify({"ok": False, "error": "Live Python camera tracking is not active."}), 503
    try:
        duration = max(1.0, min(8.0, float(data.get("duration_sec", 2.0))))
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "duration_sec must be a number."}), 400
    ok, message = producer.start_calibration_step(str(data.get("step", "")), duration)
    return jsonify({"ok": ok, "message": message}), (200 if ok else 400)


@app.route("/vision/calibration/commit", methods=["POST"])
@require_token
def vision_calibration_commit():
    source = getattr(pipeline, "frame_source", None)
    producer = getattr(source, "producer", None)
    if producer is None or producer.use_mock:
        return jsonify({"ok": False, "error": "Live Python camera tracking is not active."}), 503
    ok, message = producer.commit_calibration()
    return jsonify({"ok": ok, "message": message}), (200 if ok else 409)


@app.route("/vision/calibration/cancel", methods=["POST"])
@require_token
def vision_calibration_cancel():
    source = getattr(pipeline, "frame_source", None)
    producer = getattr(source, "producer", None)
    if producer is not None:
        producer.cancel_calibration()
    return jsonify({"ok": True})


# -------------------------------------------------------------
# CALIBRATION ENDPOINTS (Section D, B2)
# -------------------------------------------------------------
@app.route("/calibrate/start", methods=["POST"])
@require_token
def calibrate_start():
    data = request.get_json(silent=True) or {}
    profile_id = data.get("profile_id", "user_profile")
    res = pipeline.calibration.start(profile_id)
    return jsonify(res)


@app.route("/calibrate/step", methods=["POST"])
@require_token
def calibrate_step():
    data = request.get_json(silent=True) or {}
    step = data.get("step", "neutral")
    rep = int(data.get("rep", 1))
    res = pipeline.calibration.execute_step(step, rep)
    return jsonify(res)


@app.route("/calibrate/commit", methods=["POST"])
@require_token
def calibrate_commit():
    res = pipeline.calibration.commit()
    if res.get("ok"):
        # Push vision_params for newly activated profile
        pipeline.emit_status()
    return jsonify(res)


# -------------------------------------------------------------
# PROFILE ENDPOINTS (Section D, B2)
# -------------------------------------------------------------
@app.route("/profiles", methods=["GET"])
@require_token
def get_profiles():
    return jsonify({"profiles": profile_mgr.list_profiles()})


@app.route("/profile/<profile_id>", methods=["GET"])
@require_token
def get_profile(profile_id):
    p = profile_mgr.get_profile(profile_id)
    if not p:
        return jsonify({"ok": False, "error": f"Profile '{profile_id}' not found"}), 404
    return jsonify(p)


@app.route("/profile/<profile_id>", methods=["PUT"])
@require_token
def update_profile(profile_id):
    data = request.get_json(silent=True) or {}
    ok = profile_mgr.save_profile(profile_id, data)
    return jsonify({"ok": ok})


@app.route("/profile/<profile_id>/activate", methods=["POST"])
@require_token
def activate_profile(profile_id):
    p = profile_mgr.activate(profile_id)
    if not p:
        return jsonify({"ok": False, "error": f"Profile '{profile_id}' not found"}), 404

    # Update pipeline parameters
    ui_state, _ = pipeline.adapt.compute_ui_state(
        pipeline.effort.current_level, pipeline.effort.range_now, p
    )
    bus.broadcast(ui_state)
    pipeline.emit_status()
    return jsonify({"ok": True})


# -------------------------------------------------------------
# SAFETY ENDPOINTS (Section D, B4)
# -------------------------------------------------------------
@app.route("/pause", methods=["POST"])
@require_token
def pause_system():
    pipeline.safety.pause()
    return jsonify({"ok": True, "paused": pipeline.safety.paused, "locked": pipeline.safety.locked})


@app.route("/resume", methods=["POST"])
@require_token
def resume_system():
    pipeline.safety.resume()
    return jsonify({"ok": True, "paused": pipeline.safety.paused, "locked": pipeline.safety.locked})


@app.route("/lock", methods=["POST"])
@require_token
def lock_system():
    pipeline.safety.lock()
    return jsonify({"ok": True, "paused": pipeline.safety.paused, "locked": pipeline.safety.locked})


@app.route("/unlock", methods=["POST"])
@require_token
def unlock_system():
    pipeline.safety.unlock()
    return jsonify({"ok": True, "paused": pipeline.safety.paused, "locked": pipeline.safety.locked})


# -------------------------------------------------------------
# MODE & CHANNEL ENDPOINTS (Section D, B7, B8)
# -------------------------------------------------------------
@app.route("/mode", methods=["POST"])
@require_token
def set_mode():
    data = request.get_json(silent=True) or {}
    new_mode = data.get("mode", "flux")
    if new_mode not in ("flux", "static"):
        return jsonify({"ok": False, "error": "Mode must be 'flux' or 'static'"}), 400

    pipeline.adapt.set_mode(new_mode)
    profile = profile_mgr.active_profile
    ui_state, _ = pipeline.adapt.compute_ui_state(
        pipeline.effort.current_level, pipeline.effort.range_now, profile
    )
    bus.broadcast(ui_state)
    pipeline.emit_status()
    return jsonify({"ok": True, "mode": new_mode})


@app.route("/control-mode", methods=["POST"])
@require_token
def set_control_mode():
    data = request.get_json(silent=True) or {}
    mode = data.get("mode")
    if mode not in ("head", "speech", "mouse", "hybrid"):
        return jsonify({"ok": False, "error": "Mode must be head, speech, mouse, or hybrid"}), 400
    pipeline.control_mode = mode
    pipeline.emit_status()
    return jsonify({"ok": True, "mode": mode})


@app.route("/channel/accept", methods=["POST"])
@require_token
def accept_channel():
    data = request.get_json(silent=True) or {}
    channel = data.get("channel", "gesture")
    ok = pipeline.channels.accept_channel(channel)
    if not ok:
        return jsonify({"ok": False, "error": f"Invalid channel '{channel}'"}), 400

    pipeline.adapt.primary_channel = channel
    profile = profile_mgr.active_profile
    ui_state, _ = pipeline.adapt.compute_ui_state(
        pipeline.effort.current_level, pipeline.effort.range_now, profile
    )
    bus.broadcast(ui_state)
    return jsonify({"ok": True, "primary_channel": channel})


# -------------------------------------------------------------
# UNDO ENDPOINT (Section D, B9, G8)
# -------------------------------------------------------------
@app.route("/undo", methods=["POST"])
@require_token
def undo_action():
    res = pipeline.handle_undo()
    return jsonify(res)


# -------------------------------------------------------------
# BENCHMARK STORAGE ENDPOINTS (Section D, B10, Section H)
# -------------------------------------------------------------
@app.route("/bench/log", methods=["POST"])
@require_token
def bench_log():
    row_data = request.get_json(silent=True) or {}
    ok = bench_storage.log_trial(row_data)
    return jsonify({"ok": ok})


@app.route("/bench/export", methods=["GET"])
@require_token
def bench_export():
    session_id = request.args.get("session_id")
    csv_text = bench_storage.export_csv(session_id)
    return Response(csv_text, mimetype="text/csv", headers={"Content-Disposition": "attachment; filename=bench_export.csv"})


# -------------------------------------------------------------
# DEV TOOLS ENDPOINTS (Section D, B6, G7)
# -------------------------------------------------------------
@app.route("/dev/effort", methods=["POST"])
@require_token
def dev_effort():
    data = request.get_json(silent=True) or {}
    score = data.get("score")
    if score is not None:
        pipeline.effort.dev_score_override = float(score)
        pipeline.effort.simulated = True
    else:
        pipeline.effort.dev_score_override = None
        pipeline.effort.simulated = False
    return jsonify({"ok": True, "simulated": pipeline.effort.simulated})


@app.route("/dev/level", methods=["POST"])
@require_token
def dev_level():
    data = request.get_json(silent=True) or {}
    lvl = data.get("level")
    if lvl in ("fresh", "moderate", "high", "rest"):
        pipeline.effort.dev_level_override = lvl
    else:
        pipeline.effort.dev_level_override = None
    return jsonify({"ok": True, "level": pipeline.effort.current_level})


@app.route("/pointer/snap", methods=["POST"])
@require_token
def pointer_snap():
    """Adjust neutral shift so pointer lands at requested normalized coordinates."""
    data = request.get_json(silent=True) or {}
    nx = float(data.get("nx", 0.5))
    ny = float(data.get("ny", 0.5))

    # Shift neutral
    pipeline.adapt.neutral_shift["dx"] = round(nx - 0.5, 3)
    pipeline.adapt.neutral_shift["dy"] = round(ny - 0.5, 3)
    profile = profile_mgr.active_profile
    params = pipeline.adapt.compute_ui_state(pipeline.effort.current_level, pipeline.effort.range_now, profile)[0]
    pipeline.adapt._emit_vision_params(params["smoothing_alpha"], params["gain"], profile)
    return jsonify({"ok": True})


# -------------------------------------------------------------
# APP INITIALIZATION & CLI
# -------------------------------------------------------------
def create_app(source_type: str = "mock", replay_file: str = None, simulate_os: bool = False, camera_index: int = 0, dev_mode: bool = None):
    global pipeline, SERVER_TOKEN
    if dev_mode is True or os.environ.get("FLUX_DEV") == "1" or FLUX_DEV:
        SERVER_TOKEN = DEV_TOKEN
    if source_type == "mock":
        frame_source = MockFrameSource()
    elif source_type == "replay":
        if not replay_file or not os.path.exists(replay_file):
            print(f"[Warning] Replay file '{replay_file}' not found, falling back to mock source.")
            frame_source = MockFrameSource()
        else:
            frame_source = ReplayFrameSource(replay_file)
    elif source_type == "live":
        frame_source = LiveFrameSource(camera_index=camera_index)
    else:
        frame_source = MockFrameSource()

    pipeline = ProcessorPipeline(frame_source=frame_source, simulate_os=simulate_os)
    pipeline.start()
    return app


def main():
    parser = argparse.ArgumentParser(description="NeuroCursor / FLUX Unified Backend & Vision Server")
    parser.add_argument("--host", default=DEFAULT_HOST, help="Binding host (default 127.0.0.1)")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="Port (default 5000)")
    parser.add_argument("--source", default="live", choices=["live", "mock", "replay"], help="Input source: live (default webcam), mock, or replay")
    parser.add_argument("--camera-index", type=int, default=0, help="Webcam device index for live mode (default 0)")
    parser.add_argument("--replay-file", default=None, help="Path to JSONL file for replay source")
    parser.add_argument("--simulate", action="store_true", help="Run OS mouse control in simulation mode")
    parser.add_argument("--dev", action="store_true", default=True, help="Enable FLUX_DEV mode with fixed token (default True)")
    parser.add_argument("--no-dev", dest="dev", action="store_false", help="Disable FLUX_DEV mode")
    parser.add_argument("--open-browser", action="store_true", help="Automatically launch frontend in default browser")
    args = parser.parse_args()

    if args.dev:
        global SERVER_TOKEN
        SERVER_TOKEN = DEV_TOKEN

    app_instance = create_app(
        source_type=args.source,
        replay_file=args.replay_file,
        simulate_os=args.simulate,
        camera_index=args.camera_index
    )

    url = f"http://{args.host}:{args.port}"
    print(f"\n=======================================================")
    print(f"  NeuroCursor (FLUX) Server Online at {url}")
    print(f"  Frontend Interface: {url}/")
    print(f"  Security Token: {SERVER_TOKEN}")
    print(f"  SSE Stream: {url}/stream?token={SERVER_TOKEN}")
    print(f"  Source Mode: {args.source}")
    print(f"=======================================================\n")

    if args.open_browser:
        webbrowser.open(url)

    app_instance.run(host=args.host, port=args.port, threaded=True)


if __name__ == "__main__":
    main()
