import streamlit as st
import sqlite3
from datetime import datetime, date, timezone, timedelta
import hashlib
import os
import pandas as pd
import shutil
import json
from pathlib import Path

# ===== НАСТРОЙКИ =====
AUTH_DB = "users.db"
USERS_DIR = "users"
SESSION_FILE = "session.json"
SESSION_TIMEOUT = 30 * 24 * 60 * 60
rate_nal = 0.78
rate_card = 0.75

POPULAR_EXPENSES = [
    "🚗 Мойка", "💧 Омывайка", "🍔 Еда", "☕ Кофе", "🚬 Сигареты",
    "🔧 Мелкий ремонт", "🅿️ Парковка", "💰 Штраф", "🧴 Очиститель",
    "🔋 Зарядка", "🧰 Инструмент", "📱 Связь", "🚕 Аренда", "💊 Аптека"
]

MOSCOW_TZ = timezone(timedelta(hours=3))

# ===== CSS =====
def apply_mobile_optimized_css():
    st.markdown("""
    <style>
    * { box-sizing: border-box; }
    .main > div { padding-left: 0.5rem !important; padding-right: 0.5rem !important; }
    .block-container { padding-top: 1rem !important; padding-bottom: 1rem !important; max-width: 100% !important; }
    .user-info { display: flex; flex-direction: column; align-items: center; gap: 10px; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 20px; border-radius: 15px; margin-bottom: 20px; }
    .user-avatar { font-size: 4rem; width: 100px; height: 100px; border-radius: 50%; display: flex; align-items: center; justify-content: center; color: white; box-shadow: 0 4px 15px rgba(0,0,0,0.3); margin: 0 auto; }
    .user-name { font-size: 1.8rem; font-weight: bold; color: white; text-align: center; }
    .stButton > button { width: 100%; min-height: 48px; }
    </style>
    """, unsafe_allow_html=True)

# ===== УПРАВЛЕНИЕ СЕССИЕЙ =====
def save_session_to_disk():
    try:
        if "username" in st.session_state and st.session_state["username"]:
            session_data = {
                "username": st.session_state["username"],
                "session_start": st.session_state.session_start.isoformat() if "session_start" in st.session_state else None,
                "last_activity": st.session_state.last_activity.isoformat() if "last_activity" in st.session_state else None
            }
            with open(SESSION_FILE, 'w', encoding='utf-8') as f:
                json.dump(session_data, f)
    except Exception as e:
        print(f"Ошибка сессии: {e}")

def load_session_from_disk():
    try:
        if os.path.exists(SESSION_FILE):
            with open(SESSION_FILE, 'r', encoding='utf-8') as f:
                session_data = json.load(f)
            if session_data.get("session_start"):
                session_start = datetime.fromisoformat(session_data["session_start"])
                if session_start.tzinfo is None:
                    session_start = session_start.replace(tzinfo=MOSCOW_TZ)
                time_elapsed = (datetime.now(MOSCOW_TZ) - session_start).total_seconds()
                if time_elapsed < SESSION_TIMEOUT:
                    return session_data.get("username")
    except Exception as e:
        print(f"Ошибка загрузки сессии: {e}")
    return None

def clear_session_disk():
    if os.path.exists(SESSION_FILE):
        os.remove(SESSION_FILE)

def init_session():
    if "session_start" not in st.session_state:
        st.session_state.session_start = datetime.now(MOSCOW_TZ)
    st.session_state.last_activity = datetime.now(MOSCOW_TZ)
    save_session_to_disk()
    time_elapsed = (datetime.now(MOSCOW_TZ) - st.session_state.session_start).total_seconds()
    if time_elapsed > SESSION_TIMEOUT:
        st.session_state.clear()
        clear_session_disk()
        st.warning("⏰ Сессия истекла.")
        st.rerun()

