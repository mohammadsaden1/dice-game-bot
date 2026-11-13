import sqlite3
import random
import threading
import asyncio
from flask import Flask, request, jsonify, render_template_string
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters

# --- تنظیمات اختصاصی شما ---
TOKEN = "9181613672:AAFFvHP4GzIzfPr-J960EQJNT7aFtXaCPPE"
ADMIN_USER_ID = 1951133060

# --- پایگاه داده ---
def init_db():
    conn = sqlite3.connect("casino_bot.db")
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            balance REAL DEFAULT 0.0
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS deposits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            amount REAL,
            status TEXT DEFAULT 'pending'
        )
    ''')
    conn.commit()
    conn.close()

init_db()

def get_balance(user_id):
    conn = sqlite3.connect("casino_bot.db")
    cursor = conn.cursor()
    cursor.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    if not row:
        cursor.execute("INSERT INTO users (user_id, balance) VALUES (?, 0.0)", (user_id,))
        conn.commit()
        balance = 0.0
    else:
        balance = row[0]
    conn.close()
    return balance

def update_balance(user_id, amount):
    conn = sqlite3.connect("casino_bot.db")
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, user_id))
    conn.commit()
    conn.close()

# --- فرانت‌اند مینی‌اپلیکیشن (بازی تاس) ---
WEB_APP_HTML = """
<!DOCTYPE html>
<html lang="fa" dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>بازی تاس شانس</title>
    <script src="https://telegram.org/js/telegram-web-app.js"></script>
    <style>
        body { font-family: Tahoma, sans-serif; background: #0f172a; color: #fff; text-align: center; padding: 15px; margin: 0; }
        .card { background: #1e293b; padding: 15px; border-radius: 12px; margin-bottom: 15px; box-shadow: 0 4px 6px rgba(0,0,0,0.3); }
        input, select { width: 90%; padding: 10px; margin: 8px 0; border-radius: 8px; border: 1px solid #475569; background: #0f172a; color: #fff; font-size: 16px; }
        button { background: #10b981; color: white; border: none; padding: 12px 20px; border-radius: 8px; font-size: 16px; cursor: pointer; width: 100%; font-weight: bold; margin-top: 5px; }
        button:hover { background: #059669; }
        .btn-blue { background: #3b82f6; }
        .btn-blue:hover { background: #2563eb; }
        .dice-box { font-size: 50px; margin: 15px 0; }
        .msg { font-size: 14px; margin-top: 8px; color: #f59e0b; }
    </style>
</head>
<body>
    <h2>🎲 کازینو اختصاصی تاس</h2>
    
    <div class="card">
        <h3>موجودی شما: <span id="userBalance">0</span> تومان</h3>
        <p style="font-size: 12px; color: #94a3b8;">حداقل شرط: ۱,۰۰۰ تومان | حداقل برداشت: ۶۰۰,۰۰۰ تومان</p>
    </div>

    <!-- بخش بازی تاس -->
    <div class="card">
        <h3>میز تاس‌بازی</h3>
        <label>پیش‌بینی:</label>
        <select id="betType">
            <option value="even">زوج (ضریب ۲x)</option>
            <option value="odd">فرد (ضریب ۲x)</option>
        </select>
        
        <label>مبلغ شرط (تومان):</label>
        <input type="number" id="betAmount" min="1000" placeholder="حداقل ۱۰۰۰">
        
        <div class="dice-box" id="diceDisplay">🎲</div>
        <button onclick="playDice()">پرتاب تاس 🎯</button>
        <div class="msg" id="gameMsg"></div>
    </div>

    <!-- بخش مالی -->
    <div class="card">
        <h3>امور مالی</h3>
        <button class="btn-blue" onclick="requestDeposit()">💳 شارژ حساب (کارت به کارت)</button>
        <button class="btn-blue" onclick="requestWithdraw()" style="margin-top: 10px; background: #8b5cf6;">💵 درخواست برداشت</button>
    </div>

    <script>
        const tg = window.Telegram.WebApp;
        tg.expand();
        const userId = tg.initDataUnsafe?.user?.id || 12345;

        function loadData() {
            fetch(`/api/get_user?user_id=${userId}`)
            .then(res => res.json())
            .then(data => {
                document.getElementById('userBalance').innerText = data.balance.toLocaleString();
            });
        }
        loadData();

        function playDice() {
            let amount = parseInt(document.getElementById('betAmount').value);
            let type = document.getElementById('betType').value;
            if(!amount || amount < 1000) {
                alert("حداقل مبلغ شرط ۱۰۰۰ تومان است!");
                return;
            }

            fetch('/api/play', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({user_id: userId, amount: amount, type: type})
            })
            .then(res => res.json())
            .then(data => {
                if(data.error) {
                    alert(data.error);
                    return;
                }
                document.getElementById('diceDisplay').innerText = `🎲 ${data.dice}`;
                document.getElementById('userBalance').innerText = data.balance.toLocaleString();
                if(data.win) {
                    document.getElementById('gameMsg').style.color = '#10b981';
                    document.getElementById('gameMsg').innerText = `🎉 بردید! ${data.prize.toLocaleString()} تومان اضافه شد.`;
                } else {
                    document.getElementById('gameMsg').style.color = '#ef4444';
                    document.getElementById('gameMsg').innerText = `❌ باختید!`;
                }
            });
        }

        function requestDeposit() {
            let amt = prompt("مبلغ واریزی جهت شارژ (بین ۱۰۰,۰۰۰ تا ۵,۰۰۰,۰۰۰ تومان):");
            if(!amt || amt < 100000) {
                alert("حداقل مبلغ شارژ ۱۰۰ هزار تومان است.");
                return;
            }
            tg.openTelegramLink(`https://t.me/` + encodeURIComponent("{{bot_username}}") + `?start=deposit_${amt}`);
        }

        function requestWithdraw() {
            let amt = prompt("مبلغ درخواست برداشت (حداقل ۶۰۰,۰۰۰ تومان):");
            if(!amt || amt < 600000) {
                alert("حداقل مبلغ برداشت ۶۰۰ هزار تومان است.");
                return;
            }
            let card = prompt("شماره کارت یا شبا خود را وارد کنید:");
            if(!card) return;

            fetch('/api/withdraw', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({user_id: userId, amount: amt, card: card})
            })
            .then(res => res.json())
            .then(data => {
                alert(data.msg);
                loadData();
            });
        }
    </script>
</body>
</html>
"""

# --- متغیرهای سراسری برای مدیریت پیام‌ها به ادمین ---
bot_application = None

# --- تلگرام بات ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    get_balance(user.id)
    
    args = context.args
    if args and args[0].startswith("deposit_"):
        amount = args[0].split("_")[1]
        await update.message.reply_text(
            f"💳 **شارژ حساب به مبلغ {int(amount):,} تومان**\n\n"
            "مبلغ را به کارت زیر واریز کنید:\n"
            "`6037-9971-XXXX-XXXX` (به نام مدیریت)\n\n"
            "سپس **عکس رسید** را همین‌جا بفرستید تا ادمین تایید کند.",
            parse_mode="Markdown"
        )
        context.user_data['deposit_amount'] = amount
        return

    # لینک مینی‌اپ بعد از دیپلوی روی Render
    keyboard = [[InlineKeyboardButton("🎮 باز کردن مینی‌اپ بازی تاس", web_app={"url": "https://YOUR-RENDER-URL.onrender.com"})]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"سلام {user.first_name}! 🎲\n\n"
        "به مینی‌اپلیکیشن تاس خوش آمدید. برای شروع بازی روی دکمه زیر کلیک کنید:",
        reply_markup=reply_markup
    )

async def receive_receipt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    amount = context.user_data.get('deposit_amount', 100000)
    
    keyboard = [[InlineKeyboardButton("✅ تایید شارژ", callback_data=f"dep_acc_{user.id}_{amount}")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await context.bot.send_message(
        chat_id=ADMIN_USER_ID,
        text=f"🔔 **درخواست شارژ جدید**\nکاربر: {user.first_name} (`{user.id}`)\nمبلغ: {int(amount):,} تومان",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )
    if update.message.photo:
        await context.bot.send_photo(chat_id=ADMIN_USER_ID, photo=update.message.photo[-1].file_id)
    
    await update.message.reply_text("✅ رسید ارسال شد. منتظر تایید ادمین باشید.")

async def admin_approve(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    if data.startswith("dep_acc_"):
        parts = data.split("_")
        target_user_id = int(parts[2])
        amount = float(parts[3])
        
        update_balance(target_user_id, amount)
        
        await context.bot.send_message(chat_id=target_user_id, text=f"🎉 حساب شما به مبلغ {int(amount):,} تومان شارژ شد!")
        await query.edit_message_text(text=f"✅ شارژ کاربر `{target_user_id}` تایید شد.")

# --- وب‌سرور فلاسک ---
app = Flask(__name__)

@app.route('/')
def index():
    return render_template_string(WEB_APP_HTML, bot_username="YourBotUsername")

@app.route('/api/get_user')
def api_get_user():
    user_id = int(request.args.get('user_id', 0))
    return jsonify({'balance': get_balance(user_id)})

@app.route('/api/play', methods=['POST'])
def api_play():
    data = request.json
    user_id = int(data.get('user_id'))
    amount = float(data.get('amount'))
    bet_type = data.get('type')

    balance = get_balance(user_id)
    if balance < amount:
        return jsonify({'error': 'موجودی کافی نیست!'})

    update_balance(user_id, -amount)

    # الگوریتم سود خانه (House Edge): ضریب برد ۴۰٪ برای کاربر جهت سودآوری ادمین
    dice = random.randint(1, 6)
    is_even = (dice % 2 == 0)
    user_win = False
    
    if (bet_type == 'even' and is_even) or (bet_type == 'odd' and not is_even):
        if random.random() < 0.40:
            user_win = True

    prize = 0
    if user_win:
        prize = amount * 2
        update_balance(user_id, prize)

    return jsonify({
        'dice': dice,
        'win': user_win,
        'prize': prize,
        'balance': get_balance(user_id)
    })

@app.route('/api/withdraw', methods=['POST'])
def api_withdraw():
    data = request.json
    user_id = int(data.get('user_id'))
    amount = float(data.get('amount'))
    card = data.get('card')

    balance = get_balance(user_id)
    if balance < amount or amount < 600000:
        return jsonify({'msg': 'موجودی کافی نیست یا کمتر از ۶۰۰ هزار تومان است.'})

    update_balance(user_id, -amount)
    
    # ارسال پیام به ادمین به صورت امن
    if bot_application:
        asyncio.run_coroutine_threadsafe(
            bot_application.bot.send_message(
                chat_id=ADMIN_USER_ID,
                text=f"💵 **درخواست برداشت**\nکاربر: `{user_id}`\nمبلغ: {int(amount):,} تومان\nکارت: `{card}`",
                parse_mode="Markdown"
            ),
            bot_application.bot_data.get("loop")
        )

    return jsonify({'msg': 'درخواست برداشت ثبت شد.'})

def run_flask():
    app.run(host='0.0.0.0', port=5000)

async def main_async():
    global bot_application
    bot_application = Application.builder().token(TOKEN).build()
    
    # ذخیره لوپ در bot_data برای دسترسی امن از وب‌سرور
    bot_application.bot_data["loop"] = asyncio.get_running_loop()

    bot_application.add_handler(CommandHandler("start", start))
    bot_application.add_handler(CallbackQueryHandler(admin_approve, pattern="^dep_acc_"))
    bot_application.add_handler(MessageHandler(filters.PHOTO, receive_receipt))

    # اجرای وب‌سرور در پس‌زمینه
    threading.Thread(target=run_flask, daemon=True).start()

    await bot_application.initialize()
    await bot_application.start()
    await bot_application.updater.start_polling()
    
    # نگه داشتن ربات روشن
    stop_event = asyncio.Event()
    await stop_event.wait()

def main():
    try:
        asyncio.run(main_async())
    except KeyboardInterrupt:
        pass

if __name__ == "__main__":
    main()
