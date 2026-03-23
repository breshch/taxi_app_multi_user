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
SESSION_TIMEOUT = 30 * 24 * 60 * 60  # 30 дней
rate_nal = 0.78
rate_card = 0.75

POPULAR_EXPENSES = [
    "🚗 Мойка",
    "💧 Омывайка",
    "🍔 Еда",
    "☕ Кофе",
    "🚬 Сигареты",
    "🔧 Мелкий ремонт",
    "🅿️ Парковка",
    "💰 Штраф",
    "🧴 Очиститель",
    "🔋 Зарядка",
    "🧰 Инструмент",
    "📱 Связь",
    "🚕 Аренда",
    "💊 Аптека",
]

MOSCOW_TZ = timezone(timedelta(hours=3))


# ===== УПРАВЛЕНИЕ СЕССИЕЙ =====
def save_session_to_disk():
    try:
        if "username" in st.session_state and st.session_state["username"]:
            session_data = {
                "username": st.session_state["username"],
                "session_start": (
                    st.session_state.session_start.isoformat()
                    if "session_start" in st.session_state
                    else None
                ),
                "last_activity": (
                    st.session_state.last_activity.isoformat()
                    if "last_activity" in st.session_state
                    else None
                ),
            }
            with open(SESSION_FILE, "w", encoding="utf-8") as f:
                json.dump(session_data, f)
    except Exception as e:
        print(f"Ошибка при сохранении сессии: {e}")


def load_session_from_disk():
    try:
        if os.path.exists(SESSION_FILE):
            with open(SESSION_FILE, "r", encoding="utf-8") as f:
                session_data = json.load(f)
            if session_data.get("session_start"):
                session_start = datetime.fromisoformat(session_data["session_start"])
                time_elapsed = (datetime.now(MOSCOW_TZ) - session_start).total_seconds()
                if time_elapsed < SESSION_TIMEOUT:
                    return session_data.get("username")
    except Exception as e:
        print(f"Ошибка при загрузке сессии: {e}")
    return None


def clear_session_disk():
    try:
        if os.path.exists(SESSION_FILE):
            os.remove(SESSION_FILE)
    except Exception as e:
        print(f"Ошибка при удалении сессии: {e}")


# ===== МОБИЛЬНАЯ ОПТИМИЗАЦИЯ CSS =====
def apply_mobile_optimized_css():
    st.markdown(
        """
    <style>
    /* Скрываем стандартную навигацию */
    section[data-testid="stSidebarNav"] { display: none !important; }
    .st-emotion-cache-1gv3huu, .st-emotion-cache-1jzia57 { display: none !important; }
    
    /* Базовые отступы */
    * { box-sizing: border-box; }
    .main > div { padding-left: 0.5rem !important; padding-right: 0.5rem !important; }
    .block-container { padding-top: 0.5rem !important; padding-bottom: 0.5rem !important; max-width: 100% !important; }
    
    /* Карточка пользователя */
    .user-info {
        display: flex; align-items: center; gap: 15px;
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 15px; border-radius: 15px; margin-bottom: 15px;
        box-shadow: 0 4px 10px rgba(0,0,0,0.2);
    }
    .user-avatar {
        font-size: 2.5rem; background: white; width: 60px; height: 60px;
        border-radius: 50%; display: flex; align-items: center; justify-content: center;
    }
    .user-name { font-size: 1.5rem; font-weight: bold; color: white; }
    .user-name small { font-size: 0.9rem; color: rgba(255,255,255,0.9); }
    
    /* Заголовки */
    h1 { font-size: 1.4rem !important; margin: 0.5rem 0 !important; text-align: center; }
    h2 { font-size: 1.2rem !important; margin: 0.5rem 0 !important; }
    h3 { font-size: 1.1rem !important; margin: 0.3rem 0 !important; }
    
    /* Метрики */
    .stMetric { padding: 0.3rem !important; margin: 0.1rem 0 !important; }
    .stMetric label { font-size: 0.75rem !important; }
    .stMetric [data-testid="stMetricValue"] { font-size: 1.2rem !important; }
    
    /* Кнопки (удобно для пальцев) */
    .stButton > button {
        padding: 0.6rem 1rem !important; font-size: 0.95rem !important;
        margin: 0.2rem 0 !important; min-height: 44px; width: 100%;
        touch-action: manipulation;
    }
    
    /* Поля ввода */
    .stTextInput > div > div > input, .stNumberInput > div > div > input {
        padding: 0.5rem !important; font-size: 1rem !important; min-height: 44px;
    }
    .stSelectbox > div > div { min-height: 44px; font-size: 1rem !important; }
    
    /* Экспандеры */
    .stExpander { margin: 0.3rem 0 !important; }
    .stExpander > details > summary { padding: 0.5rem !important; font-size: 1rem !important; }
    
    /* Сайдбар */
    section[data-testid="stSidebar"] { width: 300px !important; }
    section[data-testid="stSidebar"] > div { padding: 0.5rem !important; }
    
    /* Таблицы */
    .stDataFrame { font-size: 0.85rem !important; }
    .stDataFrame td, .stDataFrame th { padding: 0.3rem !important; }
    
    /* Уведомления */
    .stAlert { padding: 0.5rem !important; margin: 0.3rem 0 !important; font-size: 0.9rem !important; }
    
    /* Мобильные медиа-запросы */
    @media (max-width: 640px) {
        .row-widget.stHorizontal { flex-wrap: wrap !important; gap: 0.3rem !important; }
        .row-widget.stHorizontal > div { flex: 1 1 auto !important; min-width: 45% !important; }
        .user-name { font-size: 1.3rem !important; }
        .user-avatar { width: 50px; height: 50px; font-size: 2rem !important; }
        h1 { font-size: 1.3rem !important; }
    }
    </style>
    """,
        unsafe_allow_html=True,
    )


# ===== ИНИЦИАЛИЗАЦИЯ СЕССИИ =====
def init_session():
    if "session_start" not in st.session_state:
        st.session_state.session_start = datetime.now(MOSCOW_TZ)
        st.session_state.last_activity = datetime.now(MOSCOW_TZ)
        save_session_to_disk()

    st.session_state.last_activity = datetime.now(MOSCOW_TZ)
    save_session_to_disk()

    time_elapsed = (
        datetime.now(MOSCOW_TZ) - st.session_state.session_start
    ).total_seconds()
    if time_elapsed > SESSION_TIMEOUT:
        st.session_state.clear()
        clear_session_disk()
        st.warning("⏰ Сессия истекла. Пожалуйста, войдите снова.")
        st.rerun()


