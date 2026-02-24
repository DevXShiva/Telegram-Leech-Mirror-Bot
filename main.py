import asyncio, threading, time
from pyrogram import Client, filters, idle
from bot.config import Config
from bot.helpers.fsub import check_fsub
# Naya logic import kiya gaya hai
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

# --- Commands ---

@app.on_message(filters.command("start"))
async def start_msg(c, m):
    await m.reply_text(
        f"👋 **Welcome {m.from_user.first_name}!**\n\n"
        "`/yt -n Name URL` : Social Media Leech\n"
        "`/l -n Name URL`  : Direct Link Leech\n"
        "`/status` : Check Tasks\n"
        "All files are sent to your PM! 🚀"
    )

# --- ENGINE 1: yt-dlp Command ---
@app.on_message(filters.command("yt"))
async def yt_cmd(c, m):
    if not await can_start_task(c, m): return
    
    try: await m.delete() # Privacy delete
    except: pass

    parts = m.text.split(None, 1)
    if len(parts) < 2: 
        return await c.send_message(m.chat.id, "❌ Provide link with /yt")
    
    name, url = "default", parts[1]
    if "-n " in parts[1]:
        try:
            data = parts[1].split("-n ", 1)[1].split(None, 1)
            name, url = data[0], data[1]
        except: pass

    tid = str(int(time.time()))
    asyncio.create_task(leech_logic(c, m, tid, url, name))

# --- ENGINE 2: Direct Leech Command ---
@app.on_message(filters.command("l"))
async def direct_cmd(c, m):
    if not await can_start_task(c, m): return
    
    try: await m.delete() # Privacy delete
    except: pass

    parts = m.text.split(None, 1)
    if len(parts) < 2: 
        return await c.send_message(m.chat.id, "❌ Provide direct link with /l")
    
    name, url = "default", parts[1]
    if "-n " in parts[1]:
        try:
            data = parts[1].split("-n ", 1)[1].split(None, 1)
            name, url = data[0], data[1]
        except: pass

    tid = str(int(time.time()))
    # Direct Download Logic call ho raha hai
    asyncio.create_task(direct_download_logic(c, m, tid, url, name))

@app.on_message(filters.command("status"))
async def status_cmd(c, m):
    from bot.plugins.status import status_handler
    await status_handler(c, m, ACTIVE_TASKS)

@app.on_message(filters.regex(r"^/cancel_"))
async def cancel_handler(c, m):
    tid = m.text.split("_")[1]
    if tid in ACTIVE_TASKS:
        if ACTIVE_TASKS[tid]['user_id'] == m.from_user.id or m.from_user.id == Config.OWNER_ID:
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
    print("🚀 Bot Started with Dual Engine!")
    await idle()

if __name__ == "__main__":
    asyncio.get_event_loop().run_until_complete(run())
