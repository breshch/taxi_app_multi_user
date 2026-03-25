import os
import json
import base64
import shutil
import sqlite3
from datetime import datetime, date, timezone, timedelta
import pandas as pd
import streamlit as st
from config import (
    AUTH_DB, USERS_DIR, SESSION_FILE, SESSION_TIMEOUT, MOSCOW_TZ,
    RATE_NAL, RATE_CARD, POPULAR_EXPENSES,
    ensure_users_dir, get_user_dir, get_current_db_name, get_backup_dir,
    init_auth_db, hash_password, verify_password, authenticate_user, register_user,
    get_open_shift, open_shift, close_shift_db,
    get_accumulated_beznal, set_accumulated_beznal,
    add_order_and_update_beznal, delete_order_and_update_beznal, update_order_and_adjust_beznal,
    get_shift_totals, get_last_fuel_params,
    add_extra_expense, get_extra_expenses, delete_extra_expense, get_total_extra_expenses, get_shift_orders
)

# ===== CSS (мобильная оптимизация + отступы) =====
def apply_mobile_optimized_css():
    st.markdown("""
    <style>
    * { box-sizing: border-box; }
    .main > div { 
        padding-left: 0.5rem !important; 
        padding-right: 0.5rem !important; 
        padding-top: 4rem !important;
    }
    .block-container { 
        padding-top: 3rem !important; 
        padding-bottom: 2rem !important; 
        max-width: 100% !important; 
        margin-top: 2rem;
    }
    .stTitle { margin-top: 2rem !important; padding-top: 1rem !important; }
    section[data-testid="stSidebar"] { padding-top: 2rem !important; }
    header { margin-bottom: 1rem !important; }
    .stButton button { width: 100%; min-height: 48px; }
    </style>
    """, unsafe_allow_html=True)

# ===== СЕССИЯ =====
def save_session_to_disk():
    try:
        if "username" in st.session_state and st.session_state["username"]:
            session_data = {
                "username": st.session_state["username"],
                "session_start": st.session_state.get("session_start").isoformat() if st.session_state.get("session_start") else None,
                "last_activity": st.session_state.get("last_activity").isoformat() if st.session_state.get("last_activity") else None,
            }
            with open(SESSION_FILE, "w", encoding="utf-8") as f:
                json.dump(session_data, f)
    except Exception as e:
        print(f"Ошибка сохранения сессии: {e}")

def load_session_from_disk():
    try:
        if os.path.exists(SESSION_FILE):
            with open(SESSION_FILE, "r", encoding="utf-8") as f:
                session_data = json.load(f)
            session_start_str = session_data.get("session_start")
            if session_start_str:
                session_start = datetime.fromisoformat(session_start_str)
                if session_start.tzinfo is None:
                    session_start = session_start.replace(tzinfo=MOSCOW_TZ)
                elapsed = (datetime.now(MOSCOW_TZ) - session_start).total_seconds()
                if elapsed < SESSION_TIMEOUT:
                    return session_data.get("username")
    except Exception as e:
        print(f"Ошибка загрузки сессии: {e}")
    return None

def clear_session_disk():
    try:
        if os.path.exists(SESSION_FILE):
            os.remove(SESSION_FILE)
    except Exception as e:
        print(f"Ошибка очистки файла сессии: {e}")

def init_session():
    if "session_start" not in st.session_state:
        st.session_state.session_start = datetime.now(MOSCOW_TZ)
        st.session_state.last_activity = datetime.now(MOSCOW_TZ)
        save_session_to_disk()
    elapsed = (datetime.now(MOSCOW_TZ) - st.session_state.session_start).total_seconds()
    if elapsed > SESSION_TIMEOUT:
        st.session_state.clear()
        clear_session_disk()
        st.warning("⏰ Сессия истекла. Авторизуйтесь снова.")
        st.rerun()
    else:
        st.session_state.last_activity = datetime.now(MOSCOW_TZ)
        save_session_to_disk()