def get_session_time_remaining() -> str:
    if "session_start" not in st.session_state:
        return "00:00:00"
    time_elapsed = (
        datetime.now(MOSCOW_TZ) - st.session_state.session_start
    ).total_seconds()
    time_remaining = max(0, SESSION_TIMEOUT - time_elapsed)
    days = int(time_remaining // (24 * 3600))
    hours = int((time_remaining % (24 * 3600)) // 3600)
    minutes = int((time_remaining % 3600) // 60)
    seconds = int(time_remaining % 60)
    if days > 0:
        return f"{days}д {hours:02d}:{minutes:02d}:{seconds:02d}"
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


# ===== РАБОТА С ПАПКАМИ =====
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
    user_dir = get_user_dir(username)
    safe_name = "".join(c for c in username if c.isalnum() or c in ("_", "-"))
    return os.path.join(user_dir, f"taxi_{safe_name}.db")


def get_backup_dir() -> str:
    user_dir = get_user_dir(st.session_state.get("username", "unknown"))
    backup_dir = os.path.join(user_dir, "backups")
    if not os.path.exists(backup_dir):
        os.makedirs(backup_dir)
    return backup_dir


def add_column_if_not_exists(cursor, table_name, column_name, column_type):
    try:
        cursor.execute(f"SELECT {column_name} FROM {table_name} LIMIT 1")
    except sqlite3.OperationalError:
        try:
            cursor.execute(
                f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}"
            )
            return True
        except Exception:
            return False
    return False


def check_and_create_tables():
    try:
        conn = sqlite3.connect(get_current_db_name())
        cursor = conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS shifts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL, km INTEGER DEFAULT 0,
                fuel_liters REAL DEFAULT 0, fuel_price REAL DEFAULT 0,
                is_open INTEGER DEFAULT 1, opened_at TEXT, closed_at TEXT
            )
        """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS extra_expenses (
                id INTEGER PRIMARY KEY AUTOINCREMENT, shift_id INTEGER,
                amount REAL DEFAULT 0, description TEXT, created_at TEXT,
                FOREIGN KEY (shift_id) REFERENCES shifts (id)
            )
        """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT, shift_id INTEGER,
                type TEXT NOT NULL, amount REAL NOT NULL, tips REAL DEFAULT 0,
                commission REAL NOT NULL, total REAL NOT NULL,
                beznal_added REAL DEFAULT 0, order_time TEXT
            )
        """
        )
        add_column_if_not_exists(cursor, "orders", "order_time", "TEXT")
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS accumulated_beznal (
                id INTEGER PRIMARY KEY AUTOINCREMENT, driver_id INTEGER DEFAULT 1,
                total_amount REAL DEFAULT 0, last_updated TEXT
            )
        """
        )
        cursor.execute("SELECT id FROM accumulated_beznal WHERE driver_id = 1")
        if not cursor.fetchone():
            cursor.execute(
                "INSERT INTO accumulated_beznal (driver_id, total_amount, last_updated) VALUES (1, 0, ?)",
                (datetime.now(MOSCOW_TZ).strftime("%Y-%m-%d %H:%M:%S"),),
            )
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"Ошибка при создании таблиц: {e}")
        return False


# ===== АВТОРИЗАЦИЯ =====
def get_auth_conn():
    return sqlite3.connect(AUTH_DB)


def init_auth_db():
    conn = get_auth_conn()
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL, created_at TEXT, user_dir TEXT,
            last_login TEXT, total_logins INTEGER DEFAULT 0
        )
    """
    )
    add_column_if_not_exists(cur, "users", "last_login", "TEXT")
    add_column_if_not_exists(cur, "users", "total_logins", "INTEGER DEFAULT 0")
    conn.commit()
    conn.close()


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def register_user(username: str, password: str) -> bool:
    username = username.strip()
    if not username or not password:
        return False
    ensure_users_dir()
    user_dir = get_user_dir(username)
    conn = get_auth_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            INSERT INTO users (username, password_hash, created_at, user_dir, last_login, total_logins)
            VALUES (?, ?, ?, ?, ?, ?)
        """,
            (
                username,
                hash_password(password),
                datetime.now(MOSCOW_TZ).strftime("%Y-%m-%d %H:%M:%S"),
                user_dir,
                None,
                0,
            ),
        )
        conn.commit()
        safe_name = "".join(c for c in username if c.isalnum() or c in ("_", "-"))
        db_path = os.path.join(user_dir, f"taxi_{safe_name}.db")
        if os.path.exists(db_path):
            os.remove(db_path)
        init_user_db(db_path)
        ok = True
    except sqlite3.IntegrityError:
        ok = False
    except Exception as e:
        print(f"Ошибка при регистрации: {e}")
        ok = False
    finally:
        conn.close()
    return ok


def authenticate_user(username: str, password: str) -> bool:
    username = username.strip()
    conn = get_auth_conn()
    cur = conn.cursor()
    cur.execute("SELECT password_hash FROM users WHERE username = ?", (username,))
    row = cur.fetchone()
    conn.close()
    if not row:
        return False
    return row[0] == hash_password(password)


def update_login_stats(username: str):
    conn = get_auth_conn()
    cur = conn.cursor()
    now = datetime.now(MOSCOW_TZ).strftime("%Y-%m-%d %H:%M:%S")
    try:
        cur.execute("PRAGMA table_info(users)")
        columns = [column[1] for column in cur.fetchall()]
        if "last_login" in columns and "total_logins" in columns:
            cur.execute(
                "UPDATE users SET last_login = ?, total_logins = total_logins + 1 WHERE username = ?",
                (now, username),
            )
    except Exception as e:
        print(f"Ошибка при обновлении статистики: {e}")
    finally:
        conn.commit()
        conn.close()


