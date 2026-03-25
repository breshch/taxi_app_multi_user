import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime
from typing import Dict, List, Optional
import os
from config import (
    get_db_connection, get_accumulated_beznal, set_accumulated_beznal,
    RATE_NAL, RATE_CARD, MOSCOW_TZ, get_current_db_name
)

def ensure_report_indexes(username):
    conn = get_db_connection(username)
    c = conn.cursor()
    indexes = [
        "CREATE INDEX IF NOT EXISTS idx_shifts_date ON shifts(date)",
        "CREATE INDEX IF NOT EXISTS idx_shifts_open ON shifts(is_open)",
        "CREATE INDEX IF NOT EXISTS idx_orders_shift_id ON orders(shift_id)",
        "CREATE INDEX IF NOT EXISTS idx_orders_type ON orders(type)",
        "CREATE INDEX IF NOT EXISTS idx_expenses_shift ON extra_expenses(shift_id)",
    ]
    for idx_sql in indexes:
        c.execute(idx_sql)
    conn.commit()
    conn.close()

@st.cache_data(ttl=300)
def get_available_year_months_cached(username) -> List[str]:
    ensure_report_indexes(username)
    conn = get_db_connection(username)
    c = conn.cursor()
    c.execute("""
        SELECT DISTINCT strftime('%Y-%m', date) FROM shifts
        WHERE date IS NOT NULL AND TRIM(date) != '' AND is_open = 0
        AND EXISTS (SELECT 1 FROM orders o WHERE o.shift_id = shifts.id)
        ORDER BY 1 DESC
    """)
    rows = c.fetchall()
    conn.close()
    result = []
    for (val,) in rows:
        if val:
            s = str(val)
            if len(s) >= 7 and s[:4].isdigit() and s[5:7].isdigit():
                result.append(s)
    return result

@st.cache_data(ttl=300)
def get_month_totals_cached(year_month: str, username) -> Dict:
    ensure_report_indexes(username)
    conn = get_db_connection(username)
    c = conn.cursor()
    c.execute("SELECT id FROM shifts WHERE date LIKE ? AND is_open = 0 AND EXISTS (SELECT 1 FROM orders o WHERE o.shift_id = shifts.id)", (f"{year_month}%",))
    shifts = c.fetchall()
    total_nal = total_card = total_tips = total_beznal_add = 0.0
    for (shift_id,) in shifts:
        c.execute("SELECT type, SUM(total - tips) FROM orders WHERE shift_id = ? GROUP BY type", (shift_id,))
        for typ, summ in c.fetchall():
            summ = summ or 0.0
            if typ == "нал": total_nal += summ
            elif typ == "карта": total_card += summ
        c.execute("SELECT SUM(tips), SUM(beznal_added) FROM orders WHERE shift_id = ?", (shift_id,))
        tips_sum, beznal_sum = c.fetchone() or (0.0, 0.0)
        total_tips += tips_sum
        total_beznal_add += beznal_sum
    conn.close()
    return {"нал": total_nal, "карта": total_card, "чаевые": total_tips, "безнал_добавлено": total_beznal_add, "всего": total_nal + total_card + total_tips, "смен": len(shifts)}

@st.cache_data(ttl=300)
def get_month_statistics(year_month: str, username) -> Dict:
    ensure_report_indexes(username)
    conn = get_db_connection(username)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM shifts WHERE date LIKE ? AND is_open = 0", (f"{year_month}%",))
    shifts_count = c.fetchone()[0] or 0
    c.execute("SELECT COUNT(*) FROM orders o JOIN shifts s ON o.shift_id = s.id WHERE s.date LIKE ? AND s.is_open = 0", (f"{year_month}%",))
    orders_count = c.fetchone()[0] or 0
    c.execute("SELECT AVG(total) FROM orders o JOIN shifts s ON o.shift_id = s.id WHERE s.date LIKE ? AND s.is_open = 0", (f"{year_month}%",))
    avg_check = c.fetchone()[0] or 0.0
    c.execute("SELECT SUM(fuel_liters * fuel_price) FROM shifts WHERE date LIKE ? AND is_open = 0", (f"{year_month}%",))
    fuel_cost = c.fetchone()[0] or 0.0
    c.execute("SELECT SUM(e.amount) FROM extra_expenses e JOIN shifts s ON e.shift_id = s.id WHERE s.date LIKE ? AND s.is_open = 0", (f"{year_month}%",))
    extra_expenses = c.fetchone()[0] or 0.0
    totals = get_month_totals_cached(year_month, username)
    income = totals.get("всего", 0)
    total_expenses = fuel_cost + extra_expenses
    profit = income - total_expenses
    profitability = (profit / income * 100) if income > 0 else 0
    conn.close()
    return {"смен": shifts_count, "заказов": orders_count, "средний_чек": avg_check, "бензин": fuel_cost, "расходы": total_expenses, "прибыль": profit, "рентабельность": profitability}

