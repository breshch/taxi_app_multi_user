import streamlit as st
import sqlite3
from datetime import datetime
import pandas as pd
import os
import shutil
from typing import Optional

# ===== ОБЩИЕ ФУНКЦИИ =====
def get_user_dir() -> str:
    username = st.session_state.get("username")
    if not username:
        return "users/default"
    safe_name = "".join(c for c in username if c.isalnum() or c in ("_", "-"))
    user_dir = os.path.join("users", safe_name)
    if not os.path.exists(user_dir):
        os.makedirs(user_dir)
    return user_dir

def get_current_db_name() -> str:
    username = st.session_state.get("username")
    if not username:
        return "taxi_default.db"
    safe_name = "".join(c for c in username if c.isalnum() or c in ("_", "-"))
    db_path = os.path.join("users", safe_name, f"taxi_{safe_name}.db")
    return db_path

def get_backup_dir() -> str:
    user_dir = get_user_dir()
    backup_dir = os.path.join(user_dir, "backups")
    if not os.path.exists(backup_dir):
        os.makedirs(backup_dir)
    return backup_dir

def get_connection():
    return sqlite3.connect(get_current_db_name())

# ===== КОНСТАНТЫ =====
rate_nal = 0.78
rate_card = 0.75

# ===== ФУНКЦИИ ДЛЯ ОТЧЁТОВ =====
@st.cache_data(ttl=300)
def get_available_year_months_cached():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT DISTINCT strftime('%Y-%m', date)
        FROM shifts
        WHERE date IS NOT NULL AND TRIM(date) <> ''
        AND is_open = 0
        AND EXISTS (SELECT 1 FROM orders o WHERE o.shift_id = shifts.id)
        ORDER BY 1 DESC
    """)
    rows = cur.fetchall()
    conn.close()
    res = []
    for (val,) in rows:
        if val is None: continue
        s = str(val)
        if len(s) >= 7 and s[0:4].isdigit() and s[5:7].isdigit():
            res.append(s)
    return res

@st.cache_data(ttl=300)
def get_month_totals_cached(year_month: str):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT id FROM shifts
        WHERE date LIKE ? AND is_open = 0
        AND EXISTS (SELECT 1 FROM orders o WHERE o.shift_id = shifts.id)
    """, (f"{year_month}%",))
    shifts = cur.fetchall()
    
    total_nal = 0.0; total_card = 0.0; total_tips = 0.0; total_beznal_add = 0.0

    for (shift_id,) in shifts:
        cur.execute("SELECT type, SUM(total - tips) FROM orders WHERE shift_id = ? GROUP BY type", (shift_id,))
        for typ, summ in cur.fetchall():
            summ = summ or 0.0
            # ИСПРАВЛЕНО: убраны пробелы
            if typ == "нал": total_nal += summ
            elif typ == "карта": total_card += summ

        cur.execute("SELECT SUM(tips), SUM(beznal_added) FROM orders WHERE shift_id = ?", (shift_id,))
        tips_sum, beznal_sum = cur.fetchone()
        total_tips += tips_sum or 0.0
        total_beznal_add += beznal_sum or 0.0

    conn.close()
    return {
        "нал": total_nal, "карта": total_card, "чаевые": total_tips,
        "безнал_добавлено": total_beznal_add,
        "всего": total_nal + total_card + total_tips,
        "смен": len(shifts),
    }