def get_all_users() -> list:
    conn = get_auth_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT username, COALESCE(created_at, 'неизвестно') as created_at,
            COALESCE(last_login, 'никогда') as last_login, COALESCE(total_logins, 0) as total_logins
            FROM users ORDER BY username
        """
        )
        rows = cur.fetchall()
    except:
        cur.execute("SELECT username, created_at FROM users ORDER BY username")
        rows = [(row[0], row[1], "неизвестно", 0) for row in cur.fetchall()]
    finally:
        conn.close()
    return rows


# ===== БД СМЕН И ЗАКАЗОВ =====
def get_db_connection():
    conn = sqlite3.connect(get_current_db_name())
    check_and_create_tables()
    return conn


def init_user_db(db_path: str = None):
    if db_path is None:
        db_path = get_current_db_name()
    db_dir = os.path.dirname(db_path)
    if db_dir and not os.path.exists(db_dir):
        os.makedirs(db_dir)
    if os.path.exists(db_path):
        os.remove(db_path)
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS shifts (
            id INTEGER PRIMARY KEY AUTOINCREMENT, date TEXT NOT NULL,
            km INTEGER DEFAULT 0, fuel_liters REAL DEFAULT 0, fuel_price REAL DEFAULT 0,
            is_open INTEGER DEFAULT 1, opened_at TEXT, closed_at TEXT
        )
    """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS extra_expenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT, shift_id INTEGER,
            amount REAL DEFAULT 0, description TEXT, created_at TEXT,
            FOREIGN KEY (shift_id) REFERENCES shifts (id)
        )
    """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT, shift_id INTEGER,
            type TEXT NOT NULL, amount REAL NOT NULL, tips REAL DEFAULT 0,
            commission REAL NOT NULL, total REAL NOT NULL,
            beznal_added REAL DEFAULT 0, order_time TEXT
        )
    """
    )
    try:
        cursor.execute("ALTER TABLE orders ADD COLUMN order_time TEXT")
    except sqlite3.OperationalError:
        pass
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS accumulated_beznal (
            id INTEGER PRIMARY KEY AUTOINCREMENT, driver_id INTEGER DEFAULT 1,
            total_amount REAL DEFAULT 0, last_updated TEXT
        )
    """
    )
    cursor.execute("SELECT id FROM accumulated_beznal WHERE driver_id = 1")
    if not cursor.fetchone():
        cursor.execute(
            "INSERT INTO accumulated_beznal (driver_id, total_amount, last_updated) VALUES (1, 0, ?)",
            (datetime.now(MOSCOW_TZ).strftime("%Y-%m-%d %H:%M:%S"),),
        )
    conn.commit()
    conn.close()


def get_open_shift():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, date FROM shifts WHERE is_open = 1 LIMIT 1")
    row = cursor.fetchone()
    conn.close()
    return row


def open_shift(date_str: str) -> int:
    conn = get_db_connection()
    cursor = conn.cursor()
    now = datetime.now(MOSCOW_TZ).strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute(
        "INSERT INTO shifts (date, is_open, opened_at) VALUES (?, 1, ?)",
        (date_str, now),
    )
    shift_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return shift_id


def close_shift_db(shift_id: int, km: int, liters: float, fuel_price: float):
    conn = get_db_connection()
    cursor = conn.cursor()
    now = datetime.now(MOSCOW_TZ).strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute(
        """
        UPDATE shifts SET is_open = 0, km = ?, fuel_liters = ?, fuel_price = ?, closed_at = ?
        WHERE id = ?
    """,
        (km, liters, fuel_price, now, shift_id),
    )
    conn.commit()
    conn.close()


def add_extra_expense(shift_id: int, amount: float, description: str):
    conn = get_db_connection()
    cursor = conn.cursor()
    now = datetime.now(MOSCOW_TZ).strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute(
        "INSERT INTO extra_expenses (shift_id, amount, description, created_at) VALUES (?, ?, ?, ?)",
        (shift_id, amount, description, now),
    )
    conn.commit()
    conn.close()


def get_extra_expenses(shift_id: int) -> list:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, amount, description, created_at FROM extra_expenses WHERE shift_id = ? ORDER BY id",
        (shift_id,),
    )
    rows = cursor.fetchall()
    conn.close()
    expenses = []
    for row in rows:
        expenses.append(
            {
                "id": row[0],
                "amount": row[1] or 0.0,
                "description": row[2] or "",
                "created_at": row[3] or "",
            }
        )
    return expenses


def delete_extra_expense(expense_id: int):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM extra_expenses WHERE id = ?", (expense_id,))
    conn.commit()
    conn.close()


def get_total_extra_expenses(shift_id: int) -> float:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT SUM(amount) FROM extra_expenses WHERE shift_id = ?", (shift_id,)
    )
    row = cursor.fetchone()
    conn.close()
    return row[0] or 0.0


def get_all_extra_expenses_stats() -> dict:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT description, SUM(amount), COUNT(*) FROM extra_expenses GROUP BY description ORDER BY SUM(amount) DESC"
    )
    rows = cursor.fetchall()
    conn.close()
    stats = []
    for row in rows:
        stats.append({"description": row[0], "total": row[1] or 0, "count": row[2]})
    return stats


def get_month_extra_expenses(year_month: str) -> float:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT SUM(e.amount) FROM extra_expenses e
        JOIN shifts s ON e.shift_id = s.id
        WHERE strftime('%Y-%m', s.date) = ?
    """,
        (year_month,),
    )
    row = cursor.fetchone()
    conn.close()
    return row[0] or 0.0


def add_order_db(
    shift_id, order_type, amount, tips, commission, total, beznal_added, order_time
):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO orders (shift_id, type, amount, tips, commission, total, beznal_added, order_time)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """,
        (
            shift_id,
            order_type,
            amount,
            tips,
            commission,
            total,
            beznal_added,
            order_time,
        ),
    )
    conn.commit()
    conn.close()


def update_order_db(
    order_id: int,
    order_type: str,
    amount: float,
    tips: float,
    commission: float,
    total: float,
    beznal_added: float,
):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE orders SET type = ?, amount = ?, tips = ?, commission = ?, total = ?, beznal_added = ?
        WHERE id = ?
    """,
        (order_type, amount, tips, commission, total, beznal_added, order_id),
    )
    conn.commit()
    conn.close()


def delete_order_db(order_id: int):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM orders WHERE id = ?", (order_id,))
    conn.commit()
    conn.close()


def get_shift_orders(shift_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT id, type, amount, tips, commission, total, beznal_added, order_time
        FROM orders WHERE shift_id = ? ORDER BY id DESC
    """,
        (shift_id,),
    )
    rows = cursor.fetchall()
    conn.close()
    return rows


def get_shift_totals(shift_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT type, SUM(total - tips) FROM orders WHERE shift_id = ? GROUP BY type",
        (shift_id,),
    )
    by_type = dict(cursor.fetchall())
    cursor.execute(
        "SELECT SUM(tips), SUM(beznal_added) FROM orders WHERE shift_id = ?",
        (shift_id,),
    )
    tips_sum, beznal_sum = cursor.fetchone()
    conn.close()
    by_type["чаевые"] = tips_sum or 0
    by_type["безнал_смена"] = beznal_sum or 0
    return by_type


def get_accumulated_beznal():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT total_amount FROM accumulated_beznal WHERE driver_id = 1")
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else 0.0


def add_to_accumulated_beznal(amount: float):
    conn = get_db_connection()
    cursor = conn.cursor()
    now = datetime.now(MOSCOW_TZ).strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute(
        "UPDATE accumulated_beznal SET total_amount = total_amount + ?, last_updated = ? WHERE driver_id = 1",
        (amount, now),
    )
    conn.commit()
    conn.close()


def set_accumulated_beznal(amount: float):
    conn = get_db_connection()
    cursor = conn.cursor()
    now = datetime.now(MOSCOW_TZ).strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute(
        "UPDATE accumulated_beznal SET total_amount = ?, last_updated = ? WHERE driver_id = 1",
        (amount, now),
    )
    conn.commit()
    conn.close()


def get_last_fuel_params():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT fuel_liters, km, fuel_price FROM shifts
        WHERE is_open = 0 AND km > 0 AND fuel_liters > 0 AND fuel_price > 0
        ORDER BY closed_at DESC, id DESC LIMIT 1
    """
    )
    row = cur.fetchone()
    conn.close()
    if not row:
        return 8.0, 55.0
    fuel_liters, km, fuel_price = row
    if km is None or km == 0:
        return 8.0, float(fuel_price or 55.0)
    try:
        consumption = (fuel_liters / km) * 100 if km > 0 else 8.0
    except Exception:
        consumption = 8.0
    return float(consumption or 8.0), float(fuel_price or 55.0)


def log_action(action: str, details: str = ""):
    try:
        username = st.session_state.get("username", "unknown")
        user_dir = get_user_dir(username) if username != "unknown" else "logs"
        log_dir = os.path.join(user_dir, "logs")
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)
        with open(
            os.path.join(log_dir, "user_actions.log"), "a", encoding="utf-8"
        ) as f:
            timestamp = datetime.now(MOSCOW_TZ).strftime("%Y-%m-%d %H:%M:%S")
            f.write(f"[{timestamp}] {username}: {action} - {details}\n")
    except:
        pass


