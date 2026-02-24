import asyncio, threading, time
from pyrogram import Client, filters, idle, enums
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from bot.config import Config
from bot.helpers.fsub import check_fsub
from bot.helpers.database import db
from bot.plugins.leech import leech_logic, direct_download_logic, ACTIVE_TASKS, STOP_TASKS
from bot.helpers.progress import get_status_msg
from flask import Flask

app = Client("leech_bot", Config.API_ID, Config.API_HASH, bot_token=Config.BOT_TOKEN)
web_app = Flask(__name__)

@web_app.route('/')
def home(): return "Alive", 200

# --- Helper for common limit checks ---
async def can_start_task(c, m):
    if not await check_fsub(c, m): return False
    
    if len(ACTIVE_TASKS) >= 5:
        await m.reply_text("⚠️ **Bot is Overloaded!**\nGlobally 5 tasks are running. Try later.")
        return False
        
    u_tasks = [t for t in ACTIVE_TASKS.values() if t['user_id'] == m.from_user.id]
    if len(u_tasks) >= 2: 
        await m.reply("❌ **Limit Exceeded:** Max 2 tasks per user allowed!")
        return False
    return True

# --- START COMMAND (New UI Style) ---
@app.on_message(filters.command("start") & filters.private)
async def start_msg(c, m):
    if not await check_fsub(c, m): return
    
    welcome_text = (
        f"<b>👋 Hi {m.from_user.mention}!</b>\n\n"
        "I am a powerful **Pro Leech Bot**.\n\n"
        "🚀 **Commands:**\n"
        "• `/yt URL -n Name` : Social Media Leech\n"
        "• `/l URL -n Name` : Direct Link Leech\n"
        "• `/status` : Check Tasks\n\n"
        "<b>All files are sent to your PM!</b>"
    )

    buttons = [
        [
            InlineKeyboardButton("Settings ⚙️", callback_data="settings_menu"),
            InlineKeyboardButton("Help 🛠️", callback_data="help")
        ],
        [InlineKeyboardButton("Toggle Mode: Media/File 📂", callback_data="toggle_mode")]
    ]
    
    await m.reply_text(text=welcome_text, reply_markup=InlineKeyboardMarkup(buttons))

# --- SETTINGS & CALLBACK HANDLER ---
@app.on_callback_query()
async def cb_handler(c, query):
    user_id = query.from_user.id
    
    if query.data == "settings_menu":
        mode = await db.get_upload_mode(user_id) or "Media"
        thumb = await db.get_thumb(user_id)
        thumb_status = "✅ Set" if thumb else "❌ Not Set (Auto-Gen)"
        
        settings_text = (
            f"<b>⚙️ Bot Configuration</b>\n\n"
            f"<b>Upload Mode:</b> <code>{mode}</code>\n"
            f"<b>Custom Thumb:</b> <code>{thumb_status}</code>\n\n"
            "• /set_thumb : Reply to photo\n"
            "• /set_caption : Set custom caption"
        )
        await query.message.edit_text(settings_text, reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("Back 🔙", callback_data="back_start")]
        ]))

    elif query.data == "toggle_mode":
        curr = await db.get_upload_mode(user_id) or "Media"
        new = "Document" if curr == "Media" else "Media"
        await db.set_upload_mode(user_id, new)
        await query.answer(f"✅ Upload Mode: {new}", show_alert=True)

    elif query.data == "back_start":
        await start_msg(c, query.message)

    elif query.data == "help":
        help_txt = "Send link with `/yt` or `/l` command. Use `-n` for custom name.\nExample: `/yt URL -n MyVideo`"
        await query.message.edit_text(help_txt, reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("Back 🔙", callback_data="back_start")]
        ]))

# --- ENGINE 1: yt-dlp Command ---
@app.on_message(filters.command("yt"))
async def yt_cmd(c, m):
    if not await can_start_task(c, m): return
    
    parts = m.text.split(None, 1)
    if len(parts) < 2: 
        return await m.reply("❌ Usage: `/yt URL -n Name`")
    
    raw_data = parts[1]
    name = "default"
    if "-n " in raw_data:
        url = raw_data.split("-n ")[0].strip()
        name = raw_data.split("-n ")[1].strip()
    else:
        url = raw_data.strip()

    tid = str(int(time.time()))
    asyncio.create_task(leech_logic(c, m, tid, url, name))

# --- ENGINE 2: Direct Leech Command ---
@app.on_message(filters.command("l"))
async def direct_cmd(c, m):
    if not await can_start_task(c, m): return
    
    parts = m.text.split(None, 1)
    if len(parts) < 2: 
        return await m.reply("❌ Usage: `/l URL -n Name`")
    
    raw_data = parts[1]
    name = "default"
    if "-n " in raw_data:
        url = raw_data.split("-n ")[0].strip()
        name = raw_data.split("-n ")[1].strip()
    else:
        url = raw_data.strip()

    tid = str(int(time.time()))
    asyncio.create_task(direct_download_logic(c, m, tid, url, name))

# --- OTHER COMMANDS ---
@app.on_message(filters.command("status"))
async def status_cmd(c, m):
    if not ACTIVE_TASKS:
        return await m.reply_text("❌ No active tasks!")
    status_text = await get_status_msg(ACTIVE_TASKS)
    await m.reply_text(status_text)

@app.on_message(filters.command("set_thumb") & filters.private)
async def set_thumb_cmd(c, m):
    reply = m.reply_to_message
    if not reply or not reply.photo:
        return await m.reply("❌ Reply to a <b>Photo</b> to set thumb.")
    await db.set_thumb(m.from_user.id, reply.photo.file_id)
    await m.reply("✅ **Thumbnail Saved!**")

@app.on_message(filters.regex(r"^/cancel_"))
async def cancel_handler(c, m):
    tid = m.text.split("_")[1]
    if tid in ACTIVE_TASKS:
        if ACTIVE_TASKS[tid]['user_id'] == m.from_user.id or m.from_user.id in Config.ADMINS:
            if tid not in STOP_TASKS:
                STOP_TASKS.append(tid)
                await m.reply("🛑 **Cancellation request received.**")
            else:
                await m.reply("Already cancelling...")
        else:
            await m.reply("⚠️ Not your task!")
    else:
        await m.reply("❌ Task not found.")

# --- Bot Runner ---
async def run():
    threading.Thread(target=lambda: web_app.run(host="0.0.0.0", port=10000), daemon=True).start()
    await app.start()
    print("🚀 Bot Started with UI and Dual Engine!")
    await idle()

if __name__ == "__main__":
    asyncio.get_event_loop().run_until_complete(run())