@st.cache_data(ttl=300)
def get_month_shifts_details_cached(year_month: str) -> pd.DataFrame:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT id, date, km, fuel_liters, fuel_price
        FROM shifts
        WHERE date LIKE ? AND is_open = 0
        AND EXISTS (SELECT 1 FROM orders o WHERE o.shift_id = shifts.id)
        ORDER BY date
    """, (f"{year_month}%",))
    shifts = cur.fetchall()
    rows = []
    
    for shift_id, date_str, km, fuel_liters, fuel_price in shifts:
        cur.execute("SELECT type, SUM(total - tips) FROM orders WHERE shift_id = ? GROUP BY type", (shift_id,))
        by_type = {t: s for t, s in cur.fetchall()}
        cur.execute("SELECT SUM(tips), SUM(beznal_added) FROM orders WHERE shift_id = ?", (shift_id,))
        tips_sum, beznal_sum = cur.fetchone()
        
        # ИСПРАВЛЕНО: убраны пробелы
        nal = by_type.get("нал", 0.0) or 0.0
        card = by_type.get("карта", 0.0) or 0.0
        total = nal + card + (tips_sum or 0.0)

        try: display_date = datetime.strptime(date_str, "%Y-%m-%d").strftime("%d.%m.%Y")
        except: display_date = date_str

        rows.append({
            "Дата": display_date, "date_iso": date_str,
            "Нал": nal, "Карта": card, "Чаевые": tips_sum or 0.0,
            "Δ безнал": beznal_sum or 0.0, "Км": km or 0,
            "Литры": fuel_liters or 0.0, "Цена": fuel_price or 0.0, "Всего": total,
        })

    conn.close()
    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.sort_values("date_iso").drop("date_iso", axis=1)
        df.index = list(range(1, len(df) + 1))
    return df

def get_closed_shift_id_by_date(date_str: str):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT id FROM shifts WHERE date = ? AND is_open = 0 ORDER BY id LIMIT 1", (date_str,))
    row = cur.fetchone()
    conn.close()
    return row[0] if row else None

def get_shift_orders_df(shift_id: int | None) -> pd.DataFrame:
    if shift_id is None: return pd.DataFrame()
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT type, amount, tips, beznal_added, total, order_time FROM orders WHERE shift_id = ? ORDER BY id", (shift_id,))
    rows = cur.fetchall()
    conn.close()
    data = []
    for typ, amount, tips, beznal_added, total, order_time in rows:
        data.append({
            "Время": order_time or " ",
            # ИСПРАВЛЕНО
            "Тип": "💵 Нал" if typ == "нал" else "💳 Карта",
            "Сумма": amount or 0.0, "Чаевые": tips or 0.0,
            "Δ безнал": beznal_added or 0.0, "Вам": total or 0.0,
        })
    df = pd.DataFrame(data)
    if not df.empty: df.index = list(range(1, len(df) + 1))
    return df

def get_orders_by_hour(date_str: str) -> pd.DataFrame:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT o.order_time FROM orders o
        JOIN shifts s ON o.shift_id = s.id
        WHERE s.date = ? AND s.is_open = 0 AND o.order_time IS NOT NULL
    """, (date_str,))
    times = [r[0] for r in cur.fetchall()]
    conn.close()
    
    if not times:
        return pd.DataFrame({"Час": [f"{h:02d}:00" for h in range(24)], "Заказов": [0] * 24})

    hours = []
    for t in times:
        try:
            h = int(str(t)[0:2])
            if 0 <= h <= 23: hours.append(h)
        except: continue

    if not hours:
        return pd.DataFrame({"Час": [f"{h:02d}:00" for h in range(24)], "Заказов": [0] * 24})

    s = pd.Series(hours)
    counts = s.value_counts().sort_index()
    df = pd.DataFrame({"Час": counts.index, "Заказов": counts.values})
    full = pd.DataFrame({"Час": list(range(24))})
    df = full.merge(df, on="Час", how="left").fillna(0)
    df["Заказов"] = df["Заказов"].astype(int)
    df["Час"] = df["Час"].apply(lambda h: f"{h:02d}:00")
    return df

def format_month_option(s) -> str:
    month_name = {1:"январь", 2:"февраль", 3:"март", 4:"апрель", 5:"май", 6:"июнь", 7:"июль", 8:"август", 9:"сентябрь", 10:"октябрь", 11:"ноябрь", 12:"декабрь"}
    if s is None: return "—"
    s_str = str(s)
    if len(s_str) >= 7:
        mm = s_str[5:7]
        if mm.isdigit(): return f"{s_str} ({month_name.get(int(mm), '')})"
    return s_str or "—"