# ===== БЭКАПЫ =====
def create_backup() -> str:
    backup_dir = get_backup_dir()
    timestamp = datetime.now(MOSCOW_TZ).strftime("%Y%m%d_%H%M%S")
    username = st.session_state.get("username", "unknown")
    backup_name = f"taxi_{username}_backup_{timestamp}.db"
    backup_path = os.path.join(backup_dir, backup_name)
    shutil.copy2(get_current_db_name(), backup_path)
    backups = [f for f in os.listdir(backup_dir) if f.endswith(".db")]
    backups.sort(reverse=True)
    for old_backup in backups[20:]:
        try:
            os.remove(os.path.join(backup_dir, old_backup))
        except:
            pass
    return backup_path


def list_backups() -> list:
    backup_dir = get_backup_dir()
    if not os.path.exists(backup_dir):
        return []
    backups = []
    for f in os.listdir(backup_dir):
        if f.endswith(".db"):
            file_path = os.path.join(backup_dir, f)
            file_time = datetime.fromtimestamp(os.path.getmtime(file_path))
            file_size = os.path.getsize(file_path) / 1024
            backups.append(
                {"name": f, "path": file_path, "time": file_time, "size": file_size}
            )
    backups.sort(key=lambda x: x["time"], reverse=True)
    return backups


def restore_from_backup(backup_path: str):
    if not os.path.exists(backup_path):
        raise FileNotFoundError(f"Файл бэкапа не найден: {backup_path}")
    create_backup()
    shutil.copy2(backup_path, get_current_db_name())


def download_backup(backup_path: str) -> bytes:
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


