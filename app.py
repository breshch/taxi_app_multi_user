# app.py — ПОЛНОСТЬЮ ЗАМЕНИТЕ СОДЕРЖИМОЕ
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
    .main > div { padding-left: 0.5rem !important; padding-right: 0.5rem !important; }
    .block-container { padding-top: 1rem !important; padding-bottom: 1rem !important; max-width: 100% !important; }
    .stButton button { width: 100%; min-height: 48px; }
    </style>
    """, unsafe_allow_html=True)

# ===== СЕССИЯ =====
def save_session_to_disk():
    try:
        if "username" in st.session_state and st.session_state["username"]:
            session_data = {
                "username": st.session_state["username"],
                "session_start": st.session_state.get("session_start").isoformat() if st.session_state.get("session_start") else None,
                "last_activity": st.session_state.get("last_activity").isoformat() if st.session_state.get("last_activity") else None,
            }
            with open(SESSION_FILE, "w", encoding="utf-8") as f:
                json.dump(session_data, f)
    except Exception as e:
        print(f"Ошибка сохранения сессии: {e}")

def load_session_from_disk():
    try:
        if os.path.exists(SESSION_FILE):
            with open(SESSION_FILE, "r", encoding="utf-8") as f:
                session_data = json.load(f)
            session_start_str = session_data.get("session_start")
            if session_start_str:
                session_start = datetime.fromisoformat(session_start_str)
                if session_start.tzinfo is None:
                    session_start = session_start.replace(tzinfo=MOSCOW_TZ)
                elapsed = (datetime.now(MOSCOW_TZ) - session_start).total_seconds()
                if elapsed < SESSION_TIMEOUT:
                    return session_data.get("username")
    except Exception as e:
        print(f"Ошибка загрузки сессии: {e}")
    return None

def clear_session_disk():
    try:
        if os.path.exists(SESSION_FILE):
            os.remove(SESSION_FILE)
    except Exception as e:
        print(f"Ошибка очистки файла сессии: {e}")

def init_session():
    if "session_start" not in st.session_state:
        st.session_state.session_start = datetime.now(MOSCOW_TZ)
        st.session_state.last_activity = datetime.now(MOSCOW_TZ)
        save_session_to_disk()
    elapsed = (datetime.now(MOSCOW_TZ) - st.session_state.session_start).total_seconds()
    if elapsed > SESSION_TIMEOUT:
        st.session_state.clear()
        clear_session_disk()
        st.warning("⏰ Сессия истекла. Авторизуйтесь снова.")
        st.rerun()
    else:
        st.session_state.last_activity = datetime.now(MOSCOW_TZ)
        save_session_to_disk()

def get_session_time_remaining() -> str:
    if "session_start" not in st.session_state:
        return "00:00:00"
    elapsed = (datetime.now(MOSCOW_TZ) - st.session_state.session_start).total_seconds()
    remaining = max(0, SESSION_TIMEOUT - elapsed)
    days = int(remaining // (24 * 3600))
    hours = int((remaining % (24 * 3600)) // 3600)
    minutes = int((remaining % 3600) // 60)
    seconds = int(remaining % 60)
    if days > 0:
        return f"{days}д {hours:02d}:{minutes:02d}:{seconds:02d}"
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

# ===== ПАПКИ =====
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
    username = st.session_state.get("username", "unknown")
    user_dir = get_user_dir(username)
    backup_dir = os.path.join(user_dir, "backups")
    if not os.path.exists(backup_dir):
        os.makedirs(backup_dir)
    return backup_dir

# ===== БД =====
def check_and_create_tables():
    try:
        conn = sqlite3.connect(get_current_db_name())
        c = conn.cursor()
        c.execute("""CREATE TABLE IF NOT EXISTS shifts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL, km INTEGER DEFAULT 0,
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
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            driver_id INTEGER DEFAULT 1,
            total_amount REAL DEFAULT 0,
            last_updated TEXT)""")
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

def get_db_connection():
    check_and_create_tables()
    return sqlite3.connect(get_current_db_name())

# ===== АВТОРИЗАЦИЯ =====
def init_auth_db():
    conn = sqlite3.connect(AUTH_DB)
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT NOT NULL UNIQUE,
        password_hash TEXT NOT NULL,
        created_at TEXT)""")
    conn.commit()
    conn.close()