@st.cache_data(ttl=300)
def get_month_shifts_details_cached(year_month: str, username) -> pd.DataFrame:
    ensure_report_indexes(username)
    conn = get_db_connection(username)
    c = conn.cursor()
    c.execute("""
        SELECT id, date, km, fuel_liters, fuel_price FROM shifts
        WHERE date LIKE ? AND is_open = 0
        AND EXISTS (SELECT 1 FROM orders o WHERE o.shift_id = shifts.id)
        ORDER BY date
    """, (f"{year_month}%",))
    shifts = c.fetchall()
    rows = []
    for shift_id, date_str, km, fuel_liters, fuel_price in shifts:
        c.execute("SELECT type, SUM(total - tips) FROM orders WHERE shift_id = ? GROUP BY type", (shift_id,))
        by_type = {t: s for t, s in c.fetchall()}
        c.execute("SELECT SUM(tips), SUM(beznal_added) FROM orders WHERE shift_id = ?", (shift_id,))
        tips_sum, beznal_sum = c.fetchone() or (0.0, 0.0)
        nal = by_type.get("нал", 0.0)
        card = by_type.get("карта", 0.0)
        total = nal + card + tips_sum
        try:
            display_date = datetime.strptime(date_str, "%Y-%m-%d").strftime("%d.%m.%Y")
        except:
            display_date = date_str
        rows.append({"Дата": display_date, "date_iso": date_str, "Нал": nal, "Карта": card, "Чаевые": tips_sum, "Δ безнал": beznal_sum, "Км": km or 0, "Литры": fuel_liters or 0.0, "Цена": fuel_price or 0.0, "Всего": total})
    conn.close()
    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.sort_values("date_iso").drop("date_iso", axis=1)
        df.index = list(range(1, len(df) + 1))
    return df

def format_month_option(s: Optional[str]) -> str:
    if not s: return "—"
    s_str = str(s)
    if len(s_str) < 7: return s_str
    month_names = {"01": "январь", "02": "февраль", "03": "март", "04": "апрель", "05": "май", "06": "июнь", "07": "июль", "08": "август", "09": "сентябрь", "10": "октябрь", "11": "ноябрь", "12": "декабрь"}
    mm = s_str[5:7]
    month_ru = month_names.get(mm, "")
    return f"{s_str} ({month_ru})"

def recalc_full_db(username) -> float:
    conn = get_db_connection(username)
    c = conn.cursor()
    c.execute("SELECT id, type, amount, tips FROM orders")
    rows = c.fetchall()
    for order_id, typ, amount, tips in rows:
        amount_f = float(amount or 0)
        tips_f = float(tips or 0)
        if typ == "нал":
            commission = amount_f * (1 - RATE_NAL)
            total = amount_f + tips_f
            beznal_added = -commission
        else:
            final_wo_tips = amount_f * RATE_CARD
            commission = amount_f - final_wo_tips
            total = final_wo_tips + tips_f
            beznal_added = final_wo_tips
        c.execute("UPDATE orders SET commission = ?, total = ?, beznal_added = ? WHERE id = ?", (commission, total, beznal_added, order_id))
    c.execute("SELECT COALESCE(SUM(beznal_added), 0) FROM orders")
    total_beznal = c.fetchone()[0] or 0.0
    c.execute("SELECT id FROM accumulated_beznal WHERE driver_id = 1")
    row = c.fetchone()
    now = datetime.now(MOSCOW_TZ).strftime("%Y-%m-%d %H:%M:%S")
    if row:
        c.execute("UPDATE accumulated_beznal SET total_amount = ?, last_updated = ? WHERE driver_id = 1", (total_beznal, now))
    else:
        c.execute("INSERT INTO accumulated_beznal (driver_id, total_amount, last_updated) VALUES (1, ?, ?)", (total_beznal, now))
    conn.commit()
    conn.close()
    return total_beznal

def reset_db(username):
    db_path = get_current_db_name(username)
    if os.path.exists(db_path):
        os.remove(db_path)