# ===== СТРАНИЦЫ =====
def show_main_page():
    st.title(f"🚕 {st.session_state['username']}")
    if "edit_order_id" not in st.session_state:
        st.session_state.edit_order_id = None
    if "confirm_delete" not in st.session_state:
        st.session_state.confirm_delete = {}

    open_shift_data = get_open_shift()
    if not open_shift_data:
        st.info("📭 Нет открытой смены")
        with st.expander("📝 ОТКРЫТЬ СМЕНУ", expanded=True):
            with st.form("open_shift_form"):
                date_input = st.date_input("Дата", value=date.today())
                st.caption(f"{date_input.strftime('%d.%m.%Y')}")
                submitted_tpl = st.form_submit_button(
                    "📂 ОТКРЫТЬ", use_container_width=True
                )
            if submitted_tpl:
                date_str_db = date_input.strftime("%Y-%m-%d")
                open_shift(date_str_db)
                log_action("Открытие смены", f"Дата: {date_str_db}")
                st.success(f"✅ Смена открыта: {date_input.strftime('%d.%m.%Y')}")
                st.rerun()
    else:
        shift_id, date_str = open_shift_data
        try:
            date_show = datetime.strptime(date_str, "%Y-%m-%d").strftime("%d.%m.%Y")
        except Exception:
            date_show = date_str
        st.success(f"📅 {date_show}")
        acc = get_accumulated_beznal()
        if acc != 0:
            st.metric("💰 Безнал", f"{acc:.0f} ₽")

        # ДОБАВЛЕНИЕ ЗАКАЗА
        with st.expander("➕ ЗАКАЗ", expanded=True):
            if "amount_counter" not in st.session_state:
                st.session_state.amount_counter = 0
            if "tips_counter" not in st.session_state:
                st.session_state.tips_counter = 0
            amount_key = f"amount_{st.session_state.amount_counter}"
            tips_key = f"tips_{st.session_state.tips_counter}"
            with st.form("order_form"):
                c1, c2 = st.columns(2)
                with c1:
                    amount_str = st.text_input(
                        "Сумма", value="", placeholder="650", key=amount_key
                    )
                with c2:
                    payment = st.selectbox("Тип", ["НАЛ", "КАРТА"], key="payment_input")
                tips_str = st.text_input(
                    "Чаевые", value="", placeholder="0", key=tips_key
                )
                now_moscow = datetime.now(MOSCOW_TZ)
                st.caption(f"🕒 {now_moscow.strftime('%H:%M')}")
                submitted = st.form_submit_button(
                    "💾 СОХРАНИТЬ", use_container_width=True
                )
            if submitted:
                try:
                    amount = float(amount_str.replace(",", "."))
                except ValueError:
                    st.error("Введите сумму числом")
                    st.stop()
                if amount <= 0:
                    st.error("Сумма > 0")
                    st.stop()
                tips = 0.0
                if tips_str.strip():
                    try:
                        tips = float(tips_str.replace(",", "."))
                    except ValueError:
                        st.error("Чаевые числом")
                        st.stop()
                order_time = datetime.now(MOSCOW_TZ).strftime("%H:%M")
                if payment == "НАЛ":
                    typ = "нал"
                    commission = amount * (1 - rate_nal)
                    total = amount + tips
                    beznal_added = -commission
                else:
                    typ = "карта"
                    final_wo_tips = amount * rate_card
                    commission = amount - final_wo_tips
                    total = final_wo_tips + tips
                    beznal_added = final_wo_tips
                try:
                    add_order_db(
                        shift_id,
                        typ,
                        amount,
                        tips,
                        commission,
                        total,
                        beznal_added,
                        order_time,
                    )
                    if beznal_added != 0:
                        add_to_accumulated_beznal(beznal_added)
                    human_type = "Нал" if typ == "нал" else "Карта"
                    log_action(
                        "Добавление заказа",
                        f"{human_type}, {amount:.0f} ₽, чаевые {tips:.0f} ₽",
                    )
                    st.session_state.amount_counter += 1
                    st.session_state.tips_counter += 1
                    st.success(f"✅ {human_type} {amount:.0f}₽")
                    st.rerun()
                except Exception as e:
                    st.error(f"Ошибка: {e}")

        # СПИСОК ЗАКАЗОВ
        orders = get_shift_orders(shift_id)
        totals = get_shift_totals(shift_id) if orders else {}
        nal = totals.get("нал", 0.0)
        card = totals.get("карта", 0.0)
        tips_sum = totals.get("чаевые", 0.0)
        beznal_this = totals.get("безнал_смена", 0.0)
        if orders:
            st.subheader("📋 ЗАКАЗЫ")
            for i, (
                order_id,
                typ,
                amount,
                tips,
                comm,
                total,
                beznal_add,
                order_time,
            ) in enumerate(orders, 1):
                with st.container():
                    cols = st.columns([2, 1, 1, 1])
                    with cols[0]:
                        time_str = f"{order_time}" if order_time else ""
                        type_icon = "💵" if typ == "нал" else "💳"
                        st.markdown(f"**#{i}** {time_str} {type_icon} {amount:.0f}₽")
                        if tips > 0:
                            st.caption(f"💝 {tips:.0f}")
                    with cols[1]:
                        st.markdown(f"**{total:.0f}**")
                    with cols[2]:
                        edit_key = f"edit_{order_id}"
                        if st.button("✏️", key=edit_key, use_container_width=True):
                            st.session_state.edit_order_id = order_id
                            st.session_state.edit_original_type = typ
                            st.session_state.edit_original_amount = float(amount)
                            st.session_state.edit_original_tips = float(tips)
                            st.rerun()
                    with cols[3]:
                        delete_key = f"delete_{order_id}"
                        confirm_key = f"confirm_{order_id}"
                        if confirm_key not in st.session_state.confirm_delete:
                            st.session_state.confirm_delete[confirm_key] = False
                        if st.button("🗑", key=delete_key, use_container_width=True):
                            st.session_state.confirm_delete[confirm_key] = True
                            st.rerun()
                        if st.session_state.confirm_delete.get(confirm_key, False):
                            st.caption("Удалить?")
                            if st.button(
                                "✅", key=f"yes_{order_id}", use_container_width=True
                            ):
                                if beznal_add != 0:
                                    add_to_accumulated_beznal(-beznal_add)
                                delete_order_db(order_id)
                                log_action("Удаление заказа", f"Заказ #{i}")
                                st.session_state.confirm_delete[confirm_key] = False
                                st.success(f"Заказ #{i} удалён")
                                st.rerun()
                st.divider()

            # ИТОГИ
            st.subheader("💰 ИТОГИ")
            extra_expenses = get_extra_expenses(shift_id)
            total_extra = sum(e["amount"] for e in extra_expenses)
            cols = st.columns(4)
            cols[0].metric("Нал", f"{nal:.0f}₽")
            cols[1].metric("Карта", f"{card:.0f}₽")
            cols[2].metric("Чаевые", f"{tips_sum:.0f}₽")
            cols[3].metric("Δ безнал", f"{beznal_this:.0f}₽")
            total_income = nal + card + tips_sum
            st.metric("ДОХОД", f"{total_income:.0f}₽")
            if total_extra > 0:
                st.metric(
                    "РАСХОДЫ",
                    f"{total_extra:.0f}₽",
                    delta=f"Чистые: {total_income - total_extra:.0f}₽",
                )

        # РЕДАКТИРОВАНИЕ
        if st.session_state.edit_order_id is not None:
            st.subheader("✏️ РЕДАКТИРОВАНИЕ")
            order_id = st.session_state.edit_order_id
            orig_type = st.session_state.get("edit_original_type", "нал")
            orig_amount = st.session_state.get("edit_original_amount", 0.0)
            orig_tips = st.session_state.get("edit_original_tips", 0.0)
            with st.form("edit_order_form"):
                col1, col2 = st.columns(2)
                with col1:
                    new_amount_str = st.text_input(
                        "Новая сумма", value=f"{orig_amount:.0f}"
                    )
                with col2:
                    options = ["НАЛ", "КАРТА"]
                    idx = 0 if orig_type == "нал" else 1
                    new_payment = st.selectbox("Тип", options, index=idx)
                new_tips_str = st.text_input("Новые чаевые", value=f"{orig_tips:.0f}")
                col_btn1, col_btn2 = st.columns(2)
                with col_btn1:
                    save_btn = st.form_submit_button(
                        "💾 СОХР", use_container_width=True
                    )
                with col_btn2:
                    cancel_btn = st.form_submit_button("❌", use_container_width=True)
            if cancel_btn:
                st.session_state.edit_order_id = None
                st.rerun()
            if save_btn:
                try:
                    new_amount = float(new_amount_str.replace(",", "."))
                    new_tips = float(new_tips_str.replace(",", "."))
                except ValueError:
                    st.error("Введите числа")
                    st.stop()
                if new_amount <= 0:
                    st.error("Сумма > 0")
                    st.stop()
                conn = get_db_connection()
                cur = conn.cursor()
                cur.execute(
                    "SELECT type, amount, tips, beznal_added FROM orders WHERE id = ?",
                    (order_id,),
                )
                row = cur.fetchone()
                conn.close()
                if not row:
                    st.error("Заказ не найден")
                    st.stop()
                old_type, old_amount, old_tips, old_beznal = row
                new_type = "нал" if new_payment == "НАЛ" else "карта"
                if new_type == "нал":
                    commission = new_amount * (1 - rate_nal)
                    total = new_amount + new_tips
                    new_beznal = -commission
                else:
                    final_wo_tips = new_amount * rate_card
                    commission = new_amount - final_wo_tips
                    total = final_wo_tips + new_tips
                    new_beznal = final_wo_tips
                delta_acc = -float(old_beznal or 0.0) + float(new_beznal or 0.0)
                if delta_acc != 0:
                    add_to_accumulated_beznal(delta_acc)
                update_order_db(
                    order_id,
                    new_type,
                    new_amount,
                    new_tips,
                    commission,
                    total,
                    new_beznal,
                )
                log_action("Редактирование", f"Заказ #{order_id}")
                st.success("✅ Сохранено")
                st.session_state.edit_order_id = None
                st.rerun()

        # РАСХОДЫ
        st.write("---")
        with st.expander("💸 РАСХОДЫ", expanded=False):
            st.caption("Мойка, еда и т.д.")
            st.subheader("📋 Быстрый выбор")
            with st.form("quick_expense_form"):
                col1, col2, col3 = st.columns([2, 1, 1])
                with col1:
                    expense_desc = st.selectbox(
                        "Что",
                        options=[""] + POPULAR_EXPENSES,
                        format_func=lambda x: "Выберите расход..." if x == "" else x,
                        key="quick_expense_desc",
                    )
                with col2:
                    expense_amount = st.number_input(
                        "Сумма",
                        min_value=0.0,
                        step=50.0,
                        value=100.0,
                        format="%.0f",
                        key="quick_expense_amount",
                    )
                with col3:
                    submitted = st.form_submit_button("➕", use_container_width=True)
                if (
                    submitted
                    and expense_desc
                    and expense_desc != ""
                    and expense_amount > 0
                ):
                    add_extra_expense(shift_id, expense_amount, expense_desc)
                    log_action(
                        "Добавление расхода", f"{expense_desc}: {expense_amount:.0f} ₽"
                    )
                    st.success(f"✅ Добавлено")
                    st.rerun()
            st.divider()
            with st.form("manual_expense_form"):
                st.subheader("✏️ Свой вариант")
                col1, col2, col3 = st.columns([2, 1, 1])
                with col1:
                    manual_desc = st.text_input(
                        "Что", placeholder="мойка", key="manual_desc"
                    )
                with col2:
                    manual_amount = st.number_input(
                        "Сумма",
                        min_value=0.0,
                        step=50.0,
                        format="%.0f",
                        key="manual_amount",
                    )
                with col3:
                    manual_submit = st.form_submit_button(
                        "➕", use_container_width=True
                    )
                if manual_submit and manual_desc and manual_amount > 0:
                    add_extra_expense(shift_id, manual_amount, manual_desc)
                    log_action(
                        "Добавление расхода", f"{manual_desc}: {manual_amount:.0f} ₽"
                    )
                    st.success(f"✅ Добавлено")
                    st.rerun()
            extra_expenses = get_extra_expenses(shift_id)
            if extra_expenses:
                st.subheader("📋 Текущие расходы")
                total_extra = 0
                for exp in extra_expenses:
                    cols = st.columns([3, 1, 1])
                    with cols[0]:
                        st.markdown(f"**{exp['description']}**")
                    with cols[1]:
                        st.markdown(f"{exp['amount']:.0f}₽")
                    with cols[2]:
                        if st.button(
                            "🗑", key=f"del_exp_{exp['id']}", use_container_width=True
                        ):
                            delete_extra_expense(exp["id"])
                            log_action("Удаление расхода", f"{exp['description']}")
                            st.rerun()
                    total_extra += exp["amount"]
                    st.divider()
                st.markdown(f"**ИТОГО: {total_extra:.0f}₽**")

        # ЗАКРЫТИЕ СМЕНЫ
        st.write("---")
        with st.expander("🔒 ЗАКРЫТЬ", expanded=False):
            last_consumption, last_price = get_last_fuel_params()
            total_extra = get_total_extra_expenses(shift_id)
            with st.form("close_form"):
                km = st.number_input("Км", min_value=0, step=10, value=100)
                cols = st.columns(2)
                with cols[0]:
                    consumption = st.number_input(
                        "Расход",
                        min_value=0.0,
                        step=0.5,
                        value=float(f"{last_consumption:.1f}"),
                        format="%.1f",
                    )
                with cols[1]:
                    fuel_price = st.number_input(
                        "Цена",
                        min_value=0.0,
                        step=1.0,
                        value=float(f"{last_price:.1f}"),
                        format="%.1f",
                    )
                if km > 0 and consumption > 0 and fuel_price > 0:
                    liters = (km / 100) * consumption
                    fuel_cost = liters * fuel_price
                    income = nal + card + tips_sum
                    total_costs = fuel_cost + total_extra
                    profit = income - total_costs
                    st.info(f"⛽ {liters:.1f}л = {fuel_cost:.0f}₽")
                    if total_extra > 0:
                        st.info(f"💸 Расходы: {total_extra:.0f}₽")
                    st.success(f"💰 Прибыль: {profit:.0f}₽")
                submitted_close = st.form_submit_button(
                    "🔒 ЗАКРЫТЬ", use_container_width=True, type="primary"
                )
                if submitted_close:
                    if km > 0 and consumption > 0 and fuel_price > 0:
                        liters = (km / 100) * consumption
                        fuel_cost = liters * fuel_price
                    else:
                        liters = 0.0
                        fuel_cost = 0.0
                    close_shift_db(shift_id, km, liters, fuel_price)
                    income = nal + card + tips_sum
                    total_costs = fuel_cost + total_extra
                    profit = income - total_costs
                    log_action(
                        "Закрытие смены",
                        f"Дата: {date_str}, доход: {income:.0f} ₽, прибыль: {profit:.0f} ₽",
                    )
                    st.success("✅ Смена закрыта")
                    cols = st.columns(3)
                    cols[0].metric("Доход", f"{income:.0f}₽")
                    cols[1].metric("Расходы", f"{total_costs:.0f}₽")
                    cols[2].metric("Прибыль", f"{profit:.0f}₽")
                    st.cache_data.clear()


