from aiogram import Router, F
from aiogram.types import CallbackQuery
from database import get_pool
from keyboards import back_kb

router = Router()

@router.callback_query(F.data == "top10")
async def show_top10(call: CallbackQuery):
    pool = await get_pool()

    # Получаем топ-10 станций по совокупному рейтингу
    # Рейтинг = баланс владельца * 0.3 + репутация * 1000 + общее топливо * 2
    rows = await pool.fetch("""
        SELECT 
            s.id,
            s.name,
            s.reputation,
            s.owner_id,
            u.balance as owner_balance,
            u.full_name as owner_name,
            COALESCE(SUM(t.volume_current), 0) as total_fuel
        FROM stations s
        JOIN users u ON u.id = s.owner_id
        LEFT JOIN tanks t ON t.station_id = s.id
        GROUP BY s.id, s.name, s.reputation, s.owner_id, u.balance, u.full_name
        ORDER BY (u.balance * 0.3 + s.reputation * 1000 + COALESCE(SUM(t.volume_current), 0) * 2) DESC
        LIMIT 10
    """)

    text = "🏆 <b>ТОП-10 АЗС</b>
"
    text += "<i>Рейтинг по капиталу, репутации и запасам топлива</i>

"

    for i, row in enumerate(rows, 1):
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

    # Показываем позицию текущего игрока если он не в топ-10
    user_station = await pool.fetchrow("""
        SELECT s.id, s.name, s.reputation, u.balance,
               COALESCE(SUM(t.volume_current), 0) as total_fuel
        FROM stations s
        JOIN users u ON u.id = s.owner_id
        LEFT JOIN tanks t ON t.station_id = s.id
        WHERE u.telegram_id = $1
        GROUP BY s.id, s.name, s.reputation, u.balance
    """, call.from_user.id)

    if user_station:
        # Находим позицию игрока
        all_rows = await pool.fetch("""
            SELECT s.id
            FROM stations s
            JOIN users u ON u.id = s.owner_id
            LEFT JOIN tanks t ON t.station_id = s.id
            GROUP BY s.id, u.balance, s.reputation
            ORDER BY (u.balance * 0.3 + s.reputation * 1000 + COALESCE(SUM(t.volume_current), 0) * 2) DESC
        """)

        position = None
        for idx, r in enumerate(all_rows, 1):
            if r['id'] == user_station['id']:
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
                f"💰 {user_station['balance']:,.0f} ₽ | ⭐ {user_station['reputation']}/100 | ⛽ {user_station['total_fuel']:,} л
"
            )

    await call.message.edit_text(text, reply_markup=back_kb())
