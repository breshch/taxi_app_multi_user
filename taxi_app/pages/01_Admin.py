import streamlit as st
import sqlite3
from datetime import datetime
import pandas as pd
import os
import shutil
from typing import Optional

# ===== ПОЛУЧЕНИЕ ПУТЕЙ К ФАЙЛАМ ПОЛЬЗОВАТЕЛЯ =====
def get_user_dir() -> str:
    """Возвращает путь к папке текущего пользователя."""
    username = st.session_state.get("username")
    if not username:
        return "users/default"
    
    safe_name = "".join(c for c in username if c.isalnum() or c in ("_", "-"))
    user_dir = os.path.join("users", safe_name)
    if not os.path.exists(user_dir):
        os.makedirs(user_dir)
    return user_dir

def get_current_db_name() -> str:
    """Возвращает путь к базе данных текущего пользователя."""
    username = st.session_state.get("username")
    if not username:
        return "taxi_default.db"
    
    safe_name = "".join(c for c in username if c.isalnum() or c in ("_", "-"))
    db_path = os.path.join("users", safe_name, f"taxi_{safe_name}.db")
    return db_path

def get_backup_dir() -> str:
    """Возвращает путь к папке бэкапов пользователя."""
    user_dir = get_user_dir()
    backup_dir = os.path.join(user_dir, "backups")
    if not os.path.exists(backup_dir):
        os.makedirs(backup_dir)
    return backup_dir

def get_connection():
    return sqlite3.connect(get_current_db_name())

# ===== ПРОСТАЯ АВТОРИЗАЦИЯ ДЛЯ АДМИНКИ =====
ADMIN_PASSWORD = st.secrets.get("ADMIN_PASSWORD", "changeme")

rate_nal = 0.78
rate_card = 0.75

def check_admin_auth() -> bool:
    """Простая проверка пароля, состояние держим в session_state."""
    if "username" not in st.session_state:
        st.warning("⚠️ Сначала войдите в систему через главную страницу")
        return False
    
    if "admin_authenticated" not in st.session_state:
        st.session_state.admin_authenticated = False

    if st.session_state.admin_authenticated:
        return True

    st.subheader(f"🔐 Вход в режим администрирования — {st.session_state['username']}")
    with st.form("admin_login"):
        pwd = st.text_input("Пароль администратора", type="password")
        ok = st.form_submit_button("Войти", width='stretch')

    if ok:
        if pwd == ADMIN_PASSWORD:
            st.session_state.admin_authenticated = True
            st.success("✅ Доступ к администрированию открыт.")
            st.rerun()
        else:
            st.error("❌ Неверный пароль.")
            return False

    return False

# ===== БАЗА / ХЕЛПЕРЫ =====
def ensure_accum_row(cur):
    """Гарантируем, что есть строка driver_id=1 в accumulated_beznal."""
    cur.execute("SELECT id FROM accumulated_beznal WHERE driver_id = 1")
    row = cur.fetchone()
    if not row:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cur.execute(
            """
            INSERT INTO accumulated_beznal (driver_id, total_amount, last_updated)
            VALUES (1, 0, ?)
            """,
            (now,),
        )

def safe_str_cell(v, default=""):
    """Строка из ячейки: пустые/NaN -> default."""
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return default
    s = str(v).strip()
    return s if s != "" else default

def safe_num_cell(v, default=0.0):
    """Число из ячейки: пустые/NaN/мусор -> default."""
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return default
    s = str(v).strip().replace(",", ".")
    if s == "":
        return default
    try:
        return float(s)
    except ValueError:
        return default

def parse_date_to_iso(v) -> Optional[str]:
    """
    Универсальный парсер даты:
    возвращает строку YYYY-MM-DD или None, если распарсить не удалось.
    """
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None

    from datetime import date as _date, datetime as _dt
    
    if hasattr(v, 'strftime'):
        try:
            return v.strftime("%Y-%m-%d")
        except:
            pass

    if isinstance(v, (_dt, _date)):
        dt = v.date() if isinstance(v, _dt) else v
        return dt.strftime("%Y-%m-%d")

    s = str(v).strip()
    if not s:
        return None

    fmts = [
        "%Y-%m-%d",
        "%d.%m.%Y",
        "%d-%m-%Y",
        "%d/%m/%Y",
        "%Y/%m/%d",
        "%Y.%m.%d",
    ]
    for fmt in fmts:
        try:
            dt = _dt.strptime(s, fmt)
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            continue

    dt = pd.to_datetime(s, dayfirst=True, errors="coerce")
    if pd.isna(dt):
        return None
    return dt.date().strftime("%Y-%m-%d")

