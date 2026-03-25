import os
import json
import base64
import shutil
import sqlite3
from datetime import datetime, date, timezone, timedelta
import pandas as pd
import streamlit as st
from passlib.hash import bcrypt

# ===== НАСТРОЙКИ =====
AUTH_DB = "users.db"
USERS_DIR = "users"
SESSION_FILE = "session.json"
SESSION_TIMEOUT = 30 * 24 * 60 * 60
RATE_NAL = 0.78
RATE_CARD = 0.75
MOSCOW_TZ = timezone(timedelta(hours=3))

POPULAR_EXPENSES = [
    "🚗 Мойка", "💧 Омывайка", "🍔 Еда", "☕ Кофе", "🚬 Сигареты",
    "🔧 Мелкий ремонт", "🅿️ Парковка", "💰 Штраф", "🧴 Очиститель",
    "🔋 Зарядка", "🧰 Инструмент", "📱 Связь", "🚕 Аренда", "💊 Аптека"
]

# ===== CSS =====
def apply_mobile_optimized_css():
    st.markdown("""
    <style>
    * { box-sizing: border-box; }
    .main > div { padding-left: 0.5rem !important; padding-right: 0.5rem !important; padding-top: 4rem !important; }
    .block-container { padding-top: 3rem !important; padding-bottom: 2rem !important; max-width: 100% !important; margin-top: 2rem; }
    .stTitle { margin-top: 2rem !important; padding-top: 1rem !important; }
    .stButton button { width: 100%; min-height: 48px; }
    </style>
    """, unsafe_allow_html=True)

# ===== СЕССИЯ =====
def save_session_to_disk():
    try:
        if "username" in st.session_state:
            session_data = {
                "username": st.session_state["username"],
                "session_start": st.session_state.get("session_start").isoformat() if st.session_state.get("session_start") else None,
            }
            with open(SESSION_FILE, "w", encoding="utf-8") as f:
                json.dump(session_data, f)
    except: pass

