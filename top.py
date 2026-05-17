from aiogram import Router, F
from aiogram.types import CallbackQuery
from database import get_db
from keyboards import back_kb

router = Router()

@router.callback_query(F.data == "top10")
async def show_top10(call: CallbackQuery):
    db = await get_db()

    # Получаем все станции с данными для расчёта рейтинга
    async with db.execute("""
        SELECT 
            s.id,
            s.name,
            s.reputation,
            s.owner_id,
            u.balance as owner_balance,
            u.full_name as owner_name
        FROM stations s
        JOIN users u ON u.id = s.owner_id
    """) as cursor:
        stations = await cursor.fetchall()

    # Считаем топливо для каждой станции
    station_list = []
    for st in stations:
        async with db.execute(
            "SELECT COALESCE(SUM(volume_current), 0) FROM tanks WHERE station_id=?",
            (st['id'],)
        ) as cur:
            total_fuel = (await cur.fetchone())[0]

        # Рейтинг = баланс * 0.3 + репутация * 1000 + топливо * 2
        rating = (st['owner_balance'] or 0) * 0.3 + (st['reputation'] or 0) * 1000 + (total_fuel or 0) * 2
        station_list.append({
            'id': st['id'],
            'name': st['name'],
            'reputation': st['reputation'],
            'owner_balance': st['owner_balance'],
            'owner_name': st['owner_name'],
            'total_fuel': int(total_fuel),
            'rating': rating
        })

    # Сортируем по рейтингу
    station_list.sort(key=lambda x: x['rating'], reverse=True)
    top10 = station_list[:10]

    text = "🏆 <b>ТОП-10 АЗС</b>
"
    text += "<i>Рейтинг по капиталу, репутации и запасам топлива</i>

"

    for i, row in enumerate(top10, 1):
        medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
        text += (
            f"{medal} <b>{row['name']}</b>
"
            f"   👤 {row['owner_name']}
"
            f"   💰 Баланс: {row['owner_balance']:,.0f} ₽
"
            f"   ⭐ Репутация: {row['reputation']}/100
"
            f"   ⛽ Топливо: {row['total_fuel']:,} л

"
        )

    # Позиция текущего игрока
    async with db.execute("""
        SELECT s.id, s.name, s.reputation, u.balance,
               COALESCE((SELECT SUM(volume_current) FROM tanks WHERE station_id = s.id), 0) as total_fuel
        FROM stations s
        JOIN users u ON u.id = s.owner_id
        WHERE u.telegram_id = ?
    """, (call.from_user.id,)) as cursor:
        user_station = await cursor.fetchone()

    await db.close()

    if user_station:
        position = None
        for idx, s in enumerate(station_list, 1):
            if s['id'] == user_station['id']:
                position = idx
                break

        if position and position > 10:
            text += (
                f"━ ━ ━ ━ ━ ━ ━ ━ ━
"
                f"📍 <b>Ваша позиция: #{position}</b>
"
                f"⛽ {user_station['name']}
"
                f"💰 {user_station['balance']:,.0f} ₽ | ⭐ {user_station['reputation']}/100 | ⛽ {int(user_station['total_fuel']):,} л
"
            )

    await call.message.edit_text(text, reply_markup=back_kb())
