import streamlit as st
import sqlite3
from datetime import datetime, date, timezone, timedelta
import hashlib
import os
import pandas as pd
import shutil
import io
import json
from pathlib import Path
from collections import Counter

# ===== НАСТРОЙКИ =====
AUTH_DB = "users.db"  # база с пользователями (логин/пароль)
USERS_DIR = "users"    # папка для хранения данных пользователей
SESSION_FILE = "session.json"  # файл для хранения сессии
SESSION_TIMEOUT = 30 * 24 * 60 * 60  # 30 дней в секундах

rate_nal = 0.78   # процент для нала (для расчёта комиссии)
rate_card = 0.75  # процент для карты

# Популярные затраты для быстрого выбора
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
    "💊 Аптека"
]

# Московский часовой пояс
MOSCOW_TZ = timezone(timedelta(hours=3))

# ===== УПРАВЛЕНИЕ СЕССИЕЙ НА ДИСКЕ =====
def save_session_to_disk():
    """Сохраняет данные сессии на диск"""
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
        print(f"Ошибка при сохранении сессии: {e}")

def load_session_from_disk():
    """Загружает данные сессии с диска"""
    try:
        if os.path.exists(SESSION_FILE):
            with open(SESSION_FILE, 'r', encoding='utf-8') as f:
                session_data = json.load(f)
            
            # Проверяем, не истекла ли сессия
            if session_data.get("session_start"):
                session_start = datetime.fromisoformat(session_data["session_start"])
                time_elapsed = (datetime.now(MOSCOW_TZ) - session_start).total_seconds()
                
                if time_elapsed < SESSION_TIMEOUT:
                    return session_data.get("username")
    except Exception as e:
        print(f"Ошибка при загрузке сессии: {e}")
    return None

def clear_session_disk():
    """Удаляет файл сессии"""
    try:
        if os.path.exists(SESSION_FILE):
            os.remove(SESSION_FILE)
    except Exception as e:
        print(f"Ошибка при удалении сессии: {e}")