def hash_password(password: str) -> str:
    pwd_bytes = password.strip().encode('utf-8')[:72]
    return bcrypt.hash(pwd_bytes)

def verify_password(password: str, password_hash: str) -> bool:
    try:
        pwd_bytes = password.strip().encode('utf-8')[:72]
        return bcrypt.verify(pwd_bytes, password_hash)
    except Exception:
        return False

def register_user(username: str, password: str) -> bool:
    username = username.strip()
    if not username or not password:
        return False
    ensure_users_dir()
    init_auth_db()
    conn = sqlite3.connect(AUTH_DB)
    c = conn.cursor()
    try:
        c.execute(
            "INSERT INTO users (username, password_hash, created_at) VALUES (?, ?, ?)",
            (username, hash_password(password), datetime.now(MOSCOW_TZ).strftime("%Y-%m-%d"))
        )
        conn.commit()
        db_path = get_current_db_name()
        if os.path.exists(db_path):
            os.remove(db_path)
        check_and_create_tables()
        return True
    except sqlite3.IntegrityError:
        return False
    except Exception as e:
        print(f"Ошибка регистрации: {e}")
        return False
    finally:
        conn.close()

def authenticate_user(username: str, password: str) -> bool:
    init_auth_db()
    conn = sqlite3.connect(AUTH_DB)
    c = conn.cursor()
    c.execute("SELECT password_hash FROM users WHERE username = ?", (username.strip(),))
    row = c.fetchone()
    conn.close()
    if not row:
        return False
    return verify_password(password, row[0])

# ===== СМЕНЫ И ЗАКАЗЫ =====
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
    c.execute(
        "INSERT INTO shifts (date, is_open, opened_at) VALUES (?, 1, ?)",
        (date_str, datetime.now(MOSCOW_TZ).strftime("%Y-%m-%d %H:%M:%S")),
    )
    sid = c.lastrowid
    conn.commit()
    conn.close()
    return sid

def close_shift_db(shift_id: int, km: int, liters: float, fuel_price: float):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute(
        "UPDATE shifts SET is_open = 0, km = ?, fuel_liters = ?, fuel_price = ?, closed_at = ? WHERE id = ?",
        (km, liters, fuel_price, datetime.now(MOSCOW_TZ).strftime("%Y-%m-%d %H:%M:%S"), shift_id),
    )
    conn.commit()
    conn.close()

def get_accumulated_beznal() -> float:
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT total_amount FROM accumulated_beznal WHERE driver_id = 1")
    row = c.fetchone()
    conn.close()
    return float(row[0]) if row and row[0] is not None else 0.0

def set_accumulated_beznal(amount: float):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute(
        "UPDATE accumulated_beznal SET total_amount = ?, last_updated = ? WHERE driver_id = 1",
        (amount, datetime.now(MOSCOW_TZ).strftime("%Y-%m-%d %H:%M:%S")),
    )
    conn.commit()
    conn.close()

def add_order_and_update_beznal(shift_id, order_type, amount, tips, commission, total, beznal_added, order_time):
    conn = get_db_connection()
    c = conn.cursor()
    try:
        c.execute(
            "INSERT INTO orders (shift_id, type, amount, tips, commission, total, beznal_added, order_time) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (shift_id, order_type, amount, tips, commission, total, beznal_added, order_time),
        )
        c.execute(
            "UPDATE accumulated_beznal SET total_amount = total_amount + ?, last_updated = ? WHERE driver_id = 1",
            (beznal_added, datetime.now(MOSCOW_TZ).strftime("%Y-%m-%d %H:%M:%S")),
        )
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
        if not row:
            return
        beznal_added = row[0] or 0.0
        c.execute("DELETE FROM orders WHERE id = ?", (order_id,))
        c.execute(
            "UPDATE accumulated_beznal SET total_amount = total_amount - ?, last_updated = ? WHERE driver_id = 1",
            (beznal_added, datetime.now(MOSCOW_TZ).strftime("%Y-%m-%d %H:%M:%S")),
        )
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()

