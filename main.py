import os
from flask import Flask
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import sqlite3
import threading
import time
import random
import io
from PIL import Image, ImageDraw, ImageFont

# ================= 0. MAGIC COLOR FIX =================
original_to_dict = InlineKeyboardButton.to_dict
def custom_to_dict(self):
    d = original_to_dict(self)
    if hasattr(self, 'style'):
        d['style'] = self.style
    return d
InlineKeyboardButton.to_dict = custom_to_dict

# ================= 1. NEW TOKENS & CONFIG =================
MAIN_TOKEN = "8212871280:AAHHsiW9snxpv6g7pdY-ManWIVxuemFbWW4"
FINANCE_TOKEN = "8684764660:AAFBsBCtxbu7m0ccAk4Lu1QADZicgH-dfNc"
PREDICTION_TOKEN = "8781003969:AAFysf9fPDa2_ptakcU8sVOcZI2UTRid2cc" 

ADMIN_ID = 1484173564
PREDICTION_CHANNEL = "@predictoin_profit_bot" 
SUPPORT_USERNAME = "@BOTTREADINGSUPPORT" 
BOT_USERNAME = "CLOUR_TREADING_PROFIT_BOT" 

bot_main = telebot.TeleBot(MAIN_TOKEN, threaded=True, num_threads=5)
bot_finance = telebot.TeleBot(FINANCE_TOKEN, threaded=True, num_threads=3)
bot_deposit = bot_finance
bot_withdraw = bot_finance
bot_prediction = telebot.TeleBot(PREDICTION_TOKEN)

try:
    bot_main.remove_webhook()
    bot_finance.remove_webhook()
    bot_prediction.remove_webhook()
    time.sleep(1)
except: pass

# ================= SAFE ANSWER SHIELD =================
def safe_answer(call, bot=bot_main):
    try:
        bot.answer_callback_query(call.id)
    except: pass

