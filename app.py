# app.py — ПОЛНАЯ ВЕРСИЯ v2: мобильная, без боковой панели, Telegram бэкап
import os
import json
import shutil
import sqlite3
import time
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

# ===== CSS: МОБИЛЬНАЯ ОПТИМИЗАЦИЯ =====
def apply_mobile_css():
    st.markdown("""
    <style>
    /* Скрываем боковую панель полностью */
    [data-testid="stSidebar"] { display: none !important; }
    [data-testid="collapsedControl"] { display: none !important; }

    /* Убираем лишние отступы */
    .main > div { padding: 0.5rem !important; padding-bottom: 80px !important; }
    .block-container {
        padding: 0.5rem !important;
        padding-bottom: 80px !important;
        max-width: 100% !important;
    }

    /* Крупные кнопки для пальцев */
    .stButton > button {
        width: 100% !important;
        min-height: 52px !important;
        font-size: 1rem !important;
        border-radius: 12px !important;
        font-weight: 600 !important;
    }

    /* Крупные поля ввода */
    .stTextInput input, .stNumberInput input {
        font-size: 1.1rem !important;
        min-height: 48px !important;
        border-radius: 10px !important;
    }

    /* Нижняя навигация — фиксированная */
    .bottom-nav {
        position: fixed;
        bottom: 0;
        left: 0;
        right: 0;
        background: #1e293b;
        display: flex;
        z-index: 9999;
        padding: 4px 0;
        box-shadow: 0 -2px 10px rgba(0,0,0,0.3);
    }
    .nav-btn {
        flex: 1;
        background: none;
        border: none;
        color: #94a3b8;
        padding: 8px 4px;
        cursor: pointer;
        display: flex;
        flex-direction: column;
        align-items: center;
        gap: 2px;
        font-size: 0.65rem;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        transition: color 0.2s;
    }
    .nav-btn.active { color: #38bdf8 !important; }
    .nav-btn span.icon { font-size: 1.4rem; }

    /* Карточки метрик */
    [data-testid="metric-container"] {
        background: #f8fafc;
        border-radius: 12px;
        padding: 12px !important;
        border: 1px solid #e2e8f0;
    }

    /* Заголовок страницы */
    h1 { font-size: 1.4rem !important; margin-bottom: 0.5rem !important; }
    h2 { font-size: 1.2rem !important; }
    h3 { font-size: 1.1rem !important; }

    /* Компактные разделители */
    hr { margin: 0.5rem 0 !important; }

    /* Selectbox */
    .stSelectbox select { font-size: 1rem !important; min-height: 48px !important; }

    /* Убираем "Made with Streamlit" */
    footer { display: none !important; }
    </style>
    """, unsafe_allow_html=True)


def render_bottom_nav(current_page: str):
    """Нижняя навигационная панель в мобильном стиле."""
    pages = [
        ("main",    "🏠", "Главная"),
        ("reports", "📊", "Отчёты"),
        ("admin",   "🔧", "Настройки"),
    ]
    buttons_html = ""
    for key, icon, label in pages:
        active = "active" if current_page == key else ""
        buttons_html += f"""
        <button class="nav-btn {active}" onclick="
            var inputs = window.parent.document.querySelectorAll('input[type=hidden]');
            " data-page="{key}">
            <span class="icon">{icon}</span>{label}
        </button>"""

    # Streamlit не даёт JS навигацию напрямую, используем кнопки через columns
    cols = st.columns(3)
    labels = [("🏠 Главная", "main"), ("📊 Отчёты", "reports"), ("🔧 Настройки", "admin")]
    for i, (col, (label, page_key)) in enumerate(zip(cols, labels)):
        btn_type = "primary" if current_page == page_key else "secondary"
        if col.button(label, key=f"nav_{page_key}", type=btn_type, use_container_width=True):
            st.session_state.page = page_key
            st.rerun()

    # Разделитель + отступ снизу чтобы контент не перекрывался кнопками
    st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)


# ===== СЕССИЯ =====
def save_session_to_disk():
    try:
        if "username" in st.session_state:
            data = {
                "username": st.session_state["username"],
                "session_start": st.session_state.get("session_start").isoformat()
                    if st.session_state.get("session_start") else None,
            }
            with open(SESSION_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f)
    except Exception:
        pass


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
    except Exception:
        pass
    return None


def clear_session_disk():
    try:
        if os.path.exists(SESSION_FILE):
            os.remove(SESSION_FILE)
    except Exception:
        pass


def init_session():
    if "session_start" not in st.session_state:
        st.session_state.session_start = datetime.now(MOSCOW_TZ)
        save_session_to_disk()
    elapsed = (datetime.now(MOSCOW_TZ) - st.session_state.session_start).total_seconds()
    if elapsed > SESSION_TIMEOUT:
        st.session_state.clear()
        clear_session_disk()
        st.warning("⏰ Сессия истекла, войдите снова")
        st.rerun()


# ===== ПАПКИ =====
def ensure_users_dir():
    os.makedirs(USERS_DIR, exist_ok=True)


def get_user_dir(username: str) -> str:
    safe = "".join(c for c in username if c.isalnum() or c in ("_", "-")) or "user"
    path = os.path.join(USERS_DIR, safe)
    os.makedirs(path, exist_ok=True)
    return path


