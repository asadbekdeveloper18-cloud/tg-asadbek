import logging
import os
import sqlite3
from datetime import datetime, timedelta
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    CommandHandler,
    CallbackQueryHandler,
)

try:
    from telead import TeleAdAPI
except ImportError:
    TeleAdAPI = None

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Railway'dagi Environment Variables dan tokenni oladi
TOKEN = os.environ.get("BOT_TOKEN", "SIZNING_BOT_TOKENINGIZ")

def init_db():
    conn = sqlite3.connect("shield.db")
    cursor = conn.cursor()
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS campaigns (
            campaign_id INTEGER PRIMARY KEY,
            name TEXT,
            status TEXT,
            cpm REAL,
            last_views INTEGER DEFAULT 0,
            pause_until TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            campaign_id INTEGER,
            action TEXT,
            details TEXT
        )
    """)
    
    default_settings = [
        ("api_status", "Ulangan"),
        ("api_token", ""),
        ("protection", "1"),
        ("traffic_limit", "300"),
        ("spike", "1.2"),
        ("pause_time", "10"),
        ("check_interval", "60"),
        ("auto_resume", "1"),
        ("alerts", "1"),
        ("balance_account", "Pin Up • New"),
        ("balance_remaining", "7.0455 TON"),
        ("balance_ads", "1.573 TON"),
        ("balance_spent", "36.3815 TON")
    ]
    cursor.executemany("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", default_settings)
    cursor.execute("INSERT OR IGNORE INTO campaigns (campaign_id, name, status, cpm, last_views) VALUES (57, '1717', 'active', 5.0, 0)")
    
    conn.commit()
    conn.close()

init_db()

def get_setting(key):
    conn = sqlite3.connect("shield.db")
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM settings WHERE key=?", (key,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else ""

def update_setting(key, value):
    conn = sqlite3.connect("shield.db")
    cursor = conn.cursor()
    cursor.execute("UPDATE settings SET value=? WHERE key=?", (str(value), key))
    conn.commit()
    conn.close()

def get_main_keyboard():
    keyboard = [
        [InlineKeyboardButton("📊 Dashboard", callback_data="menu_dashboard"), InlineKeyboardButton("🛡 Anti-Fraud", callback_data="menu_antifraud")],
        [InlineKeyboardButton("📈 CPM Manager", callback_data="menu_cpm"), InlineKeyboardButton("💰 Balance", callback_data="menu_balance")],
        [InlineKeyboardButton("👥 Competitors", callback_data="menu_competitors"), InlineKeyboardButton("📢 Campaigns", callback_data="menu_campaigns")],
        [InlineKeyboardButton("📜 History", callback_data="menu_history"), InlineKeyboardButton("⚙️ Settings", callback_data="menu_settings")],
        [InlineKeyboardButton("🛑 EMERGENCY STOP", callback_data="menu_emergency")]
    ]
    return InlineKeyboardMarkup(keyboard)

async def anti_fraud_worker(context: ContextTypes.DEFAULT_TYPE):
    if get_setting("protection") != "1":
        return

    conn = sqlite3.connect("shield.db")
    cursor = conn.cursor()
    now = datetime.now()
    
    cursor.execute("SELECT campaign_id, pause_until FROM campaigns WHERE status='paused' AND pause_until IS NOT NULL")
    paused_campaigns = cursor.fetchall()
    
    for camp_id, pause_until_str in paused_campaigns:
        if pause_until_str:
            pause_until = datetime.strptime(pause_until_str, "%Y-%m-%d %H:%M:%S")
            if now >= pause_until and get_setting("auto_resume") == "1":
                cursor.execute("UPDATE campaigns SET status='active', pause_until=NULL WHERE campaign_id=?", (camp_id,))
                timestamp = now.strftime("%d.%m.%Y %H:%M")
                cursor.execute("INSERT INTO history (timestamp, campaign_id, action, details) VALUES (?, ?, 'AUTO_RESUME', 'Pauza vaqti tugadi, reklama tiklandi')", (timestamp, camp_id))
                conn.commit()

    cursor.execute("SELECT campaign_id, name, last_views FROM campaigns WHERE status='active'")
    active_camps = cursor.fetchall()
    
    limit = int(get_setting("traffic_limit"))
    spike_multiplier = float(get_setting("spike"))
    pause_mins = int(get_setting("pause_time"))
    api_token = get_setting("api_token")
    
    for camp_id, name, last_views in active_camps:
        current_views = last_views
        if TeleAdAPI and api_token:
            try:
                client = TeleAdAPI(api_token)
                stats = client.get_campaign_stats(camp_id)
                current_views = stats.get("views", last_views)
            except Exception as e:
                logger.error(f"API xatoligi (ID {camp_id}): {e}")
        
        view_diff = current_views - last_views
        is_spike = view_diff > (limit * spike_multiplier)
        is_limit_exceeded = current_views > limit
        
        if is_spike or is_limit_exceeded:
            pause_until = (now + timedelta(minutes=pause_mins)).strftime("%Y-%m-%d %H:%M:%S")
            cursor.execute("UPDATE campaigns SET status='paused', pause_until=? WHERE campaign_id=?", (pause_until, camp_id))
            timestamp = now.strftime("%d.%m.%Y %H:%M")
            reason = "SPIKE DETECTED" if is_spike else "TRAFFIC LIMIT EXCEEDED"
            cursor.execute("INSERT INTO history (timestamp, campaign_id, action, details) VALUES (?, ?, 'PAUSED', ?)", (timestamp, camp_id, f"{reason}: diff={view_diff}"))
            conn.commit()
        else:
            cursor.execute("UPDATE campaigns SET last_views=? WHERE campaign_id=?", (current_views, camp_id))
            conn.commit()

    conn.close()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "🛡 **TG ADS SHIELD PRO**\n\n"
        "Bot: **ONLINE**\n"
        f"Ads API: 🟢 {get_setting('api_status')}\n"
        f"Anti-Fraud: 🟢 **ON**\n\n"
        "API ulash: /api TOKEN\n"
        "Reklama qo'shish: /add REKLAMA_ID"
    )
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=get_main_keyboard())

async def set_api_token(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if not args:
        await update.message.reply_text("Iltimos, tokenni kiriting. Masalan: `/api SIZNING_TOKEN`", parse_mode="Markdown")
        return
    token = args[0]
    update_setting("api_token", token)
    update_setting("api_status", "Ulangan")
    await update.message.reply_text("✅ Ads API token muvaffaqiyatli saqlandi va ulandi!")

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "menu_dashboard":
        conn = sqlite3.connect("shield.db")
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM campaigns WHERE status='active'")
        active_count = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM campaigns WHERE status='paused'")
        paused_count = cursor.fetchone()[0]
        conn.close()

        text = (
            "🛡 **TG ADS SHIELD PRO — DASHBOARD**\n\n"
            f"Ads API: 🟢 {get_setting('api_status')}\n"
            "Protection: 🟢 **ON**\n"
            f"Kuzatilayotgan reklamalar: {active_count}\n"
            f"Bot pauzasidagi reklamalar: {paused_count}\n\n"
            f"Limit: {get_setting('traffic_limit')} views / 5 min\n"
            f"Spike: {get_setting('spike')}x\n"
            f"Pauza: {get_setting('pause_time')} min"
        )
        await query.message.edit_text(text, parse_mode="Markdown", reply_markup=get_main_keyboard())

    elif data == "menu_antifraud":
        text = (
            "🛡 **ANTI-FRAUD**\n\n"
            "Protection: **ON**\n"
            f"Limit: {get_setting('traffic_limit')} views / 5 min\n"
            f"Spike: {get_setting('spike')}x\n"
            f"Pause: {get_setting('pause_time')} min\n\n"
            "Sozlash: ⚙️ Settings"
        )
        await query.message.edit_text(text, parse_mode="Markdown", reply_markup=get_main_keyboard())

    elif data == "menu_cpm":
        text = "📈 **CPM Manager**\n\nHozircha faqat kuzatuv mavjud. CPMni avtomatik o'zgartirish bu versiyada yoqilmagan."
        await query.message.edit_text(text, parse_mode="Markdown", reply_markup=get_main_keyboard())

    elif data == "menu_balance":
        text = (
            "💰 **TELEGRAM ADS BALANCE**\n\n"
            f"Hisob: {get_setting('balance_account')}\n"
            f"Qolgan balans: {get_setting('balance_remaining')}\n"
            f"Reklamalarda: {get_setting('balance_ads')}\n"
            f"Sarflangan: {get_setting('balance_spent')}"
        )
        await query.message.edit_text(text, parse_mode="Markdown", reply_markup=get_main_keyboard())

    elif data == "menu_competitors":
        text = "👥 **Competitors**\n\nCompetitors monitoringi bu versiyada ulanmagan."
        await query.message.edit_text(text, parse_mode="Markdown", reply_markup=get_main_keyboard())

    elif data == "menu_campaigns":
        conn = sqlite3.connect("shield.db")
        cursor = conn.cursor()
        cursor.execute("SELECT campaign_id, name, status, cpm FROM campaigns")
        rows = cursor.fetchall()
        conn.close()

        text = "📢 **CAMPAIGNS**\n\n"
        for row in rows:
            text += f"ID: {row[0]}\nNomi: {row[1]}\nHolati: {row[2]}\nCPM: {row[3]}\n\n"
        await query.message.edit_text(text, parse_mode="Markdown", reply_markup=get_main_keyboard())

    elif data == "menu_history":
        conn = sqlite3.connect("shield.db")
        cursor = conn.cursor()
        cursor.execute("SELECT timestamp, campaign_id, action, details FROM history ORDER BY id DESC LIMIT 5")
        rows = cursor.fetchall()
        conn.close()

        text = "📜 **HISTORY**\n\n"
        if not rows:
            text += "Hozircha tarix bo'sh."
        else:
            for r in rows:
                text += f"{r[0]}\nAd: {r[1]}\n{r[2]}\n{r[3]}\n\n"
        await query.message.edit_text(text, parse_mode="Markdown", reply_markup=get_main_keyboard())

    elif data == "menu_settings":
        settings_keyboard = [
            [InlineKeyboardButton("🔑 Ads API token", callback_data="set_api"), InlineKeyboardButton("🛡 Protection ON/OFF", callback_data="set_prot")],
            [InlineKeyboardButton("📊 Traffic Limit", callback_data="set_limit"), InlineKeyboardButton("⚡️ Spike", callback_data="set_spike")],
            [InlineKeyboardButton("⏱ Pause Time", callback_data="set_pause"), InlineKeyboardButton("🔄 Check Interval", callback_data="set_interval")],
            [InlineKeyboardButton("♻️ Auto Resume ON/OFF", callback_data="set_auto_resume"), InlineKeyboardButton("🔔 Alerts ON/OFF", callback_data="set_alerts")],
            [InlineKeyboardButton("◀️ Main Menu", callback_data="menu_dashboard")]
        ]
        text = (
            "⚙️ **SETTINGS**\n\n"
            f"API: {get_setting('api_status')}\n"
            f"Protection: {get_setting('protection')}\n"
            f"Traffic limit: {get_setting('traffic_limit')}\n"
            f"Spike: {get_setting('spike')}x\n"
            f"Pause time: {get_setting('pause_time')} min\n"
            f"Check interval: {get_setting('check_interval')} sec\n"
            f"Auto resume: {get_setting('auto_resume')}\n"
            f"Alerts: {get_setting('alerts')}"
        )
        await query.message.edit_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(settings_keyboard))

    elif data == "menu_emergency":
        await query.message.edit_text(
            "🛑 **EMERGENCY STOP**\nTasdiqlash uchun `/stopall CONFIRM` yuboring.",
            parse_mode="Markdown",
            reply_markup=get_main_keyboard()
        )
    
    elif data.startswith("set_"):
        await query.message.reply_text("Bu sozlamani o'zgartirish uchun qiymat yuboring (masalan: `/setlimit 400` tarzida).")

async def add_campaign(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if not args:
        await update.message.reply_text("Iltimos, reklama ID sini kiriting. Masalan: `/add 57`", parse_mode="Markdown")
        return
    
    camp_id = args[0]
    conn = sqlite3.connect("shield.db")
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO campaigns (campaign_id, name, status, cpm, last_views) VALUES (?, ?, 'active', 5.0, 0)", (camp_id, camp_id))
    
    now = datetime.now().strftime("%d.%m.%Y %H:%M")
    cursor.execute("INSERT INTO history (timestamp, campaign_id, action, details) VALUES (?, ?, 'ADDED', 'Status: active')", (now, camp_id))
    conn.commit()
    conn.close()

    await update.message.reply_text(f"✅ Reklama (ID: {camp_id}) muvaffaqiyatli qo'shildi va kuzatuvga olindi!")

async def stop_all_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if args and args[0].upper() == "CONFIRM":
        conn = sqlite3.connect("shield.db")
        cursor = conn.cursor()
        cursor.execute("UPDATE campaigns SET status='paused'")
        conn.commit()
        conn.close()
        
        await update.message.reply_text(
            "🛑 **EMERGENCY STOP FAOL!**\nBarcha faol reklamalar va himoya to'xtatildi.",
            parse_mode="Markdown",
            reply_markup=get_main_keyboard()
        )
    else:
        await update.message.reply_text(
            "⚠️ Tasdiqlash uchun buyruqni quyidagicha yuboring:\n`/stopall CONFIRM`",
            parse_mode="Markdown"
        )

def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("add", add_campaign))
    app.add_handler(CommandHandler("api", set_api_token))
    app.add_handler(CommandHandler("stopall", stop_all_command))
    app.add_handler(CallbackQueryHandler(button_handler))

    job_queue = app.job_queue
    interval = int(get_setting("check_interval"))
    job_queue.run_repeating(anti_fraud_worker, interval=interval, first=10)

    print("Bot Railway da ishga tushdi...")
    app.run_polling()

if __name__ == "__main__":
    main()