def get_session_time_remaining() -> str:
    if "session_start" not in st.session_state:
        return "00:00:00"
    elapsed = (datetime.now(MOSCOW_TZ) - st.session_state.session_start).total_seconds()
    remaining = max(0, SESSION_TIMEOUT - elapsed)
    days = int(remaining // (24 * 3600))
    hours = int((remaining % (24 * 3600)) // 3600)
    minutes = int((remaining % 3600) // 60)
    seconds = int(remaining % 60)
    if days > 0:
        return f"{days}д {hours:02d}:{minutes:02d}:{seconds:02d}"
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

# ===== БЕКАПЫ =====
def create_backup() -> str:
    backup_dir = get_backup_dir(st.session_state.get("username", "unknown"))
    ts = datetime.now(MOSCOW_TZ).strftime("%Y%m%d_%H%M%S")
    username = st.session_state.get("username", "unknown")
    backup_name = f"taxi_{username}_backup_{ts}.db"
    backup_path = os.path.join(backup_dir, backup_name)
    shutil.copy2(get_current_db_name(st.session_state.get("username")), backup_path)
    return backup_path

def list_backups() -> list:
    backup_dir = get_backup_dir(st.session_state.get("username", "unknown"))
    if not os.path.exists(backup_dir):
        return []
    backups = []
    for filename in os.listdir(backup_dir):
        if filename.endswith(".db"):
            filepath = os.path.join(backup_dir, filename)
            stat = os.stat(filepath)
            backups.append({"name": filename, "path": filepath, "time": datetime.fromtimestamp(stat.st_mtime), "size": stat.st_size / 1024})
    backups.sort(key=lambda x: x["time"], reverse=True)
    return backups

def restore_from_backup(backup_path: str):
    if not os.path.exists(backup_path):
        raise FileNotFoundError(f"Файл бэкапа не найден: {backup_path}")
    create_backup()
    shutil.copy2(backup_path, get_current_db_name(st.session_state.get("username")))
    st.cache_data.clear()  # 🔥 Очистка кэша

def download_backup(backup_path):
    with open(backup_path, "rb") as f:
        return f.read()

def upload_and_restore_backup(uploaded_file):
    if uploaded_file is not None:
        temp_path = os.path.join(get_backup_dir(st.session_state.get("username", "unknown")), "temp_restore.db")
        with open(temp_path, "wb") as f:
            f.write(uploaded_file.getbuffer())
        restore_from_backup(temp_path)
        try:
            os.remove(temp_path)
        except:
            pass
        st.cache_data.clear()  # 🔥 Очистка кэша
        return True
    return False

# ===== GOOGLE DRIVE =====
def sync_with_google_drive():
    try:
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload
        from google.auth.transport.requests import Request
        SCOPES = ["https://www.googleapis.com/auth/drive.file"]
        BACKUP_FILENAME = "taxi_backup.db"
        if not os.path.exists("credentials.json"):
            if hasattr(st, "secrets") and "google_credentials" in st.secrets:
                try:
                    encoded = st.secrets["google_credentials"]["json_data"]
                    decoded = base64.b64decode(encoded)
                    with open("credentials.json", "wb") as f:
                        f.write(decoded)
                    st.success("✅ credentials.json создан из secrets")
                except Exception as e:
                    st.error(f"❌ Ошибка secrets: {e}")
                    return False
            else:
                st.error("❌ credentials.json не найден!")
                return False
        creds = None
        if os.path.exists("token.json"):
            try:
                creds = Credentials.from_authorized_user_file("token.json", SCOPES)
            except:
                os.remove("token.json")
                creds = None
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                except:
                    creds = None
            if not creds:
                flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
                auth_url, _ = flow.authorization_url(access_type="offline", include_granted_scopes="true", prompt="consent")
                st.info("🔐 Требуется авторизация Google")
                st.markdown(f"""
                 <div style="background: #e3f2fd; padding: 15px; border-radius: 8px; margin: 10px 0;">
                     <a href="{auth_url}" target="_blank" style="font-size: 1.1rem; color: #1976d2; font-weight: bold;">Авторизоваться в Google Drive</a>
                 </div>
                 """, unsafe_allow_html=True)
                st.warning("1. Нажмите кнопку\n2. Войдите под своим Gmail\n3. Разрешите доступ\n4. Вернитесь и нажмите 'Обновить'")
                if st.button("🔄 Обновить", type="primary"):
                    st.rerun()
                return False
        service = build("drive", "v3", credentials=creds)
        results = service.files().list(q=f"name='{BACKUP_FILENAME}' and trashed=false", spaces="drive", fields="files(id, modifiedTime)").execute()
        files = results.get("files", [])
        local_path = get_current_db_name(st.session_state.get("username"))
        local_mtime = datetime.fromtimestamp(os.path.getmtime(local_path))
        if not files:
            media = MediaFileUpload(local_path, mimetype="application/octet-stream")
            service.files().create(body={"name": BACKUP_FILENAME}, media_body=media).execute()
            st.success("✅ Загружено в Google Drive!")
            return True
        else:
            cloud_mtime = datetime.fromisoformat(files[0]["modifiedTime"].replace("Z", "+00:00"))
            local_mtime_aware = local_mtime.replace(tzinfo=timezone.utc)
            if local_mtime_aware > cloud_mtime:
                media = MediaFileUpload(local_path, mimetype="application/octet-stream")
                service.files().update(fileId=files[0]["id"], media_body=media).execute()
                st.success("✅ Обновлено в Google Drive!")
            else:
                request = service.files().get_media(fileId=files[0]["id"])
                temp_path = local_path + ".temp"
                with open(temp_path, "wb") as f:
                    downloader = MediaIoBaseDownload(f, request)
                    done = False
                    while not done:
                        status, done = downloader.next_chunk()
                shutil.copy2(temp_path, local_path)
                os.remove(temp_path)
                st.success("✅ Скачано из Google Drive!")
                st.cache_data.clear()
                st.rerun()
            return True
    except Exception as e:
        st.error(f"❌ Ошибка Google Drive: {str(e)}")
        return False

# ===== UI: ГЛАВНАЯ =====
def show_main_page():
    st.title(f"👨‍💼 {st.session_state.username}")
    username = st.session_state.username
    open_shift_data = get_open_shift(username)
    if not open_shift_data:
        st.info("ℹ️ Откройте смену для работы")
        with st.expander("📅 Открыть смену", expanded=True):
            selected_date = st.date_input("Дата смены", value=date.today())
            if st.button("✅ Открыть смену", width='stretch'):
                open_shift(selected_date.strftime("%Y-%m-%d"), username)
                st.success(f"✅ Смена открыта: {selected_date.strftime('%Y-%m-%d')}")
                st.rerun()
    else:
        shift_id, date_str = open_shift_data
        st.success(f"✅ Смена открыта: **{date_str}**")
        acc_beznal = get_accumulated_beznal(username)
        if acc_beznal > 0:
            st.metric("💳 Накопленный безнал", f"{acc_beznal:.0f} ₽")
        with st.expander("➕ Новый заказ", expanded=True):
            col1, col2 = st.columns([2, 1])
            with col1:
                amount_str = st.text_input("Сумма чеком", placeholder="650", width='stretch')
            with col2:
                order_type = st.selectbox("Тип", ["нал", "карта"], index=0, help="нал=78%, карта=75%", width='stretch')
                tips_str = st.text_input("Чаевые", placeholder="0", help="Сумма чаевых", width='stretch')
            try:
                amount = float(amount_str.replace(",", "."))
                tips = float(tips_str.replace(",", ".")) if tips_str else 0.0
                if order_type == "нал":
                    commission = amount * (1 - RATE_NAL)
                    total = amount + tips
                    beznal_added = -commission
                else:
                    final_wo_tips = amount * RATE_CARD
                    commission = amount - final_wo_tips
                    total = final_wo_tips + tips
                    beznal_added = final_wo_tips
                st.caption(f"Комиссия: {commission:.0f} ₽ | Итого: {total:.0f} ₽ | Δ безнал: {beznal_added:+.0f} ₽")
            except ValueError:
                pass
            if st.button("✅ Добавить заказ", width='stretch'):
                try:
                    amount = float(amount_str.replace(",", "."))
                    tips = float(tips_str.replace(",", ".")) if tips_str else 0.0
                    order_time = datetime.now(MOSCOW_TZ).strftime("%H:%M")
                    if order_type == "нал":
                        commission = amount * (1 - RATE_NAL)
                        total = amount + tips
                        beznal_added = -commission
                        db_type = "нал"
                    else:
                        final_wo_tips = amount * RATE_CARD
                        commission = amount - final_wo_tips
                        total = final_wo_tips + tips
                        beznal_added = final_wo_tips
                        db_type = "карта"
                    add_order_and_update_beznal(shift_id, db_type, amount, tips, commission, total, beznal_added, order_time, username)
                    st.success("✅ Заказ добавлен!")
                    st.rerun()
                except ValueError:
                    st.error("❌ Проверьте сумму и чаевые")
                except Exception as e:
                    st.error(f"❌ Ошибка: {e}")
        
        # ===== СПИСОК ЗАКАЗОВ С КНОПКОЙ ✏️ ИЗМЕНИТЬ =====
        orders = get_shift_orders(shift_id, username)
        totals = get_shift_totals(shift_id, username)
        if orders:
            st.subheader("📋 Заказы смены")
            for order_row in orders:
                order_id, typ, am, ti, _, tot, bez, tm = order_row
                edit_key = f"edit_order_{order_id}"
                delete_key = f"del_order_{order_id}"
                confirm_key = f"confirm_del_order_{order_id}"
                
                cols = st.columns([3, 1, 1, 1])
                cols[0].markdown(f"**{typ}** | {tm or ''} | {am:.0f} ₽")
                cols[1].markdown(f"{tot:.0f} ₽")
                cols[2].markdown(f"{bez:+.0f} ₽")
                
                if cols[3].button("✏️", key=edit_key, help="Изменить заказ"):
                    st.session_state[f"editing_order_{order_id}"] = True
                    st.rerun()
                
                if st.session_state.get(f"editing_order_{order_id}"):
                    with st.expander(f"✏️ Редактирование заказа #{order_id}", expanded=True):
                        edit_col1, edit_col2 = st.columns([2, 1])
                        with edit_col1:
                            edit_amount = st.number_input("Сумма", value=float(am), min_value=0.0, step=10.0, key=f"edit_amt_{order_id}", width='stretch')
                        with edit_col2:
                            edit_type = st.selectbox("Тип", ["нал", "карта"], index=0 if typ == "нал" else 1, key=f"edit_type_{order_id}", width='stretch')
                            edit_tips = st.number_input("Чаевые", value=float(ti or 0), min_value=0.0, step=10.0, key=f"edit_tips_{order_id}", width='stretch')
                        if edit_type == "нал":
                            edit_commission = edit_amount * (1 - RATE_NAL)
                            edit_total = edit_amount + edit_tips
                            edit_beznal = -edit_commission
                        else:
                            edit_final = edit_amount * RATE_CARD
                            edit_commission = edit_amount - edit_final
                            edit_total = edit_final + edit_tips
                            edit_beznal = edit_final
                        st.caption(f"Комиссия: {edit_commission:.0f} ₽ | Итого: {edit_total:.0f} ₽ | Δ безнал: {edit_beznal:+.0f} ₽")
                        edit_btn_col1, edit_btn_col2 = st.columns(2)
                        if edit_btn_col1.button("💾 Сохранить", key=f"save_edit_{order_id}", width='stretch'):
                            try:
                                update_order_and_adjust_beznal(order_id, edit_type, edit_amount, edit_tips, edit_commission, edit_total, edit_beznal, username)
                                st.session_state.pop(f"editing_order_{order_id}", None)
                                st.success("✅ Заказ обновлён")
                                st.cache_data.clear()
                                st.rerun()
                            except Exception as e:
                                st.error(f"❌ Ошибка: {e}")
                        if edit_btn_col2.button("❌ Отмена", key=f"cancel_edit_{order_id}", width='stretch'):
                            st.session_state.pop(f"editing_order_{order_id}", None)
                            st.rerun()
                    st.divider()
                    continue
                
                if st.session_state.get(confirm_key):
                    c1, c2 = cols[3].columns(2)
                    if c1.button("✅ Удалить", key=f"yes_{order_id}", width='stretch'):
                        try:
                            delete_order_and_update_beznal(order_id, username)
                            st.session_state.pop(confirm_key, None)
                            st.success("✅ Заказ удалён")
                            st.rerun()
                        except Exception as e:
                            st.error(f"❌ Ошибка: {e}")
                    if c2.button("❌ Отмена", key=f"no_{order_id}", width='stretch'):
                        st.session_state.pop(confirm_key, None)
                        st.rerun()
                elif cols[3].button("🗑️", key=delete_key, help="Удалить заказ"):
                    st.session_state[confirm_key] = True
                    st.rerun()
            st.divider()
            st.metric("📊 Итого смены", f"{totals.get('нал', 0):.0f} + {totals.get('карта', 0):.0f} + {totals.get('чаевые', 0):.0f}")
        
        with st.expander("💸 Доп. расходы", expanded=False):
            st.subheader("Добавить расход")
            col1, col2, col3 = st.columns([2, 1, 1])
            with col1:
                exp_desc = st.selectbox("Тип", POPULAR_EXPENSES, key="exp_desc", width='stretch')
            with col2:
                exp_amt = st.number_input("Сумма", min_value=0.0, step=50.0, value=100.0, key="exp_amt", width='stretch')
            with col3:
                if st.button("➕ Добавить", width='stretch', key="add_exp"):
                    if exp_desc and exp_amt > 0:
                        add_extra_expense(shift_id, exp_amt, exp_desc, username)
                        st.success("✅ Расход добавлен")
                        st.rerun()
            st.divider()
            expenses = get_extra_expenses(shift_id, username)
            total_extra = 0.0
            for exp in expenses:
                cols = st.columns([3, 1, 1])
                cols[0].markdown(f"**{exp['description']}**")
                cols[1].markdown(f"{exp['amount']:.0f} ₽")
                if cols[2].button("🗑️", key=f"del_exp_{exp['id']}", width='stretch'):
                    delete_extra_expense(exp["id"], username)
                    st.rerun()
                total_extra += exp["amount"]
            if expenses:
                st.divider()
                st.metric("Итого расходов", f"{total_extra:.0f} ₽")
        
        st.divider()
        st.subheader("📈 Итоги смены")
        total_income = totals.get("нал", 0) + totals.get("карта", 0) + totals.get("чаевые", 0)
        total_extra = get_total_extra_expenses(shift_id, username)
        col1, col2, col3 = st.columns(3)
        col1.metric("Доход", f"{total_income:.0f} ₽")
        col2.metric("Расходы", f"{total_extra:.0f} ₽")
        col3.metric("Прибыль", f"{total_income - total_extra:.0f} ₽", delta=f"{total_income - total_extra:.0f}")
        
        with st.expander("⛽ Закрыть смену", expanded=False):
            last_cons, last_price = get_last_fuel_params(username)
            km_close = st.number_input("Пробег (км)", value=100, min_value=0, key="km_close", width='stretch')
            col1, col2 = st.columns(2)
            with col1:
                consumption = st.number_input("Расход (л/100км)", value=float(last_cons), step=0.5, key="cons_close", width='stretch')
            with col2:
                fuel_price = st.number_input("Цена топлива (₽/л)", value=float(last_price), step=1.0, key="fuel_close", width='stretch')
            if km_close > 0 and consumption > 0 and fuel_price > 0:
                liters = (km_close / 100) * consumption
                fuel_cost = liters * fuel_price
                profit = total_income - total_extra - fuel_cost
                st.info(f"🛢️ {liters:.1f} л × {fuel_price:.0f} ₽ = **{fuel_cost:.0f} ₽**")
                st.success(f"💰 Чистая прибыль: **{profit:.0f} ₽**")
            if not st.session_state.get("confirm_close_shift"):
                if st.button("🔒 Закрыть смену", width='stretch', type="primary"):
                    st.session_state.confirm_close_shift = True
                    st.rerun()
            else:
                st.warning("⚠️ Подтвердите закрытие смены")
                col1, col2 = st.columns(2)
                if col1.button("✅ Да, закрыть", width='stretch', type="primary"):
                    liters = (km_close / 100) * consumption if km_close > 0 else 0.0
                    close_shift_db(shift_id, km_close, liters, fuel_price, username)
                    st.session_state.pop("confirm_close_shift", None)
                    st.success("✅ Смена закрыта!")
                    st.cache_data.clear()
                    st.rerun()
                if col2.button("❌ Отмена", width='stretch'):
                    st.session_state.pop("confirm_close_shift", None)
                    st.rerun()

# ===== UI: ОТЧЁТЫ =====
def show_reports_page():
    st.title("📊 Отчёты")
    if st.button("🔄 Обновить данные", key="refresh_reports"):
        st.cache_data.clear()
        st.rerun()
    try:
        from pages_imports import get_available_year_months_cached, get_month_totals_cached, format_month_option, get_month_shifts_details_cached, get_month_statistics
        username = st.session_state.username
        year_months = get_available_year_months_cached(username)
        if not year_months:
            st.info("ℹ️ Нет закрытых смен с заказами")
            return
        selected_ym = st.selectbox("Период", year_months, index=0, format_func=format_month_option, width='stretch')
        totals = get_month_totals_cached(selected_ym, username)
        st.subheader(f"Итого за {format_month_option(selected_ym)}")
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Наличные", f"{totals.get('нал', 0):.0f} ₽")
        col2.metric("Карта", f"{totals.get('карта', 0):.0f} ₽")
        col3.metric("Чаевые", f"{totals.get('чаевые', 0):.0f} ₽")
        col4.metric("Всего", f"{totals.get('всего', 0):.0f} ₽")
        st.divider()
        df_shifts = get_month_shifts_details_cached(selected_ym, username)
        if not df_shifts.empty:
            dates = df_shifts["Дата"].unique().tolist()
            selected_date = st.selectbox("Смена", options=dates, width='stretch')
            df_day = df_shifts[df_shifts["Дата"] == selected_date].copy()
            if not df_day.empty:
                st.dataframe(df_day, width='stretch')
                row = df_day.iloc[0]
                fuel_cost = row["Литры"] * row["Цена"] if row["Литры"] > 0 else 0
                col1, col2, col3 = st.columns(3)
                col1.metric("Доход", f"{row['Всего']:.0f} ₽")
                col2.metric("Топливо", f"{fuel_cost:.0f} ₽")
                col3.metric("Прибыль", f"{row['Всего'] - fuel_cost:.0f} ₽")
        st.divider()
        stats = get_month_statistics(selected_ym, username)
        col1, col2, col3 = st.columns(3)
        col1.metric("Смен", stats.get("смен", 0))
        col2.metric("Заказов", stats.get("заказов", 0))
        col3.metric("Средний чек", f"{stats.get('средний_чек', 0):.0f} ₽")
        col1, col2, col3 = st.columns(3)
        col1.metric("Бензин", f"{stats.get('бензин', 0):.0f} ₽")
        col2.metric("Расходы", f"{stats.get('расходы', 0):.0f} ₽")
        col3.metric("Прибыль", f"{stats.get('прибыль', 0):.0f} ₽", delta=f"{stats.get('рентабельность', 0):.1f}%")
    except ImportError:
        st.error("❌ pages_imports.py не найден")
    except Exception as e:
        st.error(f"❌ Ошибка отчётов: {e}")

# ===== UI: АДМИНКА =====
def show_admin_page():
    st.title("🔧 Админка")
    admin_pwd = st.secrets.get("ADMIN_PASSWORD", "changeme")
    pwd = st.text_input("Пароль админа", type="password", width='stretch')
    if st.button("Войти", width='stretch'):
        if pwd == admin_pwd:
            st.session_state.admin_auth = True
            st.rerun()
        else:
            st.error("❌ Неверный пароль")
    if st.session_state.get("admin_auth"):
        tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(["Пересчёт", "Безнал", "Бэкапы", "Загрузка", "Google Drive", "Сброс БД"])
        username = st.session_state.username
        with tab1:
            st.write("**Пересчёт всех комиссий**")
            if st.button("🔄 Пересчитать всё", width='stretch'):
                from pages_imports import recalc_full_db
                new_total = recalc_full_db(username)
                st.success(f"✅ Пересчитано. Безнал: {new_total:.0f} ₽")
        with tab2:
            curr = get_accumulated_beznal(username)
            new_val = st.number_input("Новый безнал", value=float(curr), width='stretch')
            if st.button("💾 Установить", width='stretch'):
                set_accumulated_beznal(new_val, username)
                st.success("✅ Безнал обновлён")
                st.rerun()
        with tab3:
            if st.button("📦 Создать бэкап", width='stretch'):
                path = create_backup()
                st.success(f"✅ {os.path.basename(path)}")
            backups = list_backups()
            for b in backups:
                cols = st.columns([3, 1, 1, 1])
                cols[0].write(b["name"])
                cols[1].download_button(label="⬇️", data=download_backup(b["path"]), file_name=b["name"], key=f"db_{b['name']}", width='stretch')
                cols[2].button("📥", key=f"rb_{b['name']}", on_click=lambda p=b["path"]: restore_from_backup(p), width='stretch')
                cols[3].button("🗑️", key=f"xb_{b['name']}", on_click=lambda p=b["path"]: os.remove(p), width='stretch')
        with tab4:
            uploaded = st.file_uploader("Загрузить .db", type="db")
            if uploaded and st.button("📥 Восстановить", width='stretch'):
                if upload_and_restore_backup(uploaded):
                    st.success("✅ Восстановлено!")
                    st.rerun()
        with tab5:
            st.subheader("Google Drive")
            st.info("Автоматический бэкап/восстановление")
            if st.button("🔄 Синхронизировать", width='stretch', type="primary"):
                sync_with_google_drive()
        with tab6:
            if st.button("💥 СБРОСИТЬ БД", width='stretch', type="primary"):
                from pages_imports import reset_db
                reset_db(username)
                st.cache_data.clear()
                st.success("✅ БД сброшена")
                st.rerun()

# ===== MAIN =====
if __name__ == "__main__":
    st.set_page_config(page_title="Taxi Shift Manager", page_icon="🚕", layout="wide")
    apply_mobile_optimized_css()
    init_auth_db()
    ensure_users_dir()
    init_session()
    saved_username = load_session_from_disk()
    if saved_username and "username" not in st.session_state:
        st.session_state.username = saved_username
        st.session_state.page = "main"
    if "username" not in st.session_state:
        st.title("🚕 Taxi Shift Manager")
        st.markdown("### Вход / Регистрация")
        u = st.text_input("👤 Логин", width='stretch')
        p = st.text_input("🔑 Пароль", type="password", width='stretch')
        col1, col2 = st.columns(2)
        with col1:
            if st.button("🚀 Войти", width='stretch'):
                if authenticate_user(u, p):
                    st.session_state.username = u.strip()
                    st.session_state.page = "main"
                    st.rerun()
                else:
                    st.error("❌ Неверный логин/пароль")
        with col2:
            if st.button("➕ Регистрация", width='stretch'):
                if register_user(u, p):
                    st.success("✅ Зарегистрирован! Теперь войдите.")
                else:
                    st.error("❌ Ошибка регистрации (логин занят?)")
        st.stop()
    with st.sidebar:
        st.markdown(f"""
         <div style="text-align: center; padding: 20px 0;">
             <div style="font-size: 4rem; margin-bottom: 10px;">🚕</div>
             <div style="font-size: 1.5rem; font-weight: bold; margin-bottom: 5px;">{st.session_state.username}</div>
             <div style="color: #64748b; font-size: 0.9rem;">{get_session_time_remaining()}</div>
         </div>
         """, unsafe_allow_html=True)
        try:
            db_path = get_current_db_name(st.session_state.username)
            if os.path.exists(db_path):
                size = os.path.getsize(db_path) / 1024
                st.markdown(f"""
                 <div style="background: white; padding: 15px; border-radius: 12px; margin: 15px 0; text-align: center; box-shadow: 0 2px 8px rgba(0,0,0,0.1);">
                     <div style="font-size: 0.85rem; color: #64748b; margin-bottom: 5px;">Размер БД</div>
                     <div style="font-size: 1.5rem; font-weight: bold; color: #1e293b;">{size:.1f} KB</div>
                 </div>
                 """, unsafe_allow_html=True)
            acc = get_accumulated_beznal(st.session_state.username)
            st.markdown(f"""
             <div style="background: white; padding: 15px; border-radius: 12px; margin: 15px 0; text-align: center; box-shadow: 0 2px 8px rgba(0,0,0,0.1);">
                 <div style="font-size: 0.85rem; color: #64748b; margin-bottom: 5px;">Накопленный безнал</div>
                 <div style="font-size: 1.5rem; font-weight: bold; color: #1e293b;">{acc:.0f} ₽</div>
             </div>
             """, unsafe_allow_html=True)
        except Exception as e:
            st.error(f"Сайдбар ошибка: {e}")
        st.divider()
        if st.button("🏠 Главная", width='stretch'):
            st.session_state.page = "main"
            st.rerun()
        if st.button("📊 Отчёты", width='stretch'):
            st.session_state.page = "reports"
            st.rerun()
        if st.button("🔧 Админ", width='stretch'):
            st.session_state.page = "admin"
            st.rerun()
        st.divider()
        st.caption(f"Осталось: {get_session_time_remaining()}")
        if st.button("👋 Выход", width='stretch'):
            clear_session_disk()
            st.session_state.clear()
            st.rerun()
    page = st.session_state.get("page", "main")
    if page == "main":
        show_main_page()
    elif page == "reports":
        show_reports_page()
    elif page == "admin":
        show_admin_page()