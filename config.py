# config.py — ПОЛНАЯ ВЕРСИЯ
import sqlite3
import os
from datetime import datetime, timezone, timedelta
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

def get_current_db_name(username: str) -> str:
    if not username:
        return "taxi_default.db"
    safe_name = "".join(c for c in username if c.isalnum() or c in ("_", "-"))
    return os.path.join(get_user_dir(username), f"taxi{safe_name}.db")

def get_backup_dir(username: str) -> str:
    user_dir = get_user_dir(username if username else "unknown")
    backup_dir = os.path.join(user_dir, "backups")
    if not os.path.exists(backup_dir):
        os.makedirs(backup_dir)
    return backup_dir

# ===== СХЕМА БД =====
def get_db_schema():
    return [
        """CREATE TABLE IF NOT EXISTS shifts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL, km INTEGER DEFAULT 0,
            fuel_liters REAL DEFAULT 0, fuel_price REAL DEFAULT 0,
            is_open INTEGER DEFAULT 1, opened_at TEXT, closed_at TEXT)""",
        """CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT, shift_id INTEGER,
            type TEXT NOT NULL, amount REAL NOT NULL, tips REAL DEFAULT 0,
            commission REAL NOT NULL, total REAL NOT NULL,
            beznal_added REAL DEFAULT 0, order_time TEXT)""",
        """CREATE TABLE IF NOT EXISTS extra_expenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT, shift_id INTEGER,
            amount REAL DEFAULT 0, description TEXT, created_at TEXT)""",
        """CREATE TABLE IF NOT EXISTS accumulated_beznal (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            driver_id INTEGER DEFAULT 1,
            total_amount REAL DEFAULT 0,
            last_updated TEXT)"""
    ]

def check_and_create_tables(db_path: str):
    try:
        conn = sqlite3.connect(db_path)
        for schema in get_db_schema():
            conn.execute(schema)
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

def get_db_connection(username: str):
    db_path = get_current_db_name(username)
    check_and_create_tables(db_path)
    return sqlite3.connect(db_path)

# ===== АВТОРИЗАЦИЯ =====
def init_auth_db():
    ensure_users_dir()
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
        db_path = get_current_db_name(username)
        if os.path.exists(db_path):
            os.remove(db_path)
        check_and_create_tables(db_path)
        return True
    except sqlite3.IntegrityError:
        return False
    except Exception as e:
        print(f"Ошибка регистрации: {e}")
        return False
    finally:
        conn.close()

# ===== СМЕНЫ И ЗАКАЗЫ =====

def update_order_and_adjust_beznal(
    order_id: int,
    order_type: str,
    amount: float,
    tips: float,
    commission: float,
    total: float,
    beznal_added: float,
):
    """Обновляет заказ и корректирует накопленный безнал."""
    conn = get_db_connection()
    c = conn.cursor()
    try:
        # Получаем старое значение beznal_added
        c.execute("SELECT beznal_added FROM orders WHERE id = ?", (order_id,))
        old_row = c.fetchone()
        old_beznal = old_row[0] if old_row else 0.0
        
        # Обновляем заказ
        c.execute(
            """
            UPDATE orders 
            SET type = ?, amount = ?, tips = ?, commission = ?, total = ?, beznal_added = ?
            WHERE id = ?
            """,
            (order_type, amount, tips, commission, total, beznal_added, order_id),
        )
        
        # Корректируем накопленный безнал (разница между новым и старым)
        diff = beznal_added - old_beznal
        c.execute(
            """
            UPDATE accumulated_beznal
            SET total_amount = total_amount + ?, last_updated = ?
            WHERE driver_id = 1
            """,
            (diff, datetime.now(MOSCOW_TZ).strftime("%Y-%m-%d %H:%M:%S")),
        )
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()
def get_open_shift(username: str):
    conn = get_db_connection(username)
    c = conn.cursor()
    c.execute("SELECT id, date FROM shifts WHERE is_open = 1 LIMIT 1")
    row = c.fetchone()
    conn.close()
    return row

