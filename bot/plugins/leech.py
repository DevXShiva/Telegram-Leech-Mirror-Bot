import os, asyncio, yt_dlp, time, shutil
from pyrogram import Client, filters
from bot.config import Config
from bot.helpers.ffmpeg import generate_thumbnail
from bot.helpers.database import db
from bot.helpers.progress import get_status_msg 

# Global Tasks Tracking
ACTIVE_TASKS = {}
STOP_TASKS = []
semaphore = asyncio.Semaphore(5)

async def status_updater(msg, tid):
    """Background task jo message ko har 4-5 second mein edit karega."""
    while tid in ACTIVE_TASKS:
        try:
            status_text = await get_status_msg({tid: ACTIVE_TASKS[tid]})
            await msg.edit_text(status_text)
            await asyncio.sleep(4) 
        except Exception:
            await asyncio.sleep(4)
            continue

async def leech_logic(client, message, tid, url, name):
    async with semaphore:
        d_path = f"downloads/{tid}/"
        os.makedirs(d_path, exist_ok=True)
        user_id = message.from_user.id
        group_id = message.chat.id # Jahan se command aayi hai
        
        # 1. Task Initialization
        ACTIVE_TASKS[tid] = {
            'name': name, 'curr': 0, 'total': 1, 'status': 'Downloading', 
            'speed': '0B/s', 'eta': 'N/A', 'start_time': time.time(),
            'user_name': message.from_user.first_name, 'user_id': user_id
        }
        
        await db.add_task(tid, user_id, name)

        # Status Message Group mein bhejna
        initial_status = await get_status_msg({tid: ACTIVE_TASKS[tid]})
        status_msg = await client.send_message(group_id, initial_status)

        # Background updater shuru karna
        updater_task = asyncio.create_task(status_updater(status_msg, tid))

        def check_cancel(d):
            if tid in STOP_TASKS:
                raise Exception("Task Cancelled by User")

        def ytdl_hook(d):
            check_cancel(d)
            if d['status'] == 'downloading':
                ACTIVE_TASKS[tid].update({
                    'curr': d.get('downloaded_bytes', 0),
                    'total': d.get('total_bytes') or d.get('total_bytes_estimate', 1),
                    'speed': d.get('_speed_str', '0B/s'),
                    'eta': d.get('_eta_str', 'N/A')
                })

        try:
            # 2. Downloading Phase
            ydl_opts = {
                'format': 'best', 
                'outtmpl': f'{d_path}%(title)s.%(ext)s', 
                'progress_hooks': [ytdl_hook], 
                'quiet': True
            }
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                file_path = ydl.prepare_filename(info)
                
                if name != "default":
                    ext = os.path.splitext(file_path)[1]
                    new_path = os.path.join(d_path, f"{name}{ext}")
                    os.rename(file_path, new_path)
                    file_path = new_path

            # 3. Uploading Phase (Update Status for UI)
            ACTIVE_TASKS[tid]['status'] = "Uploading to PM"
            thumb = generate_thumbnail(file_path, f"{d_path}thumb.jpg")
            
            async def upload_progress(current, total):
                if tid in STOP_TASKS: 
                    client.stop_transmission()
                ACTIVE_TASKS[tid]['curr'], ACTIVE_TASKS[tid]['total'] = current, total

            # FILE SEND TO USER PM
            sent = await client.send_video(
                chat_id=user_id, # Private Message
                video=file_path, 
                thumb=thumb,
                caption=f"✅ **Leeched:** `{os.path.basename(file_path)}`",
                progress=upload_progress
            )
            
            # COPY TO DUMP CHANNEL
            try:
                await sent.copy(Config.DUMP_CHAT_ID, caption=f"👤 {message.from_user.mention}\n🔗 {url}")
            except: pass

            await db.increment_task_stat(user_id)
            
            # 4. Group notification with Tag
            await status_msg.edit_text(
                f"✅ {message.from_user.mention}, **Task Completed!**\n\n"
                f"📂 **File:** `{os.path.basename(file_path)}`\n"
                f"📥 **Status:** File has been sent to your PM."
            )

        except Exception as e:
            await status_msg.edit_text(f"❌ **Task Error:** `{str(e)}` \n(Make sure you started the bot in PM)")
            
        finally:
            # Loop stop karein
            updater_task.cancel()
            
            # 10 Seconds wait karein phir group msg delete karein
            await asyncio.sleep(10)
            try:
                await status_msg.delete()
            except: pass
            
            # --- AUTO-CLEANUP ---
            ACTIVE_TASKS.pop(tid, None)
            if tid in STOP_TASKS: 
                STOP_TASKS.remove(tid)
            if os.path.exists(d_path):
                shutil.rmtree(d_path, ignore_errors=True)
            await db.rm_task(tid)