def get_session_time_remaining() -> str:
    if "session_start" not in st.session_state:
        return "00:00:00"
    time_elapsed = (datetime.now(MOSCOW_TZ) - st.session_state.session_start).total_seconds()
    time_remaining = max(0, SESSION_TIMEOUT - time_elapsed)
    days = int(time_remaining // (24 * 3600))
    hours = int((time_remaining % (24 * 3600)) // 3600)
    minutes = int((time_remaining % 3600) // 60)
    seconds = int(time_remaining % 60)
    if days > 0:
        return f"{days}д {hours:02d}:{minutes:02d}:{seconds:02d}"
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

# ===== ПАПКИ И БД =====
def ensure_users_dir():
    if not os.path.exists(USERS_DIR):
        os.makedirs(USERS_DIR)

def get_user_dir(username: str) -> str:
    safe_name = "".join(c for c in username if c.isalnum() or c in ("_", "-"))
    if not safe_name:
        safe_name = "user"
    user_dir = os.path.join(USERS_DIR, safe_name)
    if not os.path.exists(user_dir):
        os.makedirs(user_dir)
    return user_dir

def get_current_db_name() -> str:
    username = st.session_state.get("username")
    if not username:
        return "taxi_default.db"
    safe_name = "".join(c for c in username if c.isalnum() or c in ("_", "-"))
    return os.path.join(get_user_dir(username), f"taxi{safe_name}.db")

def get_backup_dir() -> str:
    user_dir = get_user_dir(st.session_state.get("username", "unknown"))
    backup_dir = os.path.join(user_dir, "backups")
    if not os.path.exists(backup_dir):
        os.makedirs(backup_dir)
    return backup_dir

def check_and_create_tables():
    try:
        conn = sqlite3.connect(get_current_db_name())
        c = conn.cursor()
        c.execute("""
        CREATE TABLE IF NOT EXISTS shifts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL, km INTEGER DEFAULT 0,
            fuel_liters REAL DEFAULT 0, fuel_price REAL DEFAULT 0,
            is_open INTEGER DEFAULT 1, opened_at TEXT, closed_at TEXT
        )
        """)
        c.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT, shift_id INTEGER,
            type TEXT NOT NULL, amount REAL NOT NULL, tips REAL DEFAULT 0,
            commission REAL NOT NULL, total REAL NOT NULL,
            beznal_added REAL DEFAULT 0, order_time TEXT
        )
        """)
        c.execute("""
        CREATE TABLE IF NOT EXISTS extra_expenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT, shift_id INTEGER,
            amount REAL DEFAULT 0, description TEXT, created_at TEXT
        )
        """)
        c.execute("""
        CREATE TABLE IF NOT EXISTS accumulated_beznal (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            driver_id INTEGER DEFAULT 1,
            total_amount REAL DEFAULT 0,
            last_updated TEXT
        )
        """)
        cur = conn.cursor()
        cur.execute("SELECT id FROM accumulated_beznal WHERE driver_id = 1")
        if not cur.fetchone():
            cur.execute(
                "INSERT INTO accumulated_beznal (driver_id, total_amount, last_updated) VALUES (1, 0, ?)",
                (datetime.now(MOSCOW_TZ).strftime("%Y-%m-%d %H:%M:%S"),)
            )
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"DB Error: {e}")
        return False

# ===== АВТОРИЗАЦИЯ =====
def init_auth_db():
    conn = sqlite3.connect(AUTH_DB)
    c = conn.cursor()
    c.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT NOT NULL UNIQUE,
        password_hash TEXT NOT NULL,
        created_at TEXT
    )
    """)
    conn.commit()
    conn.close()

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()

def register_user(username: str, password: str) -> bool:
    username = username.strip()
    if not username or not password:
        return False
    ensure_users_dir()
    conn = sqlite3.connect(AUTH_DB)
    c = conn.cursor()
    try:
        c.execute("INSERT INTO users (username, password_hash, created_at) VALUES (?, ?, ?)",
                  (username, hash_password(password), datetime.now().strftime("%Y-%m-%d")))
        conn.commit()
        safe_name = "".join(c for c in username if c.isalnum() or c in ("_", "-"))
        db_path = os.path.join(get_user_dir(username), f"taxi{safe_name}.db")
        if os.path.exists(db_path):
            os.remove(db_path)
        check_and_create_tables()
        return True
    except:
        return False
    finally:
        conn.close()

def authenticate_user(username: str, password: str) -> bool:
    conn = sqlite3.connect(AUTH_DB)
    c = conn.cursor()
    c.execute("SELECT password_hash FROM users WHERE username = ?", (username.strip(),))
    row = c.fetchone()
    conn.close()
    return row and row[0] == hash_password(password)