def get_accumulated_beznal():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT total_amount FROM accumulated_beznal WHERE driver_id = 1")
    row = cur.fetchone()
    conn.close()
    return float(row[0]) if row and row[0] is not None else 0.0

def recalc_full_db():
    """Пересчитать комиссию, total и безнал по всем заказам и обновить accumulated_beznal."""
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("SELECT id, type, amount, tips FROM orders")
    rows = cur.fetchall()

    for order_id, typ, amount, tips in rows:
        amount_f = float(amount or 0)
        tips_f = float(tips or 0)

        if typ == "нал":
            final_wo_tips = amount_f
            commission = amount_f * (1 - rate_nal)
            total = amount_f + tips_f
            beznal_added = -commission
        else:
            final_wo_tips = amount_f * rate_card
            commission = amount_f - final_wo_tips
            total = final_wo_tips + tips_f
            beznal_added = final_wo_tips

        cur.execute(
            """
            UPDATE orders
            SET commission = ?, total = ?, beznal_added = ?
            WHERE id = ?
            """,
            (commission, total, beznal_added, order_id),
        )

    cur.execute("SELECT COALESCE(SUM(beznal_added), 0) FROM orders")
    total_beznal = cur.fetchone()[0] or 0.0

    cur.execute("SELECT id FROM accumulated_beznal WHERE driver_id = 1")
    row = cur.fetchone()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if row:
        cur.execute(
            """
            UPDATE accumulated_beznal
            SET total_amount = ?, last_updated = ?
            WHERE driver_id = 1
            """,
            (total_beznal, now),
        )
    else:
        cur.execute(
            """
            INSERT INTO accumulated_beznal (driver_id, total_amount, last_updated)
            VALUES (1, ?, ?)
            """,
            (total_beznal, now),
        )

    conn.commit()
    conn.close()
    return total_beznal

def import_from_excel(uploaded_file) -> int:
    """
    Импорт из Excel/CSV.
    """
    try:
        if uploaded_file.name.lower().endswith(".csv"):
            df = pd.read_csv(uploaded_file)
        else:
            df = pd.read_excel(uploaded_file)

        df.columns = [str(c).strip() for c in df.columns]
        st.write("📋 Найдены колонки:", df.columns.tolist())

        if "Сумма" not in df.columns:
            st.error("❌ В файле нет колонки 'Сумма'.")
            return 0

        df["Сумма"] = df["Сумма"].replace(r"^\s*$", pd.NA, regex=True)
        df_clean = df[df["Сумма"].notna()].copy()

        st.write(f"📊 Найдено строк с данными (Сумма не пустая): {len(df_clean)}")
        st.write("Первые 5 строк:", df_clean.head())

        if len(df_clean) == 0:
            st.error("❌ В файле нет строк с суммой!")
            return 0

        imported = 0
        errors = 0

        conn = get_connection()
        cur = conn.cursor()
        ensure_accum_row(cur)

        for idx, row in df_clean.iterrows():
            try:
                raw_amount = row.get("Сумма")
                amount_f = safe_num_cell(raw_amount, default=None)
                if amount_f is None:
                    st.warning(
                        f"❌ Строка {idx}: пустая или некорректная сумма ({raw_amount!r}), пропускаю."
                    )
                    errors += 1
                    continue

                iso_date = parse_date_to_iso(row.get("Дата"))
                if not iso_date:
                    st.warning(
                        f"❌ Строка {idx}: не удалось разобрать дату при сумме {amount_f}, пропускаю."
                    )
                    errors += 1
                    continue

                cur.execute("SELECT id FROM shifts WHERE date = ?", (iso_date,))
                s = cur.fetchone()
                if s:
                    shift_id = s[0]
                else:
                    cur.execute(
                        "INSERT INTO shifts (date, is_open, opened_at, closed_at) "
                        "VALUES (?, 0, ?, ?)",
                        (iso_date, iso_date, iso_date),
                    )
                    shift_id = cur.lastrowid

                raw_type = row.get("Тип", "нал")
                raw_type_str = safe_str_cell(raw_type, default="нал").lower()
                if raw_type_str in ("безнал", "card", "карта"):
                    typ = "карта"
                else:
                    typ = "нал"

                raw_tips = row.get("Чаевые")
                tips_f = safe_num_cell(raw_tips, default=0.0)

                if typ == "нал":
                    final_wo_tips = amount_f
                    commission = amount_f * (1 - rate_nal)
                    total = amount_f + tips_f
                    beznal_added = -commission
                else:
                    final_wo_tips = amount_f * rate_card
                    commission = amount_f - final_wo_tips
                    total = final_wo_tips + tips_f
                    beznal_added = final_wo_tips

                cur.execute(
                    """
                    INSERT INTO orders (shift_id, type, amount, tips, commission, total, beznal_added, order_time)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        shift_id,
                        typ,
                        amount_f,
                        tips_f,
                        commission,
                        total,
                        beznal_added,
                        None,
                    ),
                )

                if beznal_added != 0:
                    cur.execute(
                        """
                        UPDATE accumulated_beznal
                        SET total_amount = total_amount + ?
                        WHERE driver_id = 1
                        """,
                        (beznal_added,),
                    )

                imported += 1
            except Exception as e:
                st.warning(f"⚠️ Строка {idx}: {e}")
                errors += 1
                continue

        conn.commit()
        conn.close()

        if imported > 0:
            st.success(f"✅ Импортировано: {imported} заказов")
        if errors > 0:
            st.warning(f"⚠️ Ошибок при импорте: {errors}")
        return imported

    except Exception as e:
        st.error(f"❌ Ошибка чтения файла: {e}")
        return 0

def reset_db():
    """Полный сброс базы и создание пустых таблиц."""
    db_path = get_current_db_name()
    
    try:
        backup_path = create_backup()
        st.info(f"📦 Создан бэкап перед сбросом: {os.path.basename(backup_path)}")
    except:
        pass
    
    if os.path.exists(db_path):
        os.remove(db_path)

    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
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

    cur.execute(
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

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS accumulated_beznal (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            driver_id INTEGER DEFAULT 1,
            total_amount REAL DEFAULT 0,
            last_updated TEXT
        )
        """
    )

    ensure_accum_row(cur)

    conn.commit()
    conn.close()