# ===== АДМИНИСТРИРОВАНИЕ =====
def get_accumulated_beznal():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT total_amount FROM accumulated_beznal WHERE driver_id = 1")
    row = cur.fetchone()
    conn.close()
    return float(row[0]) if row and row[0] is not None else 0.0

def recalc_full_db():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, type, amount, tips FROM orders")
    rows = cur.fetchall()
    for order_id, typ, amount, tips in rows:
        amount_f = float(amount or 0); tips_f = float(tips or 0)
        if typ == "нал": # ИСПРАВЛЕНО
            commission = amount_f * (1 - rate_nal)
            total = amount_f + tips_f
            beznal_added = -commission
        else:
            final_wo_tips = amount_f * rate_card
            commission = amount_f - final_wo_tips
            total = final_wo_tips + tips_f
            beznal_added = final_wo_tips
        cur.execute("UPDATE orders SET commission=?, total=?, beznal_added=? WHERE id=?", (commission, total, beznal_added, order_id))
    
    cur.execute("SELECT COALESCE(SUM(beznal_added), 0) FROM orders")
    total_beznal = cur.fetchone()[0] or 0.0
    cur.execute("SELECT id FROM accumulated_beznal WHERE driver_id = 1")
    row = cur.fetchone()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if row:
        cur.execute("UPDATE accumulated_beznal SET total_amount=?, last_updated=? WHERE driver_id=1", (total_beznal, now))
    else:
        cur.execute("INSERT INTO accumulated_beznal (driver_id, total_amount, last_updated) VALUES (1, ?, ?)", (total_beznal, now))
    conn.commit()
    conn.close()
    return total_beznal

def safe_str_cell(v, default=""):
    if v is None or (isinstance(v, float) and pd.isna(v)): return default
    s = str(v).strip()
    return s if s != "" else default

def safe_num_cell(v, default=0.0):
    if v is None or (isinstance(v, float) and pd.isna(v)): return default
    s = str(v).strip().replace(",", ".")
    if s == "": return default
    try: return float(s)
    except ValueError: return default

def parse_date_to_iso(v) -> Optional[str]:
    if v is None or (isinstance(v, float) and pd.isna(v)): return None
    from datetime import date as _date, datetime as _dt
    if hasattr(v, 'strftime'):
        try: return v.strftime("%Y-%m-%d")
        except: pass
    if isinstance(v, (_dt, _date)):
        dt = v.date() if isinstance(v, _dt) else v
        return dt.strftime("%Y-%m-%d")
    s = str(v).strip()
    if not s: return None
    fmts = ["%Y-%m-%d", "%d.%m.%Y", "%d-%m-%Y", "%d/%m/%Y", "%Y/%m/%d", "%Y.%m.%d"]
    for fmt in fmts:
        try: return _dt.strptime(s, fmt).strftime("%Y-%m-%d")
        except ValueError: continue
    dt = pd.to_datetime(s, dayfirst=True, errors="coerce")
    if pd.isna(dt): return None
    return dt.date().strftime("%Y-%m-%d")