def show_reports_page():
    if not check_and_create_tables():
        st.error("❌ Ошибка БД")
        return
    st.title("📊 ОТЧЁТЫ")
    try:
        from pages_imports import (
            get_available_year_months_cached,
            get_month_totals_cached,
            get_month_shifts_details_cached,
            get_closed_shift_id_by_date,
            get_shift_orders_df,
            get_orders_by_hour,
            format_month_option,
        )

        year_months = get_available_year_months_cached()
        if not year_months:
            st.info("📭 Нет закрытых смен")
            return
        ym = st.selectbox(
            "📅 Месяц", year_months, format_func=format_month_option, index=0
        )
        df_shifts = get_month_shifts_details_cached(ym)
        totals = get_month_totals_cached(ym)
        month_extra = get_month_extra_expenses(ym)
        month_fuel_cost = 0.0
        month_fuel_liters = 0.0
        if not df_shifts.empty:
            month_fuel_cost = float(
                (df_shifts["Литры"].fillna(0) * df_shifts["Цена"].fillna(0)).sum()
            )
            month_fuel_liters = float(df_shifts["Литры"].fillna(0).sum())
        st.write("---")
        st.subheader("📄 ДЕТАЛИ ПО СМЕНЕ")
        if df_shifts.empty:
            st.write("Нет данных за выбранный месяц")
        else:
            dates = df_shifts["Дата"].unique().tolist()
            selected = st.selectbox("📆 Выберите дату смены", options=dates)
            try:
                selected_date = datetime.strptime(selected, "%d.%m.%Y").strftime(
                    "%Y-%m-%d"
                )
            except:
                selected_date = selected
            df_summary = df_shifts[df_shifts["Дата"] == selected].copy()
            if not df_summary.empty:
                st.dataframe(
                    df_summary.style.format(
                        {
                            "Нал": "{:.0f} ₽",
                            "Карта": "{:.0f} ₽",
                            "Чаевые": "{:.0f} ₽",
                            "Δ безнал": "{:.0f} ₽",
                            "Км": "{:.0f} км",
                            "Литры": "{:.1f} л",
                            "Цена": "{:.1f} ₽/л",
                            "Всего": "{:.0f} ₽",
                        }
                    ),
                    use_container_width=True,
                )
                row = df_summary.iloc[0]
                fuel_cost = float(row["Литры"] * row["Цена"])
                shift_id = get_closed_shift_id_by_date(selected_date)
                extra = get_extra_expenses(shift_id) if shift_id else []
                extra_sum = sum(e["amount"] for e in extra)
                income = float(row["Всего"])
                col1, col2, col3 = st.columns(3)
                col1.metric("💰 Доход", f"{income:.0f} ₽")
                col2.metric("⛽ Бензин", f"{fuel_cost:.0f} ₽")
                col3.metric("💸 Прочие", f"{extra_sum:.0f} ₽")
                total_costs = fuel_cost + extra_sum
                profit = income - total_costs
                st.metric(
                    "📈 Чистая прибыль",
                    f"{profit:.0f} ₽",
                    delta=f"{profit/income*100:.1f}%" if income > 0 else None,
                )
            shift_id = get_closed_shift_id_by_date(selected_date)
            if shift_id:
                df_orders = get_shift_orders_df(shift_id)
                if not df_orders.empty:
                    st.subheader("📋 ЗАКАЗЫ В СМЕНЕ")
                    st.dataframe(
                        df_orders.style.format(
                            {
                                "Сумма": "{:.0f} ₽",
                                "Чаевые": "{:.0f} ₽",
                                "Δ безнал": "{:.0f} ₽",
                                "Вам": "{:.0f} ₽",
                            }
                        ),
                        use_container_width=True,
                    )
                extra_expenses = get_extra_expenses(shift_id)
                if extra_expenses:
                    st.subheader("💸 ДОП. РАСХОДЫ")
                    exp_df = pd.DataFrame(extra_expenses)
                    st.dataframe(
                        exp_df[["description", "amount"]]
                        .rename(columns={"description": "Описание", "amount": "Сумма"})
                        .style.format({"Сумма": "{:.0f} ₽"}),
                        use_container_width=True,
                    )
                    st.caption(
                        f"💰 Всего доп. расходов: {sum(e['amount'] for e in extra_expenses):.0f} ₽"
                    )
            df_hours = get_orders_by_hour(selected_date)
            if not df_hours.empty:
                st.subheader("📊 ЗАКАЗЫ ПО ЧАСАМ")
                st.bar_chart(data=df_hours, x="Час", y="Заказов")
        st.write("---")
        st.subheader("📊 ИТОГИ ЗА МЕСЯЦ")
        col1, col2, col3 = st.columns(3)
        col1.metric("💵 Нал", f"{totals.get('нал', 0):.0f} ₽")
        col2.metric("💳 Карта", f"{totals.get('карта', 0):.0f} ₽")
        col3.metric("💝 Чаевые", f"{totals.get('чаевые', 0):.0f} ₽")
        total_income = totals.get("всего", 0)
        col4, col5, col6 = st.columns(3)
        col4.metric("📊 Δ безнал", f"{totals.get('безнал_добавлено', 0):.0f} ₽")
        col5.metric("📆 Смен", f"{totals.get('смен', 0)}")
        col6.metric("💰 ВСЕГО", f"{total_income:.0f} ₽")
        st.write("---")
        st.subheader("💰 ФИНАНСЫ ЗА МЕСЯЦ")
        col7, col8, col9 = st.columns(3)
        col7.metric("⛽ Бензин", f"{month_fuel_cost:.0f} ₽")
        col8.metric("💸 Прочие", f"{month_extra:.0f} ₽")
        total_costs = month_fuel_cost + month_extra
        col9.metric("📉 ВСЕГО", f"{total_costs:.0f} ₽")
        profit = total_income - total_costs
        profitability = (profit / total_income * 100) if total_income > 0 else 0
        col10, col11, col12 = st.columns(3)
        col10.metric(
            "📈 ПРИБЫЛЬ",
            f"{profit:.0f} ₽",
            delta=f"{profitability:.1f}%" if total_income > 0 else None,
        )
        shifts_count = totals.get("смен", 0)
        col11.metric(
            "💰 Средний доход",
            f"{total_income / shifts_count:.0f} ₽" if shifts_count > 0 else "0 ₽",
        )
        col12.metric(
            "📊 Средняя прибыль",
            f"{profit / shifts_count:.0f} ₽" if shifts_count > 0 else "0 ₽",
        )
    except Exception as e:
        st.error(f"Ошибка: {e}")


