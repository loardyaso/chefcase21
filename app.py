"""ตารางเคสนอก / เคสใน — Flask + SQLite

- ทุกคนเปิดดูได้ผ่านลิงก์ (อ่านอย่างเดียว)
- เฉพาะแอดมินที่ล็อกอินเท่านั้นที่แก้ไขและบันทึกได้ (ตรวจสิทธิ์ที่ฝั่งเซิร์ฟเวอร์)
- ข้อมูลเก็บใน SQLite ผู้ชมทุกคนเห็นข้อมูลชุดเดียวกัน
"""
import hmac
import json
import os
import re
import secrets
import sqlite3
import time
from datetime import datetime, timedelta, timezone

from flask import Flask, jsonify, render_template, request, session
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.security import check_password_hash, generate_password_hash

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get("DATABASE_PATH", os.path.join(BASE_DIR, "data", "case.db"))
ADMIN_ID = os.environ.get("ADMIN_ID", "admin")
INITIAL_PASSWORD = os.environ.get("ADMIN_PASSWORD", "1234")
_INITIAL_HASH = generate_password_hash(INITIAL_PASSWORD)

DEFAULT_STATE = {
    "rev": 1,
    "updatedAt": "",
    "names": [
        "Loard Yaso", "Mon Yooyenpensuk", "Mario Fates", "Iris Flower",
        "Candy Winnes", "Kori Paetha", "Ryu Healer", "Zoo Good",
        "Argrad Tummada", "Dream Noflowers", "Alex Paetha", "Kuma Smoking",
        "KenJi Arcobaleno", "Momay Nxluv", "Prikkhing Carden", "Pluto Boy",
    ],
    "inCount": 8,
    "caseDays": 30,
    "seed": "case-1",
    "overrides": {},
}

app = Flask(__name__)
if os.environ.get("TRUST_PROXY", "1") == "1":
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)