def open_shift(date_str: str, username: str) -> int:
    conn = get_db_connection(username)
    c = conn.cursor()
    c.execute(
        "INSERT INTO shifts (date, is_open, opened_at) VALUES (?, 1, ?)",
        (date_str, datetime.now(MOSCOW_TZ).strftime("%Y-%m-%d %H:%M:%S")),
    )
    sid = c.lastrowid
    conn.commit()
    conn.close()
    return sid

def close_shift_db(shift_id: int, km: int, liters: float, fuel_price: float, username: str):
    conn = get_db_connection(username)
    c = conn.cursor()
    c.execute(
        "UPDATE shifts SET is_open = 0, km = ?, fuel_liters = ?, fuel_price = ?, closed_at = ? WHERE id = ?",
        (km, liters, fuel_price, datetime.now(MOSCOW_TZ).strftime("%Y-%m-%d %H:%M:%S"), shift_id),
    )
    conn.commit()
    conn.close()

def get_accumulated_beznal(username: str) -> float:
    conn = get_db_connection(username)
    c = conn.cursor()
    c.execute("SELECT total_amount FROM accumulated_beznal WHERE driver_id = 1")
    row = c.fetchone()
    conn.close()
    return float(row[0]) if row and row[0] is not None else 0.0

def set_accumulated_beznal(amount: float, username: str):
    conn = get_db_connection(username)
    c = conn.cursor()
    c.execute(
        "UPDATE accumulated_beznal SET total_amount = ?, last_updated = ? WHERE driver_id = 1",
        (amount, datetime.now(MOSCOW_TZ).strftime("%Y-%m-%d %H:%M:%S")),
    )
    conn.commit()
    conn.close()

def add_order_and_update_beznal(shift_id, order_type, amount, tips, commission, total, beznal_added, order_time, username):
    conn = get_db_connection(username)
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

def delete_order_and_update_beznal(order_id, username):
    conn = get_db_connection(username)
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

def get_shift_totals(shift_id, username):
    conn = get_db_connection(username)
    c = conn.cursor()
    c.execute("SELECT type, SUM(total - tips) FROM orders WHERE shift_id = ? GROUP BY type", (shift_id,))
    by_type = dict(c.fetchall())
    c.execute("SELECT SUM(tips), SUM(beznal_added) FROM orders WHERE shift_id = ?", (shift_id,))
    tips, beznal = c.fetchone()
    conn.close()
    by_type["чаевые"] = tips or 0.0
    by_type["безнал_смена"] = beznal or 0.0
    return by_type

def get_last_fuel_params(username):
    conn = get_db_connection(username)
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

def add_extra_expense(shift_id, amount, description, username):
    conn = get_db_connection(username)
    c = conn.cursor()
    c.execute(
        "INSERT INTO extra_expenses (shift_id, amount, description, created_at) VALUES (?, ?, ?, ?)",
        (shift_id, amount, description, datetime.now(MOSCOW_TZ).strftime("%Y-%m-%d %H:%M:%S")),
    )
    conn.commit()
    conn.close()

def get_extra_expenses(shift_id, username):
    conn = get_db_connection(username)
    c = conn.cursor()
    c.execute("SELECT id, amount, description, created_at FROM extra_expenses WHERE shift_id = ? ORDER BY id", (shift_id,))
    rows = c.fetchall()
    conn.close()
    return [{"id": r[0], "amount": r[1] or 0.0, "description": r[2] or "", "created_at": r[3] or ""} for r in rows]

def delete_extra_expense(expense_id, username):
    conn = get_db_connection(username)
    c = conn.cursor()
    c.execute("DELETE FROM extra_expenses WHERE id = ?", (expense_id,))
    conn.commit()
    conn.close()

def get_total_extra_expenses(shift_id, username):
    conn = get_db_connection(username)
    c = conn.cursor()
    c.execute("SELECT SUM(amount) FROM extra_expenses WHERE shift_id = ?", (shift_id,))
    row = c.fetchone()
    conn.close()
    return row[0] or 0.0

def get_shift_orders(shift_id, username):
    conn = get_db_connection(username)
    c = conn.cursor()
    c.execute("SELECT id, type, amount, tips, commission, total, beznal_added, order_time FROM orders WHERE shift_id = ? ORDER BY id DESC", (shift_id,))
    rows = c.fetchall()
    conn.close()
    return rows