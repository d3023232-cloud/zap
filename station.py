from aiogram import Router, F
from aiogram.types import CallbackQuery
from database import get_db
from keyboards import station_management_kb, back_kb, main_menu_kb
from services.economy import get_station_total_liters

router = Router()

@router.callback_query(F.data == "my_station")
async def show_station(call: CallbackQuery):
    db = await get_db()
    async with db.execute("""
        SELECT s.*, u.balance, u.id as uid
        FROM stations s
        JOIN users u ON s.owner_id = u.id
        WHERE u.telegram_id = ?
        ORDER BY s.id LIMIT 1
    """, (call.from_user.id,)) as cursor:
        station = await cursor.fetchone()

    if not station:
        await db.close()
        return await call.answer("Сначала создайте АЗС через /start")

    async with db.execute(
        "SELECT fuel_type, volume_current, volume_total FROM tanks WHERE station_id=?",
        (station['id'],)
    ) as cursor:
        tanks = await cursor.fetchall()
    await db.close()

    tanks_text = "
".join([
        f"• {t['fuel_type']}: {t['volume_current']:,}/{t['volume_total']:,} л"
        for t in tanks
    ])

    total_liters = sum(t['volume_current'] for t in tanks)

    text = (
        f"⛽ <b>{station['name']}</b>
"
        f"📍 Локация: {station['location_type']}
"
        f"💰 Ваш баланс: {station['balance']:,.0f} ₽
"
        f"⭐ Репутация: {station['reputation']}/100
"
        f"🧹 Чистота: {station['cleanliness']}/100
"
        f"🛡 Уровень безопасности: {station['security_level']}
"
        f"🚗 Мойка: {'✅' if station['has_wash'] else '❌'}
"
        f"🏪 Магазин: {'✅' if station['has_shop'] else '❌'}

"
        f"<b>⛽ Резервуары (всего {total_liters:,} л):</b>
{tanks_text}

"
        f"💸 Аренда земли: {station['land_lease_cost']:,.0f} ₽/день"
    )

    await call.message.edit_text(text, reply_markup=station_management_kb(station['id']))

@router.callback_query(F.data.startswith("set_prices:"))
async def price_menu(call: CallbackQuery):
    station_id = int(call.data.split(":")[1])
    db = await get_db()

    async with db.execute(
        "SELECT fuel_type, volume_current FROM tanks WHERE station_id=?",
        (station_id,)
    ) as cursor:
        tanks = await cursor.fetchall()
    await db.close()

    text = "🏷 <b>Установка цен</b>

<b>Оптовые цены на сегодня:</b>
"
    for t in tanks:
        from services.economy import get_wholesale_price
        wp = await get_wholesale_price(t['fuel_type'])
        text += f"• {t['fuel_type']}: опт {wp} ₽/л | запас {t['volume_current']:,} л
"

    text += "
<i>Цены обновляются автоматически каждые 4 часа. VIP-пользователи могут устанавливать цены вручную.</i>"

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад к АЗС", callback_data="my_station")]
    ])
    await call.message.edit_text(text, reply_markup=kb)

@router.callback_query(F.data.startswith("clean_station:"))
async def clean_station(call: CallbackQuery):
    station_id = int(call.data.split(":")[1])
    db = await get_db()

    async with db.execute("SELECT * FROM stations WHERE id=?", (station_id,)) as cursor:
        station = await cursor.fetchone()

    async with db.execute("SELECT * FROM users WHERE telegram_id=?", (call.from_user.id,)) as cursor:
        user = await cursor.fetchone()

    if user['balance'] < 500:
        await db.close()
        await call.answer("❌ Недостаточно средств! Нужно 500 ₽", show_alert=True)
        return

    new_clean = min(100, station['cleanliness'] + 15)
    new_rep = min(100, station['reputation'] + 3)

    await db.execute("""
        UPDATE stations SET cleanliness = ?, reputation = ? WHERE id = ?
    """, (new_clean, new_rep, station_id))

    await db.execute("""
        UPDATE users SET balance = balance - 500 WHERE telegram_id = ?
    """, (call.from_user.id,))

    await db.commit()
    await db.close()

    await call.answer(f"✅ Уборка выполнена! Чистота {new_clean}/100, репутация +3", show_alert=True)
    await show_station(call)

@router.callback_query(F.data.startswith("stats:"))
async def station_stats(call: CallbackQuery):
    station_id = int(call.data.split(":")[1])
    db = await get_db()

    async with db.execute("""
        SELECT fuel_type, SUM(liters) as total_liters, SUM(total) as total_revenue
        FROM sales
        WHERE station_id = ? AND timestamp > datetime('now', '-24 hours')
        GROUP BY fuel_type
    """, (station_id,)) as cursor:
        sales_24h = await cursor.fetchall()

    async with db.execute("""
        SELECT SUM(total) as revenue FROM sales
        WHERE station_id = ? AND timestamp > datetime('now', '-7 days')
    """, (station_id,)) as cursor:
        sales_7d = await cursor.fetchone()

    await db.close()

    total_rev_24h = sum(s['total_revenue'] for s in sales_24h) if sales_24h else 0
    total_lit_24h = sum(s['total_liters'] for s in sales_24h) if sales_24h else 0
    total_rev_7d = sales_7d['revenue'] or 0

    text = (
        f"📈 <b>Статистика АЗС #{station_id}</b>

"
        f"<b>За 24 часа:</b>
"
        f"💰 Выручка: {total_rev_24h:,.0f} ₽
"
        f"⛽ Продано: {total_lit_24h:,.0f} л

"
        f"<b>За 7 дней:</b>
"
        f"💰 Выручка: {total_rev_7d:,.0f} ₽

"
        f"<b>По видам топлива (24ч):</b>
"
    )

    for s in sales_24h:
        text += f"• {s['fuel_type']}: {s['total_liters']:,.0f} л / {s['total_revenue']:,.0f} ₽
"

    if not sales_24h:
        text += "<i>Нет данных за последние 24 часа</i>
"

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад к АЗС", callback_data="my_station")]
    ])
    await call.message.edit_text(text, reply_markup=kb)

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