def get_current_db_name() -> str:
    username = st.session_state.get("username")
    if not username:
        return "taxi_default.db"
    safe = "".join(c for c in username if c.isalnum() or c in ("_", "-"))
    return os.path.join(get_user_dir(username), f"taxi{safe}.db")


def get_backup_dir() -> str:
    path = os.path.join(get_user_dir(st.session_state.get("username", "unknown")), "backups")
    os.makedirs(path, exist_ok=True)
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
            c.execute(
                "INSERT INTO accumulated_beznal (driver_id, total_amount, last_updated) VALUES (1, 0, ?)",
                (datetime.now(MOSCOW_TZ).strftime("%Y-%m-%d %H:%M:%S"),)
            )
        conn.commit()
        conn.close()
    except Exception as e:
        st.error(f"❌ Ошибка БД: {e}")


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
    return bcrypt.hash(password.strip().encode("utf-8")[:72])


def verify_password(password: str, pw_hash: str) -> bool:
    try:
        return bcrypt.verify(password.strip().encode("utf-8")[:72], pw_hash)
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
    except Exception:
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
    c.execute(
        "INSERT INTO shifts (date, is_open, opened_at) VALUES (?, 1, ?)",
        (date_str, datetime.now(MOSCOW_TZ).strftime("%Y-%m-%d %H:%M:%S"))
    )
    sid = c.lastrowid
    conn.commit()
    conn.close()
    return sid


def close_shift_db(shift_id: int, km: int, liters: float, fuel_price: float):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute(
        "UPDATE shifts SET is_open=0, km=?, fuel_liters=?, fuel_price=?, closed_at=? WHERE id=?",
        (km, liters, fuel_price, datetime.now(MOSCOW_TZ).strftime("%Y-%m-%d %H:%M:%S"), shift_id)
    )
    conn.commit()
    conn.close()


# ===== ЗАКАЗЫ =====
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
        "UPDATE accumulated_beznal SET total_amount=?, last_updated=? WHERE driver_id=1",
        (amount, datetime.now(MOSCOW_TZ).strftime("%Y-%m-%d %H:%M:%S"))
    )
    conn.commit()
    conn.close()


