import asyncio
from aiogram import Bot
from database import get_db
from services.economy import process_sales_tick
from services.events import generate_inspection, apply_daily_lease

async def tick_job(bot: Bot):
    db = await get_db()
    async with db.execute("SELECT id FROM stations") as cursor:
        stations = await cursor.fetchall()
    await db.close()

    for st in stations:
        revenue = await process_sales_tick(st['id'])
        if revenue > 50000:
            db = await get_db()
            async with db.execute("""
                SELECT u.telegram_id FROM users u
                JOIN stations s ON s.owner_id = u.id
                WHERE s.id = ?
            """, (st['id'],)) as cursor:
                row = await cursor.fetchone()
            await db.close()

            if row:
                try:
                    await bot.send_message(
                        row['telegram_id'],
                        f"🔥 <b>Супер-час!</b> Выручка +{revenue:,.0f} ₽ за 5 минут!"
                    )
                except Exception:
                    pass

async def daily_job(bot: Bot):
    await apply_daily_lease()
    db = await get_db()
    async with db.execute("SELECT id FROM stations") as cursor:
        stations = await cursor.fetchall()
    await db.close()

    for st in stations:
        had = await generate_inspection(st['id'])
        if had:
            db = await get_db()
            async with db.execute("""
                SELECT u.telegram_id FROM users u
                JOIN stations s ON s.owner_id = u.id
                WHERE s.id = ?
            """, (st['id'],)) as cursor:
                row = await cursor.fetchone()
            await db.close()

            if row:
                try:
                    await bot.send_message(
                        row['telegram_id'],
                        "⚠️ <b>ВНИМАНИЕ:</b> Завтра проверка! Подготовьте документы и качество топлива."
                    )
                except Exception:
                    pass

async def scheduler_loop(bot: Bot):
    """Простой цикл вместо APScheduler — не требует доп. зависимостей."""
    import time
    last_tick = 0
    last_daily = 0

    while True:
        now = time.time()

        # Тик продаж каждые 5 минут
        if now - last_tick >= 300:
            await tick_job(bot)
            last_tick = now

        # Ежедневные события в 00:00
        current_hour = datetime.now().hour
        current_min = datetime.now().minute
        if current_hour == 0 and current_min == 0 and now - last_daily >= 3600:
            await daily_job(bot)
            last_daily = now

        await asyncio.sleep(30)  # проверяем каждые 30 секунд

async def start_scheduler(bot: Bot):
    asyncio.create_task(scheduler_loop(bot))
