import asyncio
import logging
import os
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.fsm.storage.redis import RedisStorage

# Для локальной разработки загружаем .env
# На хостинге переменные окружения уже установлены
if os.path.exists(".env"):
    from dotenv import load_dotenv
    load_dotenv()

from config import cfg
from database import init_db
from handlers import start, station, top
from services.scheduler import start_scheduler

async def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    # Проверяем обязательные переменные
    if not cfg.BOT_TOKEN:
        raise ValueError("BOT_TOKEN не задан в переменных окружения! Установите его на хостинге.")

    await init_db()

    bot = Bot(token=cfg.BOT_TOKEN, parse_mode=ParseMode.HTML)
    storage = RedisStorage.from_url(cfg.REDIS_URL)
    dp = Dispatcher(storage=storage)

    dp.include_routers(start.router, station.router, top.router)

    await start_scheduler(bot)

    logging.info("Бот ЗАПРАВКА запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