# ===== БД ФУНКЦИИ =====
def get_db_connection():
    check_and_create_tables()
    return sqlite3.connect(get_current_db_name())

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
    c.execute("""
    UPDATE shifts SET is_open = 0, km = ?, fuel_liters = ?, fuel_price = ?, closed_at = ?
    WHERE id = ?
    """, (km, liters, fuel_price, datetime.now(MOSCOW_TZ).strftime("%Y-%m-%d %H:%M:%S"), shift_id))
    conn.commit()
    conn.close()

def add_extra_expense(shift_id: int, amount: float, description: str):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("INSERT INTO extra_expenses (shift_id, amount, description, created_at) VALUES (?, ?, ?, ?)",
              (shift_id, amount, description, datetime.now(MOSCOW_TZ).strftime("%Y-%m-%d %H:%M:%S")))
    conn.commit()
    conn.close()

def get_extra_expenses(shift_id: int) -> list:
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT id, amount, description, created_at FROM extra_expenses WHERE shift_id = ? ORDER BY id", (shift_id,))
    rows = c.fetchall()
    conn.close()
    return [{'id': r[0], 'amount': r[1] or 0.0, 'description': r[2] or '', 'created_at': r[3] or ''} for r in rows]

def delete_extra_expense(expense_id: int):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("DELETE FROM extra_expenses WHERE id = ?", (expense_id,))
    conn.commit()
    conn.close()

def get_total_extra_expenses(shift_id: int) -> float:
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT SUM(amount) FROM extra_expenses WHERE shift_id = ?", (shift_id,))
    row = c.fetchone()
    conn.close()
    return row[0] or 0.0