# ===== МОБИЛЬНАЯ ОПТИМИЗАЦИЯ / CSS =====
def apply_mobile_optimized_css():
    st.markdown(
        """
        <style>
        /* ПОЛНОСТЬЮ СКРЫВАЕМ АВТОМАТИЧЕСКУЮ НАВИГАЦИЮ STREAMLIT */
        section[data-testid="stSidebarNav"] {
            display: none !important;
        }
        
        /* Дополнительные селекторы для скрытия */
        .st-emotion-cache-1gv3huu, 
        .st-emotion-cache-1jzia57, 
        .st-emotion-cache-1wsixal,
        div[data-testid="stSidebarNav"] {
            display: none !important;
        }
        
        /* МОБИЛЬНАЯ ОПТИМИЗАЦИЯ */
        
        /* Убираем отступы */
        * {
            box-sizing: border-box;
        }
        
        .main > div {
            padding-left: 0.5rem !important;
            padding-right: 0.5rem !important;
        }
        
        /* Крупный ник пользователя с иконкой */
        .user-info {
            display: flex;
            align-items: center;
            gap: 15px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            padding: 20px 15px;
            border-radius: 20px;
            margin-bottom: 20px;
            box-shadow: 0 6px 12px rgba(0,0,0,0.15);
            border: 1px solid rgba(255,255,255,0.2);
        }
        
        .user-avatar {
            font-size: 3.2rem !important;
            background: white;
            width: 80px;
            height: 80px;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            box-shadow: 0 4px 8px rgba(0,0,0,0.3);
            border: 3px solid #fff;
        }
        
        .user-name {
            font-size: 2.2rem !important;
            font-weight: bold;
            color: white;
            text-shadow: 2px 2px 4px rgba(0,0,0,0.3);
            line-height: 1.2;
            letter-spacing: 0.5px;
        }
        
        .user-name small {
            font-size: 1rem;
            display: block;
            color: rgba(255,255,255,0.9);
            font-weight: normal;
            margin-top: 5px;
            text-shadow: 1px 1px 2px rgba(0,0,0,0.2);
        }
        
        /* Компактные заголовки для мобильных */
        h1 {
            font-size: 1.4rem !important;
            margin-top: 0.5rem !important;
            margin-bottom: 0.5rem !important;
            padding: 0 !important;
            text-align: center;
        }
        
        h2 {
            font-size: 1.2rem !important;
            margin-top: 0.5rem !important;
            margin-bottom: 0.3rem !important;
        }
        
        h3 {
            font-size: 1.1rem !important;
            margin-top: 0.3rem !important;
            margin-bottom: 0.2rem !important;
        }
        
        /* Компактные метрики для мобильных */
        .stMetric {
            padding: 0.3rem !important;
            margin: 0.1rem 0 !important;
        }
        
        .stMetric label {
            font-size: 0.7rem !important;
        }
        
        .stMetric [data-testid="stMetricValue"] {
            font-size: 1.1rem !important;
        }
        
        /* Уменьшаем отступы в контейнерах */
        .block-container {
            padding-top: 0.5rem !important;
            padding-bottom: 0.5rem !important;
            max-width: 100% !important;
        }
        
        /* Компактные кнопки */
        .stButton > button {
            padding: 0.3rem 0.5rem !important;
            font-size: 0.85rem !important;
            margin: 0.1rem 0 !important;
            min-height: 2.2rem;
        }
        
        /* Компактные поля ввода */
        .stTextInput > div > div > input {
            padding: 0.3rem !important;
            font-size: 0.9rem !important;
            min-height: 2.2rem;
        }
        
        .stNumberInput > div > div > input {
            padding: 0.3rem !important;
            font-size: 0.9rem !important;
            min-height: 2.2rem;
        }
        
        .stSelectbox > div > div {
            min-height: 2.2rem;
            font-size: 0.9rem !important;
        }
        
        /* Компактные экспандеры */
        .stExpander {
            margin: 0.2rem 0 !important;
        }
        
        .stExpander > details > summary {
            padding: 0.4rem !important;
            font-size: 0.95rem !important;
        }
        
        /* Компактные разделители */
        hr {
            margin: 0.5rem 0 !important;
        }
        
        /* Улучшаем сайдбар для мобильных */
        section[data-testid="stSidebar"] {
            width: 300px !important;
        }
        
        section[data-testid="stSidebar"] > div {
            padding: 0.5rem !important;
        }
        
        section[data-testid="stSidebar"] .stButton > button {
            padding: 0.7rem !important;
            font-size: 1rem !important;
            font-weight: 500;
        }
        
        /* Компактные информационные блоки */
        .stAlert {
            padding: 0.4rem !important;
            margin: 0.2rem 0 !important;
            font-size: 0.85rem !important;
        }
        
        /* Компактные таблицы */
        .stDataFrame {
            font-size: 0.8rem !important;
        }
        
        .stDataFrame td, .stDataFrame th {
            padding: 0.2rem !important;
        }
        
        /* Компактные вкладки */
        .stTabs [data-baseweb="tab"] {
            padding: 0.3rem 0.5rem !important;
            font-size: 0.8rem !important;
        }
        
        /* Кастомные классы для мобильных */
        .stats-box {
            padding: 0.4rem !important;
            margin: 0.2rem 0 !important;
            font-size: 0.9rem !important;
        }
        
        .stat-value {
            font-size: 1rem !important;
        }
        
        .stat-label {
            font-size: 0.65rem !important;
        }
        
        .warning-box {
            padding: 0.3rem !important;
            font-size: 0.8rem !important;
        }
        
        .success-box {
            padding: 0.3rem !important;
            font-size: 0.8rem !important;
        }
        
        .session-timer {
            font-size: 0.7rem !important;
            padding: 0.2rem !important;
        }
        
        /* Улучшаем отображение списка заказов */
        div[data-testid="stVerticalBlock"] > div > div > div > div[data-testid="stVerticalBlock"] {
            padding: 0.3rem !important;
            margin: 0.1rem 0 !important;
        }
        
        /* Компактные колонки */
        .row-widget.stHorizontal {
            gap: 0.2rem !important;
        }
        
        /* Убираем лишние отступы */
        .stMarkdown {
            margin-bottom: 0.2rem !important;
        }
        
        /* Компактные чекбоксы */
        .stCheckbox {
            min-height: 1.5rem;
        }
        
        .stCheckbox > div {
            font-size: 0.85rem !important;
        }
        
        /* Компактные загрузчики файлов */
        .stFileUploader {
            padding: 0.3rem !important;
        }
        
        /* Компактный таймер */
        .session-timer {
            font-size: 0.7rem !important;
            margin-top: 0.3rem !important;
            padding: 0.2rem !important;
        }
        
        /* Стили для популярных затрат */
        .popular-expense-btn {
            margin: 0.1rem !important;
        }
        
        /* Скрываем лишние элементы на мобильных */
        @media (max-width: 640px) {
            div[data-testid="column"] {
                min-width: auto !important;
            }
            
            /* Делаем колонки более гибкими */
            .row-widget.stHorizontal {
                flex-wrap: wrap !important;
            }
            
            .row-widget.stHorizontal > div {
                flex: 1 1 auto !important;
                min-width: 120px !important;
            }
            
            .user-name {
                font-size: 1.8rem !important;
            }
            
            .user-avatar {
                width: 60px;
                height: 60px;
                font-size: 2.5rem !important;
            }
        }
        
        /* Улучшаем touch-взаимодействие */
        button, input, select {
            touch-action: manipulation !important;
        }
        
        /* Увеличиваем область нажатия для маленьких кнопок */
        .stButton > button {
            min-width: 44px !important;
        }
        
        /* Компактные метрики в итогах */
        div[data-testid="metric-container"] {
            padding: 0.2rem !important;
        }
        
        /* Стили для статистики расходов */
        .expense-stat {
            background-color: #fee2e2;
            padding: 0.3rem;
            border-radius: 0.3rem;
            margin: 0.2rem 0;
            border-left: 3px solid #ef4444;
        }
        
        /* Стили для метрик в сайдбаре */
        .sidebar-metric {
            background: white;
            padding: 10px;
            border-radius: 12px;
            margin: 10px 0;
            box-shadow: 0 2px 4px rgba(0,0,0,0.05);
            text-align: center;
        }
        
        .sidebar-metric .label {
            font-size: 0.8rem;
            color: #64748b;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }
        
        .sidebar-metric .value {
            font-size: 1.4rem;
            font-weight: bold;
            color: #1e293b;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

# ===== УПРАВЛЕНИЕ СЕССИЕЙ =====
def init_session():
    """Инициализирует сессию пользователя с таймером"""
    if "session_start" not in st.session_state:
        st.session_state.session_start = datetime.now(MOSCOW_TZ)
        st.session_state.last_activity = datetime.now(MOSCOW_TZ)
        # Сохраняем на диск при инициализации
        save_session_to_disk()
    
    # Обновляем время последней активности
    st.session_state.last_activity = datetime.now(MOSCOW_TZ)
    # Сохраняем на диск при активности
    save_session_to_disk()
    
    # Проверяем, не истекла ли сессия
    time_elapsed = (datetime.now(MOSCOW_TZ) - st.session_state.session_start).total_seconds()
    if time_elapsed > SESSION_TIMEOUT:
        # Сессия истекла, выходим
        st.session_state.clear()
        clear_session_disk()
        st.warning("⏰ Сессия истекла. Пожалуйста, войдите снова.")
        st.rerun()

def get_session_time_remaining() -> str:
    """Возвращает оставшееся время сессии в формате Д:Ч:М:С"""
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
    else:
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

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

def add_column_if_not_exists(cursor, table_name, column_name, column_type):
    """Добавляет колонку в таблицу, если она не существует"""
    try:
        cursor.execute(f"SELECT {column_name} FROM {table_name} LIMIT 1")
    except sqlite3.OperationalError:
        try:
            cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}")
            print(f"Добавлена колонка {column_name} в таблицу {table_name}")
            return True
        except Exception as e:
            print(f"Ошибка при добавлении колонки {column_name}: {e}")
    return False

def check_and_create_tables():
    """Проверяет и создаёт все необходимые таблицы в базе данных"""
    try:
        conn = sqlite3.connect(get_current_db_name())
        cursor = conn.cursor()
        
        # Создаём таблицу shifts если её нет
        cursor.execute("""
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
        """)
        
        # Создаём таблицу для дополнительных расходов
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS extra_expenses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                shift_id INTEGER,
                amount REAL DEFAULT 0,
                description TEXT,
                created_at TEXT,
                FOREIGN KEY (shift_id) REFERENCES shifts (id)
            )
        """)
        
        # Создаём таблицу orders
        cursor.execute("""
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
        """)
        
        # Добавляем колонку order_time, если её нет
        add_column_if_not_exists(cursor, "orders", "order_time", "TEXT")
        
        # Создаём таблицу accumulated_beznal
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS accumulated_beznal (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                driver_id INTEGER DEFAULT 1,
                total_amount REAL DEFAULT 0,
                last_updated TEXT
            )
        """)
        
        # Добавляем начальную запись в accumulated_beznal
        cursor.execute("SELECT id FROM accumulated_beznal WHERE driver_id = 1")
        if not cursor.fetchone():
            cursor.execute(
                "INSERT INTO accumulated_beznal (driver_id, total_amount, last_updated) "
                "VALUES (1, 0, ?)",
                (datetime.now(MOSCOW_TZ).strftime("%Y-%m-%d %H:%M:%S"),),
            )
        
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"Ошибка при создании таблиц: {e}")
        return False

# ===== АВТОРИЗАЦИЯ (users.db) =====
def get_auth_conn():
    return sqlite3.connect(AUTH_DB)

def init_auth_db():
    """Инициализирует таблицу пользователей с правильной структурой"""
    conn = get_auth_conn()
    cur = conn.cursor()
    
    # Создаём таблицу с правильной структурой
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
    
    # Проверяем и добавляем недостающие колонки
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
                None,  # last_login пока пустой
                0,     # total_logins начинается с 0
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
            print(f"Удалён старый файл базы: {db_path}")
        
        # Создаём новую базу с нуля
        init_user_db(db_path)
        
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
    """Обновляет статистику входа пользователя."""
    conn = get_auth_conn()
    cur = conn.cursor()
    now = datetime.now(MOSCOW_TZ).strftime("%Y-%m-%d %H:%M:%S")
    
    try:
        # Проверяем существование колонок
        cur.execute("PRAGMA table_info(users)")
        columns = [column[1] for column in cur.fetchall()]
        
        if 'last_login' in columns and 'total_logins' in columns:
            cur.execute(
                """
                UPDATE users 
                SET last_login = ?, total_logins = total_logins + 1 
                WHERE username = ?
                """,
                (now, username),
            )
        else:
            # Если колонок нет, просто логируем в консоль
            print(f"Вход пользователя {username} в {now} (статистика не сохранена)")
    except Exception as e:
        print(f"Ошибка при обновлении статистики: {e}")
    finally:
        conn.commit()
        conn.close()

def get_all_users() -> list:
    """Возвращает список всех пользователей."""
    conn = get_auth_conn()
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT 
                username, 
                COALESCE(created_at, 'неизвестно') as created_at,
                COALESCE(last_login, 'никогда') as last_login,
                COALESCE(total_logins, 0) as total_logins 
            FROM users 
            ORDER BY username
        """)
        rows = cur.fetchall()
    except:
        # Если структура таблицы старая, возвращаем базовую информацию
        cur.execute("SELECT username, created_at FROM users ORDER BY username")
        rows = [(row[0], row[1], 'неизвестно', 0) for row in cur.fetchall()]
    finally:
        conn.close()
    return rows