# ===== ✏️ ИЗМЕНЕНИЕ ЗАКАЗА (НОВОЕ) =====
def update_order_and_adjust_beznal(order_id, order_type, amount, tips, commission, total, beznal_added):
    """Обновляет заказ и корректирует накопленный безнал."""
    conn = get_db_connection()
    c = conn.cursor()
    try:
        c.execute("SELECT beznal_added FROM orders WHERE id = ?", (order_id,))
        old_row = c.fetchone()
        old_beznal = old_row[0] if old_row else 0.0
        
        c.execute(
            "UPDATE orders SET type = ?, amount = ?, tips = ?, commission = ?, total = ?, beznal_added = ? WHERE id = ?",
            (order_type, amount, tips, commission, total, beznal_added, order_id),
        )
        
        diff = beznal_added - old_beznal
        c.execute(
            "UPDATE accumulated_beznal SET total_amount = total_amount + ?, last_updated = ? WHERE driver_id = 1",
            (diff, datetime.now(MOSCOW_TZ).strftime("%Y-%m-%d %H:%M:%S")),
        )
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
    by_type["безнал_смена"] = beznal or 0.0
    return by_type

def get_last_fuel_params():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute(
        "SELECT fuel_liters, km, fuel_price FROM shifts WHERE is_open = 0 AND km > 0 AND fuel_price > 0 ORDER BY closed_at DESC, id DESC LIMIT 1"
    )
    row = c.fetchone()
    conn.close()
    if row and row[0] and row[1]:
        consumption = (row[0] / row[1]) * 100
        return float(consumption), float(row[2] or 55.0)
    return 8.0, 55.0

def add_extra_expense(shift_id, amount, description):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute(
        "INSERT INTO extra_expenses (shift_id, amount, description, created_at) VALUES (?, ?, ?, ?)",
        (shift_id, amount, description, datetime.now(MOSCOW_TZ).strftime("%Y-%m-%d %H:%M:%S")),
    )
    conn.commit()
    conn.close()

def get_extra_expenses(shift_id):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT id, amount, description, created_at FROM extra_expenses WHERE shift_id = ? ORDER BY id", (shift_id,))
    rows = c.fetchall()
    conn.close()
    return [{"id": r[0], "amount": r[1] or 0.0, "description": r[2] or "", "created_at": r[3] or ""} for r in rows]

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

def get_shift_orders(shift_id):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT id, type, amount, tips, commission, total, beznal_added, order_time FROM orders WHERE shift_id = ? ORDER BY id DESC", (shift_id,))
    rows = c.fetchall()
    conn.close()
    return rows

# ===== БЕКАПЫ =====
def create_backup():
    backup_dir = get_backup_dir()
    ts = datetime.now(MOSCOW_TZ).strftime("%Y%m%d_%H%M%S")
    username = st.session_state.get("username", "unknown")
    backup_name = f"taxi_{username}_backup_{ts}.db"
    backup_path = os.path.join(backup_dir, backup_name)
    shutil.copy2(get_current_db_name(), backup_path)
    return backup_path

def list_backups():
    backup_dir = get_backup_dir()
    if not os.path.exists(backup_dir):
        return []
    backups = []
    for filename in os.listdir(backup_dir):
        if filename.endswith(".db"):
            filepath = os.path.join(backup_dir, filename)
            stat = os.stat(filepath)
            backups.append({
                "name": filename, "path": filepath,
                "time": datetime.fromtimestamp(stat.st_mtime),
                "size": stat.st_size / 1024,
            })
    backups.sort(key=lambda x: x["time"], reverse=True)
    return backups

def restore_from_backup(backup_path):
    if not os.path.exists(backup_path):
        raise FileNotFoundError(f"Файл бэкапа не найден: {backup_path}")
    create_backup()
    shutil.copy2(backup_path, get_current_db_name())

def download_backup(backup_path):
    with open(backup_path, "rb") as f:
        return f.read()

