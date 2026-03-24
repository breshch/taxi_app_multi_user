import streamlit as st
import sqlite3
from datetime import datetime
import pandas as pd
import os
from typing import Optional

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

def get_connection():
    conn = sqlite3.connect(get_current_db_name())
    conn.execute("""
        CREATE TABLE IF NOT EXISTS shifts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL, km INTEGER DEFAULT 0,
            fuel_liters REAL DEFAULT 0, fuel_price REAL DEFAULT 0,
            is_open INTEGER DEFAULT 1, opened_at TEXT, closed_at TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT, shift_id INTEGER,
            type TEXT NOT NULL, amount REAL NOT NULL, tips REAL DEFAULT 0,
            commission REAL NOT NULL, total REAL NOT NULL,
            beznal_added REAL DEFAULT 0, order_time TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS extra_expenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT, shift_id INTEGER,
            amount REAL DEFAULT 0, description TEXT, created_at TEXT
        )
    """)
    conn.execute("""
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
            (datetime.now().strftime("%Y-%m-%d %H:%M:%S"),)
        )
    conn.commit()
    return conn

rate_nal = 0.78
rate_card = 0.75

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
        if val is None:
            continue
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
    
    total_nal = 0.0
    total_card = 0.0
    total_tips = 0.0
    total_beznal_add = 0.0

    for (shift_id,) in shifts:
        cur.execute("SELECT type, SUM(total - tips) FROM orders WHERE shift_id = ? GROUP BY type", (shift_id,))
        for typ, summ in cur.fetchall():
            summ = summ or 0.0
            if typ == "нал":
                total_nal += summ
            elif typ == "карта":
                total_card += summ
        cur.execute("SELECT SUM(tips), SUM(beznal_added) FROM orders WHERE shift_id = ?", (shift_id,))
        tips_sum, beznal_sum = cur.fetchone()
        total_tips += tips_sum or 0.0
        total_beznal_add += beznal_sum or 0.0

    conn.close()
    return {
        "нал": total_nal,
        "карта": total_card,
        "чаевые": total_tips,
        "безнал_добавлено": total_beznal_add,
        "всего": total_nal + total_card + total_tips,
        "смен": len(shifts),
    }

@st.cache_data(ttl=300)
def get_month_statistics(year_month: str):
    conn = get_connection()
    cur = conn.cursor()
    
    cur.execute("SELECT COUNT(*) FROM shifts WHERE date LIKE ? AND is_open = 0", (f"{year_month}%",))
    shifts_count = cur.fetchone()[0] or 0
    
    cur.execute("SELECT COUNT(*) FROM orders o JOIN shifts s ON o.shift_id = s.id WHERE s.date LIKE ? AND s.is_open = 0", (f"{year_month}%",))
    orders_count = cur.fetchone()[0] or 0
    
    cur.execute("SELECT AVG(total) FROM orders o JOIN shifts s ON o.shift_id = s.id WHERE s.date LIKE ? AND s.is_open = 0", (f"{year_month}%",))
    avg_check = cur.fetchone()[0] or 0.0
    
    cur.execute("SELECT SUM(fuel_liters * fuel_price) FROM shifts WHERE date LIKE ? AND is_open = 0", (f"{year_month}%",))
    fuel_cost = cur.fetchone()[0] or 0.0
    
    cur.execute("SELECT SUM(e.amount) FROM extra_expenses e JOIN shifts s ON e.shift_id = s.id WHERE s.date LIKE ? AND s.is_open = 0", (f"{year_month}%",))
    extra_expenses = cur.fetchone()[0] or 0.0
    
    totals = get_month_totals_cached(year_month)
    income = totals.get("всего", 0)
    
    total_expenses = fuel_cost + extra_expenses
    profit = income - total_expenses
    profitability = (profit / income * 100) if income > 0 else 0
    
    conn.close()
    
    return {
        "смен": shifts_count,
        "заказов": orders_count,
        "средний_чек": avg_check,
        "бензин": fuel_cost,
        "расходы": total_expenses,
        "прибыль": profit,
        "рентабельность": profitability
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
        
        nal = by_type.get("нал", 0.0) or 0.0
        card = by_type.get("карта", 0.0) or 0.0
        total = nal + card + (tips_sum or 0.0)

        try:
            display_date = datetime.strptime(date_str, "%Y-%m-%d").strftime("%d.%m.%Y")
        except:
            display_date = date_str

        rows.append({
            "Дата": display_date,
            "date_iso": date_str,
            "Нал": nal,
            "Карта": card,
            "Чаевые": tips_sum or 0.0,
            "Δ безнал": beznal_sum or 0.0,
            "Км": km or 0,
            "Литры": fuel_liters or 0.0,
            "Цена": fuel_price or 0.0,
            "Всего": total,
        })

    conn.close()
    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.sort_values("date_iso").drop("date_iso", axis=1)
        df.index = list(range(1, len(df) + 1))
    return df

def format_month_option(s) -> str:
    month_name = {
        1: "январь", 2: "февраль", 3: "март", 4: "апрель",
        5: "май", 6: "июнь", 7: "июль", 8: "август",
        9: "сентябрь", 10: "октябрь", 11: "ноябрь", 12: "декабрь"
    }
    if s is None:
        return "—"
    s_str = str(s)
    if len(s_str) >= 7:
        mm = s_str[5:7]
        if mm.isdigit():
            m = int(mm)
            return f"{s_str} ({month_name.get(m, '')})"
    return s_str or "—"

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
        amount_f = float(amount or 0)
        tips_f = float(tips or 0)
        if typ == "нал":
            commission = amount_f * (1 - rate_nal)
            total = amount_f + tips_f
            beznal_added = -commission
        else:
            final_wo_tips = amount_f * rate_card
            commission = amount_f - final_wo_tips
            total = final_wo_tips + tips_f
            beznal_added = final_wo_tips
        cur.execute(
            "UPDATE orders SET commission = ?, total = ?, beznal_added = ? WHERE id = ?",
            (commission, total, beznal_added, order_id)
        )
    
    cur.execute("SELECT COALESCE(SUM(beznal_added), 0) FROM orders")
    total_beznal = cur.fetchone()[0] or 0.0
    
    cur.execute("SELECT id FROM accumulated_beznal WHERE driver_id = 1")
    row = cur.fetchone()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    if row:
        cur.execute(
            "UPDATE accumulated_beznal SET total_amount = ?, last_updated = ? WHERE driver_id = 1",
            (total_beznal, now)
        )
    else:
        cur.execute(
            "INSERT INTO accumulated_beznal (driver_id, total_amount, last_updated) VALUES (1, ?, ?)",
            (total_beznal, now)
        )
    
    conn.commit()
    conn.close()
    return total_beznal

def reset_db():
    db_path = get_current_db_name()
    if os.path.exists(db_path):
        os.remove(db_path)

def normalize_shift_dates():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, date FROM shifts")
    rows = cur.fetchall()
    fixed = 0
    skipped = 0
    for shift_id, date_str in rows:
        try:
            parsed = datetime.strptime(date_str, "%Y-%m-%d")
            new_val = parsed.strftime("%Y-%m-%d")
        except:
            new_val = None
        s = str(date_str).strip() if date_str is not None else ""
        if new_val and new_val != s:
            cur.execute("UPDATE shifts SET date = ? WHERE id = ?", (new_val, shift_id))
            fixed += 1
        else:
            skipped += 1
    conn.commit()
    conn.close()
    return fixed, skipped