def load_session_from_disk():
    try:
        if os.path.exists(SESSION_FILE):
            with open(SESSION_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            start_str = data.get("session_start")
            if start_str:
                start = datetime.fromisoformat(start_str).replace(tzinfo=MOSCOW_TZ)
                if (datetime.now(MOSCOW_TZ) - start).total_seconds() < SESSION_TIMEOUT:
                    return data.get("username")
    except: pass
    return None

def clear_session_disk():
    try:
        if os.path.exists(SESSION_FILE): os.remove(SESSION_FILE)
    except: pass

def init_session():
    if "session_start" not in st.session_state:
        st.session_state.session_start = datetime.now(MOSCOW_TZ)
        save_session_to_disk()
    elapsed = (datetime.now(MOSCOW_TZ) - st.session_state.session_start).total_seconds()
    if elapsed > SESSION_TIMEOUT:
        st.session_state.clear()
        clear_session_disk()
        st.warning("⏰ Сессия истекла")
        st.rerun()

def get_session_time_remaining() -> str:
    if "session_start" not in st.session_state: return "00:00:00"
    remaining = max(0, SESSION_TIMEOUT - (datetime.now(MOSCOW_TZ) - st.session_state.session_start).total_seconds())
    h, m, s = int(remaining // 3600), int((remaining % 3600) // 60), int(remaining % 60)
    return f"{h:02d}:{m:02d}:{s:02d}"

# ===== ПАПКИ =====
def ensure_users_dir():
    if not os.path.exists(USERS_DIR): os.makedirs(USERS_DIR)

def get_user_dir(username: str) -> str:
    safe = "".join(c for c in username if c.isalnum() or c in ("_", "-")) or "user"
    path = os.path.join(USERS_DIR, safe)
    if not os.path.exists(path): os.makedirs(path)
    return path

def get_current_db_name() -> str:
    username = st.session_state.get("username")
    if not username: return "taxi_default.db"
    safe = "".join(c for c in username if c.isalnum() or c in ("_", "-"))
    return os.path.join(get_user_dir(username), f"taxi{safe}.db")

def get_backup_dir() -> str:
    path = os.path.join(get_user_dir(st.session_state.get("username", "unknown")), "backups")
    if not os.path.exists(path): os.makedirs(path)
    return path

# ===== БД =====
def check_and_create_tables():
    try:
        conn = sqlite3.connect(get_current_db_name())
        c = conn.cursor()
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
        c.execute("SELECT id FROM accumulated_beznal WHERE driver_id = 1")
        if not c.fetchone():
            c.execute("INSERT INTO accumulated_beznal (driver_id, total_amount, last_updated) VALUES (1, 0, ?)",
                     (datetime.now(MOSCOW_TZ).strftime("%Y-%m-%d %H:%M:%S"),))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"DB Error: {e}")

def get_db_connection():
    check_and_create_tables()
    return sqlite3.connect(get_current_db_name())

# ===== АВТОРИЗАЦИЯ =====
def init_auth_db():
    conn = sqlite3.connect(AUTH_DB)
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT NOT NULL UNIQUE,
        password_hash TEXT NOT NULL, created_at TEXT)""")
    conn.commit()
    conn.close()

def hash_password(password: str) -> str:
    return bcrypt.hash(password.strip().encode('utf-8')[:72])

def verify_password(password: str, hash: str) -> bool:
    try: return bcrypt.verify(password.strip().encode('utf-8')[:72], hash)
    except: return False

def register_user(username: str, password: str) -> bool:
    username = username.strip()
    if not username or not password: return False
    ensure_users_dir()
    init_auth_db()
    conn = sqlite3.connect(AUTH_DB)
    c = conn.cursor()
    try:
        c.execute("INSERT INTO users (username, password_hash, created_at) VALUES (?, ?, ?)",
                 (username, hash_password(password), datetime.now(MOSCOW_TZ).strftime("%Y-%m-%d")))
        conn.commit()
        db_path = get_current_db_name()
        if os.path.exists(db_path): os.remove(db_path)
        check_and_create_tables()
        return True
    except: return False
    finally: conn.close()

def authenticate_user(username: str, password: str) -> bool:
    init_auth_db()
    conn = sqlite3.connect(AUTH_DB)
    c = conn.cursor()
    c.execute("SELECT password_hash FROM users WHERE username = ?", (username.strip(),))
    row = c.fetchone()
    conn.close()
    return verify_password(password, row[0]) if row else False

# ===== СМЕНЫ =====
def get_open_shift():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT id, date FROM shifts WHERE is_open = 1 LIMIT 1")
    row = c.fetchone()
    conn.close()
    return row

def open_shift(date_str: str) -> int:
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("INSERT INTO shifts (date, is_open, opened_at) VALUES (?, 1, ?)",
             (date_str, datetime.now(MOSCOW_TZ).strftime("%Y-%m-%d %H:%M:%S")))
    sid = c.lastrowid
    conn.commit()
    conn.close()
    return sid

def close_shift_db(shift_id: int, km: int, liters: float, fuel_price: float):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("UPDATE shifts SET is_open = 0, km = ?, fuel_liters = ?, fuel_price = ?, closed_at = ? WHERE id = ?",
             (km, liters, fuel_price, datetime.now(MOSCOW_TZ).strftime("%Y-%m-%d %H:%M:%S"), shift_id))
    conn.commit()
    conn.close()

# ===== ЗАКАЗЫ =====
def get_accumulated_beznal() -> float:
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT total_amount FROM accumulated_beznal WHERE driver_id = 1")
    row = c.fetchone()
    conn.close()
    return float(row[0]) if row and row[0] else 0.0

def set_accumulated_beznal(amount: float):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("UPDATE accumulated_beznal SET total_amount = ?, last_updated = ? WHERE driver_id = 1",
             (amount, datetime.now(MOSCOW_TZ).strftime("%Y-%m-%d %H:%M:%S")))
    conn.commit()
    conn.close()

def add_order_and_update_beznal(shift_id, order_type, amount, tips, commission, total, beznal_added, order_time):
    conn = get_db_connection()
    c = conn.cursor()
    try:
        c.execute("INSERT INTO orders (shift_id, type, amount, tips, commission, total, beznal_added, order_time) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                 (shift_id, order_type, amount, tips, commission, total, beznal_added, order_time))
        c.execute("UPDATE accumulated_beznal SET total_amount = total_amount + ?, last_updated = ? WHERE driver_id = 1",
                 (beznal_added, datetime.now(MOSCOW_TZ).strftime("%Y-%m-%d %H:%M:%S")))
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()

def delete_order_and_update_beznal(order_id):
    conn = get_db_connection()
    c = conn.cursor()
    try:
        c.execute("SELECT beznal_added FROM orders WHERE id = ?", (order_id,))
        row = c.fetchone()
        if row:
            beznal = row[0] or 0.0
            c.execute("DELETE FROM orders WHERE id = ?", (order_id,))
            c.execute("UPDATE accumulated_beznal SET total_amount = total_amount - ?, last_updated = ? WHERE driver_id = 1",
                     (beznal, datetime.now(MOSCOW_TZ).strftime("%Y-%m-%d %H:%M:%S")))
            conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()

def update_order_and_adjust_beznal(order_id, order_type, amount, tips, commission, total, beznal_added):
    conn = get_db_connection()
    c = conn.cursor()
    try:
        c.execute("SELECT beznal_added FROM orders WHERE id = ?", (order_id,))
        old = c.fetchone()
        old_beznal = old[0] if old else 0.0
        c.execute("UPDATE orders SET type = ?, amount = ?, tips = ?, commission = ?, total = ?, beznal_added = ? WHERE id = ?",
                 (order_type, amount, tips, commission, total, beznal_added, order_id))
        diff = beznal_added - old_beznal
        c.execute("UPDATE accumulated_beznal SET total_amount = total_amount + ?, last_updated = ? WHERE driver_id = 1",
                 (diff, datetime.now(MOSCOW_TZ).strftime("%Y-%m-%d %H:%M:%S")))
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()

def get_shift_totals(shift_id):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT type, SUM(total - tips) FROM orders WHERE shift_id = ? GROUP BY type", (shift_id,))
    by_type = dict(c.fetchall())
    c.execute("SELECT SUM(tips), SUM(beznal_added) FROM orders WHERE shift_id = ?", (shift_id,))
    tips, beznal = c.fetchone()
    conn.close()
    by_type["чаевые"] = tips or 0.0
    return by_type

def get_shift_orders(shift_id):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT id, type, amount, tips, commission, total, beznal_added, order_time FROM orders WHERE shift_id = ? ORDER BY id DESC", (shift_id,))
    rows = c.fetchall()
    conn.close()
    return rows

def get_last_fuel_params():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT fuel_liters, km, fuel_price FROM shifts WHERE is_open = 0 AND km > 0 AND fuel_price > 0 ORDER BY closed_at DESC LIMIT 1")
    row = c.fetchone()
    conn.close()
    if row and row[0] and row[1]:
        return (row[0] / row[1]) * 100, float(row[2] or 55.0)
    return 8.0, 55.0

# ===== РАСХОДЫ =====
def add_extra_expense(shift_id, amount, description):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("INSERT INTO extra_expenses (shift_id, amount, description, created_at) VALUES (?, ?, ?, ?)",
             (shift_id, amount, description, datetime.now(MOSCOW_TZ).strftime("%Y-%m-%d %H:%M:%S")))
    conn.commit()
    conn.close()

def get_extra_expenses(shift_id):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT id, amount, description, created_at FROM extra_expenses WHERE shift_id = ? ORDER BY id", (shift_id,))
    rows = c.fetchall()
    conn.close()
    return [{"id": r[0], "amount": r[1] or 0.0, "description": r[2] or ""} for r in rows]

def delete_extra_expense(expense_id):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("DELETE FROM extra_expenses WHERE id = ?", (expense_id,))
    conn.commit()
    conn.close()

def get_total_extra_expenses(shift_id):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT SUM(amount) FROM extra_expenses WHERE shift_id = ?", (shift_id,))
    row = c.fetchone()
    conn.close()
    return row[0] or 0.0

# ===== БЕКАПЫ =====
def create_backup():
    backup_dir = get_backup_dir()
    ts = datetime.now(MOSCOW_TZ).strftime("%Y%m%d_%H%M%S")
    path = os.path.join(backup_dir, f"taxi_{st.session_state.get('username', 'unknown')}_backup_{ts}.db")
    shutil.copy2(get_current_db_name(), path)
    return path

def list_backups():
    backup_dir = get_backup_dir()
    if not os.path.exists(backup_dir): return []
    backups = []
    for f in os.listdir(backup_dir):
        if f.endswith(".db"):
            path = os.path.join(backup_dir, f)
            stat = os.stat(path)
            backups.append({"name": f, "path": path, "time": datetime.fromtimestamp(stat.st_mtime), "size": stat.st_size / 1024})
    return sorted(backups, key=lambda x: x["time"], reverse=True)

def restore_from_backup(backup_path):
    if not os.path.exists(backup_path): raise FileNotFoundError(f"Файл не найден: {backup_path}")
    create_backup()
    shutil.copy2(backup_path, get_current_db_name())
    st.cache_data.clear()

def download_backup(path):
    with open(path, "rb") as f: return f.read()

def upload_and_restore_backup(file):
    if file:
        temp = os.path.join(get_backup_dir(), "temp_restore.db")
        with open(temp, "wb") as f: f.write(file.getbuffer())
        restore_from_backup(temp)
        try: os.remove(temp)
        except: pass
        return True
    return False

# ===== GOOGLE DRIVE =====
def sync_with_google_drive():
    try:
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload
        from google.auth.transport.requests import Request
        
        SCOPES = ["https://www.googleapis.com/auth/drive.file"]
        BACKUP_FILENAME = "taxi_backup.db"
        
        if not os.path.exists("credentials.json"):
            if hasattr(st, "secrets") and "google_credentials" in st.secrets:
                with open("credentials.json", "wb") as f:
                    f.write(base64.b64decode(st.secrets["google_credentials"]["json_data"]))
            else:
                st.error("❌ credentials.json не найден!")
                return False
        
        creds = None
        if os.path.exists("token.json"):
            try: creds = Credentials.from_authorized_user_file("token.json", SCOPES)
            except: creds = None
        
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                try: creds.refresh(Request())
                except: creds = None
            if not creds:
                flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
                auth_url, _ = flow.authorization_url(access_type="offline", prompt="consent")
                st.markdown(f"[🔐 Авторизоваться в Google Drive]({auth_url})")
                if st.button("🔄 Обновить"): st.rerun()
                return False
        
        service = build("drive", "v3", credentials=creds)
        results = service.files().list(q=f"name='{BACKUP_FILENAME}'", spaces="drive", fields="files(id, modifiedTime)").execute()
        files = results.get("files", [])
        local_path = get_current_db_name()
        local_mtime = datetime.fromtimestamp(os.path.getmtime(local_path)).replace(tzinfo=timezone.utc)
        
        if not files:
            service.files().create(body={"name": BACKUP_FILENAME}, media_body=MediaFileUpload(local_path)).execute()
            st.success("✅ Загружено в Google Drive!")
        else:
            cloud_mtime = datetime.fromisoformat(files[0]["modifiedTime"].replace("Z", "+00:00"))
            if local_mtime > cloud_mtime:
                service.files().update(fileId=files[0]["id"], media_body=MediaFileUpload(local_path)).execute()
                st.success("✅ Обновлено в Google Drive!")
            else:
                with open(local_path + ".temp", "wb") as f:
                    downloader = MediaIoBaseDownload(f, service.files().get_media(fileId=files[0]["id"]))
                    done = False
                    while not done: _, done = downloader.next_chunk()
                shutil.copy2(local_path + ".temp", local_path)
                os.remove(local_path + ".temp")
                st.success("✅ Скачано из Google Drive!")
                st.cache_data.clear()
                st.rerun()
        return True
    except Exception as e:
        st.error(f"❌ Ошибка: {e}")
        return False

# ===== UI: ГЛАВНАЯ =====
def show_main_page():
    st.title(f"👨‍💼 {st.session_state.username}")
    check_and_create_tables()
    open_shift_data = get_open_shift()
    
    if not open_shift_data:
        st.info("ℹ️ Откройте смену для работы")
        with st.expander("📅 Открыть смену", expanded=True):
            selected_date = st.date_input("Дата смены", value=date.today())
            if st.button("✅ Открыть смену", width='stretch'):
                open_shift(selected_date.strftime("%Y-%m-%d"))
                st.rerun()
    else:
        shift_id, date_str = open_shift_data
        st.success(f"✅ Смена открыта: **{date_str}**")
        
        acc = get_accumulated_beznal()
        if acc > 0: st.metric("💳 Накопленный безнал", f"{acc:.0f} ₽")
        
        with st.expander("➕ Новый заказ", expanded=True):
            col1, col2 = st.columns([2, 1])
            with col1:
                amount_str = st.text_input("Сумма чеком", placeholder="650", width='stretch')
            with col2:
                order_type = st.selectbox("Тип", ["нал", "карта"], index=0, width='stretch')
                tips_str = st.text_input("Чаевые", placeholder="0", width='stretch')
            
            if st.button("✅ Добавить заказ", width='stretch'):
                try:
                    amount = float(amount_str.replace(",", "."))
                    tips = float(tips_str.replace(",", ".")) if tips_str else 0.0
                    order_time = datetime.now(MOSCOW_TZ).strftime("%H:%M")
                    if order_type == "нал":
                        commission = amount * (1 - RATE_NAL)
                        total = amount + tips
                        beznal_added = -commission
                        db_type = "нал"
                    else:
                        final = amount * RATE_CARD
                        commission = amount - final
                        total = final + tips
                        beznal_added = final
                        db_type = "карта"
                    add_order_and_update_beznal(shift_id, db_type, amount, tips, commission, total, beznal_added, order_time)
                    st.rerun()
                except: st.error("❌ Проверьте сумму")
        
        orders = get_shift_orders(shift_id)
        totals = get_shift_totals(shift_id)
        if orders:
            st.subheader("📋 Заказы смены")
            for order_row in orders:
                order_id, typ, am, ti, _, tot, bez, tm = order_row
                cols = st.columns([3, 1, 1, 1])
                cols[0].markdown(f"**{typ}** | {tm or ''} | {am:.0f} ₽")
                cols[1].markdown(f"{tot:.0f} ₽")
                cols[2].markdown(f"{bez:+.0f} ₽")
                
                edit_key = f"edit_{order_id}"
                if cols[3].button("✏️", key=edit_key):
                    st.session_state[f"editing_{order_id}"] = True
                    st.rerun()
                
                if st.session_state.get(f"editing_{order_id}"):
                    with st.expander(f"✏️ Редактирование #{order_id}", expanded=True):
                        e_amt = st.number_input("Сумма", value=float(am), key=f"e_amt_{order_id}", width='stretch')
                        e_type = st.selectbox("Тип", ["нал", "карта"], index=0 if typ == "нал" else 1, key=f"e_type_{order_id}", width='stretch')
                        e_tips = st.number_input("Чаевые", value=float(ti or 0), key=f"e_tips_{order_id}", width='stretch')
                        if e_type == "нал":
                            e_comm = e_amt * (1 - RATE_NAL)
                            e_tot = e_amt + e_tips
                            e_bez = -e_comm
                        else:
                            e_final = e_amt * RATE_CARD
                            e_comm = e_amt - e_final
                            e_tot = e_final + e_tips
                            e_bez = e_final
                        if st.button("💾 Сохранить", key=f"save_{order_id}", width='stretch'):
                            update_order_and_adjust_beznal(order_id, e_type, e_amt, e_tips, e_comm, e_tot, e_bez)
                            st.session_state.pop(f"editing_{order_id}", None)
                            st.cache_data.clear()
                            st.rerun()
                        if st.button("❌ Отмена", key=f"cancel_{order_id}", width='stretch'):
                            st.session_state.pop(f"editing_{order_id}", None)
                            st.rerun()
                    continue
                
                del_key = f"del_{order_id}"
                conf_key = f"conf_{order_id}"
                if st.session_state.get(conf_key):
                    c1, c2 = cols[3].columns(2)
                    if c1.button("✅", key=f"yes_{order_id}", width='stretch'):
                        delete_order_and_update_beznal(order_id)
                        st.session_state.pop(conf_key, None)
                        st.rerun()
                    if c2.button("❌", key=f"no_{order_id}", width='stretch'):
                        st.session_state.pop(conf_key, None)
                        st.rerun()
                elif cols[3].button("🗑️", key=del_key):
                    st.session_state[conf_key] = True
                    st.rerun()
            
            st.divider()
            st.metric("📊 Итого", f"{totals.get('нал', 0):.0f} + {totals.get('карта', 0):.0f} + {totals.get('чаевые', 0):.0f}")
        
        with st.expander("💸 Расходы", expanded=False):
            col1, col2, col3 = st.columns([2, 1, 1])
            with col1: exp_desc = st.selectbox("Тип", POPULAR_EXPENSES, key="exp_desc", width='stretch')
            with col2: exp_amt = st.number_input("Сумма", min_value=0.0, step=50.0, value=100.0, key="exp_amt", width='stretch')
            with col3:
                if st.button("➕", key="add_exp", width='stretch'):
                    add_extra_expense(shift_id, exp_amt, exp_desc)
                    st.rerun()
            
            expenses = get_extra_expenses(shift_id)
            total_extra = 0.0
            for exp in expenses:
                cols = st.columns([3, 1, 1])
                cols[0].markdown(f"**{exp['description']}**")
                cols[1].markdown(f"{exp['amount']:.0f} ₽")
                if cols[2].button("🗑️", key=f"del_exp_{exp['id']}", width='stretch'):
                    delete_extra_expense(exp["id"])
                    st.rerun()
                total_extra += exp["amount"]
            if expenses:
                st.divider()
                st.metric("Итого расходов", f"{total_extra:.0f} ₽")
        
        st.divider()
        total_income = totals.get("нал", 0) + totals.get("карта", 0) + totals.get("чаевые", 0)
        col1, col2, col3 = st.columns(3)
        col1.metric("Доход", f"{total_income:.0f} ₽")
        col2.metric("Расходы", f"{total_extra:.0f} ₽")
        col3.metric("Прибыль", f"{total_income - total_extra:.0f} ₽")
        
        with st.expander("⛽ Закрыть смену", expanded=False):
            last_cons, last_price = get_last_fuel_params()
            km = st.number_input("Пробег (км)", value=100, min_value=0, key="km_close", width='stretch')
            c1, c2 = st.columns(2)
            with c1: cons = st.number_input("Расход (л/100км)", value=float(last_cons), step=0.5, key="cons_close", width='stretch')
            with c2: price = st.number_input("Цена (₽/л)", value=float(last_price), step=1.0, key="fuel_close", width='stretch')
            if km > 0 and cons > 0 and price > 0:
                liters = (km / 100) * cons
                st.info(f"🛢️ {liters:.1f} л × {price:.0f} ₽ = **{liters * price:.0f} ₽**")
            if not st.session_state.get("confirm_close"):
                if st.button("🔒 Закрыть смену", width='stretch', type="primary"):
                    st.session_state.confirm_close = True
                    st.rerun()
            else:
                c1, c2 = st.columns(2)
                if c1.button("✅ Да", width='stretch', type="primary"):
                    close_shift_db(shift_id, km, (km / 100) * cons if km > 0 else 0.0, price)
                    st.session_state.pop("confirm_close", None)
                    st.cache_data.clear()
                    st.rerun()
                if c2.button("❌ Отмена", width='stretch'):
                    st.session_state.pop("confirm_close", None)
                    st.rerun()

# ===== UI: ОТЧЁТЫ =====
def show_reports_page():
    st.title("📊 Отчёты")
    check_and_create_tables()
    
    if st.button("🔄 Обновить данные", width='stretch'):
        st.cache_data.clear()
        st.rerun()
    
    try:
        from pages_imports import (
            get_available_year_months_cached,
            get_available_days_cached,
            get_month_totals_cached,
            get_day_report_cached,
            format_month_option,
            get_month_shifts_details_cached,
            get_month_statistics,
        )
        
        # 1. Выбор месяца
        year_months = get_available_year_months_cached()
        if not year_months:
            st.info("ℹ️ Нет закрытых смен")
            return
        
        selected_ym = st.selectbox("📅 Период (месяц)", year_months, index=0, format_func=format_month_option, width='stretch')
        
        # 2. Выбор дня
        st.divider()
        available_days = get_available_days_cached(selected_ym)
        if available_days:
            selected_day = st.selectbox(
                "📆 Выберите день",
                available_days,
                format_func=lambda d: f"{d[:10]} ({['пн','вт','ср','чт','пт','сб','вс'][datetime.strptime(d, '%Y-%m-%d').weekday()]})",
                width='stretch'
            )
            
            # 3. Отчёт по дню
            day_report = get_day_report_cached(selected_day)
            st.subheader(f"📋 Отчёт за {selected_day[:10]}")
            
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("💰 Доход", f"{day_report['всего']:.0f} ₽")
            c2.metric("💸 Расходы", f"{day_report['расходы'] + day_report['топливо']:.0f} ₽")
            c3.metric("⛽ Топливо", f"{day_report['топливо']:.0f} ₽")
            c4.metric("📈 Прибыль", f"{day_report['прибыль']:.0f} ₽", delta=f"{day_report['прибыль']:.0f} ₽", delta_color="normal")
            
            st.divider()
            c1, c2, c3 = st.columns(3)
            c1.metric("💵 Нал", f"{day_report['нал']:.0f} ₽")
            c2.metric("💳 Карта", f"{day_report['карта']:.0f} ₽")
            c3.metric("💡 Чаевые", f"{day_report['чаевые']:.0f} ₽")
            
            st.divider()
            c1, c2 = st.columns(2)
            c1.metric("🚕 Смен", day_report['смен'])
            c2.metric("📦 Заказов", day_report['заказов'])
            st.divider()
        else:
            st.info(f"ℹ️ В {format_month_option(selected_ym)} нет закрытых смен")
        
        # 4. Отчёт по месяцу
        st.subheader(f"📊 Итого за {format_month_option(selected_ym)}")
        totals = get_month_totals_cached(selected_ym)
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Наличные", f"{totals.get('нал', 0):.0f} ₽")
        c2.metric("Карта", f"{totals.get('карта', 0):.0f} ₽")
        c3.metric("Чаевые", f"{totals.get('чаевые', 0):.0f} ₽")
        c4.metric("Всего", f"{totals.get('всего', 0):.0f} ₽")
        
        st.divider()
        df = get_month_shifts_details_cached(selected_ym)
        if not df.empty: st.dataframe(df, width='stretch')
        
        st.divider()
        stats = get_month_statistics(selected_ym)
        c1, c2, c3 = st.columns(3)
        c1.metric("Смен", stats.get("смен", 0))
        c2.metric("Заказов", stats.get("заказов", 0))
        c3.metric("Средний чек", f"{stats.get('средний_чек', 0):.0f} ₽")
        c1, c2, c3 = st.columns(3)
        c1.metric("Бензин", f"{stats.get('бензин', 0):.0f} ₽")
        c2.metric("Расходы", f"{stats.get('расходы', 0):.0f} ₽")
        c3.metric("Прибыль", f"{stats.get('прибыль', 0):.0f} ₽", delta=f"{stats.get('рентабельность', 0):.1f}%")
        
    except ImportError as e:
        st.error(f"❌ pages_imports.py: {e}")
    except Exception as e:
        st.error(f"❌ Ошибка: {e}")

# ===== UI: АДМИНКА =====
def show_admin_page():
    st.title("🔧 Админка")
    admin_pwd = st.secrets.get("ADMIN_PASSWORD", "changeme")
    pwd = st.text_input("Пароль админа", type="password", width='stretch')
    if st.button("Войти", width='stretch'):
        if pwd == admin_pwd:
            st.session_state.admin_auth = True
            st.rerun()
        else: st.error("❌ Неверный пароль")
    
    if st.session_state.get("admin_auth"):
        tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(["Пересчёт", "Безнал", "Бэкапы", "Загрузка", "Google Drive", "Сброс"])
        with tab1:
            if st.button("🔄 Пересчитать всё", width='stretch'):
                from pages_imports import recalc_full_db
                st.success(f"✅ Безнал: {recalc_full_db():.0f} ₽")
        with tab2:
            new_val = st.number_input("Новый безнал", value=float(get_accumulated_beznal()), width='stretch')
            if st.button("💾 Установить", width='stretch'):
                set_accumulated_beznal(new_val)
                st.rerun()
        with tab3:
            if st.button("📦 Создать бэкап", width='stretch'):
                st.success(f"✅ {os.path.basename(create_backup())}")
            for b in list_backups():
                cols = st.columns([3, 1, 1, 1])
                cols[0].write(b["name"])
                cols[1].download_button("⬇️", download_backup(b["path"]), b["name"], key=f"dl_{b['name']}", width='stretch')
                cols[2].button("📥", key=f"rb_{b['name']}", on_click=lambda p=b["path"]: restore_from_backup(p), width='stretch')
                cols[3].button("🗑️", key=f"xb_{b['name']}", on_click=lambda p=b["path"]: os.remove(p), width='stretch')
        with tab4:
            uploaded = st.file_uploader("Загрузить .db", type="db")
            if uploaded and st.button("📥 Восстановить", width='stretch'):
                if upload_and_restore_backup(uploaded):
                    st.success("✅ Восстановлено!")
                    st.rerun()
        with tab5:
            if st.button("🔄 Синхронизировать", width='stretch', type="primary"):
                sync_with_google_drive()
        with tab6:
            if st.button("💥 СБРОСИТЬ БД", width='stretch', type="primary"):
                from pages_imports import reset_db
                reset_db()
                st.cache_data.clear()
                st.success("✅ Сброшено")
                st.rerun()

# ===== MAIN =====
if __name__ == "__main__":
    st.set_page_config(page_title="Taxi Shift Manager", page_icon="🚕", layout="wide")
    apply_mobile_optimized_css()
    init_auth_db()
    ensure_users_dir()
    init_session()
    
    saved = load_session_from_disk()
    if saved and "username" not in st.session_state:
        st.session_state.username = saved
        st.session_state.page = "main"
    
    if "username" not in st.session_state:
        st.title("🚕 Taxi Shift Manager")
        st.markdown("### Вход / Регистрация")
        u = st.text_input("👤 Логин", width='stretch')
        p = st.text_input("🔑 Пароль", type="password", width='stretch')
        c1, c2 = st.columns(2)
        with c1:
            if st.button("🚀 Войти", width='stretch'):
                if authenticate_user(u, p):
                    st.session_state.username = u.strip()
                    st.session_state.page = "main"
                    st.rerun()
                else: st.error("❌ Неверный логин/пароль")
        with c2:
            if st.button("➕ Регистрация", width='stretch'):
                if register_user(u, p):
                    st.success("✅ Зарегистрирован! Войдите.")
                else: st.error("❌ Ошибка (логин занят?)")
        st.stop()
    
    with st.sidebar:
        st.markdown(f"""
        <div style="text-align: center; padding: 20px 0;">
            <div style="font-size: 4rem;">🚕</div>
            <div style="font-size: 1.5rem; font-weight: bold;">{st.session_state.username}</div>
            <div style="color: #64748b;">{get_session_time_remaining()}</div>
        </div>
        """, unsafe_allow_html=True)
        
        try:
            db_path = get_current_db_name()
            if os.path.exists(db_path):
                st.markdown(f"""
                <div style="background: white; padding: 15px; border-radius: 12px; margin: 15px 0; text-align: center;">
                    <div style="font-size: 0.85rem; color: #64748b;">Размер БД</div>
                    <div style="font-size: 1.5rem; font-weight: bold;">{os.path.getsize(db_path) / 1024:.1f} KB</div>
                </div>
                """, unsafe_allow_html=True)
            st.markdown(f"""
            <div style="background: white; padding: 15px; border-radius: 12px; margin: 15px 0; text-align: center;">
                <div style="font-size: 0.85rem; color: #64748b;">Накопленный безнал</div>
                <div style="font-size: 1.5rem; font-weight: bold;">{get_accumulated_beznal():.0f} ₽</div>
            </div>
            """, unsafe_allow_html=True)
        except: pass
        
        st.divider()
        if st.button("🏠 Главная", width='stretch'): st.session_state.page = "main"; st.rerun()
        if st.button("📊 Отчёты", width='stretch'): st.session_state.page = "reports"; st.rerun()
        if st.button("🔧 Админ", width='stretch'): st.session_state.page = "admin"; st.rerun()
        st.divider()
        if st.button("👋 Выход", width='stretch'):
            clear_session_disk()
            st.session_state.clear()
            st.rerun()
    
    page = st.session_state.get("page", "main")
    if page == "main": show_main_page()
    elif page == "reports": show_reports_page()
    elif page == "admin": show_admin_page()