# app.py — Taxi Shift Manager (чистая версия)
import os
import json
import base64
import shutil
import sqlite3
import time
import urllib.request
import urllib.parse
from datetime import datetime, date, timezone, timedelta
import pandas as pd
import streamlit as st
from passlib.hash import bcrypt

# ===== НАСТРОЙКИ =====
AUTH_DB = "users.db"
USERS_DIR = "users"
SESSION_FILE = "session.json"
SESSION_TIMEOUT = 7 * 24 * 60 * 60  # 7 дней
RATE_NAL = 0.78
RATE_CARD = 0.75
MOSCOW_TZ = timezone(timedelta(hours=3))
YADISK_API = "https://cloud-api.yandex.net/v1/disk"
YADISK_ROOT = "disk:/jet"
POPULAR_EXPENSES = [
    "🚗 Мойка", "💧 Омывайка", "🍔 Еда", "☕ Кофе", "🚬 Сигареты",
    "🔧 Мелкий ремонт", "🅿️ Парковка", "💰 Штраф", "🧴 Очиститель",
    "🔋 Зарядка", "🧰 Инструмент", "📱 Связь", "🚕 Аренда", "💊 Аптека"
]

def get_master_admin_pwd() -> str:
    try: return st.secrets.get("MASTER_ADMIN_PASSWORD", "")
    except: return ""

def is_master_admin() -> bool:
    return st.session_state.get("master_admin_auth", False)

# ===== CSS =====
def apply_css():
    st.markdown("""<style>
    .main > div { padding-left:.75rem !important; padding-right:.75rem !important; }
    .block-container { padding-top:5rem !important; padding-bottom:2rem !important; max-width:100% !important; }
    .stButton > button { width:100% !important; min-height:52px !important; font-size:1rem !important; border-radius:12px !important; font-weight:600 !important; }
    .stTextInput input, .stNumberInput input { font-size:1.1rem !important; min-height:48px !important; border-radius:10px !important; }
    [data-testid="metric-container"] { background:#f8fafc; border-radius:12px; padding:12px !important; border:1px solid #e2e8f0; }
    [data-testid="stSidebarNav"] { display:none !important; }
    div[data-testid="stDecoration"] { display:none !important; }
    footer { visibility:hidden; }
    h1 { font-size:1.5rem !important; } h2 { font-size:1.3rem !important; } h3 { font-size:1.1rem !important; }
    hr { margin:.5rem 0 !important; }
    </style>""", unsafe_allow_html=True)

# ===== СЕССИЯ =====
def save_session():
    # Не сохраняем сессию если пользователь не авторизован
    username = st.session_state.get("username")
    if not username:
        return
    try:
        with open(SESSION_FILE, "w", encoding="utf-8") as f:
            json.dump({
                "username": username,
                "session_start": st.session_state.get("session_start").isoformat()
                    if st.session_state.get("session_start") else None
            }, f)
    except Exception: pass

def load_session():
    try:
        if os.path.exists(SESSION_FILE):
            data = json.load(open(SESSION_FILE, "r", encoding="utf-8"))
            username = data.get("username")
            if not username:
                return None
            start = data.get("session_start")
            if start:
                dt = datetime.fromisoformat(start).replace(tzinfo=MOSCOW_TZ)
                if (datetime.now(MOSCOW_TZ) - dt).total_seconds() < SESSION_TIMEOUT:
                    return username
    except Exception: pass
    return None

def clear_session():
    try:
        if os.path.exists(SESSION_FILE): os.remove(SESSION_FILE)
    except Exception: pass

def init_session():
    if "session_start" not in st.session_state:
        st.session_state.session_start = datetime.now(MOSCOW_TZ)
    else:
        # Обновляем время при каждом заходе — сессия не истекает пока пользуются
        st.session_state.session_start = datetime.now(MOSCOW_TZ)
    # Сохраняем только если пользователь уже авторизован
    save_session()
    if (datetime.now(MOSCOW_TZ) - st.session_state.session_start).total_seconds() > SESSION_TIMEOUT:
        st.session_state.clear(); clear_session()
        st.warning("⏰ Сессия истекла"); st.rerun()

# ===== ПАПКИ =====
def ensure_users_dir(): os.makedirs(USERS_DIR, exist_ok=True)

def get_user_dir(username: str) -> str:
    safe = "".join(c for c in username if c.isalnum() or c in ("_", "-")) or "user"
    path = os.path.join(USERS_DIR, safe); os.makedirs(path, exist_ok=True); return path

def get_current_db_name() -> str:
    u = st.session_state.get("username")
    if not u: return "taxi_default.db"
    safe = "".join(c for c in u if c.isalnum() or c in ("_", "-"))
    return os.path.join(get_user_dir(u), f"taxi{safe}.db")

def get_backup_dir() -> str:
    path = os.path.join(get_user_dir(st.session_state.get("username", "unknown")), "backups")
    os.makedirs(path, exist_ok=True); return path

def get_temp_backup_path() -> str:
    u = st.session_state.get("username", "unknown")
    return os.path.join(get_user_dir(u), "temp_shift_backup.db")

def create_temp_backup():
    try:
        src = get_current_db_name()
        dst = get_temp_backup_path()
        if os.path.exists(src):
            shutil.copy2(src, dst)
    except Exception:
        pass

def delete_temp_backup():
    try:
        p = get_temp_backup_path()
        if os.path.exists(p):
            os.remove(p)
    except Exception:
        pass

def get_temp_backup_info():
    p = get_temp_backup_path()
    if not os.path.exists(p):
        return None
    try:
        conn = sqlite3.connect(p); c = conn.cursor()
        c.execute("SELECT id, date FROM shifts WHERE is_open=1 LIMIT 1")
        row = c.fetchone()
        if not row:
            c.execute("SELECT id, date FROM shifts ORDER BY id DESC LIMIT 1")
            row = c.fetchone()
        if row:
            shift_id, shift_date = row
            c.execute("SELECT COUNT(*), COALESCE(SUM(total),0) FROM orders WHERE shift_id=?", (shift_id,))
            cnt, total = c.fetchone()
            conn.close()
            return {"date": shift_date or "?", "orders": int(cnt or 0), "total": float(total or 0)}
        conn.close()
        return None
    except Exception:
        return None

def restore_from_temp_backup() -> bool:
    p = get_temp_backup_path()
    if not os.path.exists(p):
        return False
    try:
        dst = get_current_db_name()
        if os.path.exists(dst):
            shutil.copy2(dst, dst + ".pre_restore")
        shutil.copy2(p, dst)
        st.cache_data.clear()
        return True
    except Exception:
        return False

def check_db_has_data() -> bool:
    try:
        conn = get_db(); c = conn.cursor()
        c.execute("""SELECT COUNT(*) FROM shifts WHERE is_open=0
                     AND EXISTS (SELECT 1 FROM orders o WHERE o.shift_id=shifts.id)""")
        cnt = c.fetchone()[0] or 0
        conn.close()
        return cnt > 0
    except Exception:
        return False

# ===== БД =====
def check_and_create_tables():
    try:
        conn = sqlite3.connect(get_current_db_name()); c = conn.cursor()
        c.execute("""CREATE TABLE IF NOT EXISTS shifts (
            id INTEGER PRIMARY KEY AUTOINCREMENT, date TEXT NOT NULL, km INTEGER DEFAULT 0,
            fuel_liters REAL DEFAULT 0, fuel_price REAL DEFAULT 0,
            is_open INTEGER DEFAULT 1, opened_at TEXT, closed_at TEXT)""")
        c.execute("""CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT, shift_id INTEGER,
            type TEXT NOT NULL, amount REAL NOT NULL, tips REAL DEFAULT 0,
            commission REAL NOT NULL, total REAL NOT NULL,
            beznal_added REAL DEFAULT 0, order_time TEXT)""")
        c.execute("""CREATE TABLE IF NOT EXISTS extra_expenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT, shift_id INTEGER,
            amount REAL DEFAULT 0, description TEXT, created_at TEXT)""")
        c.execute("""CREATE TABLE IF NOT EXISTS accumulated_beznal (
            id INTEGER PRIMARY KEY AUTOINCREMENT, driver_id INTEGER DEFAULT 1,
            total_amount REAL DEFAULT 0, last_updated TEXT)""")
        c.execute("""CREATE TABLE IF NOT EXISTS beznal_payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT, amount REAL NOT NULL,
            payment_date TEXT NOT NULL, note TEXT DEFAULT '', created_at TEXT)""")
        c.execute("""CREATE TABLE IF NOT EXISTS user_profile (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            driver_name TEXT DEFAULT '', driver_number TEXT DEFAULT '',
            photo_base64 TEXT DEFAULT '', name_font_size INTEGER DEFAULT 28,
            updated_at TEXT)""")
        c.execute("SELECT id FROM accumulated_beznal WHERE driver_id=1")
        if not c.fetchone():
            c.execute("INSERT INTO accumulated_beznal (driver_id,total_amount,last_updated) VALUES (1,0,?)",
                      (datetime.now(MOSCOW_TZ).strftime("%Y-%m-%d %H:%M:%S"),))
        conn.commit(); conn.close()
    except Exception as e: st.error(f"❌ Ошибка БД: {e}")

def get_db(): check_and_create_tables(); return sqlite3.connect(get_current_db_name())