def upload_and_restore_backup(uploaded_file):
    if uploaded_file is not None:
        temp_path = os.path.join(get_backup_dir(), "temp_restore.db")
        with open(temp_path, "wb") as f:
            f.write(uploaded_file.getbuffer())
        restore_from_backup(temp_path)
        try:
            os.remove(temp_path)
        except:
            pass
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
                try:
                    encoded = st.secrets["google_credentials"]["json_data"]
                    decoded = base64.b64decode(encoded)
                    with open("credentials.json", "wb") as f:
                        f.write(decoded)
                    st.success("✅ credentials.json создан из secrets")
                except Exception as e:
                    st.error(f"❌ Ошибка secrets: {e}")
                    return False
            else:
                st.error("❌ credentials.json не найден!")
                return False
        creds = None
        if os.path.exists("token.json"):
            try:
                creds = Credentials.from_authorized_user_file("token.json", SCOPES)
            except:
                os.remove("token.json")
                creds = None
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                except:
                    creds = None
            if not creds:
                flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
                auth_url, _ = flow.authorization_url(access_type="offline", include_granted_scopes="true", prompt="consent")
                st.info("🔐 Требуется авторизация Google")
                st.markdown(f"""
                 <div style="background: #e3f2fd; padding: 15px; border-radius: 8px; margin: 10px 0;">
                     <a href="{auth_url}" target="_blank" style="font-size: 1.1rem; color: #1976d2; font-weight: bold;">Авторизоваться в Google Drive</a>
                 </div>
                 """, unsafe_allow_html=True)
                st.warning("1. Нажмите кнопку\n2. Войдите под своим Gmail\n3. Разрешите доступ\n4. Вернитесь и нажмите 'Обновить'")
                if st.button("🔄 Обновить", type="primary"):
                    st.rerun()
                return False
        service = build("drive", "v3", credentials=creds)
        results = service.files().list(q=f"name='{BACKUP_FILENAME}' and trashed=false", spaces="drive", fields="files(id, modifiedTime)").execute()
        files = results.get("files", [])
        local_path = get_current_db_name()
        local_mtime = datetime.fromtimestamp(os.path.getmtime(local_path))
        if not files:
            media = MediaFileUpload(local_path, mimetype="application/octet-stream")
            service.files().create(body={"name": BACKUP_FILENAME}, media_body=media).execute()
            st.success("✅ Загружено в Google Drive!")
            return True
        else:
            cloud_mtime = datetime.fromisoformat(files[0]["modifiedTime"].replace("Z", "+00:00"))
            local_mtime_aware = local_mtime.replace(tzinfo=timezone.utc)
            if local_mtime_aware > cloud_mtime:
                media = MediaFileUpload(local_path, mimetype="application/octet-stream")
                service.files().update(fileId=files[0]["id"], media_body=media).execute()
                st.success("✅ Обновлено в Google Drive!")
            else:
                request = service.files().get_media(fileId=files[0]["id"])
                temp_path = local_path + ".temp"
                with open(temp_path, "wb") as f:
                    downloader = MediaIoBaseDownload(f, request)
                    done = False
                    while not done:
                        status, done = downloader.next_chunk()
                shutil.copy2(temp_path, local_path)
                os.remove(temp_path)
                st.success("✅ Скачано из Google Drive!")
                st.cache_data.clear()
                st.rerun()
            return True
    except Exception as e:
        st.error(f"❌ Ошибка Google Drive: {str(e)}")
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
            if st.button("✅ Открыть смену", use_container_width=True):
                open_shift(selected_date.strftime("%Y-%m-%d"))
                st.success(f"✅ Смена открыта: {selected_date.strftime('%Y-%m-%d')}")
                st.rerun()
    else:
        shift_id, date_str = open_shift_data
        st.success(f"✅ Смена открыта: **{date_str}**")
        acc_beznal = get_accumulated_beznal()
        if acc_beznal > 0:
            st.metric("💳 Накопленный безнал", f"{acc_beznal:.0f} ₽")
        with st.expander("➕ Новый заказ", expanded=True):
            col1, col2 = st.columns([2, 1])
            with col1:
                amount_str = st.text_input("Сумма чеком", placeholder="650")
            with col2:
                order_type = st.selectbox("Тип", ["нал", "карта"], index=0, help="нал=78%, карта=75%")
                tips_str = st.text_input("Чаевые", placeholder="0", help="Сумма чаевых")
            try:
                amount = float(amount_str.replace(",", "."))
                tips = float(tips_str.replace(",", ".")) if tips_str else 0.0
                if order_type == "нал":
                    commission = amount * (1 - RATE_NAL)
                    total = amount + tips
                    beznal_added = -commission
                else:
                    final_wo_tips = amount * RATE_CARD
                    commission = amount - final_wo_tips
                    total = final_wo_tips + tips
                    beznal_added = final_wo_tips
                st.caption(f"Комиссия: {commission:.0f} ₽ | Итого: {total:.0f} ₽ | Δ безнал: {beznal_added:+.0f} ₽")
            except ValueError:
                pass
            if st.button("✅ Добавить заказ", use_container_width=True):
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
                        final_wo_tips = amount * RATE_CARD
                        commission = amount - final_wo_tips
                        total = final_wo_tips + tips
                        beznal_added = final_wo_tips
                        db_type = "карта"
                    add_order_and_update_beznal(shift_id, db_type, amount, tips, commission, total, beznal_added, order_time)
                    st.success("✅ Заказ добавлен!")
                    st.rerun()
                except ValueError:
                    st.error("❌ Проверьте сумму и чаевые")
                except Exception as e:
                    st.error(f"❌ Ошибка: {e}")
        
        # ===== СПИСОК ЗАКАЗОВ С КНОПКОЙ ✏️ ИЗМЕНИТЬ =====
        orders = get_shift_orders(shift_id)
        totals = get_shift_totals(shift_id)
        if orders:
            st.subheader("📋 Заказы смены")
            for order_row in orders:
                order_id, typ, am, ti, _, tot, bez, tm = order_row
                edit_key = f"edit_order_{order_id}"
                delete_key = f"del_order_{order_id}"
                confirm_key = f"confirm_del_order_{order_id}"
                
                cols = st.columns([3, 1, 1, 1])  # 4 колонки: инфо, итого, безнал, кнопки
                cols[0].markdown(f"**{typ}** | {tm or ''} | {am:.0f} ₽")
                cols[1].markdown(f"{tot:.0f} ₽")
                cols[2].markdown(f"{bez:+.0f} ₽")
                
                # Кнопка редактирования
                if cols[3].button("✏️", key=edit_key, help="Изменить заказ"):
                    st.session_state[f"editing_order_{order_id}"] = True
                    st.rerun()
                
                # Режим редактирования
                if st.session_state.get(f"editing_order_{order_id}"):
                    with st.expander(f"✏️ Редактирование заказа #{order_id}", expanded=True):
                        edit_col1, edit_col2 = st.columns([2, 1])
                        with edit_col1:
                            edit_amount = st.number_input("Сумма", value=float(am), min_value=0.0, step=10.0, key=f"edit_amt_{order_id}")
                        with edit_col2:
                            edit_type = st.selectbox("Тип", ["нал", "карта"], index=0 if typ == "нал" else 1, key=f"edit_type_{order_id}")
                            edit_tips = st.number_input("Чаевые", value=float(ti or 0), min_value=0.0, step=10.0, key=f"edit_tips_{order_id}")
                        if edit_type == "нал":
                            edit_commission = edit_amount * (1 - RATE_NAL)
                            edit_total = edit_amount + edit_tips
                            edit_beznal = -edit_commission
                        else:
                            edit_final = edit_amount * RATE_CARD
                            edit_commission = edit_amount - edit_final
                            edit_total = edit_final + edit_tips
                            edit_beznal = edit_final
                        st.caption(f"Комиссия: {edit_commission:.0f} ₽ | Итого: {edit_total:.0f} ₽ | Δ безнал: {edit_beznal:+.0f} ₽")
                        edit_btn_col1, edit_btn_col2 = st.columns(2)
                        if edit_btn_col1.button("💾 Сохранить", key=f"save_edit_{order_id}", use_container_width=True):
                            try:
                                update_order_and_adjust_beznal(order_id, edit_type, edit_amount, edit_tips, edit_commission, edit_total, edit_beznal)
                                st.session_state.pop(f"editing_order_{order_id}", None)
                                st.success("✅ Заказ обновлён")
                                st.cache_data.clear()
                                st.rerun()
                            except Exception as e:
                                st.error(f"❌ Ошибка: {e}")
                        if edit_btn_col2.button("❌ Отмена", key=f"cancel_edit_{order_id}", use_container_width=True):
                            st.session_state.pop(f"editing_order_{order_id}", None)
                            st.rerun()
                    st.divider()
                    continue
                
                # Кнопка удаления
                if st.session_state.get(confirm_key):
                    c1, c2 = cols[3].columns(2)
                    if c1.button("✅ Удалить", key=f"yes_{order_id}", use_container_width=True):
                        try:
                            delete_order_and_update_beznal(order_id)
                            st.session_state.pop(confirm_key, None)
                            st.success("✅ Заказ удалён")
                            st.rerun()
                        except Exception as e:
                            st.error(f"❌ Ошибка: {e}")
                    if c2.button("❌ Отмена", key=f"no_{order_id}", use_container_width=True):
                        st.session_state.pop(confirm_key, None)
                        st.rerun()
                elif cols[3].button("🗑️", key=delete_key, help="Удалить заказ"):
                    st.session_state[confirm_key] = True
                    st.rerun()
            st.divider()
            st.metric("📊 Итого смены", f"{totals.get('нал', 0):.0f} + {totals.get('карта', 0):.0f} + {totals.get('чаевые', 0):.0f}")
        
        with st.expander("💸 Доп. расходы", expanded=False):
            st.subheader("Добавить расход")
            col1, col2, col3 = st.columns([2, 1, 1])
            with col1:
                exp_desc = st.selectbox("Тип", POPULAR_EXPENSES, key="exp_desc")
            with col2:
                exp_amt = st.number_input("Сумма", min_value=0.0, step=50.0, value=100.0, key="exp_amt")
            with col3:
                if st.button("➕ Добавить", use_container_width=True, key="add_exp"):
                    if exp_desc and exp_amt > 0:
                        add_extra_expense(shift_id, exp_amt, exp_desc)
                        st.success("✅ Расход добавлен")
                        st.rerun()
            st.divider()
            expenses = get_extra_expenses(shift_id)
            total_extra = 0.0
            for exp in expenses:
                cols = st.columns([3, 1, 1])
                cols[0].markdown(f"**{exp['description']}**")
                cols[1].markdown(f"{exp['amount']:.0f} ₽")
                if cols[2].button("🗑️", key=f"del_exp_{exp['id']}", use_container_width=True):
                    delete_extra_expense(exp["id"])
                    st.rerun()
                total_extra += exp["amount"]
            if expenses:
                st.divider()
                st.metric("Итого расходов", f"{total_extra:.0f} ₽")
        
        st.divider()
        st.subheader("📈 Итоги смены")
        total_income = totals.get("нал", 0) + totals.get("карта", 0) + totals.get("чаевые", 0)
        total_extra = get_total_extra_expenses(shift_id)
        col1, col2, col3 = st.columns(3)
        col1.metric("Доход", f"{total_income:.0f} ₽")
        col2.metric("Расходы", f"{total_extra:.0f} ₽")
        col3.metric("Прибыль", f"{total_income - total_extra:.0f} ₽", delta=f"{total_income - total_extra:.0f}")
        
        with st.expander("⛽ Закрыть смену", expanded=False):
            last_cons, last_price = get_last_fuel_params()
            km_close = st.number_input("Пробег (км)", value=100, min_value=0, key="km_close")
            col1, col2 = st.columns(2)
            with col1:
                consumption = st.number_input("Расход (л/100км)", value=float(last_cons), step=0.5, key="cons_close")
            with col2:
                fuel_price = st.number_input("Цена топлива (₽/л)", value=float(last_price), step=1.0, key="fuel_close")
            if km_close > 0 and consumption > 0 and fuel_price > 0:
                liters = (km_close / 100) * consumption
                fuel_cost = liters * fuel_price
                profit = total_income - total_extra - fuel_cost
                st.info(f"🛢️ {liters:.1f} л × {fuel_price:.0f} ₽ = **{fuel_cost:.0f} ₽**")
                st.success(f"💰 Чистая прибыль: **{profit:.0f} ₽**")
            if not st.session_state.get("confirm_close_shift"):
                if st.button("🔒 Закрыть смену", use_container_width=True, type="primary"):
                    st.session_state.confirm_close_shift = True
                    st.rerun()
            else:
                st.warning("⚠️ Подтвердите закрытие смены")
                col1, col2 = st.columns(2)
                if col1.button("✅ Да, закрыть", use_container_width=True, type="primary"):
                    liters = (km_close / 100) * consumption if km_close > 0 else 0.0
                    close_shift_db(shift_id, km_close, liters, fuel_price)
                    st.session_state.pop("confirm_close_shift", None)
                    st.success("✅ Смена закрыта!")
                    st.cache_data.clear()
                    st.rerun()
                if col2.button("❌ Отмена", use_container_width=True):
                    st.session_state.pop("confirm_close_shift", None)
                    st.rerun()

