import streamlit as st
import sqlite3
from datetime import datetime, date, timezone, timedelta
import hashlib
import os
import sys

# ===== НАСТРОЙКИ =====
AUTH_DB = "users.db"  # база с пользователями (логин/пароль)
USERS_DIR = "users"    # папка для хранения данных пользователей

rate_nal = 0.78   # процент для нала (для расчёта комиссии)
rate_card = 0.75  # процент для карты

# Московский часовой пояс
MOSCOW_TZ = timezone(timedelta(hours=3))

# ===== СТРОГИЙ СТИЛЬ =====
def apply_strict_style():
    st.markdown(
        """
        <style>
        /* Основной фон */
        .stApp {
            background: #f5f5f5;
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
        }
        
        /* Контейнер */
        .block-container {
            padding: 2rem 1rem;
            max-width: 800px;
            margin: 0 auto;
        }
        
        /* Заголовки */
        h1 {
            font-size: 1.8rem !important;
            font-weight: 500 !important;
            color: #1e293b !important;
            border-bottom: 2px solid #334155;
            padding-bottom: 0.5rem;
            margin-bottom: 1.5rem !important;
        }
        
        h2 {
            font-size: 1.4rem !important;
            font-weight: 500 !important;
            color: #334155 !important;
            margin-top: 1rem !important;
            margin-bottom: 0.75rem !important;
        }
        
        h3 {
            font-size: 1.2rem !important;
            font-weight: 500 !important;
            color: #475569 !important;
        }
        
        /* Строгие кнопки */
        .stButton > button {
            border-radius: 0 !important;
            border: 1px solid #334155 !important;
            background-color: white !important;
            color: #1e293b !important;
            font-weight: 400 !important;
            font-size: 0.95rem !important;
            padding: 0.5rem 1rem !important;
            transition: all 0.1s ease !important;
            box-shadow: none !important;
            width: 100%;
        }
        
        .stButton > button:hover {
            background-color: #f1f5f9 !important;
            border-color: #0f172a !important;
            color: #0f172a !important;
        }
        
        .stButton > button:active {
            background-color: #e2e8f0 !important;
            transform: none !important;
        }
        
        /* Кнопки в сайдбаре - строгий стиль */
        section[data-testid="stSidebar"] .stButton > button {
            text-align: left;
            background-color: transparent !important;
            border: none !important;
            border-left: 3px solid transparent !important;
            border-radius: 0 !important;
            padding: 0.75rem 1rem !important;
            margin: 0 !important;
            font-weight: 400 !important;
            font-size: 0.95rem !important;
            letter-spacing: 0.5px;
        }
        
        section[data-testid="stSidebar"] .stButton > button:hover {
            background-color: #e2e8f0 !important;
            border-left: 3px solid #64748b !important;
        }
        
        section[data-testid="stSidebar"] .stButton > button[kind="primary"] {
            background-color: #e2e8f0 !important;
            border-left: 3px solid #0f172a !important;
            font-weight: 500 !important;
        }
        
        /* Скрываем автоматическую навигацию Streamlit */
        section[data-testid="stSidebar"] .st-emotion-cache-1gv3huu {
            display: none !important;
        }
        
        section[data-testid="stSidebar"] .st-emotion-cache-1jzia57 {
            display: none !important;
        }
        
        /* Скрываем элементы навигации */
        div[data-testid="stSidebarNav"] {
            display: none !important;
        }
        
        /* Убираем отступы для нашей навигации */
        section[data-testid="stSidebar"] > div {
            padding-top: 1rem;
        }
        
        /* Поля ввода */
        .stTextInput > div > div > input {
            border-radius: 0 !important;
            border: 1px solid #cbd5e1 !important;
            padding: 0.5rem !important;
            font-size: 0.95rem !important;
        }
        
        .stTextInput > div > div > input:focus {
            border-color: #475569 !important;
            box-shadow: none !important;
        }
        
        .stNumberInput > div > div > input {
            border-radius: 0 !important;
            border: 1px solid #cbd5e1 !important;
        }
        
        /* Выпадающие списки */
        .stSelectbox > div > div {
            border-radius: 0 !important;
            border: 1px solid #cbd5e1 !important;
        }
        
        /* Метрики */
        .stMetric {
            background-color: white;
            border: 1px solid #e2e8f0;
            padding: 1rem;
            margin: 0.25rem 0;
        }
        
        .stMetric label {
            color: #64748b !important;
            font-weight: 400 !important;
        }
        
        .stMetric [data-testid="stMetricValue"] {
            font-weight: 500 !important;
            color: #1e293b !important;
        }
        
        /* Разделители */
        hr {
            margin: 1.5rem 0 !important;
            border-color: #cbd5e1 !important;
        }
        
        /* Контейнеры */
        .stExpander {
            border: 1px solid #e2e8f0 !important;
            border-radius: 0 !important;
            background-color: white !important;
            margin: 0.5rem 0 !important;
        }
        
        .stExpander > details > summary {
            border-radius: 0 !important;
            font-weight: 500 !important;
            padding: 0.75rem !important;
        }
        
        /* Инфо-боксы */
        .stAlert {
            border-radius: 0 !important;
            border-left: 4px solid !important;
        }
        
        .stInfo {
            background-color: #f8fafc !important;
            border-left-color: #475569 !important;
        }
        
        .stSuccess {
            background-color: #f0fdf4 !important;
            border-left-color: #166534 !important;
        }
        
        .stError {
            background-color: #fef2f2 !important;
            border-left-color: #991b1b !important;
        }
        
        /* Сайдбар */
        section[data-testid="stSidebar"] {
            background-color: #f8fafc;
            border-right: 1px solid #e2e8f0;
        }
        
        section[data-testid="stSidebar"] .stMarkdown {
            padding: 0 0.5rem;
        }
        
        /* Карточки заказов */
        div[data-testid="stVerticalBlock"] > div > div > div > div[data-testid="stVerticalBlock"] {
            background-color: white;
            border: 1px solid #e2e8f0;
            padding: 0.75rem;
            margin: 0.25rem 0;
        }
        
        /* Таблицы */
        .stDataFrame {
            border: 1px solid #e2e8f0;
        }
        
        .stDataFrame th {
            background-color: #f8fafc;
            font-weight: 500;
            color: #334155;
        }
        
        /* Вкладки */
        .stTabs [data-baseweb="tab-list"] {
            gap: 0;
            border-bottom: 1px solid #cbd5e1;
        }
        
        .stTabs [data-baseweb="tab"] {
            border-radius: 0;
            padding: 0.5rem 1rem;
            font-weight: 400;
        }
        
        .stTabs [aria-selected="true"] {
            background-color: #f1f5f9;
            border-bottom: 2px solid #334155;
            font-weight: 500;
        }
        
        /* Кастомные классы */
        .user-info {
            background-color: white;
            border: 1px solid #e2e8f0;
            padding: 0.75rem;
            margin-bottom: 1rem;
            font-size: 0.9rem;
        }
        
        .nav-header {
            font-size: 0.75rem;
            text-transform: uppercase;
            letter-spacing: 1px;
            color: #64748b;
            padding: 0.5rem 1rem;
            margin-top: 1rem;
            font-weight: 500;
        }
        
        .stats-box {
            background-color: white;
            border: 1px solid #e2e8f0;
            padding: 1rem;
            margin: 0.5rem 0;
        }
        
        .stat-value {
            font-size: 1.2rem;
            font-weight: 500;
            color: #1e293b;
        }
        
        .stat-label {
            font-size: 0.75rem;
            color: #64748b;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }
        
        .footer-info {
            font-size: 0.7rem;
            color: #94a3b8;
            text-align: center;
            margin-top: 2rem;
            padding-top: 1rem;
            border-top: 1px solid #e2e8f0;
        }
        
        /* Скрываем все автоматические элементы навигации */
        .st-emotion-cache-1gv3huu, .st-emotion-cache-1jzia57, .st-emotion-cache-1wsixal {
            display: none !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

# ===== РАБОТА С ПАПКАМИ ПОЛЬЗОВАТЕЛЕЙ =====
def ensure_users_dir():
    """Создаёт папку для пользователей, если её нет."""
    if not os.path.exists(USERS_DIR):
        os.makedirs(USERS_DIR)

def get_user_dir(username: str) -> str:
    """Возвращает путь к папке пользователя."""
    safe_name = "".join(c for c in username if c.isalnum() or c in ("_", "-"))
    if not safe_name:
        safe_name = "user"
    user_dir = os.path.join(USERS_DIR, safe_name)
    if not os.path.exists(user_dir):
        os.makedirs(user_dir)
    return user_dir

def get_current_db_name() -> str:
    """
    Имя базы для текущего пользователя с путём к папке пользователя.
    """
    username = st.session_state.get("username")
    if not username:
        return "taxi_default.db"
    
    user_dir = get_user_dir(username)
    safe_name = "".join(c for c in username if c.isalnum() or c in ("_", "-"))
    db_path = os.path.join(user_dir, f"taxi_{safe_name}.db")
    return db_path

def get_backup_dir() -> str:
    """Возвращает путь к папке бэкапов пользователя."""
    user_dir = get_user_dir(st.session_state.get("username", "unknown"))
    backup_dir = os.path.join(user_dir, "backups")
    if not os.path.exists(backup_dir):
        os.makedirs(backup_dir)
    return backup_dir

# ===== ФУНКЦИИ ДЛЯ БЭКАПОВ =====
def create_auto_backup(reason: str = "") -> str:
    """
    Автоматически создаёт бэкап базы данных.
    Возвращает путь к созданному бэкапу.
    """
    try:
        db_path = get_current_db_name()
        if not os.path.exists(db_path):
            return None
        
        backup_dir = get_backup_dir()
        timestamp = datetime.now(MOSCOW_TZ).strftime("%Y%m%d_%H%M%S")
        username = st.session_state.get("username", "unknown")
        
        # Формируем имя бэкапа с причиной
        if reason:
            safe_reason = "".join(c for c in reason if c.isalnum() or c in ("_", "-"))
            backup_name = f"auto_{username}_{safe_reason}_{timestamp}.db"
        else:
            backup_name = f"auto_{username}_{timestamp}.db"
        
        backup_path = os.path.join(backup_dir, backup_name)
        
        # Создаём копию
        import shutil
        shutil.copy2(db_path, backup_path)
        
        # Ограничиваем количество авто-бэкапов (оставляем последние 20)
        cleanup_old_backups(backup_dir, max_backups=20)
        
        return backup_path
    except Exception as e:
        print(f"Ошибка при создании авто-бэкапа: {e}")
        return None

def cleanup_old_backups(backup_dir: str, max_backups: int = 20):
    """Оставляет только последние max_backups бэкапов."""
    try:
        backups = [
            os.path.join(backup_dir, f) 
            for f in os.listdir(backup_dir) 
            if f.endswith('.db') and f.startswith('auto_')
        ]
        backups.sort(key=os.path.getmtime, reverse=True)
        
        for old_backup in backups[max_backups:]:
            os.remove(old_backup)
    except Exception as e:
        print(f"Ошибка при очистке старых бэкапов: {e}")

def switch_user(new_username: str):
    """Переключает текущего пользователя."""
    old_username = st.session_state.get("username")
    
    if old_username and old_username != new_username:
        # Создаём бэкап при переключении пользователя
        backup_path = create_auto_backup(f"switch_from_{old_username}")
        if backup_path:
            st.session_state[f"last_backup_{old_username}"] = os.path.basename(backup_path)
    
    st.session_state["username"] = new_username
    st.session_state["db_name"] = get_current_db_name()
    st.session_state["user_dir"] = get_user_dir(new_username)
    st.session_state["page"] = "main"
    
    log_action("Смена пользователя", f"{old_username} -> {new_username}")

# ===== АВТОРИЗАЦИЯ (users.db) =====
def get_auth_conn():
    return sqlite3.connect(AUTH_DB)

def init_auth_db():
    conn = get_auth_conn()
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            created_at TEXT,
            user_dir TEXT,
            last_login TEXT,
            total_logins INTEGER DEFAULT 0
        )
        """
    )
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
            INSERT INTO users (username, password_hash, created_at, user_dir, total_logins)
            VALUES (?, ?, ?, ?, 0)
            """,
            (
                username,
                hash_password(password),
                datetime.now(MOSCOW_TZ).strftime("%Y-%m-%d %H:%M:%S"),
                user_dir,
            ),
        )
        conn.commit()
        ok = True
        
        # ПОЛНОСТЬЮ НОВАЯ БАЗА для пользователя
        safe_name = "".join(c for c in username if c.isalnum() or c in ("_", "-"))
        db_path = os.path.join(user_dir, f"taxi_{safe_name}.db")
        
        # Если файл уже существует - удаляем его
        if os.path.exists(db_path):
            os.remove(db_path)
        
        # Создаём новую базу с нуля
        init_user_db(db_path)
        
    except sqlite3.IntegrityError:
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
    """Обновляет статистику входа пользователя."""
    conn = get_auth_conn()
    cur = conn.cursor()
    now = datetime.now(MOSCOW_TZ).strftime("%Y-%m-%d %H:%M:%S")
    cur.execute(
        """
        UPDATE users 
        SET last_login = ?, total_logins = total_logins + 1 
        WHERE username = ?
        """,
        (now, username),
    )
    conn.commit()
    conn.close()

def get_all_users() -> list:
    """Возвращает список всех пользователей."""
    conn = get_auth_conn()
    cur = conn.cursor()
    cur.execute("SELECT username, created_at, last_login, total_logins FROM users ORDER BY username")
    rows = cur.fetchall()
    conn.close()
    return rows

# ===== ФУНКЦИИ БД ДЛЯ СМЕН И ЗАКАЗОВ =====
def get_db_connection():
    return sqlite3.connect(get_current_db_name())

def init_user_db(db_path: str = None):
    """Инициализирует базу данных пользователя."""
    if db_path is None:
        db_path = get_current_db_name()
    
    # Создаём папку, если её нет
    db_dir = os.path.dirname(db_path)
    if db_dir and not os.path.exists(db_dir):
        os.makedirs(db_dir)
    
    # Если файл существует, удаляем его для новой чистой базы
    if os.path.exists(db_path):
        os.remove(db_path)
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS shifts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            km INTEGER DEFAULT 0,
            fuel_liters REAL DEFAULT 0,
            fuel_price REAL DEFAULT 0,
            is_open INTEGER DEFAULT 1,
            opened_at TEXT,
            closed_at TEXT
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            shift_id INTEGER,
            type TEXT NOT NULL,
            amount REAL NOT NULL,
            tips REAL DEFAULT 0,
            commission REAL NOT NULL,
            total REAL NOT NULL,
            beznal_added REAL DEFAULT 0,
            order_time TEXT
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
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            driver_id INTEGER DEFAULT 1,
            total_amount REAL DEFAULT 0,
            last_updated TEXT
        )
        """
    )

    cursor.execute("SELECT id FROM accumulated_beznal WHERE driver_id = 1")
    if not cursor.fetchone():
        cursor.execute(
            "INSERT INTO accumulated_beznal "
            "(driver_id, total_amount, last_updated) "
            "VALUES (1, 0, ?)",
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
        UPDATE shifts
        SET is_open = 0, km = ?, fuel_liters = ?, fuel_price = ?, closed_at = ?
        WHERE id = ?
        """,
        (km, liters, fuel_price, now, shift_id),
    )
    conn.commit()
    conn.close()

def add_order_db(
    shift_id,
    order_type,
    amount,
    tips,
    commission,
    total,
    beznal_added,
    order_time,
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

def update_order_db(order_id: int, order_type: str, amount: float, tips: float,
                    commission: float, total: float, beznal_added: float):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE orders
        SET type = ?, amount = ?, tips = ?, commission = ?, total = ?, beznal_added = ?
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
        FROM orders
        WHERE shift_id = ?
        ORDER BY id
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
        "SELECT type, SUM(total - tips) FROM orders "
        "WHERE shift_id = ? GROUP BY type",
        (shift_id,),
    )
    by_type = dict(cursor.fetchall())

    cursor.execute(
        "SELECT SUM(tips), SUM(beznal_added) FROM orders WHERE shift_id = ?",
        (shift_id,),
    )
    tips_sum, beznal_sum = cursor.fetchone()
    tips_sum = tips_sum or 0
    beznal_sum = beznal_sum or 0

    conn.close()

    by_type["чаевые"] = tips_sum
    by_type["безнал_смена"] = beznal_sum
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
        """
        UPDATE accumulated_beznal
        SET total_amount = total_amount + ?, last_updated = ?
        WHERE driver_id = 1
        """,
        (amount, now),
    )
    conn.commit()
    conn.close()

def get_last_fuel_params():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT fuel_liters, km, fuel_price
        FROM shifts
        WHERE is_open = 0
          AND km > 0
          AND fuel_liters > 0
          AND fuel_price > 0
        ORDER BY closed_at DESC, id DESC
        LIMIT 1
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
    """Логирование действий пользователя"""
    try:
        username = st.session_state.get("username", "unknown")
        user_dir = get_user_dir(username) if username != "unknown" else "logs"
        log_dir = os.path.join(user_dir, "logs")
        
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)
            
        with open(os.path.join(log_dir, "user_actions.log"), "a", encoding="utf-8") as f:
            timestamp = datetime.now(MOSCOW_TZ).strftime("%Y-%m-%d %H:%M:%S")
            f.write(f"[{timestamp}] {username}: {action} - {details}\n")
    except:
        pass

# ===== ФУНКЦИИ ДЛЯ СТРАНИЦ =====
def show_main_page():
    """Отображает главную страницу с учётом смен"""
    st.title(f"🚕 ПРОГРАММА УЧЁТА — {st.session_state['username']}")

    # для редактирования заказов
    if "edit_order_id" not in st.session_state:
        st.session_state.edit_order_id = None
        
    # для подтверждения удаления
    if "confirm_delete" not in st.session_state:
        st.session_state.confirm_delete = {}

    open_shift_data = get_open_shift()

    if not open_shift_data:
        st.info("📭 Сейчас нет открытой смены")

        with st.expander("📝 Открыть новую смену", expanded=True):
            with st.form("open_shift_form"):
                date_input = st.date_input(
                    "Дата смены",
                    value=date.today(),
                )
                st.caption(f"Выбрано: {date_input.strftime('%d.%m.%Y')}")
                submitted_tpl = st.form_submit_button("📂 Открыть смену", use_container_width=True)

            if submitted_tpl:
                date_str_db = date_input.strftime("%Y-%m-%d")
                open_shift(date_str_db)
                date_str_show = date_input.strftime("%d.%m.%Y")
                log_action("Открытие смены", f"Дата: {date_str_db}")
                
                # Создаём бэкап при открытии смены
                backup_path = create_auto_backup("shift_opened")
                
                st.success(f"✅ Смена открыта: {date_str_show}")
                if backup_path:
                    st.caption(f"📦 Авто-бэкап: {os.path.basename(backup_path)}")
                st.rerun()

    else:
        shift_id, date_str = open_shift_data
        try:
            date_show = datetime.strptime(date_str, "%Y-%m-%d").strftime("%d.%m.%Y")
        except Exception:
            date_show = date_str
            
        # Статистика в строгом стиле
        col1, col2, col3 = st.columns(3)
        with col1:
            st.markdown('<div class="stats-box"><div class="stat-label">СМЕНА</div><div class="stat-value">' + date_show + '</div></div>', unsafe_allow_html=True)
        
        acc = get_accumulated_beznal()
        with col2:
            st.markdown(f'<div class="stats-box"><div class="stat-label">БЕЗНАЛ</div><div class="stat-value">{acc:.0f} ₽</div></div>', unsafe_allow_html=True)
        
        with col3:
            orders_count = len(get_shift_orders(shift_id))
            st.markdown(f'<div class="stats-box"><div class="stat-label">ЗАКАЗЫ</div><div class="stat-value">{orders_count}</div></div>', unsafe_allow_html=True)

        # ===== ДОБАВЛЕНИЕ ЗАКАЗА =====
        with st.expander("➕ ДОБАВИТЬ ЗАКАЗ", expanded=True):
            with st.form("order_form"):
                c1, c2 = st.columns(2)
                with c1:
                    amount_str = st.text_input(
                        "Сумма заказа, ₽",
                        value="",
                        placeholder="например, 650",
                    )
                with c2:
                    payment = st.selectbox("Тип оплаты", ["Наличные", "Карта"])

                tips_str = st.text_input(
                    "Чаевые, ₽",
                    value="",
                    placeholder="0 (если без чаевых)",
                )

                now_moscow = datetime.now(MOSCOW_TZ)
                st.caption(f"🕒 Текущее время: {now_moscow.strftime('%H:%M')}")

                submitted = st.form_submit_button("💾 СОХРАНИТЬ ЗАКАЗ", use_container_width=True)

            if submitted:
                try:
                    amount = float(amount_str.replace(",", "."))
                except ValueError:
                    st.error("Введите сумму заказа числом.")
                    st.stop()

                if amount <= 0:
                    st.error("Сумма заказа должна быть больше нуля.")
                    st.stop()

                tips = 0.0
                if tips_str.strip():
                    try:
                        tips = float(tips_str.replace(",", "."))
                    except ValueError:
                        st.error("Чаевые нужно вводить числом (или оставить пустым).")
                        st.stop()

                order_time = datetime.now(MOSCOW_TZ).strftime("%H:%M")

                if payment == "Наличные":
                    typ = "нал"
                    final_wo_tips = amount
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
                        shift_id, typ, amount, tips, commission, total, beznal_added, order_time
                    )

                    if beznal_added != 0:
                        add_to_accumulated_beznal(beznal_added)

                    human_type = "Нал" if typ == "нал" else "Карта"
                    log_action("Добавление заказа", f"{human_type}, сумма {amount:.0f} ₽, чаевые {tips:.0f} ₽")
                    
                    # Создаём бэкап после добавления заказа (каждые 5 заказов)
                    if (orders_count + 1) % 5 == 0:
                        backup_path = create_auto_backup("orders_milestone")
                        st.success(
                            f"✅ Заказ добавлен: {human_type}, {amount:.0f} ₽, чаевые {tips:.0f} ₽\n\n"
                            f"📦 Авто-бэкап: {os.path.basename(backup_path) if backup_path else 'не создан'}"
                        )
                    else:
                        st.success(
                            f"✅ Заказ добавлен: {human_type}, {amount:.0f} ₽, чаевые {tips:.0f} ₽"
                        )
                    st.rerun()
                except Exception as e:
                    st.error(f"Ошибка при сохранении заказа: {e}")

        # ===== СПИСОК ЗАКАЗОВ =====
        orders = get_shift_orders(shift_id)
        totals = get_shift_totals(shift_id) if orders else {}
        nal = totals.get("нал", 0.0)
        card = totals.get("карта", 0.0)
        tips_sum = totals.get("чаевые", 0.0)
        beznal_this = totals.get("безнал_смена", 0.0)

        if orders:
            st.subheader("📋 ЗАКАЗЫ ЗА СМЕНУ")

            for i, (order_id, typ, amount, tips, comm, total, beznal_add, order_time) in enumerate(
                orders, 1
            ):
                with st.container():
                    cols = st.columns([4, 1, 1, 1])
                    
                    with cols[0]:
                        time_str = f"{order_time} · " if order_time else ""
                        type_icon = "💵" if typ == "нал" else "💳"
                        st.markdown(f"**#{i}** {time_str}{type_icon} **{amount:.0f} ₽**")
                        details = []
                        if tips > 0:
                            details.append(f"чаевые {tips:.0f} ₽")
                        if beznal_add > 0:
                            details.append(f"+{beznal_add:.0f} ₽ безнал")
                        elif beznal_add < 0:
                            details.append(f"{beznal_add:.0f} ₽ списано")
                        if details:
                            st.caption(" · ".join(details))
                    
                    with cols[1]:
                        st.markdown(f"**{total:.0f}** ₽")
                    
                    with cols[2]:
                        edit_key = f"edit_{order_id}"
                        if st.button("✏️", key=edit_key, help="Редактировать"):
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
                        
                        if st.button("🗑", key=delete_key, help="Удалить"):
                            st.session_state.confirm_delete[confirm_key] = True
                            st.rerun()
                        
                        if st.session_state.confirm_delete.get(confirm_key, False):
                            st.markdown("Удалить?")
                            if st.button("✅ Да", key=f"yes_{order_id}"):
                                if beznal_add != 0:
                                    add_to_accumulated_beznal(-beznal_add)
                                delete_order_db(order_id)
                                log_action("Удаление заказа", f"Заказ #{i}, сумма {amount:.0f} ₽")
                                st.session_state.confirm_delete[confirm_key] = False
                                st.success(f"Заказ #{i} удалён.")
                                st.rerun()

                st.divider()

            # Итоги по смене
            st.subheader("💼 ИТОГИ СМЕНЫ")
            
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Наличные", f"{nal:.0f} ₽")
            col2.metric("Карта", f"{card:.0f} ₽")
            col3.metric("Чаевые", f"{tips_sum:.0f} ₽")
            col4.metric("Δ безнала", f"{beznal_this:.0f} ₽")
            
            total_day = nal + card + tips_sum
            st.markdown(f'<div class="stats-box" style="margin-top:1rem"><span class="stat-label">ВСЕГО ЗА СМЕНУ</span> <span class="stat-value">{total_day:.0f} ₽</span></div>', unsafe_allow_html=True)

        # ===== ФОРМА РЕДАКТИРОВАНИЯ =====
        if st.session_state.edit_order_id is not None:
            st.subheader("✏️ РЕДАКТИРОВАНИЕ ЗАКАЗА")
            order_id = st.session_state.edit_order_id
            orig_type = st.session_state.get("edit_original_type", "нал")
            orig_amount = st.session_state.get("edit_original_amount", 0.0)
            orig_tips = st.session_state.get("edit_original_tips", 0.0)

            with st.form("edit_order_form"):
                col1, col2 = st.columns(2)
                with col1:
                    new_amount_str = st.text_input(
                        "Новая сумма, ₽",
                        value=f"{orig_amount:.0f}",
                    )
                with col2:
                    payment_options = ["Наличные", "Карта"]
                    default_index = 0 if orig_type == "нал" else 1
                    new_payment = st.selectbox("Тип оплаты", payment_options, index=default_index)

                new_tips_str = st.text_input(
                    "Новые чаевые, ₽",
                    value=f"{orig_tips:.0f}",
                )

                col_btn1, col_btn2 = st.columns(2)
                with col_btn1:
                    save_btn = st.form_submit_button("💾 СОХРАНИТЬ", use_container_width=True)
                with col_btn2:
                    cancel_btn = st.form_submit_button("ОТМЕНА", use_container_width=True)

            if cancel_btn:
                st.session_state.edit_order_id = None
                st.rerun()

            if save_btn:
                try:
                    new_amount = float(new_amount_str.replace(",", "."))
                    new_tips = float(new_tips_str.replace(",", "."))
                except ValueError:
                    st.error("Введите числа корректно")
                    st.stop()

                if new_amount <= 0:
                    st.error("Сумма должна быть больше нуля")
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

                # Определяем новый тип
                new_type = "нал" if new_payment == "Наличные" else "карта"

                # Рассчитываем новые значения
                if new_type == "нал":
                    commission = new_amount * (1 - rate_nal)
                    total = new_amount + new_tips
                    new_beznal = -commission
                else:
                    final_wo_tips = new_amount * rate_card
                    commission = new_amount - final_wo_tips
                    total = final_wo_tips + new_tips
                    new_beznal = final_wo_tips

                # Обновляем накопленный безнал
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

                log_action("Редактирование заказа", f"Заказ #{order_id}, новая сумма {new_amount:.0f} ₽")
                st.success("✅ Изменения сохранены")
                st.session_state.edit_order_id = None
                st.rerun()

        # ===== ЗАКРЫТИЕ СМЕНЫ С АВТОМАТИЧЕСКИМ БЭКАПОМ =====
        st.write("---")
        with st.expander("🔒 ЗАКРЫТЬ СМЕНУ"):
            last_consumption, last_price = get_last_fuel_params()

            with st.form("close_form"):
                km = st.number_input("Километраж за смену (км)", min_value=0, step=10, value=100)

                col1, col2 = st.columns(2)
                with col1:
                    consumption = st.number_input(
                        "Расход, л/100км",
                        min_value=0.0,
                        step=0.5,
                        value=float(f"{last_consumption:.1f}"),
                        format="%.1f",
                    )
                with col2:
                    fuel_price = st.number_input(
                        "Цена бензина, ₽/л",
                        min_value=0.0,
                        step=1.0,
                        value=float(f"{last_price:.1f}"),
                        format="%.1f",
                    )

                if km > 0 and consumption > 0 and fuel_price > 0:
                    liters = (km / 100) * consumption
                    fuel_cost = liters * fuel_price
                    st.markdown(f'<div class="stats-box"><span class="stat-label">РАСХОД ТОПЛИВА</span> <span class="stat-value">{liters:.1f} л · {fuel_cost:.0f} ₽</span></div>', unsafe_allow_html=True)

                submitted_close = st.form_submit_button("🔒 ЗАКРЫТЬ СМЕНУ", use_container_width=True, type="primary")

            if submitted_close:
                if km > 0 and consumption > 0 and fuel_price > 0:
                    liters = (km / 100) * consumption
                    fuel_cost = liters * fuel_price
                else:
                    liters = 0.0
                    fuel_cost = 0.0

                close_shift_db(shift_id, km, liters, fuel_price)

                income = nal + card + tips_sum
                profit = income - fuel_cost

                # Создаём финальный бэкап при закрытии смены
                backup_path = create_auto_backup("shift_closed")

                log_action("Закрытие смены", f"Дата: {date_str}, доход: {income:.0f} ₽, прибыль: {profit:.0f} ₽")
                
                st.success("✅ Смена закрыта")
                
                col1, col2, col3 = st.columns(3)
                col1.metric("Доход", f"{income:.0f} ₽")
                col2.metric("Бензин", f"{fuel_cost:.0f} ₽")
                col3.metric("Прибыль", f"{profit:.0f} ₽")
                
                if backup_path:
                    st.info(f"📦 Создан авто-бэкап: {os.path.basename(backup_path)}")

# ===== UI / ЗАПУСК =====
st.set_page_config(page_title="Такси учёт", page_icon="🚕", layout="centered")
apply_strict_style()
init_auth_db()
ensure_users_dir()

# ----- ЛОГИН / РЕГИСТРАЦИЯ -----
if "username" not in st.session_state:
    st.title("🚕 ТАКСИ УЧЁТ — ВХОД")

    tab_login, tab_reg = st.tabs(["ВХОД", "РЕГИСТРАЦИЯ"])

    with tab_login:
        with st.form("login_form"):
            login_username = st.text_input("Имя пользователя")
            login_password = st.text_input("Пароль", type="password")
            login_btn = st.form_submit_button("ВОЙТИ", use_container_width=True)

        if login_btn:
            if not login_username or not login_password:
                st.error("Введите имя пользователя и пароль")
            elif authenticate_user(login_username, login_password):
                update_login_stats(login_username.strip())
                switch_user(login_username.strip())
                st.rerun()
            else:
                st.error("Неверное имя пользователя или пароль")

    with tab_reg:
        st.caption("Регистрация нового пользователя")
        with st.form("register_form"):
            reg_username = st.text_input("Имя пользователя")
            reg_password = st.text_input("Пароль", type="password")
            reg_password2 = st.text_input("Повтор пароля", type="password")
            reg_btn = st.form_submit_button("ЗАРЕГИСТРИРОВАТЬСЯ", use_container_width=True)

        if reg_btn:
            if not reg_username or not reg_password:
                st.error("Имя и пароль не могут быть пустыми")
            elif reg_password != reg_password2:
                st.error("Пароли не совпадают")
            elif len(reg_password) < 4:
                st.error("Пароль должен быть не менее 4 символов")
            else:
                if register_user(reg_username, reg_password):
                    st.success("✅ Пользователь создан. Теперь можно войти")
                    log_action("Регистрация", f"Новый пользователь {reg_username}")
                else:
                    st.error("❌ Такой пользователь уже существует")

    st.stop()

# ===== ПОСЛЕ ВХОДА =====
st.session_state["db_name"] = get_current_db_name()

# Устанавливаем страницу по умолчанию
if "page" not in st.session_state:
    st.session_state["page"] = "main"

# Информация в сайдбаре с навигацией (ТОЛЬКО РУССКИЕ НАЗВАНИЯ)
with st.sidebar:
    st.markdown(f'<div class="user-info"><strong>{st.session_state["username"]}</strong><br>Папка: {os.path.basename(st.session_state.get("user_dir", "unknown"))}</div>', unsafe_allow_html=True)
    
    st.markdown('<div class="nav-header">НАВИГАЦИЯ</div>', unsafe_allow_html=True)
    
    # Кнопки навигации с русскими названиями (СТРОГИЙ СТИЛЬ)
    if st.button("📋 ПРОГРАММА", use_container_width=True,
                 type="primary" if st.session_state["page"] == "main" else "secondary"):
        st.session_state["page"] = "main"
        st.rerun()
    
    if st.button("📊 ОТЧЁТЫ", use_container_width=True,
                 type="primary" if st.session_state["page"] == "reports" else "secondary"):
        st.session_state["page"] = "reports"
        st.rerun()
    
    if st.button("⚙️ АДМИНКА", use_container_width=True,
                 type="primary" if st.session_state["page"] == "admin" else "secondary"):
        st.session_state["page"] = "admin"
        st.rerun()
    
    st.markdown("---")
    
    # Информация о бэкапах
    backup_dir = get_backup_dir()
    if os.path.exists(backup_dir):
        backups = [f for f in os.listdir(backup_dir) if f.endswith('.db')]
        st.markdown(f'<div class="stats-box"><span class="stat-label">БЭКАПОВ</span> <span class="stat-value">{len(backups)}</span></div>', unsafe_allow_html=True)
    
    if st.button("🚪 ВЫЙТИ", use_container_width=True):
        # Создаём бэкап при выходе
        backup_path = create_auto_backup("logout")
        log_action("Выход", f"Пользователь {st.session_state['username']}")
        st.session_state.clear()
        st.rerun()
    
    st.markdown('<div class="footer-info">ТАКСИ УЧЁТ v2.0<br>СТРОГИЙ СТИЛЬ</div>', unsafe_allow_html=True)

# Отображаем выбранную страницу
if st.session_state["page"] == "main":
    show_main_page()
elif st.session_state["page"] == "reports":
    # Импортируем и показываем страницу отчётов
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location("reports_module", "Reports.py")
        reports_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(reports_module)
        
        # Заменяем st на текущий st
        reports_module.st = st
        
        # Вызываем основную функцию отчётов
        if hasattr(reports_module, 'main'):
            reports_module.main()
        else:
            st.warning("Функция main не найдена в Reports.py")
    except Exception as e:
        st.error(f"Ошибка загрузки отчётов: {e}")
        st.info("Убедитесь, что файл Reports.py существует")
elif st.session_state["page"] == "admin":
    # Импортируем и показываем страницу админки
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location("admin_module", "Admin.py")
        admin_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(admin_module)
        
        # Заменяем st на текущий st
        admin_module.st = st
        
        # Вызываем основную функцию админки
        if hasattr(admin_module, 'main'):
            admin_module.main()
        else:
            st.warning("Функция main не найдена в Admin.py")
    except Exception as e:
        st.error(f"Ошибка загрузки админки: {e}")
        st.info("Убедитесь, что файл Admin.py существует")