# ===== АВТОРИЗАЦИЯ =====
def init_auth_db():
    conn = sqlite3.connect(AUTH_DB); c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT NOT NULL UNIQUE,
        password_hash TEXT NOT NULL, created_at TEXT)""")
    conn.commit(); conn.close()

def hash_pw(p: str) -> str: return bcrypt.hash(p.strip().encode("utf-8")[:72])
def verify_pw(p: str, h: str) -> bool:
    try: return bcrypt.verify(p.strip().encode("utf-8")[:72], h)
    except: return False

def register_user(u: str, p: str) -> bool:
    u = u.strip()
    if not u or not p: return False
    ensure_users_dir(); init_auth_db()
    conn = sqlite3.connect(AUTH_DB); c = conn.cursor()
    try:
        c.execute("INSERT INTO users (username,password_hash,created_at) VALUES (?,?,?)",
                  (u, hash_pw(p), datetime.now(MOSCOW_TZ).strftime("%Y-%m-%d")))
        conn.commit()
        db = get_current_db_name()
        if os.path.exists(db): os.remove(db)
        check_and_create_tables(); return True
    except: return False
    finally: conn.close()

def authenticate_user(u: str, p: str) -> bool:
    init_auth_db(); conn = sqlite3.connect(AUTH_DB); c = conn.cursor()
    c.execute("SELECT password_hash FROM users WHERE username=?", (u.strip(),))
    row = c.fetchone(); conn.close()
    return verify_pw(p, row[0]) if row else False

def get_all_users() -> list:
    init_auth_db(); conn = sqlite3.connect(AUTH_DB); c = conn.cursor()
    c.execute("SELECT username, created_at FROM users ORDER BY created_at DESC")
    rows = c.fetchall(); conn.close()
    return [{"username": r[0], "created": r[1]} for r in rows]

def change_password(u: str, new_p: str) -> bool:
    conn = sqlite3.connect(AUTH_DB); c = conn.cursor()
    try:
        c.execute("UPDATE users SET password_hash=? WHERE username=?", (hash_pw(new_p), u))
        conn.commit(); return c.rowcount > 0
    except: return False
    finally: conn.close()

def delete_user(u: str):
    conn = sqlite3.connect(AUTH_DB); c = conn.cursor()
    c.execute("DELETE FROM users WHERE username=?", (u,)); conn.commit(); conn.close()

# ===== ПРОФИЛЬ =====
def get_user_profile() -> dict:
    conn = get_db(); c = conn.cursor()
    c.execute("SELECT driver_name,driver_number,photo_base64,name_font_size FROM user_profile LIMIT 1")
    row = c.fetchone(); conn.close()
    if row: return {"name": row[0] or "", "number": row[1] or "",
                    "photo": row[2] or "", "font_size": int(row[3] or 28)}
    return {"name": "", "number": "", "photo": "", "font_size": 28}

def save_user_profile(name: str, number: str, photo_b64: str, font_size: int):
    conn = get_db(); c = conn.cursor(); now = datetime.now(MOSCOW_TZ).strftime("%Y-%m-%d %H:%M:%S")
    c.execute("SELECT id FROM user_profile LIMIT 1")
    if c.fetchone():
        if photo_b64:
            c.execute("UPDATE user_profile SET driver_name=?,driver_number=?,photo_base64=?,name_font_size=?,updated_at=?",
                      (name, number, photo_b64, font_size, now))
        else:
            c.execute("UPDATE user_profile SET driver_name=?,driver_number=?,name_font_size=?,updated_at=? WHERE 1",
                      (name, number, font_size, now))
    else:
        c.execute("INSERT INTO user_profile (driver_name,driver_number,photo_base64,name_font_size,updated_at) VALUES (?,?,?,?,?)",
                  (name, number, photo_b64, font_size, now))
    conn.commit(); conn.close()

def delete_user_photo():
    conn = get_db(); c = conn.cursor()
    c.execute("UPDATE user_profile SET photo_base64='' WHERE 1"); conn.commit(); conn.close()

# ===== СМЕНЫ =====
def get_open_shift():
    conn = get_db(); c = conn.cursor()
    c.execute("SELECT id,date FROM shifts WHERE is_open=1 LIMIT 1")
    row = c.fetchone(); conn.close(); return row

def open_shift(date_str: str) -> int:
    conn = get_db(); c = conn.cursor()
    c.execute("INSERT INTO shifts (date,is_open,opened_at) VALUES (?,1,?)",
              (date_str, datetime.now(MOSCOW_TZ).strftime("%Y-%m-%d %H:%M:%S")))
    sid = c.lastrowid; conn.commit(); conn.close(); return sid

def close_shift_db(shift_id: int, km: int, liters: float, fuel_price: float):
    conn = get_db(); c = conn.cursor()
    c.execute("UPDATE shifts SET is_open=0,km=?,fuel_liters=?,fuel_price=?,closed_at=? WHERE id=?",
              (km, liters, fuel_price, datetime.now(MOSCOW_TZ).strftime("%Y-%m-%d %H:%M:%S"), shift_id))
    conn.commit(); conn.close()

# ===== БЕЗНАЛ =====
def get_accumulated_beznal() -> float:
    conn = get_db(); c = conn.cursor()
    c.execute("SELECT total_amount FROM accumulated_beznal WHERE driver_id=1")
    row = c.fetchone(); conn.close(); return float(row[0]) if row and row[0] is not None else 0.0

def set_accumulated_beznal(amount: float):
    conn = get_db(); c = conn.cursor()
    c.execute("UPDATE accumulated_beznal SET total_amount=?,last_updated=? WHERE driver_id=1",
              (amount, datetime.now(MOSCOW_TZ).strftime("%Y-%m-%d %H:%M:%S")))
    conn.commit(); conn.close()

def add_beznal_payment(amount: float, payment_date: str, note: str = ""):
    conn = get_db(); c = conn.cursor()
    try:
        c.execute("INSERT INTO beznal_payments (amount,payment_date,note,created_at) VALUES (?,?,?,?)",
                  (amount, payment_date, note, datetime.now(MOSCOW_TZ).strftime("%Y-%m-%d %H:%M:%S")))
        c.execute("UPDATE accumulated_beznal SET total_amount=total_amount-?,last_updated=? WHERE driver_id=1",
                  (amount, datetime.now(MOSCOW_TZ).strftime("%Y-%m-%d %H:%M:%S")))
        conn.commit()
    except Exception as e: conn.rollback(); raise e
    finally: conn.close()

def get_beznal_payments() -> list:
    conn = get_db(); c = conn.cursor()
    c.execute("SELECT id,amount,payment_date,note FROM beznal_payments ORDER BY payment_date DESC,id DESC")
    rows = c.fetchall(); conn.close()
    return [{"id": r[0], "amount": r[1], "date": r[2], "note": r[3] or ""} for r in rows]

def delete_beznal_payment(pid: int):
    conn = get_db(); c = conn.cursor()
    try:
        c.execute("SELECT amount FROM beznal_payments WHERE id=?", (pid,))
        row = c.fetchone()
        if row:
            c.execute("DELETE FROM beznal_payments WHERE id=?", (pid,))
            c.execute("UPDATE accumulated_beznal SET total_amount=total_amount+?,last_updated=? WHERE driver_id=1",
                      (row[0], datetime.now(MOSCOW_TZ).strftime("%Y-%m-%d %H:%M:%S")))
            conn.commit()
    except Exception as e: conn.rollback(); raise e
    finally: conn.close()

# ===== ЗАКАЗЫ =====
def add_order_and_update_beznal(shift_id, otype, amount, tips, commission, total, beznal_added, order_time):
    conn = get_db(); c = conn.cursor()
    try:
        c.execute("INSERT INTO orders (shift_id,type,amount,tips,commission,total,beznal_added,order_time) VALUES (?,?,?,?,?,?,?,?)",
                  (shift_id, otype, amount, tips, commission, total, beznal_added, order_time))
        c.execute("UPDATE accumulated_beznal SET total_amount=total_amount+?,last_updated=? WHERE driver_id=1",
                  (beznal_added, datetime.now(MOSCOW_TZ).strftime("%Y-%m-%d %H:%M:%S")))
        conn.commit()
    except Exception as e: conn.rollback(); raise e
    finally: conn.close()

def delete_order_and_update_beznal(order_id):
    conn = get_db(); c = conn.cursor()
    try:
        c.execute("SELECT beznal_added FROM orders WHERE id=?", (order_id,))
        row = c.fetchone()
        if row:
            c.execute("DELETE FROM orders WHERE id=?", (order_id,))
            c.execute("UPDATE accumulated_beznal SET total_amount=total_amount-?,last_updated=? WHERE driver_id=1",
                      (row[0] or 0.0, datetime.now(MOSCOW_TZ).strftime("%Y-%m-%d %H:%M:%S")))
            conn.commit()
    except Exception as e: conn.rollback(); raise e
    finally: conn.close()

def update_order_and_adjust_beznal(order_id, otype, amount, tips, commission, total, beznal_added):
    conn = get_db(); c = conn.cursor()
    try:
        c.execute("SELECT beznal_added FROM orders WHERE id=?", (order_id,))
        old = c.fetchone(); old_bez = old[0] if old else 0.0
        c.execute("UPDATE orders SET type=?,amount=?,tips=?,commission=?,total=?,beznal_added=? WHERE id=?",
                  (otype, amount, tips, commission, total, beznal_added, order_id))
        c.execute("UPDATE accumulated_beznal SET total_amount=total_amount+?,last_updated=? WHERE driver_id=1",
                  (beznal_added - old_bez, datetime.now(MOSCOW_TZ).strftime("%Y-%m-%d %H:%M:%S")))
        conn.commit()
    except Exception as e: conn.rollback(); raise e
    finally: conn.close()

def get_shift_totals(shift_id):
    conn = get_db(); c = conn.cursor()
    c.execute("SELECT type,SUM(total-tips) FROM orders WHERE shift_id=? GROUP BY type", (shift_id,))
    by_type = dict(c.fetchall())
    c.execute("SELECT SUM(tips) FROM orders WHERE shift_id=?", (shift_id,))
    by_type["чаевые"] = c.fetchone()[0] or 0.0; conn.close(); return by_type

def get_shift_orders(shift_id):
    conn = get_db(); c = conn.cursor()
    c.execute("SELECT id,type,amount,tips,commission,total,beznal_added,order_time FROM orders WHERE shift_id=? ORDER BY id DESC", (shift_id,))
    rows = c.fetchall(); conn.close(); return rows

def get_last_fuel_params():
    conn = get_db(); c = conn.cursor()
    c.execute("SELECT fuel_liters,km,fuel_price FROM shifts WHERE is_open=0 AND km>0 AND fuel_price>0 ORDER BY closed_at DESC LIMIT 1")
    row = c.fetchone(); conn.close()
    if row and row[0] and row[1]: return (row[0]/row[1])*100, float(row[2] or 55.0)
    return 8.0, 55.0

# ===== РАСХОДЫ =====
def add_extra_expense(shift_id, amount, description):
    conn = get_db(); c = conn.cursor()
    c.execute("INSERT INTO extra_expenses (shift_id,amount,description,created_at) VALUES (?,?,?,?)",
              (shift_id, amount, description, datetime.now(MOSCOW_TZ).strftime("%Y-%m-%d %H:%M:%S")))
    conn.commit(); conn.close()

def get_extra_expenses(shift_id):
    conn = get_db(); c = conn.cursor()
    c.execute("SELECT id,amount,description FROM extra_expenses WHERE shift_id=? ORDER BY id", (shift_id,))
    rows = c.fetchall(); conn.close()
    return [{"id": r[0], "amount": r[1] or 0.0, "description": r[2] or ""} for r in rows]

def delete_extra_expense(eid):
    conn = get_db(); c = conn.cursor()
    c.execute("DELETE FROM extra_expenses WHERE id=?", (eid,)); conn.commit(); conn.close()

def get_total_extra_expenses(shift_id) -> float:
    conn = get_db(); c = conn.cursor()
    c.execute("SELECT SUM(amount) FROM extra_expenses WHERE shift_id=?", (shift_id,))
    row = c.fetchone(); conn.close(); return row[0] or 0.0

# ===== ЛОКАЛЬНЫЕ БЭКАПЫ =====
def create_backup() -> str:
    backup_dir = get_backup_dir(); ts = datetime.now(MOSCOW_TZ).strftime("%Y%m%d_%H%M%S")
    path = os.path.join(backup_dir, f"taxi_{st.session_state.get('username','u')}_{ts}.db")
    shutil.copy2(get_current_db_name(), path); return path

def list_backups():
    backup_dir = get_backup_dir()
    if not os.path.exists(backup_dir): return []
    result = []
    for f in os.listdir(backup_dir):
        if f.endswith(".db"):
            path = os.path.join(backup_dir, f); stat = os.stat(path)
            result.append({"name": f, "path": path,
                           "time": datetime.fromtimestamp(stat.st_mtime),
                           "size": stat.st_size / 1024})
    return sorted(result, key=lambda x: x["time"], reverse=True)

def restore_from_backup(backup_path: str):
    if not os.path.exists(backup_path): raise FileNotFoundError(f"Не найден: {backup_path}")
    create_backup(); shutil.copy2(backup_path, get_current_db_name()); st.cache_data.clear()

def upload_and_restore_backup(file) -> bool:
    if not file: return False
    db_path = get_current_db_name()
    try:
        if os.path.exists(db_path): create_backup()
    except Exception: pass
    raw = file.read()
    with open(db_path, "wb") as f: f.write(raw)
    try:
        conn = sqlite3.connect(db_path); conn.execute("SELECT name FROM sqlite_master LIMIT 1"); conn.close()
    except Exception as e: raise ValueError(f"Не SQLite: {e}")
    st.cache_data.clear(); return True

# ===== ЯНДЕКС ДИСК =====
def get_yadisk_token() -> str:
    token = ""
    try: token = st.secrets.get("YADISK_TOKEN", "")
    except Exception: pass
    return str(st.session_state.get("yadisk_token", token)).strip()

def _yadisk_user_dir(username: str) -> str:
    safe = "".join(c for c in username if c.isalnum() or c in ("_","-")) or "user"
    return f"{YADISK_ROOT}/{safe}"

def _yadisk_backup_path(username: str, date_str: str) -> str:
    return f"{_yadisk_user_dir(username)}/backup_{date_str}.db"

def _yadisk_api(method: str, url: str, token: str, data=None, params: dict = None, timeout: int = 30) -> tuple:
    if params: url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"OAuth {token}")
    req.add_header("Accept", "application/json")
    if data: req.add_header("Content-Type", "application/octet-stream")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            try: return resp.status, json.loads(raw)
            except: return resp.status, raw
    except Exception as e:
        code = getattr(e, "code", 0)
        try: return code, json.loads(e.read())
        except: return code, {"message": str(e)}

def yadisk_check_token(token: str) -> bool:
    if not token: return False
    try:
        req = urllib.request.Request("https://cloud-api.yandex.net/v1/disk",
                                     headers={"Authorization": f"OAuth {token}"})
        with urllib.request.urlopen(req, timeout=5) as r: return r.status == 200
    except: return False

def yadisk_upload_backup(token: str, shift_date: str = None) -> bool:
    db_path = get_current_db_name()
    if not os.path.exists(db_path): st.error("❌ БД не найдена"); return False
    if not token: st.error("❌ Нет токена"); return False
    username = st.session_state.get("username", "unknown")
    date_str = shift_date or datetime.now(MOSCOW_TZ).strftime("%Y-%m-%d")
    remote_path = _yadisk_backup_path(username, date_str)
    for folder in [YADISK_ROOT, _yadisk_user_dir(username)]:
        _yadisk_api("PUT", f"{YADISK_API}/resources", token, params={"path": folder})
    status, resp = _yadisk_api("GET", f"{YADISK_API}/resources/upload", token,
                                params={"path": remote_path, "overwrite": "true"})
    if status != 200:
        msg = resp.get("message", str(resp)) if isinstance(resp, dict) else str(resp)
        st.error(f"❌ Ошибка получения URL (код {status}): {msg}"); return False
    upload_url = resp.get("href") if isinstance(resp, dict) else None
    if not upload_url: st.error("❌ Нет URL загрузки"); return False
    with open(db_path, "rb") as f: db_bytes = f.read()
    req = urllib.request.Request(upload_url, data=db_bytes, method="PUT")
    req.add_header("Content-Type", "application/octet-stream")
    try:
        with urllib.request.urlopen(req, timeout=120) as r: return r.status in (200,201,202,204)
    except Exception as e:
        st.error(f"❌ Ошибка загрузки: {e}"); return False

def yadisk_list_backups(token: str) -> list:
    if not token: return []
    username = st.session_state.get("username", "unknown")
    user_dir = _yadisk_user_dir(username)
    status, resp = _yadisk_api("GET", f"{YADISK_API}/resources", token,
                                params={"path": user_dir, "limit": 100,
                                        "fields": "_embedded.items.name,_embedded.items.path,_embedded.items.modified,_embedded.items.size"})
    if status != 200: return []
    items = resp.get("_embedded", {}).get("items", []) if isinstance(resp, dict) else []
    result = []
    for item in items:
        if item.get("name", "").endswith(".db"):
            modified = item.get("modified", "")
            try:
                dt = datetime.fromisoformat(modified.replace("Z", "+00:00"))
                modified = dt.astimezone(MOSCOW_TZ).strftime("%d.%m.%Y %H:%M")
            except: pass
            result.append({"name": item["name"], "path": item["path"],
                           "modified": modified, "size_kb": (item.get("size") or 0) // 1024})
    return sorted(result, key=lambda x: x["name"], reverse=True)

def yadisk_download_backup(token: str, remote_path: str = None) -> bool:
    if not token: st.error("❌ Нет токена"); return False
    if not remote_path:
        backups = yadisk_list_backups(token)
        if not backups: st.warning("⚠️ Нет бэкапов"); return False
        remote_path = backups[0]["path"]
    status, resp = _yadisk_api("GET", f"{YADISK_API}/resources/download", token,
                                params={"path": remote_path})
    if status == 404: st.warning("⚠️ Файл не найден"); return False
    if status != 200:
        msg = resp.get("message", str(resp)) if isinstance(resp, dict) else str(resp)
        st.error(f"❌ Ошибка скачивания (код {status}): {msg}"); return False
    download_url = resp.get("href") if isinstance(resp, dict) else None
    if not download_url: st.error("❌ Нет URL скачивания"); return False
    try:
        with urllib.request.urlopen(download_url, timeout=120) as r: db_bytes = r.read()
    except Exception as e: st.error(f"❌ Ошибка: {e}"); return False
    if len(db_bytes) < 100: st.error("❌ Файл слишком мал"); return False
    db_path = get_current_db_name()
    try:
        if os.path.exists(db_path): create_backup()
    except: pass
    with open(db_path, "wb") as f: f.write(db_bytes)
    try:
        conn = sqlite3.connect(db_path); conn.execute("SELECT name FROM sqlite_master LIMIT 1"); conn.close()
    except Exception as e: raise ValueError(f"Файл повреждён: {e}")
    st.cache_data.clear(); return True

def yadisk_delete_backup(token: str, remote_path: str) -> bool:
    if not token or not remote_path: return False
    url = f"{YADISK_API}/resources?path={urllib.parse.quote(remote_path)}&permanently=true"
    req = urllib.request.Request(url, method="DELETE")
    req.add_header("Authorization", f"OAuth {token}")
    try:
        with urllib.request.urlopen(req, timeout=15) as r: return r.status in (200,204)
    except Exception as e:
        return getattr(e, "code", 0) in (200, 204)

def yadisk_cleanup_old_backups(token: str, keep: int = 3, min_age_days: int = 7) -> int:
    """
    Удаляет старые бэкапы на Яндекс Диске.
    Правило: если бэкап старше min_age_days И есть как минимум keep более новых — удалить.
    Всегда оставляет keep самых свежих бэкапов независимо от возраста.
    Возвращает количество удалённых файлов.
    """
    if not token: return 0
    backups = yadisk_list_backups(token)
    if len(backups) <= keep: return 0  # нечего удалять

    # backups отсортированы по имени desc (новые первые)
    # Те что за пределами keep последних — кандидаты на удаление
    candidates = backups[keep:]
    now = datetime.now(MOSCOW_TZ)
    deleted = 0

    for b in candidates:
        # Парсим дату из имени файла: backup_YYYY-MM-DD.db
        try:
            name = b["name"]  # например backup_2026-03-01.db
            date_part = name.replace("backup_", "").replace(".db", "")  # 2026-03-01
            backup_dt = datetime.strptime(date_part, "%Y-%m-%d").replace(tzinfo=MOSCOW_TZ)
            age_days = (now - backup_dt).days
        except Exception:
            continue  # если не можем распарсить дату — не трогаем

        if age_days >= min_age_days:
            if yadisk_delete_backup(token, b["path"]):
                deleted += 1

    return deleted

# ===== QR-КОД ЧЕКА =====
def parse_qr_text(text: str) -> dict:
    result = {"amount": None, "date": None, "raw": text.strip()}
    if not text:
        return result
    try:
        import urllib.parse as _up
        qr = text.strip()
        if "?" in qr:
            qr = qr.split("?", 1)[1]
        params = dict(_up.parse_qsl(qr, keep_blank_values=True))
        if "s" in params:
            result["amount"] = float(params["s"].replace(",", "."))
        if "t" in params:
            t = params["t"]
            if len(t) >= 8:
                result["date"] = f"{t[0:4]}-{t[4:6]}-{t[6:8]}"
    except Exception:
        pass
    return result

def decode_qr_image(image_bytes: bytes) -> str:
    try:
        from PIL import Image
        from pyzbar.pyzbar import decode
        import io
        img = Image.open(io.BytesIO(image_bytes))
        decoded = decode(img)
        if decoded:
            return decoded[0].data.decode("utf-8")
    except ImportError:
        return "__no_pyzbar__"
    except Exception:
        pass
    return ""

def render_profile_header(shift_id=None):
    profile = get_user_profile()
    acc = get_accumulated_beznal()
    font_size = profile.get("font_size", 28)
    driver_name = profile.get("name") or st.session_state.get("username", "")
    driver_number = profile.get("number", "")
    photo_b64 = profile.get("photo", "")

    # Считаем заказы текущей смены если она открыта
    order_count = None
    if shift_id is not None:
        conn = get_db(); c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM orders WHERE shift_id=?", (shift_id,))
        order_count = c.fetchone()[0] or 0
        conn.close()

    col_photo, col_info, col_beznal = st.columns([1, 3, 2])
    with col_photo:
        if photo_b64:
            st.markdown(
                f'<img src="data:image/jpeg;base64,{photo_b64}" '
                f'style="width:70px;height:70px;border-radius:50%;object-fit:cover;margin-top:4px;">',
                unsafe_allow_html=True)
        else:
            st.markdown(
                '<div style="width:70px;height:70px;border-radius:50%;background:#e2e8f0;'
                'display:flex;align-items:center;justify-content:center;font-size:2rem;">👤</div>',
                unsafe_allow_html=True)
    with col_info:
        display_number = driver_number if driver_number else "—"
        st.markdown(
            f"<div style='display:flex;gap:32px;align-items:flex-start;'>"
            f"<div>"
            f"<div style='color:#94a3b8;font-size:0.78rem;text-transform:uppercase;letter-spacing:.06em;margin-bottom:3px;'>🚕 Водитель</div>"
            f"<div style='font-size:{font_size}px;font-weight:700;line-height:1.2;'>{driver_name}</div>"
            f"</div>"
            f"<div>"
            f"<div style='color:#94a3b8;font-size:0.78rem;text-transform:uppercase;letter-spacing:.06em;margin-bottom:3px;'>📡 Позывной</div>"
            f"<div style='font-size:{font_size}px;font-weight:700;line-height:1.2;'>{display_number}</div>"
            f"</div>"
            f"</div>",
            unsafe_allow_html=True)
    with col_beznal:
        if order_count is not None:
            c1, c2 = st.columns(2)
            c1.metric("💳 Безнал", f"{acc:.0f} ₽")
            c2.metric("📦 Заказов", order_count)
        else:
            st.metric("💳 Безнал", f"{acc:.0f} ₽")

# ===== ПРОВЕРКА ВОССТАНОВЛЕНИЯ ПРИ СТАРТЕ =====
def check_and_offer_restore():
    """Один раз после логина — предлагает восстановить если БД пуста."""
    if st.session_state.get("restore_check_done"):
        return

    has_data = check_db_has_data()
    if has_data:
        st.session_state["restore_check_done"] = True
        return

    temp_info = get_temp_backup_info()
    token = get_yadisk_token()

    if not temp_info and not token:
        st.session_state["restore_check_done"] = True
        return

    if temp_info:
        d = temp_info["date"]
        n = temp_info["orders"]
        s = temp_info["total"]
        msg = ("⚠️ **Обнаружен бэкап незавершённой смены** от " + str(d) +
               " · " + str(n) + " заказ(ов) · " + str(int(s)) + " ₽ — Похоже, данные были потеряны. Восстановить?")
        st.warning(msg)
        c1, c2, c3 = st.columns(3)
        if c1.button("✅ Восстановить (temp)", use_container_width=True, type="primary", key="rb_temp"):
            if restore_from_temp_backup():
                st.session_state["restore_check_done"] = True
                st.success("✅ Данные смены восстановлены!")
                st.rerun()
            else:
                st.error("❌ Не удалось восстановить")
        if token:
            if c2.button("☁️ С Яндекс Диска", use_container_width=True, key="rb_yd"):
                with st.spinner("Загружаю..."):
                    try:
                        if yadisk_download_backup(token):
                            delete_temp_backup()
                            st.session_state["restore_check_done"] = True
                            st.success("✅ Восстановлено с Яндекс Диска!")
                            st.rerun()
                    except Exception as e:
                        st.error(f"❌ {e}")
        if c3.button("✖️ Пропустить", use_container_width=True, key="rb_skip"):
            st.session_state["restore_check_done"] = True
            st.rerun()
        st.stop()

    elif token:
        yd_backups = yadisk_list_backups(token)
        if yd_backups:
            latest = yd_backups[0]
            latest = yd_backups[0]
            yd_msg = ("⚠️ **База данных пуста.** Найден бэкап на Яндекс Диске: **" +
                      latest["name"] + "** (" + latest["modified"] + ") — Восстановить?")
            st.warning(yd_msg)
            c1, c2 = st.columns(2)
            if c1.button("✅ Восстановить с Яндекс Диска", use_container_width=True, type="primary", key="rb_yd2"):
                with st.spinner("Загружаю..."):
                    try:
                        if yadisk_download_backup(token):
                            st.session_state["restore_check_done"] = True
                            st.success("✅ Восстановлено!")
                            st.rerun()
                    except Exception as e:
                        st.error(f"❌ {e}")
            if c2.button("✖️ Пропустить", use_container_width=True, key="rb_skip2"):
                st.session_state["restore_check_done"] = True
                st.rerun()
            st.stop()
        else:
            st.session_state["restore_check_done"] = True

# ===== UI: ВХОД =====
def show_login_page():
    st.markdown("""
    <div style="text-align:center;padding:2rem 0 1rem;">
        <div style="font-size:4rem;">🚕</div>
        <h1 style="margin:0;">Taxi Shift Manager</h1>
        <p style="color:#64748b;">Учёт смен и доходов</p>
    </div>""", unsafe_allow_html=True)
    u = st.text_input("👤 Логин", placeholder="Введите логин")
    p = st.text_input("🔑 Пароль", type="password", placeholder="Введите пароль")
    c1, c2 = st.columns(2)
    with c1:
        if st.button("🚀 Войти", use_container_width=True, type="primary"):
            if authenticate_user(u, p):
                st.session_state.username = u.strip()
                st.session_state.page = "main"
                st.session_state.session_start = datetime.now(MOSCOW_TZ)
                save_session()
                st.rerun()
            else: st.error("❌ Неверный логин или пароль")
    with c2:
        if st.button("➕ Регистрация", use_container_width=True):
            if register_user(u, p): st.success("✅ Зарегистрирован! Войдите.")
            else: st.error("❌ Логин занят или ошибка")

# ===== UI: ГЛАВНАЯ =====
def show_main_page():
    check_and_create_tables()
    open_shift_data = get_open_shift()

    if not open_shift_data:
        render_profile_header()  # без счётчика — смены нет
        st.info("ℹ️ Нет открытой смены")
        with st.expander("📅 Открыть смену", expanded=True):
            selected_date = st.date_input("📅 Дата", value=date.today())
            if st.button("✅ Открыть смену", use_container_width=True, type="primary"):
                open_shift(selected_date.strftime("%Y-%m-%d")); st.rerun()
        return

    shift_id, date_str = open_shift_data
    render_profile_header(shift_id=shift_id)  # со счётчиком заказов

    # ===== ПРОВЕРКА ДЛИТЕЛЬНОСТИ СМЕНЫ =====
    conn_check = get_db()
    c_check = conn_check.cursor()
    c_check.execute("SELECT opened_at FROM shifts WHERE id=?", (shift_id,))
    row_check = c_check.fetchone()
    conn_check.close()
    if row_check and row_check[0]:
        try:
            opened_at = datetime.strptime(row_check[0], "%Y-%m-%d %H:%M:%S").replace(tzinfo=MOSCOW_TZ)
            hours_open = (datetime.now(MOSCOW_TZ) - opened_at).total_seconds() / 3600
            if hours_open > 12:
                st.warning(f"⚠️ Смена открыта **{hours_open:.0f} ч** — не забудьте закрыть смену!")
            elif hours_open > 10:
                st.info(f"ℹ️ Смена идёт {hours_open:.0f} ч")
        except Exception:
            pass

    st.success(f"✅ Смена: **{date_str}**")

    # Флаг сброса — очищаем ДО создания виджетов
    if st.session_state.pop("reset_order_fields", False):
        for k in ["order_amount", "order_tips"]:
            st.session_state.pop(k, None)

    with st.expander("➕ Добавить заказ", expanded=True):
        col1, col2 = st.columns([3, 2])
        with col1:
            amount_str = st.text_input("💰 Сумма чеком (₽)", placeholder="650", key="order_amount")
        with col2:
            order_type = st.selectbox("💳 Тип", ["нал", "карта"], key="order_type")

        tips_str = st.text_input("💡 Чаевые (₽)", placeholder="0", key="order_tips")
        # Предпросмотр
        try:
            pa = float(amount_str.replace(",", ".")) if amount_str else 0.0
            pt = float(tips_str.replace(",", ".")) if tips_str else 0.0
            if pa > 0:
                if order_type == "нал":
                    pc = pa * (1 - RATE_NAL)
                    st.caption(f"📊 Комиссия: **{pc:.0f} ₽** | На руки: **{pa + pt:.0f} ₽** | Безнал: **{-pc:+.0f} ₽**")
                else:
                    pf = pa * RATE_CARD
                    st.caption(f"📊 Комиссия: **{pa - pf:.0f} ₽** | На руки: **{pf + pt:.0f} ₽** | Безнал: **+{pf:.0f} ₽**")
        except: pass

        if st.button("✅ Добавить заказ", use_container_width=True, type="primary", key="btn_add_order"):
            try:
                amount = float(str(amount_str).replace(",", ".").strip())
                tips = float(str(tips_str).replace(",", ".").strip()) if tips_str else 0.0
                if amount <= 0: st.error("❌ Сумма должна быть больше 0")
                else:
                    order_time = datetime.now(MOSCOW_TZ).strftime("%H:%M")
                    if order_type == "нал":
                        commission = amount * (1 - RATE_NAL); total = amount + tips; beznal_added = -commission; db_type = "нал"
                    else:
                        final = amount * RATE_CARD; commission = amount - final; total = final + tips; beznal_added = final; db_type = "карта"
                    add_order_and_update_beznal(shift_id, db_type, amount, tips, commission, total, beznal_added, order_time)
                    create_temp_backup()
                    st.session_state["reset_order_fields"] = True
                    st.rerun()
            except (ValueError, AttributeError):
                st.error("❌ Введите корректное число (например: 650)")

    # ===== СПИСОК ЗАКАЗОВ =====
    orders = get_shift_orders(shift_id)
    totals = get_shift_totals(shift_id)

    if orders:
        st.markdown("### 📋 Заказы смены")
        for order_id, typ, am, ti, _, tot, bez, tm in orders:
            if st.session_state.get(f"editing_{order_id}"):
                with st.container():
                    st.markdown(f"**✏️ Заказ #{order_id}**")
                    e_amt = st.number_input("💰 Сумма", value=float(am), min_value=0.1, key=f"e_amt_{order_id}")
                    e_type = st.selectbox("💳 Тип", ["нал","карта"], index=0 if typ=="нал" else 1, key=f"e_type_{order_id}")
                    e_tips = st.number_input("💡 Чаевые", value=float(ti or 0), min_value=0.0, key=f"e_tips_{order_id}")
                    if e_type == "нал": e_comm=e_amt*(1-RATE_NAL); e_tot=e_amt+e_tips; e_bez=-e_comm
                    else: ef=e_amt*RATE_CARD; e_comm=e_amt-ef; e_tot=ef+e_tips; e_bez=ef
                    c1, c2 = st.columns(2)
                    if c1.button("💾 Сохранить", key=f"save_{order_id}", use_container_width=True, type="primary"):
                        update_order_and_adjust_beznal(order_id, e_type, e_amt, e_tips, e_comm, e_tot, e_bez)
                        st.session_state.pop(f"editing_{order_id}", None); st.cache_data.clear(); st.rerun()
                    if c2.button("❌ Отмена", key=f"cancel_{order_id}", use_container_width=True):
                        st.session_state.pop(f"editing_{order_id}", None); st.rerun()
                continue

            icon = "💵" if typ == "нал" else "💳"
            st.markdown(f"{icon} **{typ}** | {tm or ''} | чек: **{am:.0f}₽** → **{tot:.0f}₽** | безнал: **{bez:+.0f}₽**")
            cols = st.columns(2)
            if cols[0].button("✏️ Изменить", key=f"edit_{order_id}", use_container_width=True):
                st.session_state[f"editing_{order_id}"] = True; st.rerun()
            conf_key = f"conf_{order_id}"
            if st.session_state.get(conf_key):
                c1, c2 = cols[1].columns(2)
                if c1.button("✅", key=f"yes_{order_id}", use_container_width=True):
                    delete_order_and_update_beznal(order_id); st.session_state.pop(conf_key, None); st.rerun()
                if c2.button("❌", key=f"no_{order_id}", use_container_width=True):
                    st.session_state.pop(conf_key, None); st.rerun()
            else:
                if cols[1].button("🗑️ Удалить", key=f"del_{order_id}", use_container_width=True):
                    st.session_state[conf_key] = True; st.rerun()
            st.divider()

        nal_sum = totals.get("нал", 0); card_sum = totals.get("карта", 0); tips_sum = totals.get("чаевые", 0)
        total_income = nal_sum + card_sum + tips_sum
        st.markdown("### 💰 Итог смены")
        c1, c2, c3 = st.columns(3)
        c1.metric("💵 Нал + чаевые", f"{nal_sum + tips_sum:.0f} ₽")
        c2.metric("💳 Безнал", f"{card_sum:.0f} ₽")
        c3.metric("💰 Всего", f"{total_income:.0f} ₽")
    else:
        total_income = 0.0

    # ===== РАСХОДЫ И ЗАКРЫТИЕ =====
    st.divider()
    total_extra = get_total_extra_expenses(shift_id)

    col_exp, col_close = st.columns(2)
    with col_exp:
        exp_label = f"💸 Расходы  {total_extra:.0f} ₽" if total_extra > 0 else "💸 Добавить расход"
        if st.button(exp_label, use_container_width=True, key="btn_toggle_exp"):
            st.session_state["show_expenses"] = not st.session_state.get("show_expenses", False)
            st.rerun()
    with col_close:
        if st.button("🔒 Закрыть смену", use_container_width=True, key="btn_toggle_close", type="primary"):
            st.session_state["show_close"] = not st.session_state.get("show_close", False)
            st.rerun()

    # Блок расходов
    if st.session_state.get("show_expenses", False):
        with st.container():
            st.markdown("---")
            st.markdown("### 💸 Расходы")

        st.markdown("**📷 Сканировать QR с чека:**")
        qr_tab1, qr_tab2, qr_tab3 = st.tabs(["📸 Камера", "🖼️ Загрузить фото", "📋 Текст из QR"])

        def _save_qr_result(img_bytes) -> bool:
            qr_text = decode_qr_image(img_bytes)
            if qr_text == "__no_pyzbar__":
                st.warning("⚠️ pyzbar не установлен. Используйте вкладку 'Текст из QR'.")
                return False
            if qr_text:
                parsed = parse_qr_text(qr_text)
                if parsed["amount"]:
                    st.session_state["qr_amount"] = parsed["amount"]
                    st.session_state["qr_date"] = parsed.get("date", "")
                    return True
                else:
                    st.warning("⚠️ QR прочитан, сумма не найдена")
                    st.code(qr_text)
            else:
                st.error("❌ QR не распознан — держите чек ровно при хорошем освещении")
            return False

        with qr_tab1:
            st.caption("📷 Задняя камера — наведите на QR-код чека")
            cam = st.camera_input("Сфотографировать QR", key="qr_camera")
            if cam and not st.session_state.get("qr_amount"):
                if _save_qr_result(cam.getvalue()):
                    st.success(f"✅ Сумма: **{st.session_state['qr_amount']:.2f} ₽**")

        with qr_tab2:
            st.caption("Загрузите готовое фото QR")
            upl = st.file_uploader("Фото QR", type=["jpg","jpeg","png"], key="qr_upload")
            if upl and not st.session_state.get("qr_amount"):
                if _save_qr_result(upl.read()):
                    st.success(f"✅ Сумма: **{st.session_state['qr_amount']:.2f} ₽**")

        with qr_tab3:
            st.caption("Наведите камеру телефона на QR → скопируйте текст → вставьте сюда")
            qr_raw = st.text_area("Текст из QR", placeholder="t=20240315T1423&s=450.00&fn=...",
                                  height=70, key="qr_raw_text")
            if st.button("🔍 Распознать текст", use_container_width=True, key="btn_parse_qr"):
                if qr_raw.strip():
                    parsed = parse_qr_text(qr_raw)
                    if parsed["amount"]:
                        st.session_state["qr_amount"] = parsed["amount"]
                        st.session_state["qr_date"] = parsed.get("date", "")
                        st.success(f"✅ Сумма: **{parsed['amount']:.2f} ₽**"
                                   + (f" · {parsed['date']}" if parsed.get("date") else ""))
                    else:
                        st.error("❌ Сумма не найдена в тексте QR")
                else:
                    st.warning("⚠️ Вставьте текст из QR")

        st.divider()

        qr_amount = st.session_state.get("qr_amount")
        qr_date = st.session_state.get("qr_date", "")

        if qr_amount:
            st.info(f"📋 Из QR: **{qr_amount:.2f} ₽**" + (f" · {qr_date}" if qr_date else ""))

        exp_desc = st.selectbox("📝 Тип расхода", POPULAR_EXPENSES, key="exp_desc")

        amt_widget_key = f"exp_amt_{int(qr_amount * 100) if qr_amount else 0}"
        default_val = float(qr_amount) if qr_amount else 100.0
        exp_amt = st.number_input("💰 Сумма (₽)", min_value=0.0, step=10.0,
                                   value=default_val, key=amt_widget_key)

        c1, c2 = st.columns(2)
        if c1.button("➕ Добавить расход", use_container_width=True,
                     key="btn_add_exp", type="primary"):
            if exp_amt > 0:
                add_extra_expense(shift_id, exp_amt, exp_desc)
                st.session_state.pop("qr_amount", None)
                st.session_state.pop("qr_date", None)
                st.rerun()
            else:
                st.error("❌ Введите сумму больше 0")

        if qr_amount:
            if c2.button("✖️ Сбросить QR", use_container_width=True, key="btn_reset_qr"):
                st.session_state.pop("qr_amount", None)
                st.session_state.pop("qr_date", None)
                st.rerun()

        expenses = get_extra_expenses(shift_id)
        if expenses:
            st.divider()
            for exp in expenses:
                c1, c2 = st.columns([4, 1])
                c1.markdown(f"**{exp['description']}** — {exp['amount']:.0f} ₽")
                if c2.button("🗑️", key=f"del_exp_{exp['id']}", use_container_width=True):
                    delete_extra_expense(exp["id"]); st.rerun()
            if st.button("✖️ Скрыть расходы", use_container_width=True, key="btn_hide_exp"):
                st.session_state["show_expenses"] = False; st.rerun()

    # Блок закрытия смены
    if st.session_state.get("show_close", False):
        with st.container():
            st.markdown("---")
            st.markdown("### ⛽ Закрыть смену")
            last_cons, last_price = get_last_fuel_params()
            km = st.number_input("🛣️ Пробег (км)", value=100, min_value=0, key="km_close")
            c1, c2 = st.columns(2)
            with c1: cons = st.number_input("⛽ Расход л/100км", value=float(last_cons), step=0.5, key="cons_close")
            with c2: price = st.number_input("💰 Цена топлива ₽/л", value=float(last_price), step=1.0, key="fuel_close")
            if km > 0 and cons > 0:
                liters = (km / 100) * cons
                st.info(f"🛢️ {liters:.1f} л × {price:.0f} ₽ = **{liters * price:.0f} ₽**")
            if not st.session_state.get("confirm_close"):
                c1, c2 = st.columns(2)
                if c1.button("✅ Да, закрыть смену", use_container_width=True, type="primary", key="btn_do_close"):
                    st.session_state.confirm_close = True; st.rerun()
                if c2.button("✖️ Отмена", use_container_width=True, key="btn_cancel_close"):
                    st.session_state["show_close"] = False; st.rerun()
            else:
                st.error("⚠️ Последнее подтверждение — смена будет закрыта!")
                c1, c2 = st.columns(2)
                if c1.button("🔒 ЗАКРЫТЬ", use_container_width=True, type="primary", key="btn_confirm_close"):
                    liters_val = (km / 100) * cons if km > 0 else 0.0
                    close_shift_db(shift_id, km, liters_val, price)
                    st.session_state.pop("confirm_close", None)
                    st.session_state["show_close"] = False
                    st.cache_data.clear()
                    delete_temp_backup()  # удаляем temp после закрытия смены
                    token = get_yadisk_token()
                    if token:
                        try:
                            if yadisk_upload_backup(token, shift_date=date_str):
                                # Автоочистка: оставляем 3 последних, удаляем старше 7 дней
                                cleaned = yadisk_cleanup_old_backups(token, keep=3, min_age_days=7)
                                msg = "✅ Смена закрыта · Бэкап → Яндекс Диск"
                                if cleaned > 0:
                                    msg += f" · 🗑️ удалено старых: {cleaned}"
                                st.success(msg)
                            else: st.warning("⚠️ Смена закрыта, бэкап не удался")
                        except Exception as e: st.warning(f"⚠️ Смена закрыта, ошибка: {e}")
                    else: st.success("✅ Смена закрыта")
                    st.rerun()
                if c2.button("❌ Нет, не закрывать", use_container_width=True, key="btn_abort_close"):
                    st.session_state.pop("confirm_close", None); st.rerun()

    # ===== ИТОГ =====
    st.divider()
    profit = total_income - total_extra
    c1, c2, c3 = st.columns(3)
    c1.metric("💰 Доход", f"{total_income:.0f} ₽")
    c2.metric("💸 Расходы", f"{total_extra:.0f} ₽")
    c3.metric("📈 Прибыль", f"{profit:.0f} ₽", delta=f"{profit:.0f}")

# ===== UI: ОТЧЁТЫ =====
def show_reports_page():
    st.markdown("## 📊 Отчёты")
    check_and_create_tables()
    if st.button("🔄 Обновить", use_container_width=True): st.cache_data.clear(); st.rerun()
    try:
        from pages_imports import (get_available_year_months_cached, get_available_days_cached,
            get_month_totals_cached, get_day_report_cached, format_month_option,
            get_month_shifts_details_cached, get_month_statistics)
        year_months = get_available_year_months_cached()
        if not year_months: st.info("ℹ️ Нет закрытых смен"); return
        selected_ym = st.selectbox("📅 Период", year_months, index=0, format_func=format_month_option)
        available_days = get_available_days_cached(selected_ym)
        if available_days:
            weekdays = ["пн","вт","ср","чт","пт","сб","вс"]
            selected_day = st.selectbox("📆 День", available_days,
                format_func=lambda d: f"{d[:10]} ({weekdays[datetime.strptime(d,'%Y-%m-%d').weekday()]})")
            dr = get_day_report_cached(selected_day)
            st.markdown(f"### 📋 {selected_day[:10]}")
            c1,c2,c3,c4 = st.columns(4)
            c1.metric("💰 Доход", f"{dr['всего']:.0f} ₽"); c2.metric("💸 Расходы", f"{(dr['расходы']+dr['топливо']):.0f} ₽")
            c3.metric("⛽ Топливо", f"{dr['топливо']:.0f} ₽"); c4.metric("📈 Прибыль", f"{dr['прибыль']:.0f} ₽")
            c1,c2,c3 = st.columns(3)
            c1.metric("💵 Нал", f"{dr['нал']:.0f} ₽"); c2.metric("💳 Карта", f"{dr['карта']:.0f} ₽"); c3.metric("💡 Чаевые", f"{dr['чаевые']:.0f} ₽")

            # Таблица всех заказов за выбранный день
            st.markdown("#### 🧾 Все заказы за день")
            conn = get_db()
            c_db = conn.cursor()
            c_db.execute("""
                SELECT s.id, o.order_time, o.type, o.amount, o.tips,
                       o.commission, o.total, o.beznal_added
                FROM orders o
                JOIN shifts s ON o.shift_id = s.id
                WHERE s.date = ? AND s.is_open = 0
                ORDER BY s.id, o.id
            """, (selected_day,))
            rows = c_db.fetchall()

            # Расходы за день
            c_db.execute("""
                SELECT e.description, e.amount, e.created_at
                FROM extra_expenses e
                JOIN shifts s ON e.shift_id = s.id
                WHERE s.date = ? AND s.is_open = 0
                ORDER BY e.id
            """, (selected_day,))
            expenses_rows = c_db.fetchall()
            conn.close()

            if rows:
                orders_df = pd.DataFrame(rows, columns=[
                    "Смена №", "Время", "Тип", "Чек ₽", "Чаевые ₽",
                    "Комиссия ₽", "На руки ₽", "Δ Безнал ₽"
                ])
                # Добавляем порядковый номер строки
                orders_df.insert(0, "№", range(1, len(orders_df) + 1))
                orders_df["Чек ₽"] = orders_df["Чек ₽"].round(0).astype(int)
                orders_df["Чаевые ₽"] = orders_df["Чаевые ₽"].round(0).astype(int)
                orders_df["Комиссия ₽"] = orders_df["Комиссия ₽"].round(0).astype(int)
                orders_df["На руки ₽"] = orders_df["На руки ₽"].round(0).astype(int)
                orders_df["Δ Безнал ₽"] = orders_df["Δ Безнал ₽"].round(0).astype(int)
                st.dataframe(orders_df, use_container_width=True, hide_index=True)
                st.caption(f"Итого заказов: {len(rows)} · "
                           f"Нал: {orders_df[orders_df['Тип']=='нал']['На руки ₽'].sum()} ₽ · "
                           f"Карта: {orders_df[orders_df['Тип']=='карта']['На руки ₽'].sum()} ₽")
            else:
                st.info("Нет заказов за этот день")

            if expenses_rows:
                st.markdown("#### 💸 Расходы за день")
                exp_df = pd.DataFrame(expenses_rows, columns=["Описание", "Сумма ₽", "Время"])
                exp_df["Время"] = exp_df["Время"].str[:16]
                exp_df["Сумма ₽"] = exp_df["Сумма ₽"].round(0).astype(int)
                st.dataframe(exp_df, use_container_width=True, hide_index=True)

            st.divider()
        st.markdown(f"### 📊 {format_month_option(selected_ym)}")
        totals = get_month_totals_cached(selected_ym)
        c1,c2,c3,c4 = st.columns(4)
        c1.metric("💵 Нал", f"{totals.get('нал',0):.0f} ₽"); c2.metric("💳 Карта", f"{totals.get('карта',0):.0f} ₽")
        c3.metric("💡 Чаевые", f"{totals.get('чаевые',0):.0f} ₽"); c4.metric("💰 Всего", f"{totals.get('всего',0):.0f} ₽")
        stats = get_month_statistics(selected_ym)
        c1,c2,c3 = st.columns(3)
        c1.metric("🚕 Смен", stats.get("смен",0)); c2.metric("📦 Заказов", stats.get("заказов",0)); c3.metric("📊 Средний чек", f"{stats.get('средний_чек',0):.0f} ₽")
        c1,c2,c3 = st.columns(3)
        c1.metric("⛽ Бензин", f"{stats.get('бензин',0):.0f} ₽"); c2.metric("💸 Расходы", f"{stats.get('расходы',0):.0f} ₽")
        c3.metric("📈 Прибыль", f"{stats.get('прибыль',0):.0f} ₽", delta=f"{stats.get('рентабельность',0):.1f}%")
        df = get_month_shifts_details_cached(selected_ym)
        if not df.empty: st.divider(); st.dataframe(df, use_container_width=True)
    except ImportError as e: st.error(f"❌ pages_imports.py: {e}")
    except Exception as e: st.error(f"❌ Ошибка: {e}")

# ===== UI: СТАТИСТИКА =====
def show_stats_page():
    st.markdown("## 📈 Статистика")
    check_and_create_tables()
    if st.button("🔄 Обновить", use_container_width=True, key="stats_refresh"):
        st.cache_data.clear(); st.rerun()

    conn = get_db(); c = conn.cursor()

    c.execute("""
        SELECT
            COUNT(DISTINCT s.id),
            COUNT(o.id),
            COALESCE(SUM(o.total), 0),
            COALESCE(SUM(CASE WHEN o.type='нал' THEN o.total-o.tips ELSE 0 END), 0),
            COALESCE(SUM(CASE WHEN o.type='карта' THEN o.total-o.tips ELSE 0 END), 0),
            COALESCE(SUM(o.tips), 0),
            COALESCE(AVG(o.total), 0),
            COALESCE(MAX(o.total), 0)
        FROM orders o
        JOIN shifts s ON o.shift_id = s.id
        WHERE s.is_open = 0
    """)
    row = c.fetchone()
    if not row or row[0] == 0:
        conn.close()
        st.info("📭 Нет данных для статистики. Закройте хотя бы одну смену.")
        return

    total_shifts, total_orders, total_income, total_nal, total_card, total_tips, avg_check, max_check = row

    c.execute("SELECT COALESCE(SUM(fuel_liters*fuel_price),0), COALESCE(SUM(km),0) FROM shifts WHERE is_open=0 AND fuel_price>0")
    fuel_cost, total_km = c.fetchone()
    fuel_cost = float(fuel_cost or 0); total_km = int(total_km or 0)

    c.execute("SELECT COALESCE(SUM(e.amount),0) FROM extra_expenses e JOIN shifts s ON e.shift_id=s.id WHERE s.is_open=0")
    extra_cost = float(c.fetchone()[0] or 0.0)
    total_profit = total_income - fuel_cost - extra_cost

    # Рекорды
    c.execute("""
        SELECT s.date, COUNT(o.id), COALESCE(SUM(o.total),0),
               COALESCE(s.fuel_liters*s.fuel_price,0)
        FROM shifts s
        LEFT JOIN orders o ON o.shift_id=s.id
        WHERE s.is_open=0
        GROUP BY s.id ORDER BY SUM(o.total) DESC LIMIT 1
    """)
    best_income_row = c.fetchone()

    c.execute("""
        SELECT s.date, COUNT(o.id) as cnt
        FROM shifts s JOIN orders o ON o.shift_id=s.id
        WHERE s.is_open=0
        GROUP BY s.id ORDER BY cnt DESC LIMIT 1
    """)
    most_orders_row = c.fetchone()

    c.execute("""
        SELECT o.total, o.type, o.order_time, s.date
        FROM orders o JOIN shifts s ON o.shift_id=s.id
        WHERE s.is_open=0 ORDER BY o.total DESC LIMIT 1
    """)
    max_order_row = c.fetchone()

    # По дням недели
    c.execute("""
        SELECT strftime('%w', s.date) as dow,
               COUNT(o.id), COALESCE(AVG(o.total),0), COALESCE(SUM(o.total),0)
        FROM orders o JOIN shifts s ON o.shift_id=s.id
        WHERE s.is_open=0 AND s.date IS NOT NULL
        GROUP BY dow ORDER BY CAST(dow AS INTEGER)
    """)
    dow_rows = c.fetchall()

    # По часам
    c.execute("""
        SELECT CAST(substr(o.order_time,1,2) AS INTEGER) as hr,
               COUNT(*), COALESCE(AVG(o.total),0)
        FROM orders o JOIN shifts s ON o.shift_id=s.id
        WHERE s.is_open=0 AND o.order_time IS NOT NULL AND length(o.order_time)>=2
        GROUP BY hr ORDER BY hr
    """)
    hour_rows = c.fetchall()

    # Тренд по месяцам
    c.execute("""
        SELECT strftime('%Y-%m', s.date) as ym,
               COUNT(DISTINCT s.id), COUNT(o.id),
               COALESCE(SUM(o.total),0),
               COALESCE(SUM(s.fuel_liters*s.fuel_price),0)
        FROM orders o JOIN shifts s ON o.shift_id=s.id
        WHERE s.is_open=0
        GROUP BY ym ORDER BY ym DESC LIMIT 12
    """)
    month_rows = c.fetchall()
    conn.close()

    # ===== ВЫВОД =====
    st.markdown("### 🏆 Итого за всё время")
    col1,col2,col3,col4 = st.columns(4)
    col1.metric("🚕 Смен", total_shifts)
    col2.metric("📦 Заказов", total_orders)
    col3.metric("💰 Доход", f"{total_income:.0f} ₽")
    col4.metric("📈 Прибыль", f"{total_profit:.0f} ₽")

    col1,col2,col3,col4 = st.columns(4)
    col1.metric("💵 Нал", f"{total_nal:.0f} ₽")
    col2.metric("💳 Карта", f"{total_card:.0f} ₽")
    col3.metric("💝 Чаевые", f"{total_tips:.0f} ₽")
    col4.metric("⛽ Топливо", f"{fuel_cost:.0f} ₽")

    col1,col2,col3,col4 = st.columns(4)
    col1.metric("📊 Средний чек", f"{avg_check:.0f} ₽")
    col2.metric("💸 Доп. расходы", f"{extra_cost:.0f} ₽")
    col3.metric("🛣️ Км пробега", f"{total_km:,}".replace(",", " "))
    avg_per_shift = total_income / total_shifts if total_shifts > 0 else 0
    col4.metric("💵 Доход/смена", f"{avg_per_shift:.0f} ₽")

    st.divider()
    st.markdown("### 🥇 Рекорды")
    col1, col2, col3 = st.columns(3)
    if best_income_row:
        col1.metric("🏆 Лучшая смена (доход)", f"{best_income_row[2]:.0f} ₽", delta=str(best_income_row[0]))
    if most_orders_row:
        col2.metric("📦 Макс. заказов за смену", str(most_orders_row[1]), delta=str(most_orders_row[0]))
    if max_order_row:
        lbl = str(max_order_row[1]) + " " + str(max_order_row[2] or "") + " " + str(max_order_row[3] or "")
        col3.metric("💎 Макс. заказ", f"{max_order_row[0]:.0f} ₽", delta=lbl.strip())

    st.divider()
    st.markdown("### 📅 По дням недели")
    if dow_rows:
        dow_names = {"0":"Вс","1":"Пн","2":"Вт","3":"Ср","4":"Чт","5":"Пт","6":"Сб"}
        df_dow = pd.DataFrame(dow_rows, columns=["dow","заказов","средний_чек","сумма"])
        df_dow["день"] = df_dow["dow"].apply(lambda x: dow_names.get(str(x), str(x)))
        df_dow["средний_чек"] = df_dow["средний_чек"].round(0).astype(int)
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("**Кол-во заказов**")
            st.bar_chart(df_dow.set_index("день")["заказов"])
        with col2:
            st.markdown("**Средний чек, ₽**")
            st.bar_chart(df_dow.set_index("день")["средний_чек"])

    st.divider()
    st.markdown("### ⏰ Активность по часам")
    if hour_rows:
        df_h = pd.DataFrame(hour_rows, columns=["час","заказов","средний_чек"])
        full = pd.DataFrame({"час": list(range(24))})
        df_h = full.merge(df_h, on="час", how="left").fillna(0)
        df_h["заказов"] = df_h["заказов"].astype(int)
        df_h["средний_чек"] = df_h["средний_чек"].round(0).astype(int)
        df_h["час_str"] = df_h["час"].apply(lambda h: f"{int(h):02d}:00")
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("**Кол-во заказов**")
            st.bar_chart(df_h.set_index("час_str")["заказов"])
        with col2:
            st.markdown("**Средний чек, ₽**")
            st.bar_chart(df_h.set_index("час_str")["средний_чек"])

    st.divider()
    st.markdown("### 📆 Тренд по месяцам")
    if month_rows:
        df_m = pd.DataFrame(month_rows, columns=["месяц","смен","заказов","доход","топливо"])
        df_m["прибыль"] = (df_m["доход"] - df_m["топливо"]).round(0).astype(int)
        df_m["доход"] = df_m["доход"].round(0).astype(int)
        df_m["топливо"] = df_m["топливо"].round(0).astype(int)
        df_m = df_m.sort_values("месяц")
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("**Доход и прибыль, ₽**")
            st.line_chart(df_m.set_index("месяц")[["доход","прибыль"]])
        with col2:
            st.markdown("**Заказов по месяцам**")
            st.bar_chart(df_m.set_index("месяц")["заказов"])
        st.markdown("**Детали по месяцам**")
        df_show = df_m[["месяц","смен","заказов","доход","топливо","прибыль"]].sort_values("месяц", ascending=False)
        st.dataframe(df_show, use_container_width=True, hide_index=True)

# ===== UI: НАСТРОЙКИ =====
def show_admin_page():
    st.markdown("## 🔧 Настройки")
    current_user = st.session_state.get("username", "")

    master_pwd = get_master_admin_pwd()

    if is_master_admin():
        tab1, tab2, tab3, tab4, tab5 = st.tabs([
            "💾 Бэкап", "💳 Безнал", "👤 Профиль", "⚠️ Сброс", "👑 Мастер-админ"
        ])
    else:
        tab1, tab2, tab3, tab4 = st.tabs([
            "💾 Бэкап", "💳 Безнал", "👤 Профиль", "⚠️ Сброс"
        ])

    # ===== TAB 1: БЭКАП =====
    with tab1:
        tok = get_yadisk_token()
        token_ok = yadisk_check_token(tok)

        st.markdown("#### ☁️ Яндекс Диск")
        if token_ok:
            st.success(f"✅ Подключён · `jet/{current_user}/backup_<дата>.db`")
            with st.expander("🔑 Изменить токен", expanded=False):
                new_tok = st.text_input("OAuth-токен", value=tok, type="password", key="input_yd_token")
                if st.button("💾 Сохранить токен", use_container_width=True, key="save_tok"):
                    st.session_state.yadisk_token = new_tok.strip(); st.rerun()
        else:
            if tok: st.error("❌ Токен не работает")
            else: st.warning("⚠️ Токен не задан")
            with st.expander("ℹ️ Как получить токен", expanded=not tok):
                st.markdown("""
