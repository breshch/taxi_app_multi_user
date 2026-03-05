import streamlit as st
import sqlite3
from datetime import datetime, date, timezone, timedelta
import hashlib
import os
import pandas as pd

# ===== НАСТРОЙКИ =====
AUTH_DB = "users.db"  # база с пользователями (логин/пароль)
USERS_DIR = "users"    # папка для хранения данных пользователей

rate_nal = 0.78   # процент для нала (для расчёта комиссии)
rate_card = 0.75  # процент для карты

# Московский часовой пояс
MOSCOW_TZ = timezone(timedelta(hours=3))

# ===== КАСТОМНЫЙ ДИЗАЙН / CSS =====
def apply_custom_css():
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
        
        /* Убираем отступы сверху в сайдбаре */
        section[data-testid="stSidebar"] > div {
            padding-top: 0rem !important;
        }
        
        .stApp {
            background: #f3f4f6;
            color: #111827;
            font-family: system-ui, -apple-system, BlinkMacSystemFont, "SF Pro Text", sans-serif;
        }
        .block-container {
            padding-top: 0.8rem;
            padding-bottom: 0.8rem;
            max-width: 720px;
        }
        h1 {
            font-size: 1.6rem !important;
            text-align: center;
            margin-bottom: 0.5rem;
            color: #0f172a;
        }
        h2, h3 {
            color: #1f2933;
            font-size: 1.1rem !important;
            margin-top: 0.8rem;
            margin-bottom: 0.4rem;
        }
        .streamlit-expanderHeader {
            font-weight: 600;
            font-size: 0.95rem;
        }
        .stExpander {
            background: #ffffff !important;
            border-radius: 0.75rem !important;
            border: 1px solid #e5e7eb !important;
            padding: 0.2rem 0.4rem !important;
        }
        .stMetric {
            background-color: #ffffff;
            padding: 0.4rem 0.6rem;
            border-radius: 0.75rem;
            border: 1px solid #e5e7eb;
        }
        button[kind="primary"], button[kind="secondary"] {
            border-radius: 999px !important;
            padding-top: 0.5rem !important;
            padding-bottom: 0.5rem !important;
            font-weight: 600 !important;
            background-color: #bfdbfe !important;
            color: #111827 !important;
            border: 1px solid #93c5fd !important;
        }
        button[kind="primary"]:hover, button[kind="secondary"]:hover {
            background-color: #93c5fd !important;
            color: #111827 !important;
        }
        hr {
            margin: 0.3rem 0 !important;
            border-color: #e5e7eb;
        }
        .stForm, .stMarkdown, .stNumberInput, .stSelectbox, .stFileUploader {
            margin-bottom: 0.4rem !important;
        }
        .stContainer {
            background-color: transparent;
        }
        .warning-box {
            background-color: #fff3cd;
            border: 1px solid #ffeeba;
            color: #856404;
            padding: 0.5rem;
            border-radius: 0.5rem;
            margin: 0.5rem 0;
        }
        /* Стили для кнопок навигации */
        div.row-widget.stButton > button {
            text-align: left;
            padding: 0.5rem 1rem;
            margin: 0.2rem 0;
            border-radius: 0.5rem;
            background-color: #f9fafb;
            border: 1px solid #e5e7eb;
            font-weight: normal;
        }
        div.row-widget.stButton > button:hover {
            background-color: #e5e7eb;
            border-color: #93c5fd;
        }
        div.row-widget.stButton > button.active-nav {
            background-color: #bfdbfe;
            border-color: #93c5fd;
            font-weight: 600;
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

def check_and_create_tables():
    """Проверяет и создаёт все необходимые таблицы в базе данных"""
    conn = sqlite3.connect(get_current_db_name())
    cursor = conn.cursor()
    
    # Создаём таблицу shifts
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
    try:
        cursor.execute("ALTER TABLE orders ADD COLUMN order_time TEXT")
    except sqlite3.OperationalError:
        pass
    
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
            user_dir TEXT
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
            INSERT INTO users (username, password_hash, created_at, user_dir)
            VALUES (?, ?, ?, ?)
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
            print(f"Удалён старый файл базы: {db_path}")
        
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
        st.info("📭 СЕЙЧАС НЕТ ОТКРЫТОЙ СМЕНЫ")

        with st.expander("📝 ОТКРЫТЬ НОВУЮ СМЕНУ", expanded=True):
            with st.form("open_shift_form"):
                date_input = st.date_input(
                    "Дата смены",
                    value=date.today(),
                )
                st.caption(f"Выбрано: {date_input.strftime('%d.%m.%Y')}")
                submitted_tpl = st.form_submit_button("📂 ОТКРЫТЬ СМЕНУ", width='stretch')

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
        st.success(f"📅 Открыта смена: {date_show}")

        acc = get_accumulated_beznal()
        if acc != 0:
            st.metric("Накопленный безнал", f"{acc:.0f} ₽")

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
                    payment = st.selectbox("Тип оплаты", ["НАЛИЧНЫЕ", "КАРТА"])

                tips_str = st.text_input(
                    "Чаевые, ₽",
                    value="",
                    placeholder="0 (если без чаевых)",
                )

                now_moscow = datetime.now(MOSCOW_TZ)
                st.caption(f"🕒 Текущее время: {now_moscow.strftime('%H:%M')}")

                submitted = st.form_submit_button("💾 СОХРАНИТЬ ЗАКАЗ", width='stretch')

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

                if payment == "НАЛИЧНЫЕ":
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
                    st.success(
                        f"✅ Заказ добавлен: {human_type}, {amount:.0f} ₽, чаевые {tips:.0f} ₽"
                    )
                    st.rerun()
                except Exception as e:
                    st.error(f"Ошибка при сохранении заказа: {e}")

        # ===== СПИСОК ЗАКАЗОВ + КНОПКИ РЕДАКТА/УДАЛЕНИЯ =====
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
                    left, mid, right = st.columns([3, 1, 1])

                    with left:
                        time_str = f"{order_time} · " if order_time else ""
                        st.markdown(
                            f"**#{i}** · {time_str}"
                            f"{'💵 Нал' if typ == 'нал' else '💳 Карта'} · "
                            f"{amount:.0f} ₽"
                        )
                        details = []
                        if tips > 0:
                            details.append(f"чаевые {tips:.0f} ₽")
                        if beznal_add > 0:
                            details.append(f"+{beznal_add:.0f} ₽ в безнал")
                        elif beznal_add < 0:
                            details.append(f"{beznal_add:.0f} ₽ списано с безнала")
                        if details:
                            st.caption(", ".join(details))

                    with right:
                        st.markdown(f"**Вам:** {total:.0f} ₽")

                    with mid:
                        edit_key = f"edit_{order_id}"
                        delete_key = f"delete_{order_id}"
                        confirm_key = f"confirm_{order_id}"

                        if st.button("✏️", key=edit_key):
                            st.session_state.edit_order_id = order_id
                            st.session_state.edit_original_type = typ
                            st.session_state.edit_original_amount = float(amount)
                            st.session_state.edit_original_tips = float(tips)
                            st.rerun()

                        # Удаление с подтверждением
                        if confirm_key not in st.session_state.confirm_delete:
                            st.session_state.confirm_delete[confirm_key] = False
                        
                        if st.button("🗑", key=delete_key):
                            st.session_state.confirm_delete[confirm_key] = True
                            st.rerun()
                        
                        if st.session_state.confirm_delete.get(confirm_key, False):
                            st.markdown('<div class="warning-box">Удалить? Нажмите 🗑 ещё раз</div>', unsafe_allow_html=True)
                            if st.button("✅ ДА", key=f"yes_{order_id}"):
                                if beznal_add != 0:
                                    add_to_accumulated_beznal(-beznal_add)
                                delete_order_db(order_id)
                                log_action("Удаление заказа", f"Заказ #{i}, сумма {amount:.0f} ₽")
                                st.session_state.confirm_delete[confirm_key] = False
                                st.success(f"Заказ #{i} удалён.")
                                st.rerun()

                st.divider()

            st.subheader("💼 ИТОГИ ПО СМЕНЕ")
            top = st.container()
            bottom = st.container()
            with top:
                c1, c2 = st.columns(2)
                c1.metric("Нал", f"{nal:.0f} ₽")
                c2.metric("Карта", f"{card:.0f} ₽")
            with bottom:
                c3, c4 = st.columns(2)
                c3.metric("Чаевые", f"{tips_sum:.0f} ₽")
                c4.metric("Изм. безнала", f"{beznal_this:.0f} ₽")

            total_day = nal + card + tips_sum
            st.caption(f"Всего за смену (до бензина): {total_day:.0f} ₽")

        # ===== ФОРМА РЕДАКТИРОВАНИЯ ВЫБРАННОГО ЗАКАЗА =====
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
                        "Новая сумма заказа, ₽",
                        value=f"{orig_amount:.0f}",
                    )
                with col2:
                    new_payment = st.selectbox(
                        "Тип оплаты",
                        ["НАЛИЧНЫЕ", "КАРТА"],
                        index=0 if orig_type == "нал" else 1,
                    )

                new_tips_str = st.text_input(
                    "Новые чаевые, ₽",
                    value=f"{orig_tips:.0f}",
                )

                col_btn1, col_btn2 = st.columns(2)
                with col_btn1:
                    save_btn = st.form_submit_button("💾 СОХРАНИТЬ", width='stretch')
                with col_btn2:
                    cancel_btn = st.form_submit_button("ОТМЕНА", width='stretch')

            if cancel_btn and not save_btn:
                st.session_state.edit_order_id = None
                st.rerun()

            if save_btn:
                try:
                    new_amount = float(new_amount_str.replace(",", "."))
                except ValueError:
                    st.error("Сумма заказа должна быть числом.")
                    st.stop()

                if new_amount <= 0:
                    st.error("Сумма заказа должна быть больше нуля.")
                    st.stop()

                try:
                    new_tips = float(new_tips_str.replace(",", "."))
                except ValueError:
                    st.error("Чаевые должны быть числом.")
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
                    st.error("Не удалось найти заказ в базе.")
                    st.stop()

                old_type, old_amount, old_tips, old_beznal = row

                if new_payment == "НАЛИЧНЫЕ":
                    new_type = "нал"
                    final_wo_tips = new_amount
                    commission = new_amount * (1 - rate_nal)
                    total = new_amount + new_tips
                    new_beznal = -commission
                else:
                    new_type = "карта"
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

                log_action("Редактирование заказа", f"Заказ #{order_id}, новая сумма {new_amount:.0f} ₽")
                st.success("✅ Изменения сохранены.")
                st.session_state.edit_order_id = None
                st.rerun()

        # ===== ЗАКРЫТИЕ СМЕНЫ =====
        st.write("---")
        with st.expander("🔒 ЗАКРЫТЬ СМЕНУ"):
            last_consumption, last_price = get_last_fuel_params()

            with st.form("close_form"):
                km = st.number_input(
                    "Километраж за смену (км)", min_value=0, step=10
                )

                col1, col2 = st.columns(2)
                with col1:
                    consumption = st.number_input(
                        "Расход, л на 100 км",
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
                    st.write(
                        f"Расход: {liters:.1f} л, бензин: {fuel_cost:.2f} ₽"
                    )
                else:
                    liters = 0.0
                    fuel_cost = 0.0

                submitted_close = st.form_submit_button("🔒 ЗАКРЫТЬ СМЕНУ", width='stretch')

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

                log_action("Закрытие смены", f"Дата: {date_str}, доход: {income:.0f} ₽, прибыль: {profit:.0f} ₽")
                st.success("✅ Смена закрыта.")
                r1, r2, r3 = st.columns(3)
                r1.metric("Доход", f"{income:.0f} ₽")
                r2.metric("Бензин", f"{fuel_cost:.0f} ₽")
                r3.metric("Чистая прибыль", f"{profit:.0f} ₽")
                st.info("📊 Проверьте отчёт в разделе ОТЧЁТЫ для детализации.")

def show_reports_page():
    """Отображает страницу отчётов"""
    # Проверяем и создаём таблицы
    check_and_create_tables()
    
    st.title(f"📊 ОТЧЁТЫ — {st.session_state['username']}")
    
    # Импортируем функции из pages_imports.py
    try:
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
            st.info("📭 Пока нет закрытых смен с заказами для формирования отчёта.")
            
            with st.expander("📋 Пример формата данных для импорта"):
                example_data = pd.DataFrame({
                    "Дата": ["01.02.2026", "02.02.2026"],
                    "Тип": ["нал", "карта"],
                    "Сумма": [1500, 2000],
                    "Чаевые": [100, 0]
                })
                st.dataframe(example_data, width='stretch')
                st.caption("Загрузите файл в таком формате через страницу АДМИНКА")
            return
        
        ym = st.selectbox(
            "📅 Выберите месяц",
            year_months,
            format_func=format_month_option,
            index=0,
        )
        
        df_shifts = get_month_shifts_details_cached(ym)
        totals = get_month_totals_cached(ym)
        
        st.write("---")
        st.subheader("📄 Отчёт по смене")
        
        if df_shifts.empty:
            st.write("Нет закрытых смен с заказами за выбранный месяц.")
        else:
            available_dates = df_shifts["Дата"].unique().tolist()
            selected_date_display = st.selectbox("📆 Дата смены", options=available_dates)
            
            try:
                selected_date = datetime.strptime(selected_date_display, "%d.%m.%Y").strftime("%Y-%m-%d")
            except:
                selected_date = selected_date_display
            
            df_shift_summary = df_shifts[df_shifts["Дата"] == selected_date_display].copy()
            if not df_shift_summary.empty:
                st.dataframe(df_shift_summary, width='stretch')
            
            shift_id = get_closed_shift_id_by_date(selected_date)
            df_orders = get_shift_orders_df(shift_id)
            if not df_orders.empty:
                st.dataframe(df_orders, width='stretch')
            
            df_hours = get_orders_by_hour(selected_date)
            st.bar_chart(data=df_hours, x="Час", y="Заказов", width='stretch')
        
        st.write("---")
        st.subheader("📊 Отчёт за месяц")
        
        col1, col2, col3 = st.columns(3)
        col1.metric("Нал", f"{totals.get('нал', 0):.0f} ₽")
        col2.metric("Карта", f"{totals.get('карта', 0):.0f} ₽")
        col3.metric("Чаевые", f"{totals.get('чаевые', 0):.0f} ₽")
        
    except ImportError as e:
        st.error(f"Ошибка загрузки модуля отчётов: {e}")
        st.info("Убедитесь, что файл pages_imports.py существует в корневой папке")

def show_admin_page():
    """Отображает страницу администрирования"""
    # Проверяем и создаём таблицы
    check_and_create_tables()
    
    st.title(f"🛠 АДМИНИСТРИРОВАНИЕ — {st.session_state['username']}")
    
    # Проверка пароля администратора
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
    
    # Импортируем функции из pages_imports.py
    try:
        from pages_imports import (
            get_accumulated_beznal,
            recalc_full_db,
            import_from_excel,
            import_from_gsheet,
            create_backup,
            list_backups,
            restore_backup,
            reset_db,
            normalize_shift_dates
        )
        
        tab1, tab2, tab3, tab4, tab5 = st.tabs([
            "📥 ИМПОРТ", "🔄 ПЕРЕСЧЁТ", "🗄 БЭКАПЫ", "🔧 ИНСТРУМЕНТЫ", "⚠️ СБРОС"
        ])
        
        with tab1:
            st.header("📥 ИМПОРТ ДАННЫХ")
            
            with st.expander("📄 Импорт из Google Sheets", expanded=False):
                sheet_url = st.text_input("Ссылка на Google Sheets")
                if st.button("🚀 ИМПОРТИРОВАТЬ", width='stretch'):
                    with st.spinner("Импортируем..."):
                        imported = import_from_gsheet(sheet_url)
                        if imported > 0:
                            st.success(f"✅ Импортировано {imported} заказов")
            
            with st.expander("📂 Импорт из файла", expanded=True):
                uploaded_file = st.file_uploader("Выберите файл", type=["xlsx", "xls", "csv"])
                if uploaded_file and st.button("📤 ИМПОРТИРОВАТЬ", width='stretch'):
                    with st.spinner("Импортируем..."):
                        imported = import_from_excel(uploaded_file)
                        if imported > 0:
                            st.success(f"✅ Импортировано {imported} заказов")
        
        with tab2:
            st.header("🔄 ПЕРЕСЧЁТ ДАННЫХ")
            current = get_accumulated_beznal()
            st.metric("Текущий безнал", f"{current:.0f} ₽")
            
            if st.button("🔄 ПЕРЕСЧИТАТЬ ВСЁ", width='stretch', type="primary"):
                with st.spinner("Пересчитываем..."):
                    new_total = recalc_full_db()
                    st.success(f"✅ Пересчёт завершён. Новый безнал: {new_total:.0f} ₽")
        
        with tab3:
            st.header("🗄 БЭКАПЫ")
            col1, col2 = st.columns(2)
            
            with col1:
                if st.button("📦 СОЗДАТЬ БЭКАП", width='stretch'):
                    try:
                        path = create_backup()
                        st.success(f"✅ Бэкап создан: {os.path.basename(path)}")
                    except Exception as e:
                        st.error(f"Ошибка: {e}")
            
            with col2:
                backups = list_backups()
                if backups:
                    labels = [lbl for lbl, _ in backups]
                    selected = st.selectbox("Выберите бэкап", labels)
                    
                    if st.button("🔄 ВОССТАНОВИТЬ", width='stretch'):
                        try:
                            restore_backup(dict(backups)[selected])
                            st.success("✅ База восстановлена")
                            st.cache_data.clear()
                        except Exception as e:
                            st.error(f"Ошибка: {e}")
        
        with tab4:
            st.header("🔧 ИНСТРУМЕНТЫ")
            if st.button("🛠 ИСПРАВИТЬ ФОРМАТ ДАТ", width='stretch'):
                fixed, skipped = normalize_shift_dates()
                st.success(f"✅ Исправлено дат: {fixed}, без изменений: {skipped}")
        
        with tab5:
            st.header("⚠️ ОПАСНАЯ ЗОНА")
            st.error("🚨 Полный сброс базы удалит все данные!")
            
            confirm = st.checkbox("Я понимаю, что все данные будут удалены")
            confirm2 = st.checkbox("Я сделал бэкап")
            
            if confirm and confirm2:
                if st.button("🗑 УДАЛИТЬ БАЗУ", type="primary", width='stretch'):
                    reset_db()
                    st.success("✅ База сброшена")
                    st.cache_data.clear()
        
    except ImportError as e:
        st.error(f"Ошибка загрузки модуля администрирования: {e}")
        st.info("Убедитесь, что файл pages_imports.py существует в корневой папке")

# ===== UI / ЗАПУСК =====
st.set_page_config(
    page_title="Такси учёт", 
    page_icon="🚕", 
    layout="centered",
    initial_sidebar_state="expanded"
)

apply_custom_css()
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
            login_btn = st.form_submit_button("ВОЙТИ", width='stretch')

        if login_btn:
            if not login_username or not login_password:
                st.error("Введите имя пользователя и пароль.")
            elif authenticate_user(login_username, login_password):
                st.session_state["username"] = login_username.strip()
                st.session_state["db_name"] = get_current_db_name()
                st.session_state["user_dir"] = get_user_dir(login_username.strip())
                st.session_state["page"] = "main"
                st.success(f"✅ Добро пожаловать, {st.session_state['username']}!")
                log_action("Вход в систему", f"Пользователь {st.session_state['username']}")
                st.rerun()
            else:
                st.error("❌ Неверное имя пользователя или пароль.")

    with tab_reg:
        st.caption("Регистрация нового пользователя.")
        with st.form("register_form"):
            reg_username = st.text_input("Имя пользователя")
            reg_password = st.text_input("Пароль", type="password")
            reg_password2 = st.text_input("Повтор пароля", type="password")
            reg_btn = st.form_submit_button("ЗАРЕГИСТРИРОВАТЬСЯ", width='stretch')

        if reg_btn:
            if not reg_username or not reg_password:
                st.error("Имя пользователя и пароль не могут быть пустыми.")
            elif reg_password != reg_password2:
                st.error("Пароли не совпадают.")
            elif len(reg_password) < 4:
                st.error("Пароль должен быть не менее 4 символов.")
            else:
                ok = register_user(reg_username, reg_password)
                if ok:
                    st.success("✅ Пользователь создан. Теперь можно войти.")
                    log_action("Регистрация", f"Новый пользователь {reg_username}")
                else:
                    st.error("❌ Такой пользователь уже существует.")

    st.stop()

# ===== ПОСЛЕ ВХОДА =====
st.session_state["db_name"] = get_current_db_name()

if "page" not in st.session_state:
    st.session_state["page"] = "main"

# Информация в сайдбаре с навигацией
with st.sidebar:
    st.markdown(f"### 👤 {st.session_state['username']}")
    st.markdown(f"📁 Папка: {os.path.basename(st.session_state.get('user_dir', 'unknown'))}")
    st.markdown(f"📊 База: {os.path.basename(get_current_db_name())}")
    
    try:
        db_path = get_current_db_name()
        if os.path.exists(db_path):
            db_size = os.path.getsize(db_path) / 1024
            st.caption(f"📦 Размер: {db_size:.1f} KB")
    except:
        pass
    
    st.markdown("---")
    st.markdown("**НАВИГАЦИЯ:**")
    
    # Кнопки навигации с русскими названиями
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
    
    st.markdown("---")
    
    if st.button("🚪 ВЫЙТИ", width='stretch'):
        log_action("Выход", f"Пользователь {st.session_state['username']}")
        st.session_state.clear()
        st.rerun()

# Отображаем выбранную страницу
if st.session_state["page"] == "main":
    show_main_page()
elif st.session_state["page"] == "reports":
    show_reports_page()
elif st.session_state["page"] == "admin":
    show_admin_page()