def add_order_db(shift_id, order_type, amount, tips, commission, total, beznal_added, order_time):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("""
    INSERT INTO orders (shift_id, type, amount, tips, commission, total, beznal_added, order_time)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (shift_id, order_type, amount, tips, commission, total, beznal_added, order_time))
    conn.commit()
    conn.close()

def get_shift_orders(shift_id):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("""
    SELECT id, type, amount, tips, commission, total, beznal_added, order_time
    FROM orders WHERE shift_id = ? ORDER BY id DESC
    """, (shift_id,))
    rows = c.fetchall()
    conn.close()
    return rows

def get_shift_totals(shift_id):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT type, SUM(total - tips) FROM orders WHERE shift_id = ? GROUP BY type", (shift_id,))
    by_type = dict(c.fetchall())
    c.execute("SELECT SUM(tips), SUM(beznal_added) FROM orders WHERE shift_id = ?", (shift_id,))
    tips, beznal = c.fetchone()
    conn.close()
    by_type["чаевые"] = tips or 0
    by_type["безнал_смена"] = beznal or 0
    return by_type

def get_accumulated_beznal():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT total_amount FROM accumulated_beznal WHERE driver_id = 1")
    row = c.fetchone()
    conn.close()
    return row[0] if row else 0.0

def add_to_accumulated_beznal(amount: float):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("UPDATE accumulated_beznal SET total_amount = total_amount + ?, last_updated = ? WHERE driver_id = 1",
              (amount, datetime.now(MOSCOW_TZ).strftime("%Y-%m-%d %H:%M:%S")))
    conn.commit()
    conn.close()

def set_accumulated_beznal(amount: float):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("UPDATE accumulated_beznal SET total_amount = ?, last_updated = ? WHERE driver_id = 1",
              (amount, datetime.now(MOSCOW_TZ).strftime("%Y-%m-%d %H:%M:%S")))
    conn.commit()
    conn.close()

def get_last_fuel_params():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("""
    SELECT fuel_liters, km, fuel_price FROM shifts
    WHERE is_open = 0 AND km > 0 AND fuel_liters > 0 AND fuel_price > 0
    ORDER BY closed_at DESC, id DESC LIMIT 1
    """)
    row = c.fetchone()
    conn.close()
    if not row:
        return 8.0, 55.0
    fuel_liters, km, fuel_price = row
    if km is None or km == 0:
        return 8.0, float(fuel_price or 55.0)
    try:
        consumption = (fuel_liters / km) * 100 if km > 0 else 8.0
    except:
        consumption = 8.0
    return float(consumption or 8.0), float(fuel_price or 55.0)

# ===== БЭКАПЫ =====
def create_backup() -> str:
    backup_dir = get_backup_dir()
    ts = datetime.now(MOSCOW_TZ).strftime("%Y%m%d_%H%M%S")
    username = st.session_state.get("username", "unknown")
    backup_name = f"taxi_{username}_backup_{ts}.db"
    backup_path = os.path.join(backup_dir, backup_name)
    shutil.copy2(get_current_db_name(), backup_path)
    return backup_path

def list_backups() -> list:
    backup_dir = get_backup_dir()
    if not os.path.exists(backup_dir):
        return []
    backups = []
    for f in os.listdir(backup_dir):
        if f.endswith('.db'):
            file_path = os.path.join(backup_dir, f)
            file_time = datetime.fromtimestamp(os.path.getmtime(file_path))
            file_size = os.path.getsize(file_path) / 1024
            backups.append({'name': f, 'path': file_path, 'time': file_time, 'size': file_size})
    backups.sort(key=lambda x: x['time'], reverse=True)
    return backups

def restore_from_backup(backup_path: str):
    if not os.path.exists(backup_path):
        raise FileNotFoundError(f"Файл бэкапа не найден: {backup_path}")
    create_backup()
    shutil.copy2(backup_path, get_current_db_name())

def download_backup(backup_path: str) -> bytes:
    with open(backup_path, 'rb') as f:
        return f.read()

def upload_and_restore_backup(uploaded_file):
    if uploaded_file is not None:
        temp_path = os.path.join(get_backup_dir(), "temp_restore.db")
        with open(temp_path, 'wb') as f:
            f.write(uploaded_file.getbuffer())
        restore_from_backup(temp_path)
        try:
            os.remove(temp_path)
        except:
            pass
        return True
    return False

# ===== GOOGLE DRIVE СИНХРОНИЗАЦИЯ =====
def sync_with_google_drive():
    try:
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload
        from google.auth.transport.requests import Request
        import base64
        
        SCOPES = ['https://www.googleapis.com/auth/drive.file']
        BACKUP_FILENAME = 'taxi_backup.db'
        
        # === СОЗДАЁМ credentials.json ИЗ SECRETS ===
        if not os.path.exists('credentials.json'):
            if hasattr(st, 'secrets') and 'google_credentials' in st.secrets:
                try:
                    encoded = st.secrets['google_credentials']['json_data']
                    decoded = base64.b64decode(encoded)
                    with open('credentials.json', 'wb') as f:
                        f.write(decoded)
                    st.success("✅ credentials.json создан из secrets")
                except Exception as e:
                    st.error(f"❌ Ошибка создания credentials.json: {e}")
                    return False
            else:
                st.error("❌ Файл credentials.json не найден!")
                st.info("📁 Добавьте в Settings → Secrets:")
                st.code('[google_credentials]\njson_data = "ваш_base64_код"', language='toml')
                return False
        
        # === АВТОРИЗАЦИЯ ===
        creds = None
        if os.path.exists('token.json'):
            creds = Credentials.from_authorized_user_file('token.json', SCOPES)
        
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
                creds = flow.run_local_server(port=0, open_browser=True)
            
            with open('token.json', 'w', encoding='utf-8') as token:
                token.write(creds.to_json())
            st.success("✅ Авторизация успешна! Токен сохранён.")
            st.rerun()

        # === СИНХРОНИЗАЦИЯ ===
        service = build('drive', 'v3', credentials=creds)
        results = service.files().list(
            q=f"name='{BACKUP_FILENAME}' and trashed=false",
            spaces='drive',
            fields='files(id, modifiedTime)'
        ).execute()
        files = results.get('files', [])
        
        local_path = get_current_db_name()
        local_mtime = datetime.fromtimestamp(os.path.getmtime(local_path))
        
        if not files:
            media = MediaFileUpload(local_path, mimetype='application/octet-stream')
            service.files().create(
                body={'name': BACKUP_FILENAME},
                media_body=media
            ).execute()
            st.success("✅ Загружено в Google Drive!")
            return True
        else:
            cloud_mtime = datetime.fromisoformat(
                files[0]['modifiedTime'].replace('Z', '+00:00')
            )
            local_mtime_aware = local_mtime.replace(tzinfo=timezone.utc)
            
            if local_mtime_aware > cloud_mtime:
                media = MediaFileUpload(local_path, mimetype='application/octet-stream')
                service.files().update(
                    fileId=files[0]['id'],
                    media_body=media
                ).execute()
                st.success("✅ Обновлено в Google Drive!")
                return True
            else:
                request = service.files().get_media(fileId=files[0]['id'])
                temp_path = local_path + ".temp"
                with open(temp_path, 'wb') as f:
                    downloader = MediaIoBaseDownload(f, request)
                    done = False
                    while not done:
                        status, done = downloader.next_chunk()
                shutil.copy2(temp_path, local_path)
                os.remove(temp_path)
                st.success("✅ Скачано из Google Drive!")
                st.cache_data.clear()
                st.rerun()
                
    except Exception as e:
        st.error(f"❌ Ошибка синхронизации: {str(e)}")
        return False
# ===== СТРАНИЦЫ =====
def show_main_page():
    st.title(f"🚕 {st.session_state['username']}")
    check_and_create_tables()
    
    open_shift_data = get_open_shift()
    if not open_shift_data:
        st.info("📭 Нет открытой смены")
        with st.expander("📝 ОТКРЫТЬ СМЕНУ", expanded=True):
            d = st.date_input("Дата", value=date.today())
            if st.button("📂 Открыть новую смену", width="stretch"):
                open_shift(d.strftime("%Y-%m-%d"))
                st.rerun()
    else:
        sid, date_str = open_shift_data
        st.success(f"📅 {date_str}")
        acc = get_accumulated_beznal()
        if acc != 0:
            st.metric("💰 Безнал", f"{acc:.0f} ₽")

        with st.expander("➕ ДОБАВИТЬ ЗАКАЗ", expanded=True):
            c1, c2 = st.columns(2)
            amt = c1.text_input("Сумма заказа", placeholder="650")
            typ = c2.selectbox("Тип оплаты", ["НАЛ", "КАРТА"])
            tips = st.text_input("Чаевые", placeholder="0")
            if st.button("💾 Сохранить заказ", width="stretch"):
                if amt:
                    a = float(amt.replace(",", "."))
                    t = float(tips.replace(",", ".")) if tips else 0.0
                    order_time = datetime.now(MOSCOW_TZ).strftime("%H:%M")
                    if typ == "НАЛ":
                        comm = a * (1 - rate_nal); tot = a + t; bez = -comm; db_type = "нал"
                    else:
                        final = a * rate_card; comm = a - final; tot = final + t; bez = final; db_type = "карта"
                    add_order_db(sid, db_type, a, t, comm, tot, bez, order_time)
                    if bez != 0: add_to_accumulated_beznal(bez)
                    st.rerun()

        orders = get_shift_orders(sid)
        if orders:
            st.subheader("📋 Список заказов")
            totals = get_shift_totals(sid)
            for i, (_, tp, am, ti, _, tot, _, tm) in enumerate(orders, 1):
                cols = st.columns([2, 1, 1])
                cols[0].markdown(f"**#{i}** {tm or ''} {'💵' if tp=='нал' else '💳'} {am:.0f}₽")
                cols[1].markdown(f"**{tot:.0f}**")
                if cols[2].button("🗑 Удалить", key=f"d{i}", width="stretch"):
                    st.success("Удалено"); st.rerun()
            st.divider()
            st.metric("ДОХОД", f"{totals.get('нал',0)+totals.get('карта',0)+totals.get('чаевые',0):.0f}₽")

        # ===== ДОП ЗАТРАТЫ =====
        with st.expander("💸 ДОП ЗАТРАТЫ", expanded=False):
            st.subheader("➕ Добавить расход")
            c1, c2, c3 = st.columns([2, 1, 1])
            with c1:
                exp_desc = st.selectbox("Что", options=[""] + POPULAR_EXPENSES, key="exp_desc")
            with c2:
                exp_amt = st.number_input("Сумма", min_value=0.0, step=50.0, value=100.0, key="exp_amt")
            with c3:
                if st.button("➕ Добавить", width="stretch", key="add_exp"):
                    if exp_desc and exp_amt > 0:
                        add_extra_expense(sid, exp_amt, exp_desc)
                        st.success("✅ Добавлено")
                        st.rerun()
            
            st.divider()
            st.subheader("📋 Текущие расходы")
            expenses = get_extra_expenses(sid)
            total_extra = 0.0
            for exp in expenses:
                cols = st.columns([3, 1, 1])
                cols[0].markdown(f"**{exp['description']}**")
                cols[1].markdown(f"**{exp['amount']:.0f}₽**")
                if cols[2].button("🗑", key=f"delexp{exp['id']}", width="stretch"):
                    delete_extra_expense(exp['id'])
                    st.rerun()
                total_extra += exp['amount']
            if expenses:
                st.divider()
                st.metric("💸 ИТОГО РАСХОДЫ", f"{total_extra:.0f}₽")
        
        # ===== ИТОГИ СМЕНЫ =====
        st.divider()
        st.subheader("💰 ИТОГИ СМЕНЫ")
        total_income = totals.get('нал',0)+totals.get('карта',0)+totals.get('чаевые',0)
        total_extra = get_total_extra_expenses(sid)
        col1, col2, col3 = st.columns(3)
        col1.metric("📊 Доход", f"{total_income:.0f}₽")
        col2.metric("💸 Расходы", f"{total_extra:.0f}₽")
        col3.metric("📈 Чистыми", f"{total_income - total_extra:.0f}₽", delta=f"{total_income - total_extra:.0f}₽")
        
        # ===== ЗАКРЫТЬ СМЕНУ =====
        with st.expander("🔒 ЗАКРЫТЬ СМЕНУ", expanded=False):
            last_cons, last_price = get_last_fuel_params()
            km = st.number_input("Пробег (км)", value=100, key="km_close")
            c1, c2 = st.columns(2)
            with c1:
                consumption = st.number_input("Расход л/100км", value=float(f"{last_cons:.1f}"), step=0.5, key="cons_close")
            with c2:
                fuel_price = st.number_input("Цена топлива ₽/л", value=float(f"{last_price:.1f}"), step=1.0, key="fuel_close")
            if km > 0 and consumption > 0 and fuel_price > 0:
                liters = (km / 100) * consumption
                fuel_cost = liters * fuel_price
                profit = total_income - total_extra - fuel_cost
                st.info(f"⛽ {liters:.1f}л = {fuel_cost:.0f}₽")
                st.success(f"💰 Прибыль: {profit:.0f}₽")
            if st.button("🔒 Закрыть смену", width="stretch", type="primary", key="close_shift"):
                liters = (km / 100) * consumption if km > 0 else 0.0
                close_shift_db(sid, km, liters, fuel_price)
                st.success("✅ Смена закрыта")
                st.cache_data.clear()
                st.rerun()

def show_reports_page():
    st.title("📊 ОТЧЁТЫ И СТАТИСТИКА")
    check_and_create_tables()
    try:
        from pages_imports import get_available_year_months_cached, get_month_totals_cached, format_month_option, get_month_shifts_details_cached
        year_months = get_available_year_months_cached()
        if not year_months:
            st.info("📭 Нет закрытых смен")
            return
        
        ym = st.selectbox("📅 Выберите месяц", year_months, format_func=format_month_option, index=0)
        
        # ИТОГИ ЗА МЕСЯЦ
        totals = get_month_totals_cached(ym)
        st.subheader("💰 ИТОГИ ЗА МЕСЯЦ")
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("💵 Нал", f"{totals.get('нал', 0):.0f} ₽")
        col2.metric("💳 Карта", f"{totals.get('карта', 0):.0f} ₽")
        col3.metric("💝 Чаевые", f"{totals.get('чаевые', 0):.0f} ₽")
        col4.metric("📊 ВСЕГО", f"{totals.get('всего', 0):.0f} ₽")
        
        st.divider()
        
        # ДЕТАЛИ ПО СМЕНАМ (ОТЧЁТЫ ЗА ДЕНЬ)
        st.subheader("📋 ОТЧЁТЫ ПО ДНЯМ")
        df_shifts = get_month_shifts_details_cached(ym)
        if not df_shifts.empty:
            # Выбор дня
            dates = df_shifts["Дата"].unique().tolist()
            selected_date = st.selectbox("📆 Выберите день", options=dates)
            
            # Фильтр по дню
            df_day = df_shifts[df_shifts["Дата"] == selected_date].copy()
            if not df_day.empty:
                st.dataframe(df_day, width="stretch")
                
                row = df_day.iloc[0]
                st.divider()
                st.subheader("📊 ИТОГИ ЗА ДЕНЬ")
                c1, c2, c3 = st.columns(3)
                c1.metric("💰 Доход", f"{row['Всего']:.0f}₽")
                fuel_cost = row['Литры'] * row['Цена'] if row['Литры'] > 0 else 0
                c2.metric("⛽ Бензин", f"{fuel_cost:.0f}₽")
                c3.metric("📈 Чистыми", f"{row['Всего'] - fuel_cost:.0f}₽")
        else:
            st.info("📭 Нет данных за этот месяц")
        
        st.divider()
        
        # СТАТИСТИКА
        from pages_imports import get_month_statistics
        stats = get_month_statistics(ym)
        st.subheader("📈 СТАТИСТИКА ЗА МЕСЯЦ")
        c1, c2, c3 = st.columns(3)
        c1.metric("📅 Смен", f"{stats.get('смен', 0)}")
        c2.metric("📝 Заказов", f"{stats.get('заказов', 0)}")
        c3.metric("💰 Средний чек", f"{stats.get('средний_чек', 0):.0f} ₽")
        
        c1, c2, c3 = st.columns(3)
        c1.metric("⛽ Бензин", f"{stats.get('бензин', 0):.0f} ₽")
        c2.metric("💸 Расходы", f"{stats.get('расходы', 0):.0f} ₽")
        profit = stats.get('прибыль', 0)
        c3.metric("📈 Прибыль", f"{profit:.0f} ₽", delta=f"{stats.get('рентабельность', 0):.1f}%" if profit > 0 else None)
        
    except Exception as e:
        st.error(f"Ошибка: {e}")
        st.exception(e)

def show_admin_page():
    st.title("🛠 АДМИНКА")
    pwd = st.text_input("Пароль админа", type="password")
    if st.button("🔓 Войти", width="stretch"):
        if pwd == st.secrets.get("ADMIN_PASSWORD", "changeme"):
            st.session_state.admin_auth = True
            st.rerun()
        else:
            st.error("Неверный пароль")
    
    if st.session_state.get("admin_auth"):
        tabs = st.tabs(["📥 ИМПОРТ", "🔄 ПЕРЕСЧЁТ", "✏️ БЕЗНАЛ", "🗄 БЭКАПЫ", "💾 ЗАГРУЗКА", "☁️ GOOGLE DRIVE", "🔧 ИНСТРУМЕНТЫ"])
        
        with tabs[0]:
            st.write("Импорт из Excel/CSV")
        
        with tabs[1]:
            from pages_imports import recalc_full_db, get_accumulated_beznal
            if st.button("🔄 Пересчитать", width="stretch"):
                new_total = recalc_full_db()
                st.success(f"Готово. Безнал: {new_total:.0f} ₽")
        
        with tabs[2]:
            curr = get_accumulated_beznal()
            new_val = st.number_input("Значение", value=float(curr))
            if st.button("💾 Сохранить", width="stretch"):
                set_accumulated_beznal(new_val)
                st.success("Сохранено"); st.rerun()
        
        with tabs[3]:
            if st.button("📦 Создать бэкап", width="stretch"):
                path = create_backup()
                st.success(f"Создан: {os.path.basename(path)}")
            backups = list_backups()
            for b in backups:
                cols = st.columns([3, 1, 1, 1])
                cols[0].write(f"{b['name']}")
                if cols[1].button("📥", key=f"d{b['name']}", width="stretch"):
                    st.download_button("Скачать", download_backup(b['path']), b['name'])
                if cols[2].button("🔄", key=f"r{b['name']}", width="stretch"):
                    restore_from_backup(b['path']); st.rerun()
                if cols[3].button("🗑", key=f"x{b['name']}", width="stretch"):
                    os.remove(b['path']); st.rerun()

        with tabs[4]:
            uploaded = st.file_uploader("Загрузить бэкап", type=["db"])
            if uploaded and st.button("✅ Восстановить", width="stretch"):
                if upload_and_restore_backup(uploaded):
                    st.success("Восстановлено!"); st.rerun()

        with tabs[5]:
            st.subheader("☁️ Google Drive Синхронизация")
            st.info("Нажмите кнопку ниже. Откроется окно браузера для входа в Google.")
            if st.button("🔄 Синхронизировать", width="stretch", type="primary"):
                sync_with_google_drive()
        
        with tabs[6]:
            if st.button("🗑 Сброс", width="stretch"):
                from pages_imports import reset_db
                reset_db()
                st.success("Сброшено"); st.rerun()

# ===== ЗАПУСК =====
st.set_page_config(page_title="Такси учёт", page_icon="🚕", layout="wide")
apply_mobile_optimized_css()
init_auth_db()
ensure_users_dir()
init_session()

saved_username = load_session_from_disk()
if saved_username and "username" not in st.session_state:
    st.session_state["username"] = saved_username
    st.session_state["page"] = "main"

if "username" not in st.session_state:
    st.title("🚕 ВХОД")
    u = st.text_input("Логин")
    p = st.text_input("Пароль", type="password")
    if st.button("🔓 Войти", width="stretch"):
        if authenticate_user(u, p):
            st.session_state.username = u.strip()
            st.session_state.page = "main"
            st.rerun()
        else:
            st.error("Ошибка")
    if st.button("📝 Регистрация", width="stretch"):
        if register_user(u, p):
            st.success("Создан!"); st.rerun()
        else:
            st.error("Ошибка")
    st.stop()

# ===== ЛЕВАЯ ПАНЕЛЬ (SIDEBAR) =====
with st.sidebar:
    st.markdown(f"""
    <div style="text-align: center; padding: 20px 0;">
        <div style="font-size: 4rem; margin-bottom: 10px;">🚕</div>
        <div style="font-size: 1.5rem; font-weight: bold; margin-bottom: 5px;">{st.session_state['username']}</div>
        <div style="color: #64748b; font-size: 0.9rem;">👨‍ водитель</div>
    </div>
    """, unsafe_allow_html=True)
    
    try:
        db_path = get_current_db_name()
        if os.path.exists(db_path):
            size = os.path.getsize(db_path) / 1024
            st.markdown(f"""
            <div style="background: white; padding: 15px; border-radius: 12px; margin: 15px 0; text-align: center; box-shadow: 0 2px 8px rgba(0,0,0,0.1);">
                <div style="font-size: 0.85rem; color: #64748b; margin-bottom: 5px;">📦 Размер БД</div>
                <div style="font-size: 1.5rem; font-weight: bold; color: #1e293b;">{size:.1f} KB</div>
            </div>
            """, unsafe_allow_html=True)
        acc = get_accumulated_beznal()
        st.markdown(f"""
        <div style="background: white; padding: 15px; border-radius: 12px; margin: 15px 0; text-align: center; box-shadow: 0 2px 8px rgba(0,0,0,0.1);">
            <div style="font-size: 0.85rem; color: #64748b; margin-bottom: 5px;">💰 Безнал</div>
            <div style="font-size: 1.5rem; font-weight: bold; color: #1e293b;">{acc:.0f} ₽</div>
        </div>
        """, unsafe_allow_html=True)
    except:
        pass

    st.divider()

    if st.button("📋 Главная", width="stretch", type="primary" if st.session_state.get("page")=="main" else "secondary"):
        st.session_state.page="main"
        st.rerun()

    if st.button("📊 Отчёты", width="stretch", type="primary" if st.session_state.get("page")=="reports" else "secondary"):
        st.session_state.page="reports"
        st.rerun()

    if st.button("⚙️ Админка", width="stretch", type="primary" if st.session_state.get("page")=="admin" else "secondary"):
        st.session_state.page="admin"
        st.rerun()

    st.divider()
    st.caption(f"⏱️ Сессия: {get_session_time_remaining()}")

    if st.button("🚪 Выйти", width="stretch"):
        clear_session_disk()
        st.session_state.clear()
        st.rerun()

# ===== ОТРИСОВКА СТРАНИЦ =====
if st.session_state.get("page") == "main":
    show_main_page()
elif st.session_state.get("page") == "reports":
    show_reports_page()
elif st.session_state.get("page") == "admin":
    show_admin_page()