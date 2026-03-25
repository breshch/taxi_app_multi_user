import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime
from typing import Dict, List, Optional
import os
from app import get_db_connection, get_current_db_name, RATE_NAL, RATE_CARD, MOSCOW_TZ

def ensure_report_indexes():
    conn = get_db_connection()
    c = conn.cursor()
    for idx in [
        "CREATE INDEX IF NOT EXISTS idx_shifts_date ON shifts(date)",
        "CREATE INDEX IF NOT EXISTS idx_shifts_open ON shifts(is_open)",
        "CREATE INDEX IF NOT EXISTS idx_orders_shift_id ON orders(shift_id)",
        "CREATE INDEX IF NOT EXISTS idx_orders_type ON orders(type)",
        "CREATE INDEX IF NOT EXISTS idx_expenses_shift ON extra_expenses(shift_id)",
    ]:
        c.execute(idx)
    conn.commit()
    conn.close()

@st.cache_data(ttl=300)
def get_available_year_months_cached() -> List[str]:
    ensure_report_indexes()
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("""SELECT DISTINCT strftime('%Y-%m', date) FROM shifts
        WHERE date IS NOT NULL AND TRIM(date) != '' AND is_open = 0
        AND EXISTS (SELECT 1 FROM orders o WHERE o.shift_id = shifts.id)
        ORDER BY 1 DESC""")
    rows = c.fetchall()
    conn.close()
    return [str(val) for (val,) in rows if val and len(str(val)) >= 7]

@st.cache_data(ttl=300)
def get_available_days_cached(year_month: str) -> List[str]:
    ensure_report_indexes()
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("""SELECT DISTINCT date FROM shifts
        WHERE date LIKE ? AND is_open = 0
        AND EXISTS (SELECT 1 FROM orders o WHERE o.shift_id = shifts.id)
        ORDER BY date DESC""", (f"{year_month}%",))
    rows = c.fetchall()
    conn.close()
    return [row[0] for row in rows if row[0]]

@st.cache_data(ttl=300)
def get_day_report_cached(date_str: str) -> Dict:
    ensure_report_indexes()
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT id, km, fuel_liters, fuel_price FROM shifts WHERE date = ? AND is_open = 0", (date_str,))
    shifts = c.fetchall()
    total_income = total_nal = total_card = total_tips = total_fuel = total_extra = total_orders = 0.0

    for shift_id, km, fuel_liters, fuel_price in shifts:
        c.execute("SELECT type, SUM(total - tips), SUM(tips) FROM orders WHERE shift_id = ? GROUP BY type", (shift_id,))
        for typ, summ, tips in c.fetchall():
            summ = summ or 0.0
            tips = tips or 0.0
            total_income += summ + tips
            total_tips += tips
            if typ == "нал": total_nal += summ
            elif typ == "карта": total_card += summ
        c.execute("SELECT COUNT(*) FROM orders WHERE shift_id = ?", (shift_id,))
        total_orders += c.fetchone()[0] or 0
        total_fuel += (fuel_liters or 0.0) * (fuel_price or 0.0)
        c.execute("SELECT SUM(amount) FROM extra_expenses WHERE shift_id = ?", (shift_id,))
        total_extra += c.fetchone()[0] or 0.0

    conn.close()
    return {
        "дата": date_str, "смен": len(shifts), "заказов": int(total_orders),
        "нал": total_nal, "карта": total_card, "чаевые": total_tips, "всего": total_income,
        "топливо": total_fuel, "расходы": total_extra, "прибыль": total_income - total_fuel - total_extra,
    }

@st.cache_data(ttl=300)
def get_month_totals_cached(year_month: str) -> Dict:
    ensure_report_indexes()
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT id FROM shifts WHERE date LIKE ? AND is_open = 0 AND EXISTS (SELECT 1 FROM orders o WHERE o.shift_id = shifts.id)", (f"{year_month}%",))
    shifts = c.fetchall()
    total_nal = total_card = total_tips = 0.0
    for (shift_id,) in shifts:
        c.execute("SELECT type, SUM(total - tips) FROM orders WHERE shift_id = ? GROUP BY type", (shift_id,))
        for typ, summ in c.fetchall():
            if typ == "нал": total_nal += summ or 0.0
            elif typ == "карта": total_card += summ or 0.0
        c.execute("SELECT SUM(tips) FROM orders WHERE shift_id = ?", (shift_id,))
        total_tips += c.fetchone()[0] or 0.0
    conn.close()
    return {"нал": total_nal, "карта": total_card, "чаевые": total_tips, "всего": total_nal + total_card + total_tips, "смен": len(shifts)}