# ===== ФУНКЦИИ БД ДЛЯ СМЕН И ЗАКАЗОВ =====
def get_db_connection():
    conn = sqlite3.connect(get_current_db_name())
    # Проверяем и создаём таблицы при каждом подключении
    check_and_create_tables()
    return conn

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
        print(f"Удалён существующий файл для новой базы: {db_path}")
    
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
        CREATE TABLE IF NOT EXISTS extra_expenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            shift_id INTEGER,
            amount REAL DEFAULT 0,
            description TEXT,
            created_at TEXT,
            FOREIGN KEY (shift_id) REFERENCES shifts (id)
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
    print(f"Создана новая база данных: {db_path}")

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

def add_extra_expense(shift_id: int, amount: float, description: str):
    """Добавляет дополнительный расход для смены"""
    conn = get_db_connection()
    cursor = conn.cursor()
    now = datetime.now(MOSCOW_TZ).strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute(
        """
        INSERT INTO extra_expenses (shift_id, amount, description, created_at)
        VALUES (?, ?, ?, ?)
        """,
        (shift_id, amount, description, now),
    )
    conn.commit()
    conn.close()

def get_extra_expenses(shift_id: int) -> list:
    """Получает все дополнительные расходы для смены"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT id, amount, description, created_at
        FROM extra_expenses
        WHERE shift_id = ?
        ORDER BY id
        """,
        (shift_id,),
    )
    rows = cursor.fetchall()
    conn.close()
    
    expenses = []
    for row in rows:
        expenses.append({
            'id': row[0],
            'amount': row[1] or 0.0,
            'description': row[2] or '',
            'created_at': row[3] or ''
        })
    return expenses

def delete_extra_expense(expense_id: int):
    """Удаляет дополнительный расход"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM extra_expenses WHERE id = ?", (expense_id,))
    conn.commit()
    conn.close()

def get_total_extra_expenses(shift_id: int) -> float:
    """Получает общую сумму дополнительных расходов для смены"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT SUM(amount) FROM extra_expenses WHERE shift_id = ?",
        (shift_id,),
    )
    row = cursor.fetchone()
    conn.close()
    return row[0] or 0.0

def get_all_extra_expenses_stats() -> dict:
    """Получает статистику по всем дополнительным расходам"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT description, SUM(amount), COUNT(*)
        FROM extra_expenses
        GROUP BY description
        ORDER BY SUM(amount) DESC
        """
    )
    rows = cursor.fetchall()
    conn.close()
    
    stats = []
    for row in rows:
        stats.append({
            'description': row[0],
            'total': row[1] or 0,
            'count': row[2]
        })
    return stats

def get_month_extra_expenses(year_month: str) -> float:
    """Получает общую сумму дополнительных расходов за месяц"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT SUM(e.amount)
        FROM extra_expenses e
        JOIN shifts s ON e.shift_id = s.id
        WHERE strftime('%Y-%m', s.date) = ?
        """,
        (year_month,),
    )
    row = cursor.fetchone()
    conn.close()
    return row[0] or 0.0

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
        ORDER BY id DESC
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

