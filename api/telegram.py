import os
import asyncio
import threading
from telegram import Bot


CHAT_ID = -1003410500390
TELEGRAM_TOPIC = {
  'default': 4294967297,
  'wooffy-be': 4294967352,
  'italco-be': 4294967355,
  'chatty-be': 4294967354,
  'generic-be': 4294967350,
  'strongbox-be': 4294967353,
  'generic-booking': 4294967351,
}

loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)


def start_loop(loop):
  asyncio.set_event_loop(loop)
  loop.run_forever()


threading.Thread(target=start_loop, args=(loop,), daemon=True).start()


def send_telegram_error(trace: str):
  bot = Bot(os.environ['TELEGRAM_TOKEN'])
  IS_DEV = int(os.environ.get('IS_DEV', 1)) == 1
  THREAD_ID = TELEGRAM_TOPIC[os.environ.get('PROJECT_NAME', 'default')]
  
  if IS_DEV:
    return

  async def send_error(text):
    await bot.send_message(
      chat_id=CHAT_ID, 
      text=text, 
      message_thread_id=THREAD_ID
    )

  asyncio.run_coroutine_threadsafe(send_error(trace), loop)
