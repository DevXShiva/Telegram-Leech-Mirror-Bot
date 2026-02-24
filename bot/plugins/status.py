import asyncio
from pyrogram import Client, filters
from bot.helpers.progress import get_status_msg

async def status_handler(client, message, ACTIVE_TASKS):
    # 1. Status message fetch aur send karna
    status_text = await get_status_msg(ACTIVE_TASKS)
    status_msg = await message.reply(status_text)
    
    # 2. 10 seconds tak wait karna
    await asyncio.sleep(10)
    
    # 3. Auto-delete logic
    try:
        # Bot ka bheja hua status message delete karein
        await status_msg.delete()
        # User ka bheja hua /status command bhi delete karein (Chat clean rakhne ke liye)
        await message.delete()
    except Exception as e:
        # Agar message pehle hi delete ho chuka ho toh error skip karein
        print(f"Status Delete Error: {e}")