def show_admin_page():
    if not check_and_create_tables():
        st.error("❌ Ошибка БД")
        return
    st.title("🛠 АДМИНИСТРИРОВАНИЕ")
    ADMIN_PASSWORD = st.secrets.get("ADMIN_PASSWORD", "changeme")
    if "admin_authenticated" not in st.session_state:
        st.session_state.admin_authenticated = False
    if not st.session_state.admin_authenticated:
        with st.form("admin_login"):
            pwd = st.text_input("Пароль администратора", type="password")
            ok = st.form_submit_button("ВОЙТИ", use_container_width=True)
            if ok and pwd == ADMIN_PASSWORD:
                st.session_state.admin_authenticated = True
                st.rerun()
            elif ok:
                st.error("❌ Неверный пароль")
        return
    tabs = st.tabs(
        ["📥 ИМПОРТ", "🔄 ПЕРЕСЧЁТ", "✏️ БЕЗНАЛ", "🗄 БЭКАПЫ", "🔧 ИНСТРУМЕНТЫ"]
    )
    with tabs[0]:
        st.subheader("📥 ИМПОРТ ДАННЫХ")
        with st.expander("📄 Google Sheets", expanded=False):
            sheet_url = st.text_input(
                "Ссылка", placeholder="https://docs.google.com/spreadsheets/d/..."
            )
            if st.button("🚀 ИМПОРТ", use_container_width=True):
                with st.spinner("Импорт..."):
                    try:
                        from pages_imports import import_from_gsheet

                        imported = import_from_gsheet(sheet_url)
                        if imported > 0:
                            st.success(f"✅ Импортировано {imported} заказов")
                    except Exception as e:
                        st.error(f"Ошибка: {e}")
        with st.expander("📂 Файл Excel/CSV", expanded=True):
            uploaded = st.file_uploader("Выберите файл", type=["xlsx", "xls", "csv"])
            if uploaded and st.button("📤 ИМПОРТ ФАЙЛА", use_container_width=True):
                with st.spinner("Импорт..."):
                    try:
                        from pages_imports import import_from_excel

                        imported = import_from_excel(uploaded)
                        if imported > 0:
                            st.success(f"✅ Импортировано {imported} заказов")
                    except Exception as e:
                        st.error(f"Ошибка: {e}")
    with tabs[1]:
        st.subheader("🔄 ПЕРЕСЧЁТ")
        try:
            from pages_imports import get_accumulated_beznal, recalc_full_db

            current = get_accumulated_beznal()
            st.metric("💰 Текущий безнал", f"{current:.0f} ₽")
            if st.button("🔄 ПЕРЕСЧИТАТЬ", use_container_width=True, type="primary"):
                with st.spinner("Пересчёт..."):
                    new_total = recalc_full_db()
                    st.success(f"✅ Готово")
                    st.metric("💰 Новый безнал", f"{new_total:.0f} ₽")
        except Exception as e:
            st.error(f"Ошибка: {e}")
    with tabs[2]:
        st.subheader("✏️ НАКОПЛЕННЫЙ БЕЗНАЛ")
        current = get_accumulated_beznal()
        st.metric("💰 Текущее", f"{current:.0f} ₽")
        with st.form("change_beznal_form"):
            new_value = st.number_input(
                "Новое значение",
                min_value=None,
                step=100.0,
                format="%.0f",
                value=float(current),
            )
            col1, col2 = st.columns(2)
            with col1:
                save_btn = st.form_submit_button(
                    "💾 СОХР", use_container_width=True, type="primary"
                )
            with col2:
                reset_btn = st.form_submit_button("🔄 СБРОС", use_container_width=True)
        if save_btn:
            set_accumulated_beznal(new_value)
            st.success(f"✅ Сохранено: {new_value:.0f} ₽")
            st.rerun()
        if reset_btn:
            set_accumulated_beznal(0)
            st.success(f"✅ Сброшено")
            st.rerun()
    with tabs[3]:
        st.subheader("🗄 БЭКАПЫ")
        col1, col2 = st.columns(2)
        with col1:
            if st.button("📦 СОЗДАТЬ", use_container_width=True, type="primary"):
                with st.spinner("Создание..."):
                    path = create_backup()
                    st.success(f"✅ {os.path.basename(path)}")
        with col2:
            backup_dir = get_backup_dir()
            st.info(f"📁 {os.path.basename(backup_dir)}")
        backups = list_backups()
        if backups:
            st.subheader("📋 СПИСОК")
            for backup in backups:
                with st.container():
                    cols = st.columns([3, 1, 1, 1])
                    with cols[0]:
                        st.markdown(f"**{backup['name']}**")
                        st.caption(
                            f"📅 {backup['time'].strftime('%d.%m.%Y %H:%M')} | {backup['size']:.1f} KB"
                        )
                    with cols[1]:
                        data = download_backup(backup["path"])
                        st.download_button(
                            label="📥",
                            data=data,
                            file_name=backup["name"],
                            key=f"d_{backup['name']}",
                            use_container_width=True,
                        )
                    with cols[2]:
                        if st.button(
                            "🔄", key=f"r_{backup['name']}", use_container_width=True
                        ):
                            restore_from_backup(backup["path"])
                            st.success("✅ Восстановлено")
                            st.cache_data.clear()
                            st.rerun()
                    with cols[3]:
                        if st.button(
                            "🗑", key=f"del_{backup['name']}", use_container_width=True
                        ):
                            os.remove(backup["path"])
                            st.success(f"✅ Удалён")
                            st.rerun()
                    st.divider()
    with tabs[4]:
        st.subheader("🔧 ИНСТРУМЕНТЫ")
        try:
            from pages_imports import normalize_shift_dates, reset_db

            with st.expander("🛠 ИСПРАВЛЕНИЕ ДАТ", expanded=False):
                if st.button("🛠 ИСПРАВИТЬ", use_container_width=True):
                    with st.spinner("Исправление..."):
                        fixed, skipped = normalize_shift_dates()
                        st.success(f"✅ Исправлено: {fixed}")
            st.divider()
            with st.expander("⚠️ СБРОС БАЗЫ", expanded=False):
                st.error("🚨 УДАЛИТ ВСЕ ДАННЫЕ")
                col1, col2 = st.columns(2)
                with col1:
                    confirm = st.checkbox("Понимаю")
                with col2:
                    confirm2 = st.checkbox("Есть бэкап")
                if confirm and confirm2:
                    if st.button(
                        "🗑 УДАЛИТЬ ВСЁ", type="primary", use_container_width=True
                    ):
                        with st.spinner("Удаление..."):
                            reset_db()
                            st.success("✅ Сброшено")
                            st.cache_data.clear()
                            st.rerun()
        except Exception as e:
            st.error(f"Ошибка: {e}")