Перейдите по ссылке (подставьте ваш ClientID):
```
https://oauth.yandex.ru/authorize?response_type=token&client_id=ВАШ_CLIENT_ID
```
Скопируйте `access_token=...` и вставьте ниже или в `secrets.toml`:
```toml
YADISK_TOKEN = "y0_AgAAAA..."
```""")
            new_tok = st.text_input("🔑 OAuth-токен", value=tok, type="password",
                                     placeholder="y0_AgAAAA...", key="input_yd_token")
            if st.button("💾 Сохранить токен", use_container_width=True, key="save_tok"):
                st.session_state.yadisk_token = new_tok.strip(); st.rerun()

        c1, c2 = st.columns(2)
        with c1:
            if st.button("📤 Загрузить сейчас", use_container_width=True, type="primary"):
                with st.spinner("Загружаю..."):
                    ds = datetime.now(MOSCOW_TZ).strftime("%Y-%m-%d")
                    if yadisk_upload_backup(tok, shift_date=ds):
                        cleaned = yadisk_cleanup_old_backups(tok, keep=3, min_age_days=7)
                        msg = f"✅ backup_{ds}.db"
                        if cleaned > 0:
                            msg += f" · 🗑️ удалено старых: {cleaned}"
                        st.success(msg)
                        st.rerun()
        with c2:
            if st.button("📥 Восстановить последний", use_container_width=True):
                with st.spinner("Скачиваю..."):
                    try:
                        if yadisk_download_backup(tok): st.success("✅ Восстановлено!"); st.rerun()
                    except Exception as e: st.error(f"❌ {e}")

        st.divider()
        st.markdown("**📋 Бэкапы на Яндекс Диске:**")
        if tok:
            with st.spinner("Загружаю список..."):
                yd_backups = yadisk_list_backups(tok)
            if yd_backups:
                # Статус и кнопка ручной очистки
                total_b = len(yd_backups)
                old_b = max(0, total_b - 3)
                info_parts = [f"Всего бэкапов: **{total_b}**"]
                if old_b > 0:
                    info_parts.append(f"можно удалить старых: **{old_b}**")
                st.caption(" · ".join(info_parts))
                if old_b > 0:
                    if st.button(f"🗑️ Очистить старые (оставить 3 последних)", use_container_width=True, key="yd_cleanup_btn"):
                        with st.spinner("Удаляю старые бэкапы..."):
                            cleaned = yadisk_cleanup_old_backups(tok, keep=3, min_age_days=0)
                            if cleaned > 0:
                                st.success(f"✅ Удалено: {cleaned} бэкап(ов)")
                            else:
                                st.info("Нечего удалять")
                            st.rerun()
                st.divider()
                for b in yd_backups:
                    c1, c2, c3 = st.columns([3, 1, 1])
                    c1.markdown(f"📄 **{b['name']}**  \n📅 {b['modified']} · {b['size_kb']} KB")
                    if c2.button("📥", key=f"yd_dl_{b['name']}", use_container_width=True, help="Восстановить"):
                        with st.spinner("Восстанавливаю..."):
                            try:
                                if yadisk_download_backup(tok, remote_path=b["path"]):
                                    st.success(f"✅ {b['name']}"); st.rerun()
                            except Exception as e: st.error(f"❌ {e}")
                    if c3.button("🗑️", key=f"yd_del_{b['name']}", use_container_width=True, help="Удалить"):
                        if yadisk_delete_backup(tok, b["path"]): st.success("✅ Удалён"); st.rerun()
                        else: st.error("❌ Не удалось удалить")
            else:
                st.info("Бэкапов нет. Появятся после закрытия первой смены.")
        else:
            st.warning("⚠️ Введите токен")

        st.divider()
        st.markdown("#### 📦 Локальные бэкапы")
        if st.button("📦 Создать локальный бэкап", use_container_width=True):
            path = create_backup(); st.success(f"✅ {os.path.basename(path)}")

        uploaded = st.file_uploader("📁 Восстановить из .db файла", type=["db"], key="restore_uploader")
        if uploaded:
            if not st.session_state.get("confirm_restore"):
                if st.button("📥 Восстановить из файла", use_container_width=True, type="primary"):
                    st.session_state.confirm_restore = True; st.rerun()
            else:
                st.warning("⚠️ Текущая БД будет заменена (автобэкап создастся)")
                c1, c2 = st.columns(2)
                if c1.button("✅ Да", use_container_width=True, type="primary"):
                    try:
                        upload_and_restore_backup(uploaded)
                        st.session_state.pop("confirm_restore", None)
                        st.success("✅ Восстановлено!"); time.sleep(1); st.rerun()
                    except Exception as e: st.error(f"❌ {e}")
                if c2.button("❌ Отмена", use_container_width=True):
                    st.session_state.pop("confirm_restore", None); st.rerun()

        for b in list_backups():
            with st.container():
                st.caption(f"📅 {b['time'].strftime('%d.%m.%Y %H:%M')} — {b['size']:.1f} KB")
                c1, c2, c3 = st.columns(3)
                with open(b["path"], "rb") as f:
                    c1.download_button("⬇️ Скачать", f.read(), b["name"], key=f"dl_{b['name']}", use_container_width=True)
                if c2.button("📥 Откат", key=f"rb_{b['name']}", use_container_width=True):
                    restore_from_backup(b["path"]); st.success("✅ Восстановлено!"); st.rerun()
                if c3.button("🗑️", key=f"xb_{b['name']}", use_container_width=True):
                    os.remove(b["path"]); st.rerun()

    # ===== TAB 2: БЕЗНАЛ =====
    with tab2:
        st.markdown("### 💳 Безнал")
        cur = get_accumulated_beznal(); payments = get_beznal_payments()
        total_paid = sum(p["amount"] for p in payments)
        st.metric("💳 Остаток", f"{cur:.0f} ₽", delta=f"Выплачено всего: {total_paid:.0f} ₽")
        st.divider()
        st.markdown("#### 💸 Внести выплату")
        c1, c2 = st.columns([2, 1])
        with c1: pay_amount = st.number_input("Сумма выплаты (₽)", min_value=0.0, step=100.0, value=float(max(0, cur)), key="pay_amount")
        with c2: pay_date = st.date_input("Дата", value=date.today(), key="pay_date")
        pay_note = st.text_input("Комментарий", placeholder="за неделю", key="pay_note")
        if pay_amount > cur: st.warning(f"⚠️ Сумма ({pay_amount:.0f}₽) > остатка ({cur:.0f}₽)")
        if st.button("💸 Зафиксировать выплату", use_container_width=True, type="primary", key="btn_pay"):
            if pay_amount <= 0: st.error("❌ Введите сумму > 0")
            else:
                try:
                    add_beznal_payment(pay_amount, pay_date.strftime("%Y-%m-%d"), pay_note.strip())
                    st.success(f"✅ {pay_amount:.0f} ₽ выплачено. Остаток: {cur - pay_amount:.0f} ₽"); st.rerun()
                except Exception as e: st.error(f"❌ {e}")
        st.divider()
        st.markdown("#### 📋 История выплат")
        if not payments: st.info("Выплат нет")
        else:
            st.caption(f"Выплат: {len(payments)} · Итого: {total_paid:.0f} ₽")
            for p in payments:
                c1, c2, c3 = st.columns([2, 3, 1])
                c1.markdown(f"**{p['amount']:.0f} ₽**")
                c2.markdown(f"📅 {p['date']}" + (f" · {p['note']}" if p['note'] else ""))
                if c3.button("🗑️", key=f"del_pay_{p['id']}", use_container_width=True):
                    try: delete_beznal_payment(p["id"]); st.rerun()
                    except Exception as e: st.error(f"❌ {e}")
        st.divider()
        with st.expander("⚙️ Ручная корректировка остатка"):
            nv = st.number_input("Установить остаток (₽)", value=float(cur), key="new_beznal")
            if st.button("💾 Установить", use_container_width=True):
                set_accumulated_beznal(nv); st.success(f"✅ {nv:.0f} ₽"); st.rerun()

    # ===== TAB 3: ПРОФИЛЬ =====
    with tab3:
        st.markdown("### 👤 Профиль водителя")
        profile = get_user_profile()
        photo_b64 = profile.get("photo", "")

        if photo_b64:
            st.markdown(f'<img src="data:image/jpeg;base64,{photo_b64}" '
                        f'style="width:90px;height:90px;border-radius:50%;object-fit:cover;">',
                        unsafe_allow_html=True)
        else:
            st.markdown('<div style="width:90px;height:90px;border-radius:50%;background:#e2e8f0;'
                        'display:flex;align-items:center;justify-content:center;font-size:2.5rem;">👤</div>',
                        unsafe_allow_html=True)

        uploaded_photo = st.file_uploader("📸 Загрузить фото", type=["jpg","jpeg","png"], key="photo_upload")
        new_photo_b64 = ""
        if uploaded_photo:
            raw = uploaded_photo.read()
            new_photo_b64 = base64.b64encode(raw).decode("utf-8")
            st.markdown(f'<img src="data:image/jpeg;base64,{new_photo_b64}" '
                        f'style="width:90px;height:90px;border-radius:50%;object-fit:cover;">',
                        unsafe_allow_html=True)
            st.caption("👆 Предпросмотр")

        if photo_b64:
            if st.button("🗑️ Удалить фото", use_container_width=True):
                delete_user_photo(); st.rerun()

        st.divider()
        p_name = st.text_input("👤 Имя водителя", value=profile.get("name", ""), placeholder="Алексей")
        p_number = st.text_input("📡 Позывной водителя", value=profile.get("number", ""), placeholder="88")
        p_font = st.slider("🔡 Размер имени", min_value=18, max_value=56,
                           value=profile.get("font_size", 28), step=2)
        preview_name = p_name or "Алексей"
        preview_number = p_number or "88"
        st.markdown(
            f"<div style='color:#94a3b8;font-size:0.78rem;text-transform:uppercase;letter-spacing:.06em;margin-bottom:3px;'>Предпросмотр</div>"
            f"<div style='display:flex;gap:32px;'>"
            f"<div><div style='color:#94a3b8;font-size:0.7rem;'>🚕 ВОДИТЕЛЬ</div>"
            f"<div style='font-size:{p_font}px;font-weight:700;'>{preview_name}</div></div>"
            f"<div><div style='color:#94a3b8;font-size:0.7rem;'>📡 ПОЗЫВНОЙ</div>"
            f"<div style='font-size:{p_font}px;font-weight:700;'>{preview_number}</div></div>"
            f"</div>", unsafe_allow_html=True)

        st.divider()
        st.markdown("#### 🔑 Сменить пароль")
        old_pwd = st.text_input("Текущий пароль", type="password", key="old_pwd")
        new_pwd1 = st.text_input("Новый пароль", type="password", key="new_pwd1")
        new_pwd2 = st.text_input("Повторите новый пароль", type="password", key="new_pwd2")
        if st.button("💾 Сменить пароль", use_container_width=True, key="btn_change_pwd"):
            if not authenticate_user(current_user, old_pwd):
                st.error("❌ Текущий пароль неверный")
            elif new_pwd1 != new_pwd2:
                st.error("❌ Новые пароли не совпадают")
            elif len(new_pwd1) < 4:
                st.error("❌ Пароль должен быть минимум 4 символа")
            else:
                if change_password(current_user, new_pwd1):
                    st.success("✅ Пароль изменён!")
                else:
                    st.error("❌ Ошибка при смене пароля")

        if st.button("💾 Сохранить профиль", use_container_width=True, type="primary"):
            save_to_use = new_photo_b64 if new_photo_b64 else photo_b64
            save_user_profile(p_name.strip(), p_number.strip(), save_to_use, p_font)
            st.success("✅ Профиль сохранён!"); st.rerun()

    # ===== TAB 4: СБРОС =====
    with tab4:
        st.markdown("### ⚠️ Опасная зона")
        st.error("Удаление всех данных — необратимо!")
        confirm_text = st.text_input("Введите СБРОС для подтверждения", placeholder="СБРОС")
        if st.button("⚠️ СБРОСИТЬ БАЗУ", use_container_width=True, type="primary"):
            if confirm_text == "СБРОС":
                try:
                    from pages_imports import reset_db
                    reset_db(); st.cache_data.clear(); st.success("✅ База сброшена"); st.rerun()
                except Exception as e: st.error(f"❌ {e}")
            else: st.error("❌ Введите СБРОС")

    # ===== TAB 5: МАСТЕР-АДМИН =====
    if is_master_admin():
        with tab5:
            st.markdown("### 👑 Мастер-администратор")

            users = get_all_users()
            st.metric("👥 Всего пользователей", len(users))
            st.divider()

            usernames = [u["username"] for u in users]
            selected_u = st.selectbox("👤 Выберите пользователя", usernames, key="master_selected_user")

            if selected_u:
                u_info = next((u for u in users if u["username"] == selected_u), None)
                st.caption(f"Зарегистрирован: {u_info.get('created', '—')}")

                orig_user = st.session_state.get("username")
                try:
                    st.session_state["username"] = selected_u
                    u_profile = get_user_profile()
                    u_beznal = get_accumulated_beznal()
                    st.session_state["username"] = orig_user
                except Exception:
                    st.session_state["username"] = orig_user
                    u_profile = {"name": "", "number": "", "font_size": 28, "photo": ""}
                    u_beznal = 0.0

                st.markdown(f"**Имя:** {u_profile.get('name') or '—'} &nbsp; "
                            f"**Позывной:** {u_profile.get('number') or '—'} &nbsp; "
                            f"**Безнал:** {u_beznal:.0f} ₽")

                st.divider()
                col1, col2 = st.columns(2)

                with col1:
                    st.markdown("**✏️ Изменить имя водителя:**")
                    new_name = st.text_input("Имя водителя", value=u_profile.get("name", ""),
                                             key=f"master_name_{selected_u}")
                    new_number = st.text_input("Позывной", value=u_profile.get("number", ""),
                                               key=f"master_number_{selected_u}")
                    if st.button("💾 Сохранить имя", use_container_width=True,
                                 key=f"master_save_name_{selected_u}", type="primary"):
                        try:
                            st.session_state["username"] = selected_u
                            save_user_profile(new_name.strip(), new_number.strip(),
                                              u_profile.get("photo", ""),
                                              u_profile.get("font_size", 28))
                            st.session_state["username"] = orig_user
                            st.success(f"✅ Имя {selected_u} обновлено")
                        except Exception as e:
                            st.session_state["username"] = orig_user
                            st.error(f"❌ {e}")

                with col2:
                    st.markdown("**🔑 Сбросить пароль:**")
                    new_pwd = st.text_input("Новый пароль", type="password",
                                            key=f"master_pwd_{selected_u}",
                                            placeholder="Минимум 4 символа")
                    new_pwd2 = st.text_input("Повторить пароль", type="password",
                                             key=f"master_pwd2_{selected_u}")
                    if st.button("🔑 Сменить пароль", use_container_width=True,
                                 key=f"master_chpwd_{selected_u}", type="primary"):
                        if not new_pwd:
                            st.warning("⚠️ Введите новый пароль")
                        elif new_pwd != new_pwd2:
                            st.error("❌ Пароли не совпадают")
                        elif len(new_pwd) < 4:
                            st.error("❌ Минимум 4 символа")
                        elif change_password(selected_u, new_pwd):
                            st.success(f"✅ Пароль {selected_u} изменён")
                        else:
                            st.error("❌ Ошибка")

                if selected_u != current_user:
                    st.divider()
                    if not st.session_state.get(f"confirm_del_{selected_u}"):
                        if st.button(f"🗑️ Удалить пользователя {selected_u}",
                                     use_container_width=True, key=f"master_del_{selected_u}"):
                            st.session_state[f"confirm_del_{selected_u}"] = True; st.rerun()
                    else:
                        st.error(f"⚠️ Удалить {selected_u}? Это необратимо!")
                        c1, c2 = st.columns(2)
                        if c1.button("✅ Да, удалить", use_container_width=True,
                                     key=f"master_confirm_del_{selected_u}", type="primary"):
                            delete_user(selected_u)
                            st.session_state.pop(f"confirm_del_{selected_u}", None)
                            st.success(f"✅ {selected_u} удалён"); st.rerun()
                        if c2.button("❌ Отмена", use_container_width=True,
                                     key=f"master_cancel_del_{selected_u}"):
                            st.session_state.pop(f"confirm_del_{selected_u}", None); st.rerun()

            st.divider()
            st.markdown("**➕ Создать нового пользователя:**")
            c1, c2 = st.columns(2)
            with c1: new_u = st.text_input("👤 Логин", key="master_new_login")
            with c2: new_p = st.text_input("🔑 Пароль", type="password", key="master_new_pwd")
            if st.button("➕ Создать пользователя", use_container_width=True):
                if register_user(new_u, new_p): st.success(f"✅ {new_u} создан"); st.rerun()
                else: st.error("❌ Логин занят или ошибка")

    if not is_master_admin() and master_pwd:
        st.divider()
        with st.expander("👑 Вход для мастер-администратора", expanded=False):
            master_input = st.text_input("Мастер-пароль", type="password", key="master_pwd_input")
            if st.button("🔐 Войти как мастер-админ", use_container_width=True):
                if master_input == master_pwd:
                    st.session_state.master_admin_auth = True
                    st.success("✅ Добро пожаловать, мастер-админ!")
                    st.rerun()
                else:
                    st.error("❌ Неверный мастер-пароль")


# ===== MAIN =====
if __name__ == "__main__":
    st.set_page_config(page_title="Taxi Shift Manager", page_icon="🚕",
                       layout="wide", initial_sidebar_state="expanded")
    apply_css(); init_auth_db(); ensure_users_dir(); init_session()

    # Пробуем восстановить сессию из файла
    saved = load_session()
    if saved and "username" not in st.session_state:
        st.session_state.username = saved
        if "page" not in st.session_state:
            st.session_state.page = "main"

    if "username" not in st.session_state:
        show_login_page(); st.stop()

    # Обновляем сессионный файл при каждом заходе авторизованного пользователя
    save_session()

    # Проверяем нужно ли восстановить данные (один раз после логина)
    check_and_offer_restore()

    # ===== САЙДБАР =====
    with st.sidebar:
        profile = get_user_profile()
        photo_b64 = profile.get("photo", "")
        driver_name = profile.get("name") or st.session_state.username
        driver_number = profile.get("number", "")

        if photo_b64:
            st.markdown(
                f'<div style="text-align:center;padding:1rem 0;">'
                f'<img src="data:image/jpeg;base64,{photo_b64}" '
                f'style="width:80px;height:80px;border-radius:50%;object-fit:cover;">'
                f'<div style="font-size:1.2rem;font-weight:bold;margin-top:8px;">{driver_name}</div>'
                f'{"<div style=color:#64748b;font-size:.85rem;>№ " + driver_number + "</div>" if driver_number else ""}'
                f'</div>', unsafe_allow_html=True)
        else:
            st.markdown(
                f'<div style="text-align:center;padding:1rem 0;">'
                f'<div style="font-size:3rem;">👤</div>'
                f'<div style="font-size:1.2rem;font-weight:bold;">{driver_name}</div>'
                f'{"<div style=color:#64748b;font-size:.85rem;>№ " + driver_number + "</div>" if driver_number else ""}'
                f'</div>', unsafe_allow_html=True)

        try:
            acc = get_accumulated_beznal()
            st.metric("💳 Безнал", f"{acc:.0f} ₽")
            db_path = get_current_db_name()
            if os.path.exists(db_path): st.caption(f"💾 БД: {os.path.getsize(db_path)/1024:.1f} KB")
        except: pass

        st.divider()
        page = st.session_state.get("page", "main")
        if st.button("🏠 Главная", use_container_width=True, type="primary" if page=="main" else "secondary"):
            st.session_state.page = "main"; st.rerun()
        if st.button("📊 Отчёты", use_container_width=True, type="primary" if page=="reports" else "secondary"):
            st.session_state.page = "reports"; st.rerun()
        if st.button("📈 Статистика", use_container_width=True, type="primary" if page=="stats" else "secondary"):
            st.session_state.page = "stats"; st.rerun()
        if st.button("🔧 Настройки", use_container_width=True, type="primary" if page=="admin" else "secondary"):
            st.session_state.page = "admin"; st.rerun()
        st.divider()
        if st.button("👋 Выйти", use_container_width=True):
            clear_session(); st.session_state.clear(); st.rerun()

    page = st.session_state.get("page", "main")
    if page == "main": show_main_page()
    elif page == "reports": show_reports_page()
    elif page == "stats": show_stats_page()
    elif page == "admin": show_admin_page()
#huy