# ===== UI: ОТЧЁТЫ =====
def show_reports_page():
    st.title("📊 Отчёты")
    check_and_create_tables()
    try:
        from pages_imports import get_available_year_months_cached, get_month_totals_cached, format_month_option, get_month_shifts_details_cached, get_month_statistics
        year_months = get_available_year_months_cached()
        if not year_months:
            st.info("ℹ️ Нет закрытых смен с заказами")
            return
        selected_ym = st.selectbox("Период", year_months, index=0, format_func=format_month_option)
        totals = get_month_totals_cached(selected_ym)
        st.subheader(f"Итого за {format_month_option(selected_ym)}")
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Наличные", f"{totals.get('нал', 0):.0f} ₽")
        col2.metric("Карта", f"{totals.get('карта', 0):.0f} ₽")
        col3.metric("Чаевые", f"{totals.get('чаевые', 0):.0f} ₽")
        col4.metric("Всего", f"{totals.get('всего', 0):.0f} ₽")
        st.divider()
        df_shifts = get_month_shifts_details_cached(selected_ym)
        if not df_shifts.empty:
            dates = df_shifts["Дата"].unique().tolist()
            selected_date = st.selectbox("Смена", options=dates)
            df_day = df_shifts[df_shifts["Дата"] == selected_date].copy()
            if not df_day.empty:
                st.dataframe(df_day, use_container_width=True)
                row = df_day.iloc[0]
                fuel_cost = row["Литры"] * row["Цена"] if row["Литры"] > 0 else 0
                col1, col2, col3 = st.columns(3)
                col1.metric("Доход", f"{row['Всего']:.0f} ₽")
                col2.metric("Топливо", f"{fuel_cost:.0f} ₽")
                col3.metric("Прибыль", f"{row['Всего'] - fuel_cost:.0f} ₽")
        st.divider()
        stats = get_month_statistics(selected_ym)
        col1, col2, col3 = st.columns(3)
        col1.metric("Смен", stats.get("смен", 0))
        col2.metric("Заказов", stats.get("заказов", 0))
        col3.metric("Средний чек", f"{stats.get('средний_чек', 0):.0f} ₽")
        col1, col2, col3 = st.columns(3)
        col1.metric("Бензин", f"{stats.get('бензин', 0):.0f} ₽")
        col2.metric("Расходы", f"{stats.get('расходы', 0):.0f} ₽")
        col3.metric("Прибыль", f"{stats.get('прибыль', 0):.0f} ₽", delta=f"{stats.get('рентабельность', 0):.1f}%")
    except ImportError:
        st.error("❌ pages_imports.py не найден")
    except Exception as e:
        st.error(f"❌ Ошибка отчётов: {e}")

