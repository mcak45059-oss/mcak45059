"""Tiny Flask server for the Apex Films waitlist.

Run:  pip install -r requirements.txt && python waitlist_server.py
Then open http://localhost:5000
"""
import json
import os
import re
import time
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory

ROOT = Path(__file__).parent
WAITLIST_FILE = Path(os.environ.get("WAITLIST_FILE", ROOT / "waitlist.jsonl"))
PORT = int(os.environ.get("PORT", "5000"))
EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
ALLOWED = {"name", "email", "company", "project_type", "monthly_volume", "notes"}

app = Flask(__name__, static_folder=str(ROOT), static_url_path="")


@app.after_request
def cors(resp):
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
    resp.headers["Access-Control-Allow-Methods"] = "POST, OPTIONS"
    return resp


@app.route("/")
def index():
    return send_from_directory(str(ROOT), "index.html")


@app.route("/api/waitlist", methods=["POST", "OPTIONS"])
def waitlist():
    if request.method == "OPTIONS":
        return ("", 204)
    payload = request.get_json(silent=True) or {}
    if payload.get("website"):
        return jsonify(ok=True)  # silently drop honeypot hits
    email = (payload.get("email") or "").strip()
    name = (payload.get("name") or "").strip()
    project_type = (payload.get("project_type") or "").strip()
    if not name or not EMAIL_RE.match(email) or not project_type:
        return jsonify(ok=False, error="invalid"), 400

    entry = {k: (payload.get(k) or "").strip() for k in ALLOWED}
    entry["ts"] = int(time.time())
    entry["ip"] = request.headers.get("X-Forwarded-For", request.remote_addr or "")

    WAITLIST_FILE.parent.mkdir(parents=True, exist_ok=True)
    with WAITLIST_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return jsonify(ok=True)


if __name__ == "__main__":
    print(f"Apex Films waitlist server on http://localhost:{PORT}")
    print(f"Storing submissions to {WAITLIST_FILE}")
    app.run(host="0.0.0.0", port=PORT)