# ---------- ฐานข้อมูล ----------
def db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def kv_get(conn, key):
    row = conn.execute("SELECT value FROM kv WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else None


def kv_set(conn, key, value):
    conn.execute(
        "INSERT INTO kv(key, value) VALUES(?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )


def init_db():
    conn = db()
    with conn:
        conn.execute("CREATE TABLE IF NOT EXISTS kv (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        if kv_get(conn, "state") is None:
            kv_set(conn, "state", json.dumps(DEFAULT_STATE, ensure_ascii=False))
        if kv_get(conn, "secret") is None:
            kv_set(conn, "secret", secrets.token_hex(32))
        secret = kv_get(conn, "secret")
    conn.close()
    return secret


app.config.update(
    SECRET_KEY=os.environ.get("SECRET_KEY") or init_db(),
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("COOKIE_SECURE", "0") == "1",
    PERMANENT_SESSION_LIFETIME=timedelta(hours=8),
    MAX_CONTENT_LENGTH=512 * 1024,
)
init_db()


def load_state():
    conn = db()
    try:
        return json.loads(kv_get(conn, "state"))
    finally:
        conn.close()


# ---------- ตรวจข้อมูลที่ส่งมา ----------
OVERRIDE_KEY = re.compile(r"^\d{4}-\d{2}-\d{2}\|.{1,100}$")


def clean_state(data):
    if not isinstance(data, dict):
        raise ValueError("รูปแบบข้อมูลไม่ถูกต้อง")
    names, seen = [], set()
    for n in data.get("names", []):
        if not isinstance(n, str):
            raise ValueError("ชื่อไม่ถูกต้อง")
        n = n.strip()
        if n and n not in seen:
            if len(n) > 100:
                raise ValueError("ชื่อยาวเกินไป")
            seen.add(n)
            names.append(n)
    if not 1 <= len(names) <= 200:
        raise ValueError("ต้องมีรายชื่อ 1–200 คน")
    try:
        in_count = int(data.get("inCount"))
        case_days = int(data.get("caseDays"))
    except (TypeError, ValueError):
        raise ValueError("จำนวนไม่ถูกต้อง")
    in_count = max(0, min(in_count, len(names)))
    if not 1 <= case_days <= 31:
        raise ValueError("จำนวนวันที่มีเคสต้องอยู่ระหว่าง 1–31")
    seed = str(data.get("seed") or "case-1")[:60]
    overrides = {}
    raw = data.get("overrides") or {}
    if not isinstance(raw, dict) or len(raw) > 20000:
        raise ValueError("ข้อมูลการแก้ด้วยมือไม่ถูกต้อง")
    for k, v in raw.items():
        if OVERRIDE_KEY.match(k) and v in ("in", "out") and k.split("|", 1)[1] in seen:
            overrides[k] = v
    return {"names": names, "inCount": in_count, "caseDays": case_days,
            "seed": seed, "overrides": overrides}


# ---------- สิทธิ์แอดมิน ----------
_attempts = {}  # ip -> [เวลาที่ล็อกอินพลาด]


def too_many_attempts(ip):
    now = time.time()
    recent = [t for t in _attempts.get(ip, []) if now - t < 300]
    _attempts[ip] = recent
    return len(recent) >= 8


def admin_hash():
    conn = db()
    try:
        return kv_get(conn, "admin_hash") or _INITIAL_HASH
    finally:
        conn.close()


def is_admin():
    return session.get("admin") is True


def json_body():
    if not request.is_json:
        return None
    return request.get_json(silent=True)


def no_store(resp):
    resp.headers["Cache-Control"] = "no-store"
    return resp


@app.after_request
def security_headers(resp):
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    resp.headers.setdefault("Referrer-Policy", "same-origin")
    return resp


# ---------- เส้นทาง ----------
@app.get("/")
def index():
    return no_store(app.make_response(
        render_template("index.html", state=load_state(), admin=is_admin())))


@app.get("/healthz")
def healthz():
    return "ok"


@app.get("/api/state")
def api_state():
    return no_store(jsonify(load_state()))


@app.get("/api/me")
def api_me():
    return no_store(jsonify(admin=is_admin()))


@app.post("/api/login")
def api_login():
    body = json_body()
    if not isinstance(body, dict):
        return jsonify(error="รูปแบบคำขอไม่ถูกต้อง"), 415
    ip = request.remote_addr or "?"
    if too_many_attempts(ip):
        return jsonify(error="ลองผิดหลายครั้งเกินไป กรุณารอ 5 นาที"), 429
    uid = str(body.get("id", ""))
    pw = str(body.get("password", ""))
    ok_id = hmac.compare_digest(uid.encode(), ADMIN_ID.encode())
    ok_pw = check_password_hash(admin_hash(), pw)
    if ok_id and ok_pw:
        session.clear()
        session["admin"] = True
        session.permanent = True
        return jsonify(ok=True)
    _attempts.setdefault(ip, []).append(time.time())
    return jsonify(error="ID หรือรหัสผ่านไม่ถูกต้อง"), 401


@app.post("/api/logout")
def api_logout():
    session.clear()
    return jsonify(ok=True)


@app.post("/api/state")
def api_save_state():
    if not is_admin():
        return jsonify(error="ต้องเข้าสู่ระบบแอดมินก่อน"), 401
    body = json_body()
    if not isinstance(body, dict):
        return jsonify(error="รูปแบบคำขอไม่ถูกต้อง"), 415
    try:
        new = clean_state(body.get("state"))
    except ValueError as e:
        return jsonify(error=str(e)), 400
    conn = db()
    try:
        with conn:
            conn.execute("BEGIN IMMEDIATE")
            current = json.loads(kv_get(conn, "state"))
            expected = body.get("expectedRev")
            if expected is not None and expected != current.get("rev"):
                return jsonify(error="มีการแก้ไขจากที่อื่นไปก่อนแล้ว", state=current), 409
            new["rev"] = int(current.get("rev", 0)) + 1
            new["updatedAt"] = datetime.now(timezone.utc).isoformat()
            kv_set(conn, "state", json.dumps(new, ensure_ascii=False))
    finally:
        conn.close()
    return jsonify(new)


@app.post("/api/password")
def api_password():
    if not is_admin():
        return jsonify(error="ต้องเข้าสู่ระบบแอดมินก่อน"), 401
    body = json_body()
    if not isinstance(body, dict):
        return jsonify(error="รูปแบบคำขอไม่ถูกต้อง"), 415
    if not check_password_hash(admin_hash(), str(body.get("current", ""))):
        return jsonify(error="รหัสผ่านปัจจุบันไม่ถูกต้อง"), 400
    new = str(body.get("new", ""))
    if len(new) < 6:
        return jsonify(error="รหัสผ่านใหม่ต้องยาวอย่างน้อย 6 ตัวอักษร"), 400
    conn = db()
    try:
        with conn:
            kv_set(conn, "admin_hash", generate_password_hash(new))
    finally:
        conn.close()
    return jsonify(ok=True)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=False)