def set_accumulated_beznal(amount: float):
    """Устанавливает новое значение накопленного безнала"""
    conn = get_db_connection()
    cursor = conn.cursor()
    now = datetime.now(MOSCOW_TZ).strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute(
        """
        UPDATE accumulated_beznal
        SET total_amount = ?, last_updated = ?
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

# ===== ФУНКЦИИ ДЛЯ БЭКАПОВ =====
def create_backup() -> str:
    """Создаёт бэкап базы данных в папке пользователя."""
    backup_dir = get_backup_dir()
    timestamp = datetime.now(MOSCOW_TZ).strftime("%Y%m%d_%H%M%S")
    username = st.session_state.get("username", "unknown")
    backup_name = f"taxi_{username}_backup_{timestamp}.db"
    backup_path = os.path.join(backup_dir, backup_name)
    
    # Копируем текущую базу
    shutil.copy2(get_current_db_name(), backup_path)
    
    # Ограничиваем количество бэкапов (оставляем последние 20)
    backups = [f for f in os.listdir(backup_dir) if f.endswith('.db')]
    backups.sort(reverse=True)
    for old_backup in backups[20:]:
        try:
            os.remove(os.path.join(backup_dir, old_backup))
        except:
            pass
    
    return backup_path

def list_backups() -> list:
    """Возвращает список всех бэкапов пользователя."""
    backup_dir = get_backup_dir()
    if not os.path.exists(backup_dir):
        return []
    
    backups = []
    for f in os.listdir(backup_dir):
        if f.endswith('.db'):
            file_path = os.path.join(backup_dir, f)
            file_time = datetime.fromtimestamp(os.path.getmtime(file_path))
            file_size = os.path.getsize(file_path) / 1024  # в KB
            backups.append({
                'name': f,
                'path': file_path,
                'time': file_time,
                'size': file_size
            })
    
    # Сортируем по времени (новые сверху)
    backups.sort(key=lambda x: x['time'], reverse=True)
    return backups

def restore_from_backup(backup_path: str):
    """Восстанавливает базу данных из бэкапа."""
    if not os.path.exists(backup_path):
        raise FileNotFoundError(f"Файл бэкапа не найден: {backup_path}")
    
    # Сначала создаём бэкап текущей базы
    create_backup()
    
    # Затем восстанавливаем выбранный бэкап
    shutil.copy2(backup_path, get_current_db_name())

def download_backup(backup_path: str) -> bytes:
    """Подготавливает файл бэкапа для скачивания."""
    with open(backup_path, 'rb') as f:
        return f.read()

def upload_and_restore_backup(uploaded_file):
    """Загружает бэкап с диска и восстанавливает."""
    if uploaded_file is not None:
        # Создаём временный файл
        temp_path = os.path.join(get_backup_dir(), "temp_restore.db")
        with open(temp_path, 'wb') as f:
            f.write(uploaded_file.getbuffer())
        
        # Восстанавливаем из временного файла
        restore_from_backup(temp_path)
        
        # Удаляем временный файл
        try:
            os.remove(temp_path)
        except:
            pass
        
        return True
    return False

# ===== ФУНКЦИИ ДЛЯ СТРАНИЦ =====
def show_main_page():
    """Отображает главную страницу с учётом смен"""
    st.title(f"🚕 {st.session_state['username']}")

    # для редактирования заказов
    if "edit_order_id" not in st.session_state:
        st.session_state.edit_order_id = None
        
    # для подтверждения удаления
    if "confirm_delete" not in st.session_state:
        st.session_state.confirm_delete = {}

    open_shift_data = get_open_shift()

    if not open_shift_data:
        st.info("📭 Нет открытой смены")

        with st.expander("📝 ОТКРЫТЬ СМЕНУ", expanded=True):
            with st.form("open_shift_form"):
                date_input = st.date_input(
                    "Дата",
                    value=date.today(),
                )
                st.caption(f"{date_input.strftime('%d.%m.%Y')}")
                submitted_tpl = st.form_submit_button("📂 ОТКРЫТЬ", width='stretch')

            if submitted_tpl:
                date_str_db = date_input.strftime("%Y-%m-%d")
                open_shift(date_str_db)
                date_str_show = date_input.strftime("%d.%m.%Y")
                log_action("Открытие смены", f"Дата: {date_str_db}")
                st.success(f"✅ Смена открыта: {date_str_show}")
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

        # ===== ДОБАВЛЕНИЕ ЗАКАЗА =====
        with st.expander("➕ ЗАКАЗ", expanded=True):
            # Используем счётчики для создания уникальных ключей
            if "amount_counter" not in st.session_state:
                st.session_state.amount_counter = 0
            if "tips_counter" not in st.session_state:
                st.session_state.tips_counter = 0
            
            # Создаём уникальные ключи для полей
            amount_key = f"amount_{st.session_state.amount_counter}"
            tips_key = f"tips_{st.session_state.tips_counter}"
            
            with st.form("order_form"):
                c1, c2 = st.columns(2)
                with c1:
                    amount_str = st.text_input(
                        "Сумма",
                        value="",
                        placeholder="650",
                        key=amount_key
                    )
                with c2:
                    payment = st.selectbox(
                        "Тип", 
                        ["НАЛ", "КАРТА"],
                        key="payment_input"
                    )

                tips_str = st.text_input(
                    "Чаевые",
                    value="",
                    placeholder="0",
                    key=tips_key
                )

                now_moscow = datetime.now(MOSCOW_TZ)
                st.caption(f"🕒 {now_moscow.strftime('%H:%M')}")

                submitted = st.form_submit_button("💾 СОХРАНИТЬ", width='stretch')

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
                    log_action("Добавление заказа", f"{human_type}, {amount:.0f} ₽, чаевые {tips:.0f} ₽")
                    
                    # Увеличиваем счётчики для создания новых ключей
                    st.session_state.amount_counter += 1
                    st.session_state.tips_counter += 1
                    
                    st.success(f"✅ {human_type} {amount:.0f}₽")
                    st.rerun()
                except Exception as e:
                    st.error(f"Ошибка: {e}")

        # ===== СПИСОК ЗАКАЗОВ =====
        orders = get_shift_orders(shift_id)
        totals = get_shift_totals(shift_id) if orders else {}
        nal = totals.get("нал", 0.0)
        card = totals.get("карта", 0.0)
        tips_sum = totals.get("чаевые", 0.0)
        beznal_this = totals.get("безнал_смена", 0.0)

        if orders:
            st.subheader("📋 ЗАКАЗЫ")

            for i, (order_id, typ, amount, tips, comm, total, beznal_add, order_time) in enumerate(
                orders, 1
            ):
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
                        if st.button("✏️", key=edit_key):
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
                        
                        if st.button("🗑", key=delete_key):
                            st.session_state.confirm_delete[confirm_key] = True
                            st.rerun()
                        
                        if st.session_state.confirm_delete.get(confirm_key, False):
                            st.caption("Удалить?")
                            if st.button("✅", key=f"yes_{order_id}"):
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
            total_extra = sum(e['amount'] for e in extra_expenses)
            
            cols = st.columns(4)
            cols[0].metric("Нал", f"{nal:.0f}₽")
            cols[1].metric("Карта", f"{card:.0f}₽")
            cols[2].metric("Чаевые", f"{tips_sum:.0f}₽")
            cols[3].metric("Δ безнал", f"{beznal_this:.0f}₽")

            total_income = nal + card + tips_sum
            st.metric("ДОХОД", f"{total_income:.0f}₽")
            if total_extra > 0:
                st.metric("РАСХОДЫ", f"{total_extra:.0f}₽", delta=f"Чистые: {total_income - total_extra:.0f}₽")

        # ===== РЕДАКТИРОВАНИЕ =====
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
                        "Новая сумма",
                        value=f"{orig_amount:.0f}",
                    )
                with col2:
                    options = ["НАЛ", "КАРТА"]
                    idx = 0 if orig_type == "нал" else 1
                    new_payment = st.selectbox("Тип", options, index=idx)

                new_tips_str = st.text_input(
                    "Новые чаевые",
                    value=f"{orig_tips:.0f}",
                )

                col_btn1, col_btn2 = st.columns(2)
                with col_btn1:
                    save_btn = st.form_submit_button("💾 СОХР", width='stretch')
                with col_btn2:
                    cancel_btn = st.form_submit_button("❌", width='stretch')

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

        # ===== ДОПОЛНИТЕЛЬНЫЕ РАСХОДЫ =====
        st.write("---")
        with st.expander("💸 РАСХОДЫ", expanded=False):
            st.caption("Мойка, еда и т.д.")
            
            # Популярные затраты в виде выпадающего списка
            st.subheader("📋 Быстрый выбор")
            
            # Единая форма с выбором из списка
            with st.form("quick_expense_form"):
                col1, col2, col3 = st.columns([2, 1, 1])
                with col1:
                    expense_desc = st.selectbox(
                        "Что",
                        options=[""] + POPULAR_EXPENSES,
                        format_func=lambda x: "Выберите расход..." if x == "" else x,
                        key="quick_expense_desc"
                    )
                with col2:
                    expense_amount = st.number_input(
                        "Сумма",
                        min_value=0.0,
                        step=50.0,
                        value=100.0,
                        format="%.0f",
                        key="quick_expense_amount"
                    )
                with col3:
                    submitted = st.form_submit_button("➕", use_container_width=True)
                
                if submitted and expense_desc and expense_desc != "" and expense_amount > 0:
                    add_extra_expense(shift_id, expense_amount, expense_desc)
                    log_action("Добавление расхода", f"{expense_desc}: {expense_amount:.0f} ₽")
                    st.success(f"✅ Добавлено")
                    st.rerun()
            
            st.divider()
            
            # Ручной ввод
            with st.form("manual_expense_form"):
                st.subheader("✏️ Свой вариант")
                col1, col2, col3 = st.columns([2, 1, 1])
                with col1:
                    manual_desc = st.text_input("Что", placeholder="мойка", key="manual_desc")
                with col2:
                    manual_amount = st.number_input("Сумма", min_value=0.0, step=50.0, format="%.0f", key="manual_amount")
                with col3:
                    manual_submit = st.form_submit_button("➕", use_container_width=True)
                
                if manual_submit and manual_desc and manual_amount > 0:
                    add_extra_expense(shift_id, manual_amount, manual_desc)
                    log_action("Добавление расхода", f"{manual_desc}: {manual_amount:.0f} ₽")
                    st.success(f"✅ Добавлено")
                    st.rerun()
            
            # Список текущих расходов
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
                        if st.button("🗑", key=f"del_exp_{exp['id']}"):
                            delete_extra_expense(exp['id'])
                            log_action("Удаление расхода", f"{exp['description']}")
                            st.rerun()
                    total_extra += exp['amount']
                    st.divider()
                
                st.markdown(f"**ИТОГО: {total_extra:.0f}₽**")

        # ===== ЗАКРЫТИЕ СМЕНЫ =====
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

                submitted_close = st.form_submit_button("🔒 ЗАКРЫТЬ", width='stretch', type="primary")

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

                log_action("Закрытие смены", 
                          f"Дата: {date_str}, доход: {income:.0f} ₽, прибыль: {profit:.0f} ₽")
                
                st.success("✅ Смена закрыта")
                
                cols = st.columns(3)
                cols[0].metric("Доход", f"{income:.0f}₽")
                cols[1].metric("Расходы", f"{total_costs:.0f}₽")
                cols[2].metric("Прибыль", f"{profit:.0f}₽")
                
                st.cache_data.clear()

def show_reports_page():
    """Отображает страницу отчётов"""
    if not check_and_create_tables():
        st.error("❌ Ошибка БД")
        return
    
    st.title(f"📊 ОТЧЁТЫ")
    
    try:
        import sys
        sys.path.append(os.path.dirname(__file__))
        
        from pages_imports import (
            get_available_year_months_cached,
            get_month_totals_cached,
            get_month_shifts_details_cached,
            get_closed_shift_id_by_date,
            get_shift_orders_df,
            get_orders_by_hour,
            format_month_option
        )
        
        year_months = get_available_year_months_cached()
        
        if not year_months:
            st.info("📭 Нет закрытых смен")
            
            with st.expander("📋 Пример"):
                example_data = pd.DataFrame({
                    "Дата": ["01.02.2026", "02.02.2026"],
                    "Тип": ["нал", "карта"],
                    "Сумма": [1500, 2000],
                    "Чаевые": [100, 0]
                })
                st.dataframe(example_data, width='stretch')
            return
        
        ym = st.selectbox(
            "📅 Месяц",
            year_months,
            format_func=format_month_option,
            index=0,
        )
        
        df_shifts = get_month_shifts_details_cached(ym)
        totals = get_month_totals_cached(ym)
        month_extra = get_month_extra_expenses(ym)
        
        # Рассчитываем расходы на бензин за месяц
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
                selected_date = datetime.strptime(selected, "%d.%m.%Y").strftime("%Y-%m-%d")
            except:
                selected_date = selected
            
            df_summary = df_shifts[df_shifts["Дата"] == selected].copy()
            if not df_summary.empty:
                st.dataframe(
                    df_summary.style.format({
                        "Нал": "{:.0f} ₽",
                        "Карта": "{:.0f} ₽",
                        "Чаевые": "{:.0f} ₽",
                        "Δ безнал": "{:.0f} ₽",
                        "Км": "{:.0f} км",
                        "Литры": "{:.1f} л",
                        "Цена": "{:.1f} ₽/л",
                        "Всего": "{:.0f} ₽",
                    }),
                    width='stretch'
                )
                
                # Расчёт расходов для выбранной смены
                row = df_summary.iloc[0]
                fuel_cost = float(row["Литры"] * row["Цена"])
                shift_id = get_closed_shift_id_by_date(selected_date)
                extra = get_extra_expenses(shift_id) if shift_id else []
                extra_sum = sum(e['amount'] for e in extra)
                income = float(row["Всего"])
                
                col1, col2, col3 = st.columns(3)
                col1.metric("💰 Доход", f"{income:.0f} ₽")
                col2.metric("⛽ Бензин", f"{fuel_cost:.0f} ₽")
                col3.metric("💸 Прочие расходы", f"{extra_sum:.0f} ₽")
                
                total_costs = fuel_cost + extra_sum
                profit = income - total_costs
                
                st.metric("📈 Чистая прибыль", f"{profit:.0f} ₽", 
                         delta=f"{profit/income*100:.1f}%" if income > 0 else None)
            
            shift_id = get_closed_shift_id_by_date(selected_date)
            if shift_id:
                df_orders = get_shift_orders_df(shift_id)
                if not df_orders.empty:
                    st.subheader("📋 ЗАКАЗЫ В СМЕНЕ")
                    st.dataframe(
                        df_orders.style.format({
                            "Сумма": "{:.0f} ₽",
                            "Чаевые": "{:.0f} ₽",
                            "Δ безнал": "{:.0f} ₽",
                            "Вам": "{:.0f} ₽",
                        }),
                        width='stretch'
                    )
                
                extra_expenses = get_extra_expenses(shift_id)
                if extra_expenses:
                    st.subheader("💸 ДОПОЛНИТЕЛЬНЫЕ РАСХОДЫ")
                    exp_df = pd.DataFrame(extra_expenses)
                    st.dataframe(
                        exp_df[['description', 'amount']].rename(
                            columns={'description': 'Описание', 'amount': 'Сумма'}
                        ).style.format({"Сумма": "{:.0f} ₽"}),
                        width='stretch'
                    )
                    st.caption(f"💰 Всего доп. расходов: {sum(e['amount'] for e in extra_expenses):.0f} ₽")
            
            df_hours = get_orders_by_hour(selected_date)
            if not df_hours.empty:
                st.subheader("📊 ЗАКАЗЫ ПО ЧАСАМ")
                st.bar_chart(data=df_hours, x="Час", y="Заказов")
        
        st.write("---")
        st.subheader("📊 ИТОГИ ЗА МЕСЯЦ")
        
        col1, col2, col3 = st.columns(3)
        col1.metric("💵 Наличные", f"{totals.get('нал', 0):.0f} ₽")
        col2.metric("💳 Карта", f"{totals.get('карта', 0):.0f} ₽")
        col3.metric("💝 Чаевые", f"{totals.get('чаевые', 0):.0f} ₽")
        
        total_income = totals.get('всего', 0)
        
        col4, col5, col6 = st.columns(3)
        col4.metric("📊 Изменение безнала", f"{totals.get('безнал_добавлено', 0):.0f} ₽")
        col5.metric("📆 Количество смен", f"{totals.get('смен', 0)}")
        col6.metric("💰 ВСЕГО ДОХОД", f"{total_income:.0f} ₽")
        
        st.write("---")
        st.subheader("💰 ФИНАНСОВЫЙ РЕЗУЛЬТАТ ЗА МЕСЯЦ")
        
        # Расходы
        col7, col8, col9 = st.columns(3)
        col7.metric("⛽ Расходы на бензин", f"{month_fuel_cost:.0f} ₽")
        col8.metric("💸 Прочие расходы", f"{month_extra:.0f} ₽")
        
        total_costs = month_fuel_cost + month_extra
        col9.metric("📉 ВСЕГО РАСХОДОВ", f"{total_costs:.0f} ₽")
        
        # Прибыль
        profit = total_income - total_costs
        profitability = (profit / total_income * 100) if total_income > 0 else 0
        
        col10, col11, col12 = st.columns(3)
        col10.metric("📈 ЧИСТАЯ ПРИБЫЛЬ", f"{profit:.0f} ₽", 
                    delta=f"{profitability:.1f}%" if total_income > 0 else None)
        
        shifts_count = totals.get('смен', 0)
        col11.metric("💰 Средний доход за смену", 
                    f"{total_income / shifts_count:.0f} ₽" if shifts_count > 0 else "0 ₽")
        col12.metric("📊 Средняя прибыль за смену", 
                    f"{profit / shifts_count:.0f} ₽" if shifts_count > 0 else "0 ₽")
        
        # Детализация расходов
        if not df_shifts.empty:
            st.write("---")
            st.subheader("📋 ДЕТАЛИЗАЦИЯ РАСХОДОВ ПО СМЕНАМ")
            
            # Создаём таблицу с детализацией
            details = []
            for _, row in df_shifts.iterrows():
                shift_date = row["Дата"]
                try:
                    shift_id = get_closed_shift_id_by_date(
                        datetime.strptime(shift_date, "%d.%m.%Y").strftime("%Y-%m-%d")
                    )
                except:
                    shift_id = None
                
                fuel = row["Литры"] * row["Цена"]
                fuel_liters = row["Литры"]
                fuel_price = row["Цена"]
                extra = sum(e['amount'] for e in get_extra_expenses(shift_id)) if shift_id else 0
                income = row["Всего"]
                profit_shift = income - fuel - extra
                
                details.append({
                    "Дата": shift_date,
                    "Доход": income,
                    "Бензин (л)": fuel_liters,
                    "Цена бензина": fuel_price,
                    "Бензин (₽)": fuel,
                    "Доп.расходы": extra,
                    "Всего расходов": fuel + extra,
                    "Прибыль": profit_shift,
                    "Рентабельность": f"{profit_shift/income*100:.1f}%" if income > 0 else "0%"
                })
            
            df_details = pd.DataFrame(details)
            st.dataframe(
                df_details.style.format({
                    "Доход": "{:.0f} ₽",
                    "Бензин (л)": "{:.1f} л",
                    "Цена бензина": "{:.1f} ₽/л",
                    "Бензин (₽)": "{:.0f} ₽",
                    "Доп.расходы": "{:.0f} ₽",
                    "Всего расходов": "{:.0f} ₽",
                    "Прибыль": "{:.0f} ₽",
                }),
                width='stretch'
            )
            
            # График доходов и расходов
            st.subheader("📊 ДИНАМИКА ДОХОДОВ И РАСХОДОВ")
            
            chart_data = pd.DataFrame({
                "Дата": [d["Дата"] for d in details],
                "Доход": [d["Доход"] for d in details],
                "Расходы (бензин)": [d["Бензин (₽)"] for d in details],
                "Расходы (прочие)": [d["Доп.расходы"] for d in details],
                "Прибыль": [d["Прибыль"] for d in details]
            })
            
            if not chart_data.empty:
                st.line_chart(data=chart_data.set_index("Дата")[["Доход", "Расходы (бензин)", "Расходы (прочие)", "Прибыль"]])
        
        st.write("---")
        st.subheader("📊 ПОЛНАЯ СТАТИСТИКА РАСХОДОВ")
        
        # Собираем статистику по всем расходам (включая бензин)
        all_expenses = []
        
        # Добавляем бензин как статью расходов
        all_expenses.append({
            'description': '⛽ Бензин',
            'total': month_fuel_cost,
            'count': len(df_shifts) if not df_shifts.empty else 0,
            'avg': month_fuel_cost / len(df_shifts) if len(df_shifts) > 0 else 0
        })
        
        # Добавляем прочие расходы как отдельную статью
        all_expenses.append({
            'description': '💸 Прочие расходы',
            'total': month_extra,
            'count': len(df_shifts) if not df_shifts.empty else 0,
            'avg': month_extra / len(df_shifts) if len(df_shifts) > 0 else 0
        })
        
        # Добавляем все доп. расходы по категориям
        expense_stats = get_all_extra_expenses_stats()
        for stat in expense_stats:
            all_expenses.append({
                'description': stat['description'],
                'total': stat['total'],
                'count': stat['count'],
                'avg': stat['total'] / stat['count'] if stat['count'] > 0 else 0
            })
        
        # Сортируем по сумме (от больших к меньшим)
        all_expenses.sort(key=lambda x: x['total'], reverse=True)
        
        # Показываем топ-15 расходов
        st.subheader("🏆 ТОП-15 РАСХОДОВ")
        
        for i, exp in enumerate(all_expenses[:15], 1):
            if exp['total'] > 0:
                # Выбираем цвет в зависимости от типа расхода
                if '⛽' in exp['description']:
                    bg_color = "#dbeafe"  # синий для бензина
                elif '💸' in exp['description']:
                    bg_color = "#fef9c3"  # желтый для прочих
                else:
                    bg_color = "#fee2e2"  # красный для остальных
                
                st.markdown(f"""
                <div style="background-color: {bg_color}; padding: 10px; border-radius: 8px; margin: 5px 0; border-left: 4px solid #3b82f6;">
                    <div style="display: flex; justify-content: space-between;">
                        <span style="font-weight: bold;">{i}. {exp['description']}</span>
                        <span style="font-weight: bold; color: #1e293b;">{exp['total']:.0f} ₽</span>
                    </div>
                    <div style="display: flex; justify-content: space-between; color: #64748b; font-size: 0.9rem;">
                        <span>📊 {exp['count']} раз(а)</span>
                        <span>💰 Средний чек: {exp['avg']:.0f} ₽</span>
                    </div>
                </div>
                """, unsafe_allow_html=True)
        
        # Круговая диаграмма структуры расходов
        if total_costs > 0:
            st.subheader("🥧 СТРУКТУРА РАСХОДОВ")
            
            # Данные для круговой диаграммы
            pie_data = pd.DataFrame({
                'Категория': ['Бензин', 'Прочие расходы'],
                'Сумма': [month_fuel_cost, month_extra]
            })
            
            # Добавляем топ-3 доп. расходов
            for exp in expense_stats[:3]:
                if exp['total'] > 0:
                    pie_data = pd.concat([pie_data, pd.DataFrame({
                        'Категория': [exp['description']],
                        'Сумма': [exp['total']]
                    })], ignore_index=True)
            
            st.bar_chart(data=pie_data.set_index('Категория'))
            
            # Процентное соотношение
            st.caption(f"""
            **Анализ расходов:**
            - Бензин: {month_fuel_cost/total_costs*100:.1f}% от всех расходов
            - Прочие расходы: {month_extra/total_costs*100:.1f}% от всех расходов
            - Средний расход на бензин за смену: {month_fuel_cost/shifts_count:.0f} ₽ ({month_fuel_liters/shifts_count:.1f} л)
            """ if shifts_count > 0 else "")
        
        # График расхода бензина по дням
        if not df_shifts.empty:
            st.subheader("📈 РАСХОД БЕНЗИНА ПО ДНЯМ")
            
            fuel_chart = pd.DataFrame({
                "Дата": [d["Дата"] for d in details],
                "Литры": [d["Бензин (л)"] for d in details],
                "Сумма (₽)": [d["Бензин (₽)"] for d in details]
            })
            
            if not fuel_chart.empty:
                col1, col2 = st.columns(2)
                with col1:
                    st.bar_chart(data=fuel_chart.set_index("Дата")[["Литры"]])
                with col2:
                    st.bar_chart(data=fuel_chart.set_index("Дата")[["Сумма (₽)"]])
        
        # Сравнение с прошлым месяцем (если есть данные)
        st.write("---")
        st.subheader("📉 СРАВНЕНИЕ С ПРЕДЫДУЩИМ МЕСЯЦЕМ")
        
        # Получаем предыдущий месяц
        year, month = map(int, ym.split('-'))
        if month == 1:
            prev_ym = f"{year-1}-12"
        else:
            prev_ym = f"{year}-{month-1:02d}"
        
        # Пытаемся получить данные за предыдущий месяц
        prev_df_shifts = get_month_shifts_details_cached(prev_ym)
        
        if not prev_df_shifts.empty:
            prev_month_extra = get_month_extra_expenses(prev_ym)
            prev_month_fuel = float(
                (prev_df_shifts["Литры"].fillna(0) * prev_df_shifts["Цена"].fillna(0)).sum()
            ) if not prev_df_shifts.empty else 0
            prev_total_income = get_month_totals_cached(prev_ym).get('всего', 0)
            
            # Рассчитываем изменения
            income_change = total_income - prev_total_income
            fuel_change = month_fuel_cost - prev_month_fuel
            extra_change = month_extra - prev_month_extra
            total_costs_change = total_costs - (prev_month_fuel + prev_month_extra)
            profit_change = profit - (prev_total_income - prev_month_fuel - prev_month_extra)
            
            col1, col2, col3 = st.columns(3)
            col1.metric("💰 Доход", f"{total_income:.0f} ₽", 
                       delta=f"{income_change:+.0f} ₽" if income_change != 0 else None)
            col2.metric("⛽ Бензин", f"{month_fuel_cost:.0f} ₽", 
                       delta=f"{fuel_change:+.0f} ₽" if fuel_change != 0 else None)
            col3.metric("💸 Прочие", f"{month_extra:.0f} ₽", 
                       delta=f"{extra_change:+.0f} ₽" if extra_change != 0 else None)
            
            col4, col5, col6 = st.columns(3)
            col4.metric("📉 Расходы", f"{total_costs:.0f} ₽", 
                       delta=f"{total_costs_change:+.0f} ₽" if total_costs_change != 0 else None)
            col5.metric("📈 Прибыль", f"{profit:.0f} ₽", 
                       delta=f"{profit_change:+.0f} ₽" if profit_change != 0 else None)
            
            if prev_total_income > 0:
                profitability_change = (profit/total_income*100) - ((prev_total_income - prev_month_fuel - prev_month_extra)/prev_total_income*100)
                col6.metric("📊 Рентабельность", f"{profit/total_income*100:.1f}%" if total_income > 0 else "0%",
                           delta=f"{profitability_change:+.1f}%" if profitability_change != 0 else None)
        else:
            st.info("📭 Нет данных за предыдущий месяц для сравнения")
        
    except Exception as e:
        st.error(f"Ошибка: {e}")
        st.exception(e)

def show_admin_page():
    """Отображает страницу администрирования"""
    if not check_and_create_tables():
        st.error("❌ Ошибка БД")
        return
    
    st.title(f"🛠 АДМИНИСТРИРОВАНИЕ")
    
    ADMIN_PASSWORD = st.secrets.get("ADMIN_PASSWORD", "changeme")
    
    if "admin_authenticated" not in st.session_state:
        st.session_state.admin_authenticated = False
    
    if not st.session_state.admin_authenticated:
        with st.form("admin_login"):
            pwd = st.text_input("Пароль администратора", type="password")
            ok = st.form_submit_button("ВОЙТИ", width='stretch')
            
            if ok and pwd == ADMIN_PASSWORD:
                st.session_state.admin_authenticated = True
                st.rerun()
            elif ok:
                st.error("❌ Неверный пароль")
        return
    
    # Создаём вкладки
    tabs = st.tabs([
        "📥 ИМПОРТ", 
        "🔄 ПЕРЕСЧЁТ", 
        "✏️ БЕЗНАЛ", 
        "🗄 БЭКАПЫ", 
        "💾 АРХИВ", 
        "🔧 ИНСТРУМЕНТЫ"
    ])
    
    with tabs[0]:
        st.subheader("📥 ИМПОРТ ДАННЫХ")
        
        with st.expander("📄 Импорт из Google Sheets", expanded=False):
            st.caption("Вставьте ссылку на Google Sheets таблицу. Таблица должна быть в формате: Дата, Тип, Сумма, Чаевые")
            sheet_url = st.text_input("Ссылка на таблицу", placeholder="https://docs.google.com/spreadsheets/d/...")
            if st.button("🚀 ИМПОРТИРОВАТЬ", width='stretch'):
                with st.spinner("Импортируем данные..."):
                    try:
                        import sys
                        sys.path.append(os.path.dirname(__file__))
                        from pages_imports import import_from_gsheet
                        imported = import_from_gsheet(sheet_url)
                        if imported > 0:
                            st.success(f"✅ Импортировано {imported} заказов")
                    except Exception as e:
                        st.error(f"Ошибка: {e}")
        
        with st.expander("📂 Импорт из файла", expanded=True):
            st.caption("Загрузите файл Excel или CSV. Формат: Дата, Тип, Сумма, Чаевые")
            uploaded = st.file_uploader("Выберите файл", type=["xlsx", "xls", "csv"])
            if uploaded and st.button("📤 ИМПОРТИРОВАТЬ ФАЙЛ", width='stretch'):
                with st.spinner("Импортируем данные..."):
                    try:
                        import sys
                        sys.path.append(os.path.dirname(__file__))
                        from pages_imports import import_from_excel
                        imported = import_from_excel(uploaded)
                        if imported > 0:
                            st.success(f"✅ Импортировано {imported} заказов")
                    except Exception as e:
                        st.error(f"Ошибка: {e}")
    
    with tabs[1]:
        st.subheader("🔄 ПЕРЕСЧЁТ ДАННЫХ")
        st.caption("Пересчёт обновит комиссии и баланс безнала по всем заказам")
        try:
            import sys
            sys.path.append(os.path.dirname(__file__))
            from pages_imports import get_accumulated_beznal, recalc_full_db
            current = get_accumulated_beznal()
            st.metric("💰 Текущий накопленный безнал", f"{current:.0f} ₽")
            
            if st.button("🔄 ПЕРЕСЧИТАТЬ ВСЁ", width='stretch', type="primary"):
                with st.spinner("Пересчитываем данные..."):
                    new_total = recalc_full_db()
                    st.success(f"✅ Пересчёт завершён")
                    st.metric("💰 Новый безнал", f"{new_total:.0f} ₽")
        except Exception as e:
            st.error(f"Ошибка: {e}")
    
    with tabs[2]:
        st.subheader("✏️ НАКОПЛЕННЫЙ БЕЗНАЛ")
        st.caption("Здесь можно вручную установить значение накопленного безнала")
        current = get_accumulated_beznal()
        st.metric("💰 Текущее значение", f"{current:.0f} ₽")
        
        with st.form("change_beznal_form"):
            new_value = st.number_input(
                "Новое значение (можно отрицательное)",
                min_value=None,
                step=100.0,
                format="%.0f",
                value=float(current),
            )
            
            col1, col2 = st.columns(2)
            with col1:
                save_btn = st.form_submit_button("💾 СОХРАНИТЬ", use_container_width=True, type="primary")
            with col2:
                reset_btn = st.form_submit_button("🔄 СБРОСИТЬ НА 0", use_container_width=True)
        
        if save_btn:
            set_accumulated_beznal(new_value)
            st.success(f"✅ Сохранено: {new_value:.0f} ₽")
            log_action("Изменение безнала", f"{new_value:.0f} ₽")
            st.rerun()
        
        if reset_btn:
            set_accumulated_beznal(0)
            st.success(f"✅ Значение сброшено на 0")
            log_action("Сброс безнала", "0 ₽")
            st.rerun()
    
    with tabs[3]:
        st.subheader("🗄 УПРАВЛЕНИЕ БЭКАПАМИ")
        
        col1, col2 = st.columns(2)
        with col1:
            if st.button("📦 СОЗДАТЬ НОВЫЙ БЭКАП", width='stretch', type="primary"):
                with st.spinner("Создаём бэкап..."):
                    path = create_backup()
                    size = os.path.getsize(path) / 1024
                    st.success(f"✅ Бэкап создан: {os.path.basename(path)}")
                    st.caption(f"📦 Размер: {size:.1f} KB")
        
        with col2:
            backup_dir = get_backup_dir()
            st.info(f"📁 Папка для бэкапов: **{os.path.basename(backup_dir)}**")
        
        backups = list_backups()
        if backups:
            st.subheader("📋 СУЩЕСТВУЮЩИЕ БЭКАПЫ")
            st.caption("Нажмите кнопку для скачивания, восстановления или удаления")
            
            for backup in backups:
                with st.container():
                    cols = st.columns([3, 1, 1, 1])
                    with cols[0]:
                        st.markdown(f"**{backup['name']}**")
                        st.caption(f"📅 {backup['time'].strftime('%d.%m.%Y %H:%M:%S')} | 📦 {backup['size']:.1f} KB")
                    with cols[1]:
                        data = download_backup(backup['path'])
                        st.download_button(
                            label="📥 Скачать", 
                            data=data, 
                            file_name=backup['name'], 
                            key=f"d_{backup['name']}",
                            help="Сохранить этот бэкап на компьютер"
                        )
                    with cols[2]:
                        if st.button("🔄 Восстановить", key=f"r_{backup['name']}", help="Восстановить базу данных из этого бэкапа"):
                            restore_from_backup(backup['path'])
                            st.success("✅ База восстановлена")
                            st.cache_data.clear()
                            st.rerun()
                    with cols[3]:
                        if st.button("🗑 Удалить", key=f"del_{backup['name']}", help="Удалить этот бэкап навсегда"):
                            os.remove(backup['path'])
                            st.success(f"✅ Бэкап удалён")
                            st.rerun()
                    st.divider()
        else:
            st.info("📭 Пока нет ни одного бэкапа. Нажмите кнопку выше, чтобы создать первый бэкап!")
    
    with tabs[4]:
        st.subheader("💾 ЗАГРУЗКА БЭКАПА")
        st.caption("Загрузите ранее сохранённый бэкап с компьютера")
        
        uploaded = st.file_uploader("Выберите файл бэкапа (.db)", type=["db"])
        if uploaded:
            size = len(uploaded.getbuffer()) / 1024
            st.caption(f"📦 Выбран файл: **{uploaded.name}** | Размер: {size:.1f} KB")
            
            st.warning("⚠️ Внимание! При восстановлении текущая база будет перезаписана. Автоматически будет создан бэкап текущей базы.")
            
            col1, col2 = st.columns(2)
            with col1:
                if st.button("✅ ВОССТАНОВИТЬ ИЗ ФАЙЛА", width='stretch', type="primary"):
                    with st.spinner("Восстанавливаем базу..."):
                        try:
                            create_backup()  # Создаём бэкап текущей базы
                            if upload_and_restore_backup(uploaded):
                                st.success("✅ База успешно восстановлена из загруженного файла")
                                st.cache_data.clear()
                                st.rerun()
                            else:
                                st.error("❌ Ошибка при восстановлении")
                        except Exception as e:
                            st.error(f"❌ Ошибка: {e}")
            with col2:
                if st.button("❌ ОТМЕНА", width='stretch'):
                    st.rerun()
    
    with tabs[5]:
        st.subheader("🔧 ИНСТРУМЕНТЫ")
        try:
            import sys
            sys.path.append(os.path.dirname(__file__))
            from pages_imports import normalize_shift_dates, reset_db
            
            with st.expander("🛠 ИСПРАВЛЕНИЕ ФОРМАТА ДАТ", expanded=False):
                st.caption("Эта операция исправляет даты смен к единому формату ГГГГ-ММ-ДД")
                if st.button("🛠 ИСПРАВИТЬ ДАТЫ", width='stretch'):
                    with st.spinner("Исправляем даты..."):
                        fixed, skipped = normalize_shift_dates()
                        st.success(f"✅ Исправлено дат: {fixed}, без изменений: {skipped}")
            
            st.divider()
            
            with st.expander("⚠️ ОПАСНАЯ ЗОНА", expanded=False):
                st.error("🚨 ПОЛНЫЙ СБРОС БАЗЫ ДАННЫХ")
                st.caption("Эта операция удалит ВСЕ смены, заказы и расходы. База станет пустой.")
                
                col1, col2 = st.columns(2)
                with col1:
                    confirm = st.checkbox("Я понимаю, что все данные будут удалены")
                with col2:
                    confirm2 = st.checkbox("Я сделал бэкап")
                
                if confirm and confirm2:
                    if st.button("🗑 УДАЛИТЬ ВСЁ", type="primary", width='stretch'):
                        with st.spinner("Удаляем данные..."):
                            reset_db()
                            st.success("✅ База полностью сброшена")
                            st.cache_data.clear()
                            st.rerun()
        except Exception as e:
            st.error(f"Ошибка: {e}")

# ===== UI / ЗАПУСК =====
st.set_page_config(
    page_title="Такси учёт", 
    page_icon="🚕", 
    layout="centered",
    initial_sidebar_state="expanded"
)

apply_mobile_optimized_css()
init_auth_db()
ensure_users_dir()

# Пытаемся загрузить сессию с диска
saved_username = load_session_from_disk()
if saved_username and "username" not in st.session_state:
    st.session_state["username"] = saved_username
    st.session_state["db_name"] = get_current_db_name()
    st.session_state["user_dir"] = get_user_dir(saved_username)
    st.session_state["page"] = "main"
    try:
        with open(SESSION_FILE, 'r') as f:
            data = json.load(f)
            if data.get("session_start"):
                st.session_state.session_start = datetime.fromisoformat(data["session_start"])
                st.session_state.last_activity = datetime.fromisoformat(data["last_activity"])
    except:
        init_session()

init_session()

# ----- ЛОГИН / РЕГИСТРАЦИЯ -----
if "username" not in st.session_state:
    st.title("🚕 ВХОД В СИСТЕМУ")

    tabs = st.tabs(["🔑 ВХОД", "📝 РЕГИСТРАЦИЯ"])

    with tabs[0]:
        with st.form("login_form"):
            username = st.text_input("Имя пользователя")
            password = st.text_input("Пароль", type="password")
            btn = st.form_submit_button("🔓 ВОЙТИ", width='stretch')

        if btn:
            if not username or not password:
                st.error("Введите имя пользователя и пароль")
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
                st.error("❌ Неверное имя пользователя или пароль")

    with tabs[1]:
        st.caption("Создайте новую учётную запись")
        with st.form("register_form"):
            reg_username = st.text_input("Имя пользователя")
            reg_password = st.text_input("Пароль", type="password")
            reg_password2 = st.text_input("Повторите пароль", type="password")
            reg_btn = st.form_submit_button("📝 ЗАРЕГИСТРИРОВАТЬСЯ", width='stretch')

        if reg_btn:
            if not reg_username or not reg_password:
                st.error("Имя пользователя и пароль не могут быть пустыми")
            elif reg_password != reg_password2:
                st.error("Пароли не совпадают")
            elif len(reg_password) < 4:
                st.error("Пароль должен быть не менее 4 символов")
            else:
                ok = register_user(reg_username, reg_password)
                if ok:
                    st.success("✅ Пользователь создан! Теперь можно войти")
                    log_action("Регистрация", f"Новый пользователь {reg_username}")
                else:
                    st.error("❌ Такой пользователь уже существует")

    st.stop()

# ===== ПОСЛЕ ВХОДА =====
st.session_state["db_name"] = get_current_db_name()

if "page" not in st.session_state:
    st.session_state["page"] = "main"

# Сайдбар с крупным ником пользователя
with st.sidebar:
    # Красивый блок с пользователем
    st.markdown(f"""
    <div class="user-info">
        <div class="user-avatar">👤</div>
        <div class="user-name">
            {st.session_state['username']}
            <small>водитель</small>
        </div>
    </div>
    """, unsafe_allow_html=True)
    
    try:
        db_path = get_current_db_name()
        if os.path.exists(db_path):
            size = os.path.getsize(db_path) / 1024
            st.markdown(f"""
            <div class="sidebar-metric">
                <div class="label">📦 Размер БД</div>
                <div class="value">{size:.1f} KB</div>
            </div>
            """, unsafe_allow_html=True)
        
        acc = get_accumulated_beznal()
        st.markdown(f"""
        <div class="sidebar-metric">
            <div class="label">💰 Накопленный безнал</div>
            <div class="value">{acc:.0f} ₽</div>
        </div>
        """, unsafe_allow_html=True)
        
        backups = list_backups()
        st.markdown(f"""
        <div class="sidebar-metric">
            <div class="label">💾 Количество бэкапов</div>
            <div class="value">{len(backups)}</div>
        </div>
        """, unsafe_allow_html=True)
    except:
        pass
    
    st.divider()
    
    if st.button("📋 ПРОГРАММА", width='stretch', 
                 type="primary" if st.session_state["page"] == "main" else "secondary"):
        st.session_state["page"] = "main"
        st.rerun()
    
    if st.button("📊 ОТЧЁТЫ", width='stretch',
                 type="primary" if st.session_state["page"] == "reports" else "secondary"):
        st.session_state["page"] = "reports"
        st.rerun()
    
    if st.button("⚙️ АДМИНКА", width='stretch',
                 type="primary" if st.session_state["page"] == "admin" else "secondary"):
        st.session_state["page"] = "admin"
        st.rerun()
    
    st.divider()
    
    time_left = get_session_time_remaining()
    st.caption(f"⏱️ Сессия активна ещё: {time_left}")
    
    if st.button("🚪 ВЫЙТИ ИЗ СИСТЕМЫ", width='stretch'):
        log_action("Выход", f"Пользователь {st.session_state['username']}")
        clear_session_disk()
        st.session_state.clear()
        st.rerun()

# Отображаем выбранную страницу
if st.session_state["page"] == "main":
    show_main_page()
elif st.session_state["page"] == "reports":
    show_reports_page()
elif st.session_state["page"] == "admin":
    show_admin_page()