# ================= 2. SUPER FAST SQLITE SETUP =================
def get_db():
    conn = sqlite3.connect('wingo_platform.db', check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL;") # Prevents Database Locked Errors
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, balance REAL DEFAULT 0, state TEXT, temp_data TEXT, refer_count INTEGER DEFAULT 0)''')
    c.execute('''CREATE TABLE IF NOT EXISTS admin_wallet (id INTEGER PRIMARY KEY, total_commission REAL DEFAULT 0)''')
    c.execute("INSERT OR IGNORE INTO admin_wallet (id, total_commission) VALUES (1, 0)")
    c.execute('''CREATE TABLE IF NOT EXISTS channels (chat_id TEXT PRIMARY KEY, name TEXT, color TEXT, invite_link TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS active_bets (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, mode TEXT, prediction TEXT, amount REAL)''')
    c.execute('''CREATE TABLE IF NOT EXISTS history (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, action TEXT, amount REAL, detail TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)''')
    c.execute('''CREATE TABLE IF NOT EXISTS game_trends (id INTEGER PRIMARY KEY AUTOINCREMENT, mode TEXT, period TEXT, number INTEGER, color TEXT, size TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS promo_codes (code TEXT PRIMARY KEY, amount REAL, uses_left INTEGER)''')
    c.execute('''CREATE TABLE IF NOT EXISTS promo_used (user_id INTEGER, code TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS period_data (mode TEXT PRIMARY KEY, period_id TEXT, number TEXT, color TEXT, size TEXT)''')
    conn.commit()
    conn.close()

init_db()

def user_exists(user_id):
    conn = get_db(); c = conn.cursor()
    c.execute("SELECT user_id FROM users WHERE user_id=?", (user_id,))
    exists = c.fetchone() is not None
    conn.close(); return exists

def get_user(user_id):
    conn = get_db(); c = conn.cursor()
    c.execute("SELECT balance, state, temp_data, refer_count FROM users WHERE user_id=?", (user_id,))
    res = c.fetchone()
    if not res:
        c.execute("INSERT INTO users (user_id, balance, state, temp_data, refer_count) VALUES (?, 0, 'idle', '', 0)", (user_id,))
        conn.commit(); res = (0, 'idle', '', 0)
    conn.close(); return res

def update_user(user_id, **kwargs):
    conn = get_db(); c = conn.cursor()
    for key, value in kwargs.items(): c.execute(f"UPDATE users SET {key}=? WHERE user_id=?", (value, user_id))
    conn.commit(); conn.close()

# ================= 3. BOSS LEVEL ADMIN COMMANDS =================
@bot_main.message_handler(commands=['admin'])
def admin_panel(message):
    if message.from_user.id != ADMIN_ID: return
    markup = InlineKeyboardMarkup()
    markup.row(InlineKeyboardButton("➕ Add Channel", callback_data="admin_add_channel", **{'style': 'primary'}), 
               InlineKeyboardButton("💼 My Wallet", callback_data="admin_wallet", **{'style': 'success'}))
    markup.row(InlineKeyboardButton("📢 Broadcast", callback_data="admin_broadcast", **{'style': 'danger'}))
    
    admin_text = (
        "🛠️ *BOSS ADMIN PANEL*\n\n"
        "Extra Commands:\n"
        "📊 `/livebets` - Dekho kis rang par kitna paisa laga hai\n"
        "💰 `/addbalance UserID Amount` - Balance badhao\n"
        "✂️ `/cutbalance UserID Amount` - Balance kaato\n"
        "🎁 `/createpromo CODE Amount Uses` - Lifafa banao\n"
    )
    bot_main.send_message(ADMIN_ID, admin_text, reply_markup=markup, parse_mode="Markdown")

@bot_main.message_handler(commands=['livebets'])
def live_tracker(message):
    if message.from_user.id != ADMIN_ID: return
    conn = get_db(); c = conn.cursor()
    c.execute("SELECT mode, prediction, SUM(amount) FROM active_bets GROUP BY mode, prediction")
    records = c.fetchall(); conn.close()
    
    if not records:
        bot_main.send_message(ADMIN_ID, "📭 Abhi koi active bet nahi hai.")
        return
        
    text = "📊 *LIVE BET TRACKER*\n━━━━━━━━━━━━━━━━━━\n"
    for r in records: text += f"🎮 Mode: *{r[0]} Min* | Choice: *{r[1].upper()}* | Total: ₹{r[2]}\n"
    bot_main.send_message(ADMIN_ID, text, parse_mode="Markdown")

@bot_main.message_handler(commands=['addbalance', 'cutbalance'])
def manual_balance(message):
    if message.from_user.id != ADMIN_ID: return
    try:
        cmd, target_id, amount = message.text.split()
        target_id, amount = int(target_id), float(amount)
        bal, _, _, _ = get_user(target_id)
        if cmd == "/addbalance": new_bal = bal + amount; action_text = "Added"
        else: new_bal = max(0, bal - amount); action_text = "Deducted"
        update_user(target_id, balance=new_bal)
        bot_main.send_message(ADMIN_ID, f"✅ Success! ₹{amount} {action_text}. New Balance: ₹{new_bal}")
        bot_main.send_message(target_id, f"🔔 Admin Update: ₹{amount} has been {action_text} from your wallet. Current Balance: ₹{new_bal}")
    except: bot_main.send_message(ADMIN_ID, "❌ Syntax Error! Use: `/addbalance UserID Amount`", parse_mode="Markdown")

@bot_main.message_handler(commands=['createpromo'])
def create_promo(message):
    if message.from_user.id != ADMIN_ID: return
    try:
        _, code, amount, uses = message.text.split()
        amount, uses = float(amount), int(uses)
        code = code.upper()
        conn = get_db(); c = conn.cursor()
        c.execute("REPLACE INTO promo_codes (code, amount, uses_left) VALUES (?, ?, ?)", (code, amount, uses))
        conn.commit(); conn.close()
        bot_main.send_message(ADMIN_ID, f"🎁 *Promo Code Created!*\n\nCode: `{code}`\nAmount: ₹{amount}\nUses: {uses}", parse_mode="Markdown")
    except: bot_main.send_message(ADMIN_ID, "❌ Syntax Error! Use: `/createpromo CODE AMOUNT USES`", parse_mode="Markdown")

@bot_main.callback_query_handler(func=lambda call: call.data.startswith("admin_"))
def admin_actions(call):
    safe_answer(call)
    try:
        action = call.data.split("_")[1]
        if action in ["add_channel", "add"]:
            msg = bot_main.send_message(ADMIN_ID, "Step 1: Bot ko channel me Admin banayein.\nStep 2: Channel ka ID (e.g. -100123...) bhejein:")
            bot_main.register_next_step_handler(msg, verify_admin_and_ask_color)
        elif action == "wallet":
            conn = get_db(); c = conn.cursor()
            c.execute("SELECT total_commission FROM admin_wallet WHERE id=1")
            bal = c.fetchone()[0]; conn.close()
            bot_main.send_message(ADMIN_ID, f"💼 Aapka Total 15% Commission: ₹{bal}")
        elif action == "broadcast":
            msg = bot_main.send_message(ADMIN_ID, "📢 Jo message sabko bhejna hai, wo type karein:")
            bot_main.register_next_step_handler(msg, process_broadcast)
    except Exception as e: bot_main.send_message(call.message.chat.id, f"⚠️ Error: {e}")

def process_broadcast(message):
    conn = get_db(); c = conn.cursor()
    c.execute("SELECT user_id FROM users")
    users = c.fetchall(); conn.close()
    sent = 0
    bot_main.send_message(ADMIN_ID, "⏳ Broadcasting started...")
    for u in users:
        try:
            bot_main.send_message(u[0], f"📢 *Admin Update*\n\n{message.text}", parse_mode="Markdown")
            sent += 1
        except: pass
    bot_main.send_message(ADMIN_ID, f"✅ Broadcast sent successfully to {sent} users!")

def verify_admin_and_ask_color(message):
    chat_id = message.text.strip()
    try:
        chat_info = bot_main.get_chat(chat_id)
        member = bot_main.get_chat_member(chat_id, bot_main.get_me().id)
        if member.status in ['administrator', 'creator']:
            try:
                invite_link = bot_main.create_chat_invite_link(chat_id, creates_join_request=True).invite_link
            except:
                try: invite_link = bot_main.export_chat_invite_link(chat_id)
                except: return bot_main.send_message(ADMIN_ID, "❌ *Error:* Invite link permission nahi hai.", parse_mode="Markdown")

            update_user(ADMIN_ID, state="wait_color", temp_data=f"{chat_id}|{chat_info.title}|{invite_link}")
            markup = InlineKeyboardMarkup()
            markup.row(InlineKeyboardButton("GREEN", callback_data="setcol_success", **{'style': 'success'}), InlineKeyboardButton("RED", callback_data="setcol_danger", **{'style': 'danger'}))
            markup.row(InlineKeyboardButton("BLUE", callback_data="setcol_primary", **{'style': 'primary'}), InlineKeyboardButton("NORMAL", callback_data="setcol_normal")) 
            bot_main.send_message(ADMIN_ID, f"✅ Bot '{chat_info.title}' mein Admin hai!\nJoin Button ka **Color** select karein:", reply_markup=markup)
        else: bot_main.send_message(ADMIN_ID, "❌ *Error:* Bot channel mein Administrator nahi hai.", parse_mode="Markdown")
    except Exception as e: bot_main.send_message(ADMIN_ID, f"❌ *Error:* {e}", parse_mode="Markdown")

@bot_main.callback_query_handler(func=lambda call: call.data.startswith("setcol_"))
def save_channel_final(call):
    safe_answer(call)
    try:
        color_style = call.data.split("_")[1]
        _, _, temp_data, _ = get_user(ADMIN_ID)
        if temp_data:
            chat_id, title, invite_link = temp_data.split("|")
            conn = get_db(); c = conn.cursor()
            c.execute("REPLACE INTO channels (chat_id, name, color, invite_link) VALUES (?, ?, ?, ?)", (chat_id, title, color_style, invite_link))
            conn.commit(); conn.close()
            bot_main.edit_message_text(f"✅ Channel '{title}' add ho gaya!", call.message.chat.id, call.message.message_id)
            update_user(ADMIN_ID, state="idle", temp_data="")
    except Exception as e: bot_main.send_message(call.message.chat.id, f"⚠️ Error: {e}")

# ================= 4. JOIN REQUEST AUTO-APPROVE =================
@bot_main.chat_join_request_handler()
def approve_join_request(message):
    try:
        bot_main.approve_chat_join_request(message.chat.id, message.from_user.id)
        bot_main.send_message(message.from_user.id, f"✅ Aapki {message.chat.title} ki Join Request approve ho gayi hai! Ab 'Try Again' click karein.")
    except: pass

# ================= 5. START MENU & FORCE SUB =================
@bot_main.message_handler(commands=['start'])
def user_start(message):
    user_id = message.from_user.id
    args = message.text.split()
    if len(args) > 1 and args[1].isdigit():
        referrer_id = int(args[1])
        if referrer_id != user_id and not user_exists(user_id):
            conn = get_db(); c = conn.cursor()
            c.execute("UPDATE users SET refer_count = refer_count + 1 WHERE user_id=?", (referrer_id,))
            conn.commit(); conn.close()

    get_user(user_id) 
    conn = get_db(); c = conn.cursor()
    c.execute("SELECT chat_id, name, color, invite_link FROM channels")
    channels = c.fetchall(); conn.close()
    
    not_joined = []
    for ch_id, name, color, invite_link in channels:
        try:
            status = bot_main.get_chat_member(ch_id, user_id).status
            if status in ['left', 'kicked']: not_joined.append((name, color, invite_link))
        except: not_joined.append((name, color, invite_link))

    if not_joined:
        markup = InlineKeyboardMarkup()
        for name, color, invite_link in not_joined:
            if color in ['success', 'danger', 'primary']: markup.add(InlineKeyboardButton(f"Join {name}", url=invite_link, **{'style': color}))
            else: markup.add(InlineKeyboardButton(f"Join {name}", url=invite_link))
        markup.add(InlineKeyboardButton("🔄 Try Again", callback_data="check_join", **{'style': 'primary'}))
        bot_main.send_photo(user_id, photo='https://files.catbox.moe/my6qos.jpg', caption="⚠️ Aage badhne ke liye sabhi channels Join karein!", reply_markup=markup)
    else: send_main_menu(user_id, message.from_user.first_name)

@bot_main.callback_query_handler(func=lambda call: call.data == "check_join")
def recheck_join(call):
    safe_answer(call)
    bot_main.delete_message(call.message.chat.id, call.message.message_id)
    user_start(call.message)

def send_main_menu(user_id, name):
    balance, _, _, _ = get_user(user_id)
    text = f"✨ *Hello {name}!* ✨\n\n💰 *Your Balance:* `₹{balance}`\n━━━━━━━━━━━━━━━━━━\n🚀 *Apna Game Mode chunein aur Earning shuru karein!*"
    markup = InlineKeyboardMarkup()
    markup.row(InlineKeyboardButton("⏱ 1 MIN", callback_data="wingo_1", **{'style': 'primary'}), InlineKeyboardButton("⏳ 2 MIN", callback_data="wingo_2", **{'style': 'primary'}))
    markup.row(InlineKeyboardButton("🕒 3 MIN", callback_data="wingo_3", **{'style': 'primary'}), InlineKeyboardButton("🕓 5 MIN", callback_data="wingo_5", **{'style': 'primary'}))
    markup.row(InlineKeyboardButton("🕔 15 MIN", callback_data="wingo_15", **{'style': 'primary'}))
    markup.row(InlineKeyboardButton("💳 DEPOSIT", callback_data="deposit", **{'style': 'success'}), InlineKeyboardButton("📤 WITHDRAW", callback_data="withdraw", **{'style': 'danger'}))
    markup.row(InlineKeyboardButton("📜 MY BETS", callback_data="history", **{'style': 'primary'}), InlineKeyboardButton("👥 REFER & EARN", callback_data="refer", **{'style': 'success'}))
    markup.row(InlineKeyboardButton("👤 PROFILE", callback_data="profile", **{'style': 'primary'}), InlineKeyboardButton("🎧 SUPPORT", callback_data="support", **{'style': 'danger'}))
    markup.row(InlineKeyboardButton("🎁 PROMO CODE", callback_data="promo_menu", **{'style': 'success'}))
    bot_main.send_message(user_id, text, reply_markup=markup, parse_mode="Markdown")

@bot_main.callback_query_handler(func=lambda call: call.data in ["refer", "profile", "support", "promo_menu"])
def extra_menus(call):
    safe_answer(call)
    try:
        user_id = call.from_user.id; balance, _, _, ref_count = get_user(user_id)
        if call.data == "refer":
            bot_link = f"https://t.me/{BOT_USERNAME}?start={user_id}"
            text = f"🎁 *REFER & EARN* 🎁\n\nApne doston ko invite karein!\n🎉 *15 Referrals = ₹15 Bonus*\n\n📊 *Aapke Referrals:* `{ref_count} / 15`\n\n🔗 *Aapka Invite Link:*\n`{bot_link}`"
            markup = InlineKeyboardMarkup().add(InlineKeyboardButton("🎁 CLAIM ₹15 BONUS", callback_data="claim_referral", **{'style': 'success'})).add(InlineKeyboardButton("🔙 Back", callback_data="back_main", **{'style': 'danger'}))
            bot_main.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=markup, parse_mode="Markdown")
        elif call.data == "profile":
            text = f"👤 *MY PROFILE* 👤\n\n🆔 *User ID:* `{user_id}`\n💰 *Total Balance:* `₹{balance}`\n👥 *Total Refs:* `{ref_count}`\n🏅 *Status:* Active User"
            markup = InlineKeyboardMarkup().add(InlineKeyboardButton("🔙 Back", callback_data="back_main", **{'style': 'danger'}))
            bot_main.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=markup, parse_mode="Markdown")
        elif call.data == "support":
            text = f"🎧 *CUSTOMER SUPPORT* 🎧\n\nAgar aapko Deposit, Withdraw ya Game mein koi problem aa rahi hai, toh direct Admin se baat karein:\n\n💬 *Contact:* {SUPPORT_USERNAME}\n⏳ *Reply Time:* 24/7 Available"
            markup = InlineKeyboardMarkup().add(InlineKeyboardButton("🔙 Back", callback_data="back_main", **{'style': 'danger'}))
            bot_main.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=markup, parse_mode="Markdown")
        elif call.data == "promo_menu":
            update_user(user_id, state="wait_promo")
            bot_main.send_message(user_id, "🎁 *PROMO CODE*\n\nKripya apna Promo Code yahan type karein:", parse_mode="Markdown")
    except Exception as e: bot_main.send_message(call.message.chat.id, f"⚠️ Menu Error: {e}")

@bot_main.callback_query_handler(func=lambda call: call.data == "claim_referral")
def claim_ref_bonus(call):
    safe_answer(call)
    try:
        user_id = call.from_user.id; bal, _, _, ref_count = get_user(user_id)
        if ref_count >= 15:
            update_user(user_id, balance=bal+15, refer_count=ref_count-15)
            bot_main.send_message(user_id, "🎉 CONGRATULATIONS! ₹15 added to your wallet!")
            bot_main.delete_message(call.message.chat.id, call.message.message_id)
            send_main_menu(user_id, call.from_user.first_name)
        else: bot_main.send_message(user_id, "❌ Pehle 15 Refer completely karo fir milega!")
    except Exception as e: bot_main.send_message(call.message.chat.id, f"⚠️ Ref Error: {e}")

# ================= 6. WINGO GAME UI =================
@bot_main.callback_query_handler(func=lambda call: call.data.startswith("wingo_"))
def wingo_menu(call):
    safe_answer(call)
    try:
        user_id = call.from_user.id; mode = call.data.split("_")[1]
        balance, _, _, _ = get_user(user_id)

        mode_seconds = int(mode) * 60; current_time = int(time.time())
        next_period_num = (current_time // mode_seconds) + 1
        period_id = f"{time.strftime('%Y%m%d')}-{mode}M-{next_period_num}"
        time_left = (next_period_num * mode_seconds) - current_time

        markup = InlineKeyboardMarkup(row_width=5)
        markup.row(InlineKeyboardButton(f"🔄 Refresh Timer (⏳ {time_left}s left)", callback_data=f"wingo_{mode}"))
        markup.row(InlineKeyboardButton("📊 Game History (Trends)", callback_data=f"trend_{mode}"))

        nums = [InlineKeyboardButton(str(i), callback_data=f"bet_{i}_{mode}", **{'style': 'success'}) for i in range(10)]
        markup.add(*nums)
        markup.row(InlineKeyboardButton("GREEN", callback_data=f"bet_grn_{mode}", **{'style': 'success'}), InlineKeyboardButton("RED", callback_data=f"bet_red_{mode}", **{'style': 'danger'}), InlineKeyboardButton("VIOLET", callback_data=f"bet_vio_{mode}", **{'style': 'primary'}))
        markup.row(InlineKeyboardButton("BIG", callback_data=f"bet_big_{mode}", **{'style': 'primary'}), InlineKeyboardButton("SMALL", callback_data=f"bet_sml_{mode}", **{'style': 'primary'}))
        markup.add(InlineKeyboardButton("🔙 Back", callback_data="back_main", **{'style': 'danger'}))
        
        text = f"🎮 *WINGO {mode} MIN*\n🆔 *Period:* `{period_id}`\n⏳ *Time Remaining:* `{time_left} Seconds`\n💰 *Balance:* `₹{balance}`\n\n👇 Apna Prediction chunein:"
        bot_main.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=markup, parse_mode="Markdown")
    except Exception as e: bot_main.send_message(call.message.chat.id, f"⚠️ Wingo Error: {e}")

@bot_main.callback_query_handler(func=lambda call: call.data.startswith("trend_"))
def show_trends(call):
    safe_answer(call)
    try:
        mode = call.data.split("_")[1]
        conn = get_db(); c = conn.cursor()
        c.execute("SELECT period, number, size, color FROM game_trends WHERE mode=? ORDER BY id DESC LIMIT 10", (mode,))
        records = c.fetchall(); conn.close()
        
        if not records: return bot_main.send_message(call.message.chat.id, "Thoda wait karein, history update hogi!")
            
        text = f"📊 *WINGO {mode} MIN - GAME HISTORY*\n━━━━━━━━━━━━━━━━━━\n`Period` | `Num` | `Size` | `Color`\n──────────────────\n"
        for r in records: text += f"`{r[0][-5:]}` | `{r[1]}` | `{r[2].upper()}` | `{r[3]}`\n"
        bot_main.send_message(call.message.chat.id, text, parse_mode="Markdown")
    except Exception as e: bot_main.send_message(call.message.chat.id, f"⚠️ Trend Error: {e}")

@bot_main.callback_query_handler(func=lambda call: call.data.startswith("bet_"))
def ask_bet_amount(call):
    safe_answer(call)
    try:
        user_id = call.from_user.id; mode = call.data.split("_")[-1]
        mode_seconds = int(mode) * 60; current_time = int(time.time())
        next_period_num = (current_time // mode_seconds) + 1
        period_id = f"{time.strftime('%Y%m%d')}-{mode}M-{next_period_num}"
        time_left = (next_period_num * mode_seconds) - current_time
        
        if time_left <= 10: return bot_main.send_message(user_id, "⚠️ Betting is closed for this period! Please wait for next.")
        update_user(user_id, state="wait_bet", temp_data=call.data)
        bot_main.send_message(user_id, f"🆔 *Period:* `{period_id}`\n💰 Kitna amount lagana hai? (Limit: ₹10 - ₹10,000)", parse_mode="Markdown")
    except Exception as e: bot_main.send_message(call.message.chat.id, f"⚠️ Bet Error: {e}")

# ================= 7. HISTORY, DEPOSIT & PROMO LOGIC =================
@bot_main.callback_query_handler(func=lambda call: call.data == "history")
def show_history(call):
    safe_answer(call)
    try:
        user_id = call.from_user.id
        conn = get_db(); c = conn.cursor()
        c.execute("SELECT action, amount, detail, timestamp FROM history WHERE user_id=? ORDER BY id DESC LIMIT 5", (user_id,))
        records = c.fetchall(); conn.close()
        if not records: return bot_main.send_message(user_id, "📭 Aapki koi bet history nahi hai.")
        hist_text = "📜 *Aapki Recent Bet History:*\n\n"
        for r in records: hist_text += f"🔹 *{r[0]}* | ₹{r[1]}\n📝 Detail: {r[2]}\n🕒 {r[3]}\n➖➖➖➖➖➖\n"
        bot_main.send_message(user_id, hist_text, parse_mode="Markdown")
    except Exception as e: bot_main.send_message(call.message.chat.id, f"⚠️ History Error: {e}")

@bot_main.callback_query_handler(func=lambda call: call.data in ["deposit", "withdraw", "back_main"])
def finance_menus(call):
    safe_answer(call)
    try:
        user_id = call.from_user.id
        if call.data == "back_main":
            bot_main.delete_message(call.message.chat.id, call.message.message_id)
            send_main_menu(user_id, call.from_user.first_name)
        elif call.data == "deposit":
            markup = InlineKeyboardMarkup()
            markup.row(InlineKeyboardButton("₹100", callback_data="dep_100", **{'style': 'success'}), InlineKeyboardButton("₹299", callback_data="dep_299", **{'style': 'success'}))
            markup.row(InlineKeyboardButton("₹599", callback_data="dep_599", **{'style': 'success'}), InlineKeyboardButton("₹999", callback_data="dep_999", **{'style': 'success'}))
            bot_main.send_message(user_id, "Deposit Amount select karein:", reply_markup=markup)
        elif call.data == "withdraw":
            update_user(user_id, state="wait_with_amt")
            bot_main.send_message(user_id, "Kitna amount withdraw karna hai? (Min 100)")
    except Exception as e: bot_main.send_message(call.message.chat.id, f"⚠️ Menu Error: {e}")

@bot_main.callback_query_handler(func=lambda call: call.data.startswith("dep_"))
def show_qr(call):
    safe_answer(call)
    try:
        amt = call.data.split("_")[1]
        update_user(call.from_user.id, state="wait_ss", temp_data=amt)
        bot_main.send_photo(call.from_user.id, photo="https://files.catbox.moe/zhw20j.jpg", caption=f"₹{amt} pay karein aur Screen shot send karo.")
    except Exception as e: bot_main.send_message(call.message.chat.id, f"⚠️ QR Error: {e}")

@bot_main.message_handler(content_types=['text', 'photo'])
def handle_inputs(message):
    user_id = message.from_user.id
    bal, state, temp, _ = get_user(user_id)

    if state == "wait_bet" and message.text and message.text.isdigit():
        amt = int(message.text)
        if 10 <= amt <= 10000:
            if bal >= amt:
                conn = get_db(); c = conn.cursor()
                c.execute("UPDATE users SET balance = balance - ?, state='idle', temp_data='' WHERE user_id=?", (amt, user_id))
                parts = temp.split("_"); prediction = parts[1]; mode = parts[2]
                c.execute("INSERT INTO active_bets (user_id, mode, prediction, amount) VALUES (?, ?, ?, ?)", (user_id, mode, prediction, amt))
                c.execute("INSERT INTO history (user_id, action, amount, detail) VALUES (?, 'Bet Placed', ?, ?)", (user_id, amt, f"Mode: {mode}M, Choice: {prediction.upper()}"))
                conn.commit(); conn.close()
                bot_main.send_message(user_id, f"✅ *Bet Placed Successfully!*\n🎮 Mode: WINGO {mode} MIN\n🎯 Choice: {prediction.upper()}\n💰 Amount: ₹{amt}\n💳 Remaining Balance: ₹{bal-amt}", parse_mode="Markdown")
            else: bot_main.send_message(user_id, "❌ Balance kam hai.")
        else: bot_main.send_message(user_id, "❌ Limit: ₹10 - ₹10,000")
        
    elif state == "wait_ss":
        if message.content_type == 'photo':
            bot_main.send_message(user_id, "⏳ Admin approval ka wait karein.")
            markup = InlineKeyboardMarkup()
            markup.row(InlineKeyboardButton("✅ Approve", callback_data=f"dapp_{user_id}_{temp}", **{'style': 'success'}), InlineKeyboardButton("❌ Reject", callback_data=f"drej_{user_id}", **{'style': 'danger'}))
            try:
                file_info = bot_main.get_file(message.photo[-1].file_id)
                downloaded_file = bot_main.download_file(file_info.file_path)
                caption_text = f"📥 *NEW DEPOSIT REQUEST*\n\n👤 User ID: `{user_id}`\n💰 Amount: `₹{temp}`"
                try: bot_deposit.send_photo(ADMIN_ID, photo=downloaded_file, caption=caption_text, reply_markup=markup, parse_mode="Markdown")
                except: bot_main.send_message(user_id, "❌ Admin ka finance bot chalu nahi hai.")
            except: bot_main.send_message(user_id, "❌ Screenshot process karne me dikkat aayi.")
            update_user(user_id, state="idle", temp_data="")
        else: bot_main.reply_to(message, "Payment karo aur screen shot send karo")
        
    elif state == "wait_with_amt" and message.text and message.text.isdigit():
        amt = int(message.text)
        if amt >= 100 and bal >= amt:
            update_user(user_id, state="wait_with_upi", temp_data=str(amt))
            bot_main.send_message(user_id, "Apna UPI ID aur Phone Number bhejein:")
        else: bot_main.send_message(user_id, "❌ Invalid amount ya balance kam hai.")
        
    elif state == "wait_with_upi":
        if not message.text: return bot_main.send_message(user_id, "❌ Kripya text message bhejein.")
        upi_or_phone = message.text.strip(); check_num = upi_or_phone.replace(" ", "")
        if "@" not in upi_or_phone and not (check_num.isdigit() and len(check_num) >= 10):
            return bot_main.send_message(user_id, "⚠️ *WARNING!* Galat Details!\nSahi UPI ID ya 10-digit Phone Number daalein.", parse_mode="Markdown")
            
        amt = float(temp); markup = InlineKeyboardMarkup()
        markup.row(InlineKeyboardButton("✅ Approve", callback_data=f"wapp_{user_id}_{amt}", **{'style': 'success'}), InlineKeyboardButton("❌ Reject", callback_data=f"wrej_{user_id}_{amt}", **{'style': 'danger'}))
        try:
            bot_withdraw.send_message(ADMIN_ID, f"📤 *WITHDRAW REQUEST*\n\nUser: `{user_id}`\nAmount: ₹{amt}\nUPI/Phone: `{upi_or_phone}`", reply_markup=markup, parse_mode="Markdown")
            bot_main.send_message(user_id, "⏳ Payment In Pending... Admin check kar rahe hain.")
            conn = get_db(); conn.execute("UPDATE users SET balance = balance - ? WHERE user_id=?", (amt, user_id))
            conn.execute("INSERT INTO history (user_id, action, amount, detail) VALUES (?, 'Withdraw Requested', ?, ?)", (user_id, amt, f"UPI: {upi_or_phone}"))
            conn.commit(); conn.close()
        except: bot_main.send_message(user_id, f"❌ Withdraw request fail ho gayi.")
        update_user(user_id, state="idle", temp_data="")

    elif state == "wait_promo" and message.text:
        code = message.text.strip().upper()
        conn = get_db(); c = conn.cursor()
        c.execute("SELECT * FROM promo_used WHERE user_id=? AND code=?", (user_id, code))
        if c.fetchone():
            bot_main.send_message(user_id, "❌ Aap ye promo code pehle hi use kar chuke hain."); update_user(user_id, state="idle"); conn.close(); return
        c.execute("SELECT amount, uses_left FROM promo_codes WHERE code=?", (code,))
        promo = c.fetchone()
        if promo and promo[1] > 0:
            p_amt = promo[0]
            c.execute("UPDATE users SET balance = balance + ? WHERE user_id=?", (p_amt, user_id))
            c.execute("UPDATE promo_codes SET uses_left = uses_left - 1 WHERE code=?", (code,))
            c.execute("INSERT INTO promo_used (user_id, code) VALUES (?, ?)", (user_id, code))
            conn.commit(); bot_main.send_message(user_id, f"🎉 *YAY!* Promo Code Applied!\n🎁 *₹{p_amt}* added to your wallet.", parse_mode="Markdown")
        else: bot_main.send_message(user_id, "❌ Invalid Promo Code ya Limit khatam ho chuki hai.")
        update_user(user_id, state="idle"); conn.close()

# ================= 8. ADMIN APPROVAL BOTS =================
@bot_deposit.callback_query_handler(func=lambda call: call.data.split('_')[0] in ["dapp", "drej", "wapp", "wrej"])
def finance_admin(call):
    safe_answer(call, bot_deposit)
    try:
        data = call.data.split("_"); action = data[0]; user_id = int(data[1])
        if action == "dapp":
            amt = float(data[2]); bal, _, _, _ = get_user(user_id); update_user(user_id, balance=bal+amt)
            try:
                conn = get_db(); conn.execute("INSERT INTO history (user_id, action, amount, detail) VALUES (?, 'Deposit Approved', ?, 'Via Admin')", (user_id, amt)); conn.commit(); conn.close()
            except: pass
            try: bot_deposit.edit_message_caption(f"✅ ₹{amt} Approved for {user_id}", call.message.chat.id, call.message.message_id)
            except: bot_deposit.edit_message_text(f"✅ ₹{amt} Approved for {user_id}", call.message.chat.id, call.message.message_id)
            bot_main.send_message(user_id, f"✅ *Deposit Successful!*\n₹{amt} added to your wallet.", parse_mode="Markdown")
        elif action == "drej":
            try: bot_deposit.edit_message_caption(f"❌ Rejected for {user_id}", call.message.chat.id, call.message.message_id)
            except: bot_deposit.edit_message_text(f"❌ Rejected for {user_id}", call.message.chat.id, call.message.message_id)
            bot_main.send_message(user_id, "❌ *PAYMENT REJECTED!* Real payment karo aur screenshot send karo.", parse_mode="Markdown")
        elif action == "wapp":
            amt = float(data[2]); bot_withdraw.edit_message_text(f"✅ Withdraw ₹{amt} Approved", call.message.chat.id, call.message.message_id)
            bot_main.send_message(user_id, f"✅ Aapke UPI id par ₹{amt} aa chuka hai.")
        elif action == "wrej":
            amt = float(data[2]); bal, _, _, _ = get_user(user_id); update_user(user_id, balance=bal+amt)
            try:
                conn = get_db(); conn.execute("INSERT INTO history (user_id, action, amount, detail) VALUES (?, 'Withdraw Rejected', ?, 'Refunded')", (user_id, amt)); conn.commit(); conn.close()
            except: pass
            bot_withdraw.edit_message_text(f"❌ Withdraw Rejected", call.message.chat.id, call.message.message_id)
            bot_main.send_message(user_id, "❌ Withdraw Reject ho gaya hai. Balance wapas add kar diya gaya hai.")
    except Exception as e: bot_deposit.send_message(call.message.chat.id, f"⚠️ Admin Error: {e}")

# ================= 9. ADVANCED POPUP IMAGE GENERATOR =================
def get_best_font(size, bold=False):
    paths = ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "arial.ttf"]
    for p in paths:
        try: return ImageFont.truetype(p, size)
        except: pass
    return ImageFont.load_default()

def create_popup_image(result_type, amount, period_id):
    popup = Image.new("RGBA", (500, 350), (255, 255, 255, 0)); draw = ImageDraw.Draw(popup)
    start_col = (255, 90, 90) if result_type == "loss" else (40, 200, 90)
    end_col = (255, 150, 150) if result_type == "loss" else (100, 255, 150)
    for y in range(350):
        r = int(start_col[0] + (end_col[0] - start_col[0]) * y / 350)
        g = int(start_col[1] + (end_col[1] - start_col[1]) * y / 350)
        b = int(start_col[2] + (end_col[2] - start_col[2]) * y / 350)
        draw.line((0, y, 500, y), fill=(r, g, b))
    draw.rounded_rectangle([(30, 80), (470, 280)], radius=20, fill=(255, 255, 255))
    font_xl = get_best_font(35, True); font_l = get_best_font(28, True); font_m = get_best_font(18, False)
    if result_type == "win":
        draw.text((120, 25), "🏆 YOU WON! 🏆", font=font_xl, fill=(255, 255, 255))
        draw.text((150, 140), f"Bonus: ₹{amount}", font=font_l, fill=(40, 200, 90))
    else:
        draw.text((100, 25), "😢 BETTER LUCK! 😢", font=font_xl, fill=(255, 255, 255))
        draw.text((170, 140), "Try Again!", font=font_l, fill=(255, 90, 90))
    draw.text((130, 220), f"Period: {period_id}", font=font_m, fill=(100, 100, 100))
    bio = io.BytesIO(); bio.name = 'result.png'; popup.save(bio, 'PNG'); bio.seek(0); return bio

# ================= 10. UNIFIED GAME ENGINES =================
def run_game_engine(mode, total_seconds):
    while True:
        try:
            now = int(time.time())
            current_period_num = now // total_seconds
            next_period_num = current_period_num + 1
            period_id = f"{time.strftime('%Y%m%d')}-{mode}M-{next_period_num}"
            end_time = next_period_num * total_seconds
            time_left = end_time - int(time.time())
            if time_left <= 0: time.sleep(1); continue

            conn = get_db(); c = conn.cursor()
            random.seed(f"WINGO_{period_id}"); number = random.randint(0, 9); random.seed() 
            size = "big" if number >= 5 else "sml"
            if number in [1, 3, 7, 9]: color_text = "GREEN"
            elif number in [2, 4, 6, 8]: color_text = "RED"
            elif number == 0: color_text = "RED / VIOLET"
            elif number == 5: color_text = "GREEN / VIOLET"

            c.execute("SELECT number FROM period_data WHERE mode=? AND period_id=?", (mode, period_id))
            if not c.fetchone():
                c.execute("REPLACE INTO period_data (mode, period_id, number, color, size) VALUES (?, ?, ?, ?, ?)", (mode, period_id, str(number), color_text, size))
                conn.commit()
                try:
                    msg = f"🔮 *LIVE WINGO {mode} MIN PREDICTION*\n\n🆔 Period: `{period_id}`\n🎯 Expected Color: *{color_text}*\n🎯 Expected Size: *{size.upper()}*\n🔢 Expected Number: *{number}*\n\n⏳ Result in {time_left} Seconds! Bet Now!"
                    bot_prediction.send_message(PREDICTION_CHANNEL, msg, parse_mode="Markdown")
                except: pass
            conn.close()

            number_str = str(number)
            if color_text == "GREEN": color_codes = ["grn"]
            elif color_text == "RED": color_codes = ["red"]
            elif color_text == "RED / VIOLET": color_codes = ["red", "vio"]
            elif color_text == "GREEN / VIOLET": color_codes = ["grn", "vio"]

            sleep_time = end_time - time.time()
            if sleep_time > 0: time.sleep(sleep_time + 1)
            
            conn = get_db(); c = conn.cursor()
            c.execute("SELECT id FROM game_trends WHERE mode=? AND period=?", (mode, period_id))
            if c.fetchone(): conn.close(); continue
                
            c.execute("INSERT INTO game_trends (mode, period, number, color, size) VALUES (?, ?, ?, ?, ?)", (mode, period_id, number, color_text, size))
            c.execute("SELECT id, user_id, prediction, amount FROM active_bets WHERE mode=?", (mode,))
            bets = c.fetchall()
            
            for bet in bets:
                bet_id, uid, pred, amt = bet; win = False; multiplier = 0
                if pred == number_str: win = True; multiplier = 9
                elif pred in ["big", "sml"] and pred == size: win = True; multiplier = 2
                elif pred in color_codes:
                    win = True
                    if pred == "vio": multiplier = 4.5
                    elif number in [0, 5]: multiplier = 1.5 
                    else: multiplier = 2
                    
                if win:
                    win_amount = amt * multiplier; admin_cut = win_amount * 0.15; user_gets = win_amount - admin_cut
                    c.execute("UPDATE users SET balance = balance + ? WHERE user_id=?", (user_gets, uid))
                    c.execute("UPDATE admin_wallet SET total_commission = total_commission + ? WHERE id=1", (admin_cut,))
                    c.execute("INSERT INTO history (user_id, action, amount, detail) VALUES (?, 'Won Bet', ?, ?)", (uid, user_gets, f"Wingo {mode}M. Bet on {pred.upper()}"))
                    try: bot_main.send_photo(uid, photo=create_popup_image("win", user_gets, period_id), caption=f"🎉 *CONGRATULATIONS! YOU WON!* 🎉\n━━━━━━━━━━━━━━━━━━\n🎮 Mode: WINGO {mode} MIN\n🆔 Period: `{period_id}`\n🎯 Your Choice: *{pred.upper()}*\n✅ Actual Result: *{color_text} / {size.upper()} / {number}*\n\n💰 Win Amount: ₹{win_amount}\n➖ Admin Fee (15%): ₹{admin_cut}\n🤑 *Added to Wallet: ₹{user_gets}*\n━━━━━━━━━━━━━━━━━━", parse_mode="Markdown")
                    except: pass
                else:
                    c.execute("INSERT INTO history (user_id, action, amount, detail) VALUES (?, 'Lost Bet', ?, ?)", (uid, amt, f"Wingo {mode}M. Result was {color_text}/{size.upper()}/{number}"))
                    try: bot_main.send_photo(uid, photo=create_popup_image("loss", 0, period_id), caption=f"❌ *BET LOST!* ❌\n━━━━━━━━━━━━━━━━━━\n🎮 Mode: WINGO {mode} MIN\n🆔 Period: `{period_id}`\n🤦‍♂️ Your Choice: *{pred.upper()}*\n🛑 Actual Result: *{color_text} / {size.upper()} / {number}*\n💸 Amount Lost: ₹{amt}\n\n*Better luck next time!* 📉\n━━━━━━━━━━━━━━━━━━", parse_mode="Markdown")
                    except: pass
                c.execute("DELETE FROM active_bets WHERE id=?", (bet_id,))
            conn.commit(); conn.close()
        except Exception as e: print(f"Engine Error: {e}"); time.sleep(3)

# ================= 11. FLASK SERVER FOR HOSTING =================
app = Flask(__name__)

@app.route('/')
def home():
    return "🚀 Wingo Platform is Fast, Live and Running on Render!"

# ================= 12. RUN ALL BOTS & ENGINES =================
if __name__ == "__main__":
    print("🚀 All Bots & Game Engines Running...")
    threading.Thread(target=lambda: bot_main.infinity_polling(skip_pending=True)).start()
    threading.Thread(target=lambda: bot_finance.infinity_polling(skip_pending=True)).start()
    
    threading.Thread(target=run_game_engine, args=('1', 60)).start()       
    threading.Thread(target=run_game_engine, args=('2', 120)).start()      
    threading.Thread(target=run_game_engine, args=('3', 180)).start()      
    threading.Thread(target=run_game_engine, args=('5', 300)).start()      
    threading.Thread(target=run_game_engine, args=('15', 900)).start()     
    
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