def import_from_excel(uploaded_file) -> int:
    try:
        if uploaded_file.name.lower().endswith(".csv"): df = pd.read_csv(uploaded_file)
        else: df = pd.read_excel(uploaded_file)
        df.columns = [str(c).strip() for c in df.columns]
        if "Сумма" not in df.columns:
            st.error("❌ В файле нет колонки 'Сумма'."); return 0
        df["Сумма"] = df["Сумма"].replace(r"^\s*$", pd.NA, regex=True)
        df_clean = df[df["Сумма"].notna()].copy()
        if len(df_clean) == 0:
            st.error("❌ В файле нет строк с суммой!"); return 0
        
        imported = 0; errors = 0
        conn = get_connection(); cur = conn.cursor()
        for idx, row in df_clean.iterrows():
            try:
                amount_f = safe_num_cell(row.get("Сумма"), default=None)
                if amount_f is None: errors += 1; continue
                iso_date = parse_date_to_iso(row.get("Дата"))
                if not iso_date: errors += 1; continue
                
                cur.execute("SELECT id FROM shifts WHERE date = ?", (iso_date,))
                s = cur.fetchone()
                if s: shift_id = s[0]
                else:
                    cur.execute("INSERT INTO shifts (date, is_open, opened_at, closed_at) VALUES (?, 0, ?, ?)", (iso_date, iso_date, iso_date))
                    shift_id = cur.lastrowid
                
                raw_type_str = safe_str_cell(row.get("Тип", "нал"), default="нал").lower()
                typ = "карта" if raw_type_str in ("безнал", "card", "карта") else "нал"
                tips_f = safe_num_cell(row.get("Чаевые"), default=0.0)
                
                if typ == "нал":
                    commission = amount_f * (1 - rate_nal); total = amount_f + tips_f; beznal_added = -commission
                else:
                    final_wo_tips = amount_f * rate_card; commission = amount_f - final_wo_tips
                    total = final_wo_tips + tips_f; beznal_added = final_wo_tips
                
                cur.execute("INSERT INTO orders (shift_id, type, amount, tips, commission, total, beznal_added, order_time) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                            (shift_id, typ, amount_f, tips_f, commission, total, beznal_added, None))
                if beznal_added != 0:
                    cur.execute("UPDATE accumulated_beznal SET total_amount = total_amount + ? WHERE driver_id = 1", (beznal_added,))
                imported += 1
            except Exception: errors += 1; continue
        conn.commit(); conn.close()
        return imported
    except Exception as e:
        st.error(f"❌ Ошибка чтения файла: {e}"); return 0

def import_from_gsheet(sheet_url: str) -> int:
    try:
        if "/edit" in sheet_url:
            base_url = sheet_url.split("/edit")[0]
            csv_url = f"{base_url}/export?format=csv"
        else:
            csv_url = sheet_url.replace("/edit?gid=", "/export?format=csv&gid=")
        df = pd.read_csv(csv_url)
        return import_from_excel(df)
    except Exception as e:
        st.error(f"❌ Ошибка: {e}"); return 0

def create_backup() -> str:
    backup_dir = get_backup_dir()
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    username = st.session_state.get("username", "unknown")
    backup_name = f"taxi_{username}_backup_{ts}.db"
    backup_path = os.path.join(backup_dir, backup_name)
    shutil.copy2(get_current_db_name(), backup_path)
    return backup_path

def list_backups() -> list[tuple[str, str]]:
    backup_dir = get_backup_dir()
    if not os.path.isdir(backup_dir): return []
    files = [os.path.join(backup_dir, f) for f in os.listdir(backup_dir) if f.endswith(".db")]
    files.sort(key=lambda p: os.path.getmtime(p), reverse=True)
    result = []
    for path in files:
        mtime = datetime.fromtimestamp(os.path.getmtime(path))
        label = f"{mtime.strftime('%d.%m.%Y %H:%M:%S')} — {os.path.basename(path)}"
        result.append((label, path))
    return result

def restore_backup(path: str):
    if not os.path.isfile(path): raise FileNotFoundError(f"Файл бэкапа не найден: {path}")
    shutil.copy2(path, get_current_db_name())

def reset_db():
    db_path = get_current_db_name()
    if os.path.exists(db_path): os.remove(db_path)

def normalize_shift_dates():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, date FROM shifts")
    rows = cur.fetchall()
    fixed = 0; skipped = 0
    for shift_id, date_str in rows:
        new_val = parse_date_to_iso(date_str)
        s = str(date_str).strip() if date_str is not None else ""
        if new_val and new_val != s:
            cur.execute("UPDATE shifts SET date = ? WHERE id = ?", (new_val, shift_id))
            fixed += 1
        else: skipped += 1
    conn.commit(); conn.close()
    return fixed, skipped