def import_from_gsheet(sheet_url: str) -> int:
    """
    Импортирует заказы из Google Sheets.
    """
    try:
        if "/edit" in sheet_url:
            base_url = sheet_url.split("/edit")[0]
            csv_url = f"{base_url}/export?format=csv"
        else:
            csv_url = sheet_url.replace("/edit?gid=", "/export?format=csv&gid=")
        
        df = pd.read_csv(csv_url)
    except Exception as e:
        st.error(f"❌ Не удалось прочитать данные из Google Sheets: {e}")
        return 0

    df.columns = [str(c).strip() for c in df.columns]
    st.write("📋 Найдены колонки в Google Sheets:", df.columns.tolist())

    if "Сумма" not in df.columns:
        st.error("❌ В таблице нет колонки 'Сумма'.")
        return 0

    df["Сумма"] = df["Сумма"].replace(r"^\s*$", pd.NA, regex=True)
    df_clean = df[df["Сумма"].notna()].copy()

    st.write(f"📊 Найдено строк с данными (Сумма не пустая): {len(df_clean)}")
    st.write("Первые 5 строк:", df_clean.head())

    if len(df_clean) == 0:
        st.error("❌ В таблице нет строк с суммой!")
        return 0

    imported = 0
    errors = 0

    conn = get_connection()
    cur = conn.cursor()
    ensure_accum_row(cur)

    for idx, row in df_clean.iterrows():
        try:
            raw_amount = row.get("Сумма")
            amount_f = safe_num_cell(raw_amount, default=None)
            if amount_f is None:
                st.warning(
                    f"❌ Строка {idx}: пустая или некорректная сумма ({raw_amount!r}), пропускаю."
                )
                errors += 1
                continue

            iso_date = parse_date_to_iso(row.get("Дата"))
            if not iso_date:
                st.warning(
                    f"❌ Строка {idx}: не удалось разобрать дату при сумме {amount_f}, пропускаю."
                )
                errors += 1
                continue

            cur.execute("SELECT id FROM shifts WHERE date = ?", (iso_date,))
            s = cur.fetchone()
            if s:
                shift_id = s[0]
            else:
                cur.execute(
                    "INSERT INTO shifts (date, is_open, opened_at, closed_at) "
                    "VALUES (?, 0, ?, ?)",
                    (iso_date, iso_date, iso_date),
                )
                shift_id = cur.lastrowid

            raw_type = row.get("Тип", "нал")
            raw_type_str = safe_str_cell(raw_type, default="нал").lower()
            if raw_type_str in ("безнал", "card", "карта"):
                typ = "карта"
            else:
                typ = "нал"

            raw_tips = row.get("Чаевые")
            tips_f = safe_num_cell(raw_tips, default=0.0)

            if typ == "нал":
                final_wo_tips = amount_f
                commission = amount_f * (1 - rate_nal)
                total = amount_f + tips_f
                beznal_added = -commission
            else:
                final_wo_tips = amount_f * rate_card
                commission = amount_f - final_wo_tips
                total = final_wo_tips + tips_f
                beznal_added = final_wo_tips

            cur.execute(
                """
                INSERT INTO orders (shift_id, type, amount, tips, commission, total, beznal_added, order_time)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    shift_id,
                    typ,
                    amount_f,
                    tips_f,
                    commission,
                    total,
                    beznal_added,
                    None,
                ),
            )

            if beznal_added != 0:
                cur.execute(
                    """
                    UPDATE accumulated_beznal
                    SET total_amount = total_amount + ?
                    WHERE driver_id = 1
                    """,
                    (beznal_added,),
                )

            imported += 1
        except Exception as e:
            st.warning(f"⚠️ Строка {idx}: {e}")
            errors += 1
            continue

    conn.commit()
    conn.close()

    if imported > 0:
        st.success(f"✅ Импортировано из Google Sheets: {imported} заказов")
    if errors > 0:
        st.warning(f"⚠️ Ошибок при импорте: {errors}")
    return imported

def normalize_shift_dates():
    """
    Привести все даты в shifts к формату YYYY-MM-DD.
    """
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, date FROM shifts")
    rows = cur.fetchall()

    fixed = 0
    skipped = 0

    for shift_id, date_str in rows:
        new_val = parse_date_to_iso(date_str)
        s = str(date_str).strip() if date_str is not None else ""
        if new_val and new_val != s:
            cur.execute("UPDATE shifts SET date = ? WHERE id = ?", (new_val, shift_id))
            fixed += 1
        else:
            skipped += 1

    conn.commit()
    conn.close()
    return fixed, skipped

# ===== БЭКАПЫ =====
def create_backup() -> str:
    """
    Делает копию DB_NAME в папку backups пользователя.
    """
    backup_dir = get_backup_dir()
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    username = st.session_state.get("username", "unknown")
    backup_name = f"taxi_{username}_backup_{ts}.db"
    backup_path = os.path.join(backup_dir, backup_name)
    shutil.copy2(get_current_db_name(), backup_path)
    return backup_path

def list_backups() -> list[tuple[str, str]]:
    """
    Возвращает список (метка_для_показа, полный_путь) для всех файлов бэкапа.
    """
    backup_dir = get_backup_dir()
    if not os.path.isdir(backup_dir):
        return []

    files = [
        os.path.join(backup_dir, f)
        for f in os.listdir(backup_dir)
        if f.endswith(".db")
    ]
    if not files:
        return []

    files.sort(key=lambda p: os.path.getmtime(p), reverse=True)

    result = []
    for path in files:
        mtime = datetime.fromtimestamp(os.path.getmtime(path))
        label = f"{mtime.strftime('%d.%m.%Y %H:%M:%S')} — {os.path.basename(path)}"
        result.append((label, path))
    return result

def restore_backup(path: str):
    """
    Перезаписывает основную базу выбранным файлом бэкапа.
    """
    if not os.path.isfile(path):
        raise FileNotFoundError(f"Файл бэкапа не найден: {path}")
    shutil.copy2(path, get_current_db_name())

# ===== UI / ЗАПУСК СТРАНИЦЫ =====
st.set_page_config(page_title="Администрирование", page_icon="🛠", layout="centered")
st.title(f"🛠 Администрирование — {st.session_state.get('username', '—')}")

# Информация в сайдбаре
with st.sidebar:
    st.markdown(f"**Пользователь:** {st.session_state.get('username', '—')}")
    st.markdown(f"**Папка:** users/{st.session_state.get('username', 'default')}")
    st.markdown(f"**База:** {os.path.basename(get_current_db_name())}")
    st.markdown(f"**Бэкапы:** {os.path.basename(get_backup_dir())}")
    st.markdown("---")
    st.markdown("**Страницы:**")
    st.markdown("- 🚕 [Главная](/.)")
    st.markdown("- 📊 [Отчёты](/01_%F0%9F%93%8A_Reports)")
    st.markdown("- 🛠 [Администрирование](/02_%F0%9F%9B%A0_Admin) (текущая)")
    st.markdown("---")

if not check_admin_auth():
    st.stop()

# Создаём вкладки для лучшей организации
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "📥 Импорт", 
    "🔄 Пересчёт", 
    "🗄 Бэкапы", 
    "🔧 Инструменты",
    "⚠️ Сброс"
])

with tab1:
    st.header("📥 Импорт данных")
    
    with st.expander("📄 Импорт из Google Sheets", expanded=False):
        st.caption(
            "Таблица должна быть доступна по ссылке (Anyone with link, Viewer). "
            "Формат колонок: Дата, Тип, Сумма, Чаевые."
        )

        default_url = (
            "https://docs.google.com/spreadsheets/d/"
            "1USdDnw5OnzcIgC0mBVWGKURDJox4ncc5SAUQn-euS3Q/edit?gid=0#gid=0"
        )

        sheet_url = st.text_input("Ссылка на Google Sheets", value=default_url)

        if st.button("🚀 Импортировать из Google Sheets", width='stretch'):
            with st.spinner("Импортируем данные..."):
                imported = import_from_gsheet(sheet_url)
                if imported > 0:
                    st.success(f"✅ Импортировано {imported} заказов")
                    st.info("📊 Проверьте данные в разделе Отчёты")

    with st.expander("📂 Импорт из файла (Excel / CSV)", expanded=True):
        uploaded_file = st.file_uploader(
            "Выберите файл Excel или CSV", type=["xlsx", "xls", "csv"]
        )
        if uploaded_file is not None:
            if st.button("📤 Импортировать из файла", width='stretch'):
                with st.spinner("Импортируем данные..."):
                    imported = import_from_excel(uploaded_file)
                    if imported > 0:
                        st.success(f"✅ Импортировано {imported} заказов")
                        st.info("📊 Проверьте данные в разделе Отчёты")

with tab2:
    st.header("🔄 Пересчёт данных")
    
    with st.expander("🔄 Пересчитать комиссии и безнал по всем заказам", expanded=True):
        current = get_accumulated_beznal()
        st.metric("Текущий накопленный безнал", f"{current:.0f} ₽")
        
        if st.button("🔄 Пересчитать всё", width='stretch', type="primary"):
            with st.spinner("Пересчитываем данные..."):
                new_total = recalc_full_db()
                delta = new_total - current
                st.success(f"✅ Пересчёт завершён!")
                st.metric("Новый накопленный безнал", f"{new_total:.0f} ₽", delta=f"{delta:.0f} ₽")

    with st.expander("✏️ Установить накопленный безнал вручную", expanded=False):
        current = get_accumulated_beznal()
        st.write(f"Сейчас в базе: {current:.0f} ₽")
        
        if current < 0:
            st.warning(f"⚠️ Текущее значение отрицательное: {current:.0f} ₽")
        
        new_value = st.number_input(
            "Новое значение накопленного безнала, ₽",
            min_value=None,
            step=100.0,
            format="%.0f",
            value=float(current),
        )

        if st.button("💾 Сохранить это значение в базу", width='stretch', type="primary"):
            conn = get_connection()
            cur = conn.cursor()
            ensure_accum_row(cur)
            cur.execute(
                """
                UPDATE accumulated_beznal
                SET total_amount = ?, last_updated = ?
                WHERE driver_id = 1
                """,
                (new_value, datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
            )
            conn.commit()
            conn.close()
            st.success(f"✅ В базе теперь записано: {new_value:.0f} ₽")
            st.cache_data.clear()
            st.rerun()

with tab3:
    st.header("🗄 Бэкап и восстановление")
    
    with st.expander("💾 Управление бэкапами", expanded=True):
        st.caption(
            "Бэкап создаёт копию файла базы данных в папке пользователя. "
            "Восстановление перезапишет текущую базу выбранным бэкапом."
        )

        col1, col2 = st.columns(2)

        with col1:
            if st.button("📦 Сделать бэкап сейчас", key="backup_now", width='stretch', type="primary"):
                try:
                    backup_path = create_backup()
                    file_size = os.path.getsize(backup_path) / 1024
                    st.success(
                        f"✅ Бэкап создан: {os.path.basename(backup_path)}\n"
                        f"📁 Папка: {os.path.dirname(backup_path)}\n"
                        f"📦 Размер: {file_size:.1f} KB"
                    )
                except Exception as e:
                    st.error(f"❌ Не удалось создать бэкап: {e}")

        with col2:
            backups = list_backups()
            if not backups:
                st.info("📭 Пока нет ни одного файла бэкапа.")
            else:
                labels = [lbl for (lbl, _) in backups]
                paths = {lbl: p for (lbl, p) in backups}
                selected_label = st.selectbox(
                    "Выберите бэкап для восстановления",
                    options=labels,
                    key="backup_select",
                )

                # Информация о выбранном бэкапе
                selected_path = paths[selected_label]
                file_size = os.path.getsize(selected_path) / 1024
                st.caption(f"📦 Размер: {file_size:.1f} KB")

                st.warning(
                    "⚠️ **ВНИМАНИЕ**: при восстановлении текущая база будет полностью "
                    "перезаписана содержимым выбранного бэкапа."
                )

                col_restore, col_delete = st.columns(2)
                with col_restore:
                    if st.button("🔄 Восстановить", key="backup_restore", width='stretch', type="primary"):
                        try:
                            restore_backup(selected_path)
                            st.success(f"✅ База восстановлена из бэкапа")
                            st.info("🔄 Перезапустите приложение для обновления данных")
                            st.cache_data.clear()
                        except Exception as e:
                            st.error(f"❌ Ошибка при восстановлении: {e}")
                
                with col_delete:
                    if st.button("🗑 Удалить бэкап", key="backup_delete", width='stretch'):
                        try:
                            os.remove(selected_path)
                            st.success(f"✅ Бэкап удалён")
                            st.rerun()
                        except Exception as e:
                            st.error(f"❌ Ошибка при удалении: {e}")

with tab4:
    st.header("🔧 Инструменты")
    
    with st.expander("🗓 Нормализовать даты смен", expanded=True):
        st.caption(
            "Исправляет формат дат в базе данных. "
            "Все даты будут приведены к виду ГГГГ-ММ-ДД."
        )
        if st.button("🛠 Исправить формат дат", width='stretch'):
            fixed, skipped = normalize_shift_dates()
            st.success(f"✅ Исправлено дат: {fixed}, без изменений: {skipped}")

    with st.expander("📊 Статистика базы данных", expanded=False):
        try:
            db_path = get_current_db_name()
            db_size = os.path.getsize(db_path) / 1024
            
            conn = get_connection()
            cur = conn.cursor()
            
            cur.execute("SELECT COUNT(*) FROM shifts")
            shifts_count = cur.fetchone()[0]
            
            cur.execute("SELECT COUNT(*) FROM orders")
            orders_count = cur.fetchone()[0]
            
            cur.execute("SELECT COUNT(*) FROM shifts WHERE is_open = 1")
            open_shifts = cur.fetchone()[0]
            
            conn.close()
            
            st.metric("Размер базы", f"{db_size:.1f} KB")
            st.metric("Всего смен", f"{shifts_count}")
            st.metric("Открытых смен", f"{open_shifts}")
            st.metric("Всего заказов", f"{orders_count}")
            
        except Exception as e:
            st.error(f"Ошибка при получении статистики: {e}")

with tab5:
    st.header("⚠️ Опасная зона")
    
    with st.expander("⚠️ Полный сброс базы", expanded=True):
        st.error(
            "🚨 **ОПАСНО**: Эта операция удалит все смены и заказы и создаст пустую базу заново. "
            "Используйте только если точно понимаете, что делаете."
        )
        
        col1, col2 = st.columns(2)
        with col1:
            confirm = st.checkbox("Я понимаю, что все данные будут безвозвратно удалены")
        with col2:
            confirm2 = st.checkbox("Я сделал бэкап перед сбросом")
        
        if confirm and confirm2:
            if st.button("🗑 УДАЛИТЬ БАЗУ И СОЗДАТЬ ЗАНОВО", type="primary", width='stretch'):
                with st.spinner("Сбрасываем базу данных..."):
                    reset_db()
                    st.success("✅ База сброшена и создана заново.")
                    st.info("🔄 Перезапустите приложение для обновления данных")
                    st.cache_data.clear()
        else:
            st.info("Подтвердите понимание и наличие бэкапа для активации кнопки сброса")

# Информация в футере
st.markdown("---")
st.caption(f"📁 Все данные хранятся в папке: {get_user_dir()}")
st.caption(f"🕒 Последнее обновление: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}")