def add_order_and_update_beznal(shift_id, order_type, amount, tips, commission, total, beznal_added, order_time):
    conn = get_db_connection()
    c = conn.cursor()
    try:
        c.execute(
            "INSERT INTO orders (shift_id, type, amount, tips, commission, total, beznal_added, order_time) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (shift_id, order_type, amount, tips, commission, total, beznal_added, order_time)
        )
        c.execute(
            "UPDATE accumulated_beznal SET total_amount=total_amount+?, last_updated=? WHERE driver_id=1",
            (beznal_added, datetime.now(MOSCOW_TZ).strftime("%Y-%m-%d %H:%M:%S"))
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
        c.execute("SELECT beznal_added FROM orders WHERE id=?", (order_id,))
        row = c.fetchone()
        if row:
            beznal = row[0] or 0.0
            c.execute("DELETE FROM orders WHERE id=?", (order_id,))
            c.execute(
                "UPDATE accumulated_beznal SET total_amount=total_amount-?, last_updated=? WHERE driver_id=1",
                (beznal, datetime.now(MOSCOW_TZ).strftime("%Y-%m-%d %H:%M:%S"))
            )
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
        c.execute("SELECT beznal_added FROM orders WHERE id=?", (order_id,))
        old = c.fetchone()
        old_beznal = old[0] if old else 0.0
        c.execute(
            "UPDATE orders SET type=?, amount=?, tips=?, commission=?, total=?, beznal_added=? WHERE id=?",
            (order_type, amount, tips, commission, total, beznal_added, order_id)
        )
        diff = beznal_added - old_beznal
        c.execute(
            "UPDATE accumulated_beznal SET total_amount=total_amount+?, last_updated=? WHERE driver_id=1",
            (diff, datetime.now(MOSCOW_TZ).strftime("%Y-%m-%d %H:%M:%S"))
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
    c.execute("SELECT type, SUM(total - tips) FROM orders WHERE shift_id=? GROUP BY type", (shift_id,))
    by_type = dict(c.fetchall())
    c.execute("SELECT SUM(tips) FROM orders WHERE shift_id=?", (shift_id,))
    tips = c.fetchone()[0] or 0.0
    conn.close()
    by_type["чаевые"] = tips
    return by_type


def get_shift_orders(shift_id):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute(
        "SELECT id, type, amount, tips, commission, total, beznal_added, order_time "
        "FROM orders WHERE shift_id=? ORDER BY id DESC",
        (shift_id,)
    )
    rows = c.fetchall()
    conn.close()
    return rows


def get_last_fuel_params():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute(
        "SELECT fuel_liters, km, fuel_price FROM shifts "
        "WHERE is_open=0 AND km>0 AND fuel_price>0 ORDER BY closed_at DESC LIMIT 1"
    )
    row = c.fetchone()
    conn.close()
    if row and row[0] and row[1]:
        return (row[0] / row[1]) * 100, float(row[2] or 55.0)
    return 8.0, 55.0


# ===== РАСХОДЫ =====
def add_extra_expense(shift_id, amount, description):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute(
        "INSERT INTO extra_expenses (shift_id, amount, description, created_at) VALUES (?, ?, ?, ?)",
        (shift_id, amount, description, datetime.now(MOSCOW_TZ).strftime("%Y-%m-%d %H:%M:%S"))
    )
    conn.commit()
    conn.close()


def get_extra_expenses(shift_id):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute(
        "SELECT id, amount, description FROM extra_expenses WHERE shift_id=? ORDER BY id",
        (shift_id,)
    )
    rows = c.fetchall()
    conn.close()
    return [{"id": r[0], "amount": r[1] or 0.0, "description": r[2] or ""} for r in rows]


def delete_extra_expense(expense_id):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("DELETE FROM extra_expenses WHERE id=?", (expense_id,))
    conn.commit()
    conn.close()


def get_total_extra_expenses(shift_id) -> float:
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT SUM(amount) FROM extra_expenses WHERE shift_id=?", (shift_id,))
    row = c.fetchone()
    conn.close()
    return row[0] or 0.0


# ===== БЭКАПЫ =====
def create_backup() -> str:
    backup_dir = get_backup_dir()
    ts = datetime.now(MOSCOW_TZ).strftime("%Y%m%d_%H%M%S")
    path = os.path.join(backup_dir, f"taxi_{st.session_state.get('username', 'u')}_{ts}.db")
    shutil.copy2(get_current_db_name(), path)
    return path


def list_backups():
    backup_dir = get_backup_dir()
    if not os.path.exists(backup_dir):
        return []
    result = []
    for f in os.listdir(backup_dir):
        if f.endswith(".db"):
            path = os.path.join(backup_dir, f)
            stat = os.stat(path)
            result.append({
                "name": f, "path": path,
                "time": datetime.fromtimestamp(stat.st_mtime),
                "size": stat.st_size / 1024
            })
    return sorted(result, key=lambda x: x["time"], reverse=True)


def restore_from_backup(backup_path: str):
    if not os.path.exists(backup_path):
        raise FileNotFoundError(f"Файл не найден: {backup_path}")
    create_backup()  # сначала бэкапим текущее
    db_path = get_current_db_name()
    shutil.copy2(backup_path, db_path)
    st.cache_data.clear()


def upload_and_restore_backup(file) -> bool:
    """Восстановление из загруженного файла. Возвращает True при успехе."""
    if not file:
        return False
    db_path = get_current_db_name()
    # Сначала бэкапим текущую БД
    try:
        if os.path.exists(db_path):
            create_backup()
    except Exception:
        pass
    # Пишем загруженный файл напрямую в db_path
    raw = file.read()
    with open(db_path, "wb") as f:
        f.write(raw)
    # Проверяем что файл валидный sqlite
    try:
        conn = sqlite3.connect(db_path)
        conn.execute("SELECT name FROM sqlite_master LIMIT 1")
        conn.close()
    except Exception as e:
        raise ValueError(f"Файл не является базой данных SQLite: {e}")
    st.cache_data.clear()
    return True


# ===== ЯНДЕКС ДИСК БЭКАП (REST API) =====
YADISK_API = "https://cloud-api.yandex.net/v1/disk"
YADISK_BACKUP_PATH = "disk:/taxi_backup/taxi_backup.db"
YADISK_BACKUP_DIR_PATH = "disk:/taxi_backup"


def get_yadisk_token() -> str:
    """Читает OAuth-токен Яндекс Диска из secrets или session_state."""
    token = ""
    try:
        token = st.secrets.get("YADISK_TOKEN", "")
    except Exception:
        pass
    return str(st.session_state.get("yadisk_token", token)).strip()


def _yadisk_api(method: str, url: str, token: str,
                data=None, params: dict = None, timeout: int = 30) -> tuple:
    """Выполняет запрос к REST API Яндекс Диска. Возвращает (status, dict_or_bytes)."""
    import urllib.request
    import urllib.parse
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"OAuth {token}")
    req.add_header("Accept", "application/json")
    if data:
        req.add_header("Content-Type", "application/octet-stream")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            try:
                return resp.status, json.loads(raw)
            except Exception:
                return resp.status, raw
    except Exception as e:
        code = getattr(e, "code", 0)
        try:
            body = e.read()
            return code, json.loads(body)
        except Exception:
            return code, {"message": str(e)}


def yadisk_upload_backup(token: str) -> bool:
    """Загружает .db файл на Яндекс Диск через REST API."""
    import urllib.request
    db_path = get_current_db_name()
    if not os.path.exists(db_path):
        st.error("❌ База данных не найдена")
        return False
    if not token:
        st.error("❌ Не задан токен Яндекс Диска")
        return False

    # Создаём папку (игнорируем ошибку если уже существует)
    _yadisk_api("PUT", f"{YADISK_API}/resources", token,
                params={"path": YADISK_BACKUP_DIR_PATH})

    # Получаем URL для загрузки
    status, resp = _yadisk_api(
        "GET", f"{YADISK_API}/resources/upload", token,
        params={"path": YADISK_BACKUP_PATH, "overwrite": "true"}
    )
    if status != 200:
        msg = resp.get("message", str(resp)) if isinstance(resp, dict) else str(resp)
        st.error(f"❌ Не удалось получить URL загрузки (код {status}): {msg}")
        return False

    upload_url = resp.get("href") if isinstance(resp, dict) else None
    if not upload_url:
        st.error("❌ Яндекс не вернул URL для загрузки")
        return False

    # Загружаем файл по подписанному URL (без заголовка авторизации)
    with open(db_path, "rb") as f:
        db_bytes = f.read()
    req = urllib.request.Request(upload_url, data=db_bytes, method="PUT")
    req.add_header("Content-Type", "application/octet-stream")
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return r.status in (200, 201, 202, 204)
    except Exception as e:
        code = getattr(e, "code", 0)
        st.error(f"❌ Ошибка загрузки файла (код {code}): {e}")
        return False


def yadisk_download_backup(token: str) -> bool:
    """Скачивает .db файл с Яндекс Диска через REST API."""
    import urllib.request
    if not token:
        st.error("❌ Не задан токен Яндекс Диска")
        return False

    # Получаем URL для скачивания
    status, resp = _yadisk_api(
        "GET", f"{YADISK_API}/resources/download", token,
        params={"path": YADISK_BACKUP_PATH}
    )
    if status == 404:
        st.warning("⚠️ Файл не найден на Яндекс Диске — сначала сделайте загрузку")
        return False
    if status != 200:
        msg = resp.get("message", str(resp)) if isinstance(resp, dict) else str(resp)
        st.error(f"❌ Не удалось получить URL скачивания (код {status}): {msg}")
        return False

    download_url = resp.get("href") if isinstance(resp, dict) else None
    if not download_url:
        st.error("❌ Яндекс не вернул URL для скачивания")
        return False

    try:
        with urllib.request.urlopen(download_url, timeout=120) as r:
            db_bytes = r.read()
    except Exception as e:
        st.error(f"❌ Ошибка скачивания: {e}")
        return False

    if len(db_bytes) < 100:
        st.error("❌ Скачанный файл слишком мал, возможно повреждён")
        return False

    db_path = get_current_db_name()
    try:
        if os.path.exists(db_path):
            create_backup()
    except Exception:
        pass

    with open(db_path, "wb") as f:
        f.write(db_bytes)

    try:
        conn = sqlite3.connect(db_path)
        conn.execute("SELECT name FROM sqlite_master LIMIT 1")
        conn.close()
    except Exception as e:
        raise ValueError(f"Скачанный файл повреждён: {e}")

    st.cache_data.clear()
    return True


def yadisk_get_backup_info(token: str) -> dict:
    """Получает информацию о файле бэкапа через REST API."""
    if not token:
        return {}
    status, resp = _yadisk_api(
        "GET", f"{YADISK_API}/resources", token,
        params={"path": YADISK_BACKUP_PATH, "fields": "modified,size"}
    )
    if status == 200 and isinstance(resp, dict):
        size_kb = (resp.get("size") or 0) // 1024
        modified = resp.get("modified", "")
        try:
            dt = datetime.fromisoformat(modified.replace("Z", "+00:00"))
            modified = dt.astimezone(MOSCOW_TZ).strftime("%d.%m.%Y %H:%M")
        except Exception:
            pass
        return {"modified": modified, "size_kb": size_kb}
    return {}


# ===== UI: ВХОД / РЕГИСТРАЦИЯ =====
def show_login_page():
    st.markdown("""
    <div style="text-align:center; padding: 2rem 0 1rem;">
        <div style="font-size: 4rem;">🚕</div>
        <h1 style="margin:0;">Taxi Shift Manager</h1>
        <p style="color:#64748b;">Учёт смен и доходов</p>
    </div>
    """, unsafe_allow_html=True)

    u = st.text_input("👤 Логин", placeholder="Введите логин")
    p = st.text_input("🔑 Пароль", type="password", placeholder="Введите пароль")

    col1, col2 = st.columns(2)
    with col1:
        if st.button("🚀 Войти", use_container_width=True, type="primary"):
            if authenticate_user(u, p):
                st.session_state.username = u.strip()
                st.session_state.page = "main"
                save_session_to_disk()
                st.rerun()
            else:
                st.error("❌ Неверный логин или пароль")
    with col2:
        if st.button("➕ Регистрация", use_container_width=True):
            if register_user(u, p):
                st.success("✅ Зарегистрирован! Войдите.")
            else:
                st.error("❌ Логин уже занят или ошибка")


# ===== UI: ГЛАВНАЯ =====
def show_main_page():
    check_and_create_tables()
    open_shift_data = get_open_shift()

    # Шапка с безналом
    acc = get_accumulated_beznal()
    col_title, col_beznal = st.columns([2, 1])
    col_title.markdown(f"## 👨‍💼 {st.session_state.username}")
    col_beznal.metric("💳 Безнал", f"{acc:.0f} ₽")

    if not open_shift_data:
        st.info("ℹ️ Нет открытой смены")
        with st.expander("📅 Открыть смену", expanded=True):
            selected_date = st.date_input("📅 Дата", value=date.today())
            if st.button("✅ Открыть смену", use_container_width=True, type="primary"):
                open_shift(selected_date.strftime("%Y-%m-%d"))
                st.rerun()
        return

    shift_id, date_str = open_shift_data
    st.success(f"✅ Смена: **{date_str}**")

    # ===== БЛОК ДОБАВЛЕНИЯ ЗАКАЗА =====
    with st.expander("➕ Добавить заказ", expanded=True):
        col1, col2 = st.columns([3, 2])
        with col1:
            amount_str = st.text_input(
                "💰 Сумма чеком (₽)",
                placeholder="650",
                key="order_amount",
                help="Введите сумму цифрами"
            )
        with col2:
            order_type = st.selectbox("💳 Тип", ["нал", "карта"], key="order_type")

        tips_str = st.text_input("💡 Чаевые (₽)", placeholder="0", value="0", key="order_tips")

        # Предпросмотр расчёта
        try:
            prev_amount = float(amount_str.replace(",", ".")) if amount_str else 0.0
            prev_tips = float(tips_str.replace(",", ".")) if tips_str else 0.0
            if prev_amount > 0:
                if order_type == "нал":
                    prev_comm = prev_amount * (1 - RATE_NAL)
                    prev_total = prev_amount + prev_tips
                    prev_bez = -prev_comm
                    st.caption(f"📊 Комиссия: **{prev_comm:.0f} ₽** | На руки: **{prev_total:.0f} ₽** | Безнал: **{prev_bez:+.0f} ₽**")
                else:
                    prev_final = prev_amount * RATE_CARD
                    prev_comm = prev_amount - prev_final
                    prev_total = prev_final + prev_tips
                    st.caption(f"📊 Комиссия: **{prev_comm:.0f} ₽** | На руки: **{prev_total:.0f} ₽** | Безнал: **+{prev_final:.0f} ₽**")
        except Exception:
            pass

        if st.button("✅ Добавить заказ", use_container_width=True, type="primary", key="btn_add_order"):
            # ИСПРАВЛЕНИЕ: сначала парсим, только потом добавляем
            parse_ok = False
            amount = 0.0
            tips = 0.0
            try:
                amount = float(str(amount_str).replace(",", ".").strip())
                tips = float(str(tips_str).replace(",", ".").strip()) if tips_str else 0.0
                if amount <= 0:
                    st.error("❌ Сумма должна быть больше 0")
                else:
                    parse_ok = True
            except (ValueError, AttributeError):
                st.error("❌ Введите корректное число (например: 650)")

            if parse_ok:
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
                try:
                    add_order_and_update_beznal(
                        shift_id, db_type, amount, tips,
                        commission, total, beznal_added, order_time
                    )
                    st.success(f"✅ Добавлен заказ {amount:.0f} ₽ ({db_type})")
                    # Обновляем безнал в шапке немедленно
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ Ошибка сохранения: {e}")

    # ===== СПИСОК ЗАКАЗОВ =====
    orders = get_shift_orders(shift_id)
    totals = get_shift_totals(shift_id)

    if orders:
        st.markdown("### 📋 Заказы смены")
        for order_row in orders:
            order_id, typ, am, ti, _, tot, bez, tm = order_row
            edit_active = st.session_state.get(f"editing_{order_id}", False)

            if edit_active:
                with st.container():
                    st.markdown(f"**✏️ Редактирование #{order_id}**")
                    e_amt = st.number_input("💰 Сумма", value=float(am), min_value=0.1, key=f"e_amt_{order_id}")
                    e_type = st.selectbox("💳 Тип", ["нал", "карта"],
                                         index=0 if typ == "нал" else 1, key=f"e_type_{order_id}")
                    e_tips = st.number_input("💡 Чаевые", value=float(ti or 0), min_value=0.0, key=f"e_tips_{order_id}")
                    if e_type == "нал":
                        e_comm = e_amt * (1 - RATE_NAL)
                        e_tot = e_amt + e_tips
                        e_bez = -e_comm
                    else:
                        e_f = e_amt * RATE_CARD
                        e_comm = e_amt - e_f
                        e_tot = e_f + e_tips
                        e_bez = e_f
                    c1, c2 = st.columns(2)
                    if c1.button("💾 Сохранить", key=f"save_{order_id}", use_container_width=True, type="primary"):
                        update_order_and_adjust_beznal(order_id, e_type, e_amt, e_tips, e_comm, e_tot, e_bez)
                        st.session_state.pop(f"editing_{order_id}", None)
                        st.cache_data.clear()
                        st.rerun()
                    if c2.button("❌ Отмена", key=f"cancel_{order_id}", use_container_width=True):
                        st.session_state.pop(f"editing_{order_id}", None)
                        st.rerun()
                continue

            # Строка заказа
            icon = "💵" if typ == "нал" else "💳"
            with st.container():
                st.markdown(
                    f"{icon} **{typ}** &nbsp;|&nbsp; {tm or ''} &nbsp;|&nbsp; "
                    f"чек: **{am:.0f} ₽** → **{tot:.0f} ₽** &nbsp;|&nbsp; безнал: **{bez:+.0f} ₽**"
                )
                cols = st.columns(2)
                if cols[0].button("✏️ Изменить", key=f"edit_{order_id}", use_container_width=True):
                    st.session_state[f"editing_{order_id}"] = True
                    st.rerun()

                conf_key = f"conf_{order_id}"
                if st.session_state.get(conf_key):
                    c1, c2 = cols[1].columns(2)
                    if c1.button("✅", key=f"yes_{order_id}", use_container_width=True):
                        delete_order_and_update_beznal(order_id)
                        st.session_state.pop(conf_key, None)
                        st.rerun()
                    if c2.button("❌", key=f"no_{order_id}", use_container_width=True):
                        st.session_state.pop(conf_key, None)
                        st.rerun()
                else:
                    if cols[1].button("🗑️ Удалить", key=f"del_{order_id}", use_container_width=True):
                        st.session_state[conf_key] = True
                        st.rerun()
            st.divider()

        # Итого смены
        nal_sum = totals.get("нал", 0)
        card_sum = totals.get("карта", 0)
        tips_sum = totals.get("чаевые", 0)
        total_income = nal_sum + card_sum + tips_sum
        c1, c2, c3 = st.columns(3)
        c1.metric("💵 Нал", f"{nal_sum:.0f} ₽")
        c2.metric("💳 Карта", f"{card_sum:.0f} ₽")
        c3.metric("💡 Чаевые", f"{tips_sum:.0f} ₽")
    else:
        total_income = 0.0

    # ===== РАСХОДЫ =====
    total_extra = get_total_extra_expenses(shift_id)
    with st.expander(f"💸 Расходы ({total_extra:.0f} ₽)", expanded=False):
        col1, col2 = st.columns([2, 1])
        with col1:
            exp_desc = st.selectbox("📝 Тип", POPULAR_EXPENSES, key="exp_desc")
        with col2:
            exp_amt = st.number_input("₽", min_value=0.0, step=50.0, value=100.0, key="exp_amt")
        if st.button("➕ Добавить расход", use_container_width=True, key="btn_add_exp"):
            add_extra_expense(shift_id, exp_amt, exp_desc)
            st.rerun()

        for exp in get_extra_expenses(shift_id):
            c1, c2 = st.columns([4, 1])
            c1.markdown(f"**{exp['description']}** — {exp['amount']:.0f} ₽")
            if c2.button("🗑️", key=f"del_exp_{exp['id']}", use_container_width=True):
                delete_extra_expense(exp["id"])
                st.rerun()

    # ===== ИТОГ СМЕНЫ =====
    st.divider()
    profit = total_income - total_extra
    c1, c2, c3 = st.columns(3)
    c1.metric("💰 Доход", f"{total_income:.0f} ₽")
    c2.metric("💸 Расходы", f"{total_extra:.0f} ₽")
    c3.metric("📈 Прибыль", f"{profit:.0f} ₽", delta=f"{profit:.0f}")

    # ===== ЗАКРЫТИЕ СМЕНЫ =====
    with st.expander("⛽ Закрыть смену", expanded=False):
        last_cons, last_price = get_last_fuel_params()
        km = st.number_input("🛣️ Пробег (км)", value=100, min_value=0, key="km_close")
        c1, c2 = st.columns(2)
        with c1:
            cons = st.number_input("⛽ Расход л/100км", value=float(last_cons), step=0.5, key="cons_close")
        with c2:
            price = st.number_input("💰 Цена топлива ₽/л", value=float(last_price), step=1.0, key="fuel_close")
        if km > 0 and cons > 0:
            liters = (km / 100) * cons
            st.info(f"🛢️ {liters:.1f} л × {price:.0f} ₽ = **{liters * price:.0f} ₽**")

        if not st.session_state.get("confirm_close"):
            if st.button("🔒 Закрыть смену", use_container_width=True, type="primary"):
                st.session_state.confirm_close = True
                st.rerun()
        else:
            st.warning("⚠️ Подтвердите закрытие")
            c1, c2 = st.columns(2)
            if c1.button("✅ Да, закрыть", use_container_width=True, type="primary"):
                liters_val = (km / 100) * cons if km > 0 else 0.0
                close_shift_db(shift_id, km, liters_val, price)
                st.session_state.pop("confirm_close", None)
                st.cache_data.clear()
                st.rerun()
            if c2.button("❌ Отмена", use_container_width=True):
                st.session_state.pop("confirm_close", None)
                st.rerun()


# ===== UI: ОТЧЁТЫ =====
def show_reports_page():
    st.markdown("## 📊 Отчёты")
    check_and_create_tables()

    if st.button("🔄 Обновить", use_container_width=True):
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

        year_months = get_available_year_months_cached()
        if not year_months:
            st.info("ℹ️ Нет закрытых смен с заказами")
            return

        selected_ym = st.selectbox(
            "📅 Период", year_months, index=0,
            format_func=format_month_option
        )

        # Дневной отчёт
        available_days = get_available_days_cached(selected_ym)
        if available_days:
            weekdays = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"]
            selected_day = st.selectbox(
                "📆 День",
                available_days,
                format_func=lambda d: f"{d[:10]} ({weekdays[datetime.strptime(d, '%Y-%m-%d').weekday()]})"
            )
            dr = get_day_report_cached(selected_day)
            st.markdown(f"### 📋 {selected_day[:10]}")
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("💰 Доход", f"{dr['всего']:.0f} ₽")
            c2.metric("💸 Расходы", f"{(dr['расходы'] + dr['топливо']):.0f} ₽")
            c3.metric("⛽ Топливо", f"{dr['топливо']:.0f} ₽")
            c4.metric("📈 Прибыль", f"{dr['прибыль']:.0f} ₽")
            c1, c2, c3 = st.columns(3)
            c1.metric("💵 Нал", f"{dr['нал']:.0f} ₽")
            c2.metric("💳 Карта", f"{dr['карта']:.0f} ₽")
            c3.metric("💡 Чаевые", f"{dr['чаевые']:.0f} ₽")
            st.divider()

        # Месячный отчёт
        st.markdown(f"### 📊 {format_month_option(selected_ym)}")
        totals = get_month_totals_cached(selected_ym)
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("💵 Нал", f"{totals.get('нал', 0):.0f} ₽")
        c2.metric("💳 Карта", f"{totals.get('карта', 0):.0f} ₽")
        c3.metric("💡 Чаевые", f"{totals.get('чаевые', 0):.0f} ₽")
        c4.metric("💰 Всего", f"{totals.get('всего', 0):.0f} ₽")

        stats = get_month_statistics(selected_ym)
        c1, c2, c3 = st.columns(3)
        c1.metric("🚕 Смен", stats.get("смен", 0))
        c2.metric("📦 Заказов", stats.get("заказов", 0))
        c3.metric("📊 Средний чек", f"{stats.get('средний_чек', 0):.0f} ₽")
        c1, c2, c3 = st.columns(3)
        c1.metric("⛽ Бензин", f"{stats.get('бензин', 0):.0f} ₽")
        c2.metric("💸 Расходы", f"{stats.get('расходы', 0):.0f} ₽")
        c3.metric("📈 Прибыль", f"{stats.get('прибыль', 0):.0f} ₽",
                  delta=f"{stats.get('рентабельность', 0):.1f}%")

        df = get_month_shifts_details_cached(selected_ym)
        if not df.empty:
            st.divider()
            st.dataframe(df, use_container_width=True)

    except ImportError as e:
        st.error(f"❌ pages_imports.py: {e}")
    except Exception as e:
        st.error(f"❌ Ошибка: {e}")


# ===== UI: НАСТРОЙКИ / АДМИНКА =====
def show_admin_page():
    st.markdown("## 🔧 Настройки")

    admin_pwd = ""
    try:
        admin_pwd = st.secrets.get("ADMIN_PASSWORD", "changeme")
    except Exception:
        admin_pwd = "changeme"

    if not st.session_state.get("admin_auth"):
        pwd = st.text_input("🔑 Пароль администратора", type="password")
        if st.button("🔐 Войти", use_container_width=True, type="primary"):
            if pwd == admin_pwd:
                st.session_state.admin_auth = True
                st.rerun()
            else:
                st.error("❌ Неверный пароль")
        return

    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "📦 Бэкапы", "☁️ Яндекс Диск", "💳 Безнал", "🔄 Пересчёт", "⚠️ Сброс"
    ])

    # ===== TAB 1: БЭКАПЫ =====
    with tab1:
        st.markdown("### 📦 Локальные бэкапы")
        if st.button("📦 Создать бэкап", use_container_width=True):
            path = create_backup()
            st.success(f"✅ {os.path.basename(path)}")

        st.markdown("**Восстановить из файла:**")
        uploaded = st.file_uploader("📁 Загрузить .db файл", type=["db"], key="restore_uploader")
        if uploaded:
            if not st.session_state.get("confirm_restore"):
                if st.button("📥 Восстановить из файла", use_container_width=True, type="primary"):
                    st.session_state.confirm_restore = True
                    st.rerun()
            else:
                st.warning("⚠️ Текущая БД будет заменена. Текущий бэкап сохранится автоматически.")
                c1, c2 = st.columns(2)
                if c1.button("✅ Да, восстановить", use_container_width=True, type="primary"):
                    try:
                        upload_and_restore_backup(uploaded)
                        st.session_state.pop("confirm_restore", None)
                        st.success("✅ База данных восстановлена! Перезагружаю...")
                        time.sleep(1)
                        st.rerun()
                    except Exception as e:
                        st.error(f"❌ Ошибка: {e}")
                if c2.button("❌ Отмена", use_container_width=True):
                    st.session_state.pop("confirm_restore", None)
                    st.rerun()

        st.divider()
        st.markdown("**Список бэкапов:**")
        for b in list_backups():
            with st.container():
                st.caption(f"📅 {b['time'].strftime('%d.%m.%Y %H:%M')} — {b['size']:.1f} KB")
                c1, c2, c3 = st.columns(3)
                with open(b["path"], "rb") as f:
                    c1.download_button(
                        "⬇️ Скачать", f.read(), b["name"],
                        key=f"dl_{b['name']}", use_container_width=True
                    )
                if c2.button("📥 Откат", key=f"rb_{b['name']}", use_container_width=True):
                    restore_from_backup(b["path"])
                    st.success("✅ Восстановлено!")
                    st.rerun()
                if c3.button("🗑️", key=f"xb_{b['name']}", use_container_width=True):
                    os.remove(b["path"])
                    st.rerun()

    # ===== TAB 2: ЯНДЕКС ДИСК =====
    with tab2:
        st.markdown("### ☁️ Яндекс Диск")
        st.info("Бэкап через WebDAV — не нужны OAuth и сторонние библиотеки. Только токен.")

        with st.expander("ℹ️ Как получить токен", expanded=False):
            st.markdown("""
**1. Получите OAuth-токен Яндекс Диска:**

Перейдите по ссылке — она сразу выдаст токен:
```
https://oauth.yandex.ru/authorize?response_type=token&client_id=72294e73f3934c7ea3e416e4e46b04eb
```
*(Это стандартный клиент WebDAV от Яндекса)*

**2. Скопируйте токен** из строки `access_token=...` в URL

**3. Вставьте токен ниже** или добавьте в `.streamlit/secrets.toml`:
```toml
YADISK_TOKEN = "AgAAAAAxxxx..."
```

Файл будет сохранён в `/taxi_backup/taxi_backup.db` на вашем Яндекс Диске.
            """)

        saved_token = get_yadisk_token()
        yd_token = st.text_input(
            "🔑 OAuth-токен Яндекс Диска",
            value=saved_token,
            type="password",
            placeholder="AgAAAAAxxxx...",
            key="input_yd_token"
        )
        if st.button("💾 Сохранить токен в сессии", use_container_width=True):
            st.session_state.yadisk_token = yd_token.strip()
            st.success("✅ Токен сохранён до перезапуска")

        # Показываем статус файла на диске
        cur_token = get_yadisk_token()
        if cur_token:
            info = yadisk_get_backup_info(cur_token)
            if info:
                st.success(f"✅ Файл найден на Яндекс Диске | "
                           f"Изменён: {info.get('modified', '?')} | "
                           f"Размер: {info.get('size_kb', 0)} KB")
            else:
                st.warning("⚠️ Файл не найден на Яндекс Диске (или токен неверный)")

        st.divider()
        col1, col2 = st.columns(2)
        with col1:
            if st.button("📤 Загрузить на Яндекс Диск", use_container_width=True, type="primary"):
                tok = get_yadisk_token()
                with st.spinner("Загружаю..."):
                    if yadisk_upload_backup(tok):
                        st.success("✅ Бэкап загружен на Яндекс Диск!")
        with col2:
            if st.button("📥 Скачать с Яндекс Диска", use_container_width=True):
                tok = get_yadisk_token()
                with st.spinner("Скачиваю..."):
                    try:
                        if yadisk_download_backup(tok):
                            st.success("✅ База восстановлена с Яндекс Диска!")
                            st.rerun()
                    except Exception as e:
                        st.error(f"❌ {e}")

    # ===== TAB 3: БЕЗНАЛ =====
    with tab3:
        st.markdown("### 💳 Накопленный безнал")
        cur = get_accumulated_beznal()
        st.metric("Текущее значение", f"{cur:.0f} ₽")
        new_val = st.number_input("Новое значение (₽)", value=float(cur), key="new_beznal")
        if st.button("💾 Установить", use_container_width=True):
            set_accumulated_beznal(new_val)
            st.success(f"✅ Установлено: {new_val:.0f} ₽")
            st.rerun()

    # ===== TAB 4: ПЕРЕСЧЁТ =====
    with tab4:
        st.markdown("### 🔄 Пересчёт комиссий")
        st.caption("Пересчитает все заказы по текущим ставкам (нал 78%, карта 75%)")
        if st.button("🔄 Пересчитать всё", use_container_width=True, type="primary"):
            try:
                from pages_imports import recalc_full_db
                new_beznal = recalc_full_db()
                st.success(f"✅ Готово. Новый безнал: {new_beznal:.0f} ₽")
            except Exception as e:
                st.error(f"❌ {e}")

    # ===== TAB 5: СБРОС =====
    with tab5:
        st.markdown("### ⚠️ Опасная зона")
        st.error("Удаление всех данных — действие необратимо!")
        confirm_text = st.text_input("Введите **СБРОС** для подтверждения", placeholder="СБРОС")
        if st.button("⚠️ СБРОСИТЬ БАЗУ", use_container_width=True, type="primary"):
            if confirm_text == "СБРОС":
                try:
                    from pages_imports import reset_db
                    reset_db()
                    st.cache_data.clear()
                    st.success("✅ База сброшена")
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ {e}")
            else:
                st.error("❌ Введите слово СБРОС")

    st.divider()
    if st.button("👋 Выйти из системы", use_container_width=True):
        clear_session_disk()
        st.session_state.clear()
        st.rerun()


# ===== MAIN =====
if __name__ == "__main__":
    st.set_page_config(
        page_title="Taxi Shift Manager",
        page_icon="🚕",
        layout="wide",
        initial_sidebar_state="collapsed"
    )
    apply_mobile_css()
    init_auth_db()
    ensure_users_dir()
    init_session()

    # Восстанавливаем сессию с диска
    saved = load_session_from_disk()
    if saved and "username" not in st.session_state:
        st.session_state.username = saved
        if "page" not in st.session_state:
            st.session_state.page = "main"

    # Страница входа
    if "username" not in st.session_state:
        show_login_page()
        st.stop()

    # Основные страницы
    page = st.session_state.get("page", "main")

    if page == "main":
        show_main_page()
    elif page == "reports":
        show_reports_page()
    elif page == "admin":
        show_admin_page()

    # Нижняя навигация — всегда внизу
    st.divider()
    render_bottom_nav(page)