# ===== UI: АДМИНКА =====
def show_admin_page():
    st.title("🔧 Админка")
    admin_pwd = st.secrets.get("ADMIN_PASSWORD", "changeme")
    pwd = st.text_input("Пароль админа", type="password")
    if st.button("Войти", use_container_width=True):
        if pwd == admin_pwd:
            st.session_state.admin_auth = True
            st.rerun()
        else:
            st.error("❌ Неверный пароль")
    if st.session_state.get("admin_auth"):
        tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(["Пересчёт", "Безнал", "Бэкапы", "Загрузка", "Google Drive", "Сброс БД"])
        with tab1:
            st.write("**Пересчёт всех комиссий**")
            if st.button("🔄 Пересчитать всё", use_container_width=True):
                from pages_imports import recalc_full_db
                new_total = recalc_full_db()
                st.success(f"✅ Пересчитано. Безнал: {new_total:.0f} ₽")
        with tab2:
            curr = get_accumulated_beznal()
            new_val = st.number_input("Новый безнал", value=float(curr))
            if st.button("💾 Установить", use_container_width=True):
                set_accumulated_beznal(new_val)
                st.success("✅ Безнал обновлён")
                st.rerun()
        with tab3:
            if st.button("📦 Создать бэкап", use_container_width=True):
                path = create_backup()
                st.success(f"✅ {os.path.basename(path)}")
            backups = list_backups()
            for b in backups:
                cols = st.columns([3, 1, 1, 1])
                cols[0].write(b["name"])
                cols[1].download_button(label="⬇️", data=download_backup(b["path"]), file_name=b["name"], key=f"db_{b['name']}", use_container_width=True)
                cols[2].button("📥", key=f"rb_{b['name']}", on_click=lambda p=b["path"]: restore_from_backup(p), use_container_width=True)
                cols[3].button("🗑️", key=f"xb_{b['name']}", on_click=lambda p=b["path"]: os.remove(p), use_container_width=True)
        with tab4:
            uploaded = st.file_uploader("Загрузить .db", type="db")
            if uploaded and st.button("📥 Восстановить", use_container_width=True):
                if upload_and_restore_backup(uploaded):
                    st.success("✅ Восстановлено!")
                    st.rerun()
        with tab5:
            st.subheader("Google Drive")
            st.info("Автоматический бэкап/восстановление")
            if st.button("🔄 Синхронизировать", use_container_width=True, type="primary"):
                sync_with_google_drive()
        with tab6:
            if st.button("💥 СБРОСИТЬ БД", use_container_width=True, type="primary"):
                from pages_imports import reset_db
                reset_db()
                st.success("✅ БД сброшена")
                st.rerun()

