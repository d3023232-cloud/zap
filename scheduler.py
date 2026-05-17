from apscheduler.schedulers.asyncio import AsyncIOScheduler
from aiogram import Bot
from database import get_pool
from services.economy import process_sales_tick
from services.events import generate_inspection, apply_daily_lease

scheduler = AsyncIOScheduler()

async def tick_job(bot: Bot):
    pool = await get_pool()
    stations = await pool.fetch("SELECT id FROM stations")
    for st in stations:
        revenue = await process_sales_tick(st['id'])
        if revenue > 50000:
            owner_tg = await pool.fetchval("""
                SELECT u.telegram_id FROM users u
                JOIN stations s ON s.owner_id = u.id
                WHERE s.id = $1
            """, st['id'])
            if owner_tg:
                try:
                    await bot.send_message(
                        owner_tg,
                        f"🔥 <b>Супер-час!</b> Выручка +{revenue:,.0f} ₽ за 5 минут!"
                    )
                except Exception:
                    pass

async def daily_job(bot: Bot):
    await apply_daily_lease()
    pool = await get_pool()
    stations = await pool.fetch("SELECT id FROM stations")
    for st in stations:
        had = await generate_inspection(st['id'])
        if had:
            owner_tg = await pool.fetchval("""
                SELECT u.telegram_id FROM users u
                JOIN stations s ON s.owner_id = u.id
                WHERE s.id = $1
            """, st['id'])
            if owner_tg:
                try:
                    await bot.send_message(
                        owner_tg,
                        "⚠️ <b>ВНИМАНИЕ:</b> Завтра проверка! Подготовьте документы и качество топлива."
                    )
                except Exception:
                    pass

async def start_scheduler(bot: Bot):
    scheduler.add_job(tick_job, 'interval', minutes=5, args=[bot], id='sales_tick')
    scheduler.add_job(daily_job, 'cron', hour=0, minute=0, args=[bot], id='daily_events')
    scheduler.start()