# ===== ЗАПУСК =====
st.set_page_config(
    page_title="Такси учёт",
    page_icon="🚕",
    layout="centered",
    initial_sidebar_state="expanded",
)
apply_mobile_optimized_css()
init_auth_db()
ensure_users_dir()

saved_username = load_session_from_disk()
if saved_username and "username" not in st.session_state:
    st.session_state["username"] = saved_username
    st.session_state["db_name"] = get_current_db_name()
    st.session_state["user_dir"] = get_user_dir(saved_username)
    st.session_state["page"] = "main"
    try:
        with open(SESSION_FILE, "r") as f:
            data = json.load(f)
        if data.get("session_start"):
            st.session_state.session_start = datetime.fromisoformat(
                data["session_start"]
            )
            st.session_state.last_activity = datetime.fromisoformat(
                data["last_activity"]
            )
    except:
        init_session()

init_session()

# ===== ЛОГИН =====
if "username" not in st.session_state:
    st.title("🚕 ВХОД")
    tabs = st.tabs(["🔑 ВХОД", "📝 РЕГИСТРАЦИЯ"])
    with tabs[0]:
        with st.form("login_form"):
            username = st.text_input("Имя пользователя")
            password = st.text_input("Пароль", type="password")
            btn = st.form_submit_button("🔓 ВОЙТИ", use_container_width=True)
        if btn:
            if not username or not password:
                st.error("Введите данные")
            elif authenticate_user(username, password):
                update_login_stats(username.strip())
                st.session_state["username"] = username.strip()
                st.session_state["db_name"] = get_current_db_name()
                st.session_state["user_dir"] = get_user_dir(username.strip())
                st.session_state["page"] = "main"
                st.session_state["session_start"] = datetime.now(MOSCOW_TZ)
                st.session_state["last_activity"] = datetime.now(MOSCOW_TZ)
                save_session_to_disk()
                st.success(f"✅ Добро пожаловать, {username}!")
                log_action("Вход", f"Пользователь {username}")
                st.rerun()
            else:
                st.error("❌ Неверно")
    with tabs[1]:
        st.caption("Создайте учётную запись")
        with st.form("register_form"):
            reg_username = st.text_input("Имя пользователя")
            reg_password = st.text_input("Пароль", type="password")
            reg_password2 = st.text_input("Повторите пароль", type="password")
            reg_btn = st.form_submit_button(
                "📝 ЗАРЕГИСТРИРОВАТЬСЯ", use_container_width=True
            )
        if reg_btn:
            if not reg_username or not reg_password:
                st.error("Заполните поля")
            elif reg_password != reg_password2:
                st.error("Пароли не совпадают")
            elif len(reg_password) < 4:
                st.error("Пароль >= 4 символов")
            else:
                ok = register_user(reg_username, reg_password)
                if ok:
                    st.success("✅ Пользователь создан!")
                    log_action("Регистрация", f"Новый пользователь {reg_username}")
                else:
                    st.error("❌ Уже существует")
    st.stop()

# ===== ПОСЛЕ ВХОДА =====
st.session_state["db_name"] = get_current_db_name()
if "page" not in st.session_state:
    st.session_state["page"] = "main"

# САЙДБАР
with st.sidebar:
    st.markdown(
        f"""
    <div class="user-info">
        <div class="user-avatar">👤</div>
        <div class="user-name">{st.session_state['username']}<small>водитель</small></div>
    </div>
    """,
        unsafe_allow_html=True,
    )
    try:
        db_path = get_current_db_name()
        if os.path.exists(db_path):
            size = os.path.getsize(db_path) / 1024
            st.markdown(
                f"""
            <div class="sidebar-metric" style="background:white;padding:10px;border-radius:12px;margin:10px 0;text-align:center;">
                <div style="font-size:0.8rem;color:#64748b;">📦 Размер БД</div>
                <div style="font-size:1.4rem;font-weight:bold;color:#1e293b;">{size:.1f} KB</div>
            </div>
            """,
                unsafe_allow_html=True,
            )
        acc = get_accumulated_beznal()
        st.markdown(
            f"""
        <div class="sidebar-metric" style="background:white;padding:10px;border-radius:12px;margin:10px 0;text-align:center;">
            <div style="font-size:0.8rem;color:#64748b;">💰 Безнал</div>
            <div style="font-size:1.4rem;font-weight:bold;color:#1e293b;">{acc:.0f} ₽</div>
        </div>
        """,
            unsafe_allow_html=True,
        )
    except:
        pass
    st.divider()
    if st.button(
        "📋 ПРОГРАММА",
        use_container_width=True,
        type="primary" if st.session_state["page"] == "main" else "secondary",
    ):
        st.session_state["page"] = "main"
        st.rerun()
    if st.button(
        "📊 ОТЧЁТЫ",
        use_container_width=True,
        type="primary" if st.session_state["page"] == "reports" else "secondary",
    ):
        st.session_state["page"] = "reports"
        st.rerun()
    if st.button(
        "⚙️ АДМИНКА",
        use_container_width=True,
        type="primary" if st.session_state["page"] == "admin" else "secondary",
    ):
        st.session_state["page"] = "admin"
        st.rerun()
    st.divider()
    time_left = get_session_time_remaining()
    st.caption(f"⏱️ Сессия: {time_left}")
    if st.button("🚪 ВЫЙТИ", use_container_width=True):
        log_action("Выход", f"Пользователь {st.session_state['username']}")
        clear_session_disk()
        st.session_state.clear()
        st.rerun()

# СТРАНИЦЫ
if st.session_state["page"] == "main":
    show_main_page()
elif st.session_state["page"] == "reports":
    show_reports_page()
elif st.session_state["page"] == "admin":
    show_admin_page()