# ===== MAIN =====
if __name__ == "__main__":
    st.set_page_config(page_title="Taxi Shift Manager", page_icon="🚕", layout="wide")
    apply_mobile_optimized_css()
    init_auth_db()
    ensure_users_dir()
    init_session()
    saved_username = load_session_from_disk()
    if saved_username and "username" not in st.session_state:
        st.session_state.username = saved_username
        st.session_state.page = "main"
    if "username" not in st.session_state:
        st.title("🚕 Taxi Shift Manager")
        st.markdown("### Вход / Регистрация")
        u = st.text_input("👤 Логин")
        p = st.text_input("🔑 Пароль", type="password")
        col1, col2 = st.columns(2)
        with col1:
            if st.button("🚀 Войти", use_container_width=True):
                if authenticate_user(u, p):
                    st.session_state.username = u.strip()
                    st.session_state.page = "main"
                    st.rerun()
                else:
                    st.error("❌ Неверный логин/пароль")
        with col2:
            if st.button("➕ Регистрация", use_container_width=True):
                if register_user(u, p):
                    st.success("✅ Зарегистрирован! Теперь войдите.")
                else:
                    st.error("❌ Ошибка регистрации (логин занят?)")
        st.stop()
    with st.sidebar:
        st.markdown(f"""
         <div style="text-align: center; padding: 20px 0;">
             <div style="font-size: 4rem; margin-bottom: 10px;">🚕</div>
             <div style="font-size: 1.5rem; font-weight: bold; margin-bottom: 5px;">{st.session_state.username}</div>
             <div style="color: #64748b; font-size: 0.9rem;">{get_session_time_remaining()}</div>
         </div>
         """, unsafe_allow_html=True)
        try:
            db_path = get_current_db_name()
            if os.path.exists(db_path):
                size = os.path.getsize(db_path) / 1024
                st.markdown(f"""
                 <div style="background: white; padding: 15px; border-radius: 12px; margin: 15px 0; text-align: center; box-shadow: 0 2px 8px rgba(0,0,0,0.1);">
                     <div style="font-size: 0.85rem; color: #64748b; margin-bottom: 5px;">Размер БД</div>
                     <div style="font-size: 1.5rem; font-weight: bold; color: #1e293b;">{size:.1f} KB</div>
                 </div>
                 """, unsafe_allow_html=True)
            acc = get_accumulated_beznal()
            st.markdown(f"""
             <div style="background: white; padding: 15px; border-radius: 12px; margin: 15px 0; text-align: center; box-shadow: 0 2px 8px rgba(0,0,0,0.1);">
                 <div style="font-size: 0.85rem; color: #64748b; margin-bottom: 5px;">Накопленный безнал</div>
                 <div style="font-size: 1.5rem; font-weight: bold; color: #1e293b;">{acc:.0f} ₽</div>
             </div>
             """, unsafe_allow_html=True)
        except Exception as e:
            st.error(f"Сайдбар ошибка: {e}")
        st.divider()
        if st.button("🏠 Главная", use_container_width=True):
            st.session_state.page = "main"
            st.rerun()
        if st.button("📊 Отчёты", use_container_width=True):
            st.session_state.page = "reports"
            st.rerun()
        if st.button("🔧 Админ", use_container_width=True):
            st.session_state.page = "admin"
            st.rerun()
        st.divider()
        st.caption(f"Осталось: {get_session_time_remaining()}")
        if st.button("👋 Выход", use_container_width=True):
            clear_session_disk()
            st.session_state.clear()
            st.rerun()
    page = st.session_state.get("page", "main")
    if page == "main":
        show_main_page()
    elif page == "reports":
        show_reports_page()
    elif page == "admin":
        show_admin_page()