@st.cache_data(ttl=300)
def get_month_statistics(year_month: str) -> Dict:
    ensure_report_indexes()
    conn = get_db_connection()
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
    extra = c.fetchone()[0] or 0.0
    totals = get_month_totals_cached(year_month)
    income = totals.get("всего", 0)
    profit = income - fuel_cost - extra
    conn.close()
    return {"смен": shifts_count, "заказов": orders_count, "средний_чек": avg_check, "бензин": fuel_cost, "расходы": fuel_cost + extra, "прибыль": profit, "рентабельность": (profit / income * 100) if income > 0 else 0}

@st.cache_data(ttl=300)
def get_month_shifts_details_cached(year_month: str) -> pd.DataFrame:
    ensure_report_indexes()
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("""SELECT id, date, km, fuel_liters, fuel_price FROM shifts
        WHERE date LIKE ? AND is_open = 0 AND EXISTS (SELECT 1 FROM orders o WHERE o.shift_id = shifts.id) ORDER BY date""", (f"{year_month}%",))
    shifts = c.fetchall()
    rows = []
    for shift_id, date_str, km, fuel_liters, fuel_price in shifts:
        c.execute("SELECT type, SUM(total - tips) FROM orders WHERE shift_id = ? GROUP BY type", (shift_id,))
        by_type = {t: s for t, s in c.fetchall()}
        c.execute("SELECT SUM(tips), SUM(beznal_added) FROM orders WHERE shift_id = ?", (shift_id,))
        tips_sum, beznal_sum = c.fetchone() or (0.0, 0.0)
        nal = by_type.get("нал", 0.0)
        card = by_type.get("карта", 0.0)
        try: display_date = datetime.strptime(date_str, "%Y-%m-%d").strftime("%d.%m.%Y")
        except: display_date = date_str
        rows.append({"Дата": display_date, "date_iso": date_str, "Нал": nal, "Карта": card, "Чаевые": tips_sum, "Δ безнал": beznal_sum, "Км": km or 0, "Литры": fuel_liters or 0.0, "Цена": fuel_price or 0.0, "Всего": nal + card + tips_sum})
    conn.close()
    df = pd.DataFrame(rows)
    if not df.empty: df = df.sort_values("date_iso").drop("date_iso", axis=1)
    return df

def format_month_option(s: Optional[str]) -> str:
    if not s: return "—"
    month_names = {"01": "январь", "02": "февраль", "03": "март", "04": "апрель", "05": "май", "06": "июнь", "07": "июль", "08": "август", "09": "сентябрь", "10": "октябрь", "11": "ноябрь", "12": "декабрь"}
    return f"{s[:7]} ({month_names.get(s[5:7], '')})" if len(s) >= 7 else s

def recalc_full_db() -> float:
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT id, type, amount, tips FROM orders")
    for order_id, typ, amount, tips in c.fetchall():
        amount_f = float(amount or 0)
        tips_f = float(tips or 0)
        if typ == "нал":
            commission = amount_f * (1 - RATE_NAL)
            total = amount_f + tips_f
            beznal_added = -commission
        else:
            final = amount_f * RATE_CARD
            commission = amount_f - final
            total = final + tips_f
            beznal_added = final
        c.execute("UPDATE orders SET commission = ?, total = ?, beznal_added = ? WHERE id = ?", (commission, total, beznal_added, order_id))
    c.execute("SELECT COALESCE(SUM(beznal_added), 0) FROM orders")
    total_beznal = c.fetchone()[0] or 0.0
    c.execute("SELECT id FROM accumulated_beznal WHERE driver_id = 1")
    now = datetime.now(MOSCOW_TZ).strftime("%Y-%m-%d %H:%M:%S")
    if c.fetchone():
        c.execute("UPDATE accumulated_beznal SET total_amount = ?, last_updated = ? WHERE driver_id = 1", (total_beznal, now))
    else:
        c.execute("INSERT INTO accumulated_beznal (driver_id, total_amount, last_updated) VALUES (1, ?, ?)", (total_beznal, now))
    conn.commit()
    conn.close()
    return total_beznal

def reset_db():
    db_path = get_current_db_name()
    if os.path.exists(db_path): os.remove(db_path)