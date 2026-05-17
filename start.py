from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from database import get_db
from keyboards import main_menu_kb, scenario_kb, admin_kb, back_kb
from texts import WELCOME_TEXT, SCENARIO_TEXTS

router = Router()

class RegisterState(StatesGroup):
    choosing_scenario = State()
    naming_station = State()

class AdminState(StatesGroup):
    give_money = State()
    take_money = State()
    give_fuel = State()
    take_fuel = State()
    change_rep = State()
    find_player = State()

async def is_admin(telegram_id: int) -> bool:
    db = await get_db()
    async with db.execute("SELECT 1 FROM admins WHERE telegram_id=?", (telegram_id,)) as cursor:
        row = await cursor.fetchone()
    await db.close()
    return row is not None

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    db = await get_db()
    async with db.execute("SELECT * FROM users WHERE telegram_id=?", (message.from_user.id,)) as cursor:
        user = await cursor.fetchone()
    await db.close()

    if not user:
        await state.set_state(RegisterState.choosing_scenario)
        await message.answer(WELCOME_TEXT, reply_markup=scenario_kb())
    else:
        await message.answer("⛽ С возвращением на трассу, босс!", reply_markup=main_menu_kb(user['id']))

@router.callback_query(RegisterState.choosing_scenario, F.data.startswith("scenario_"))
async def process_scenario(call: CallbackQuery, state: FSMContext):
    scenario = call.data.split("_")[1]
    await state.update_data(scenario=scenario)
    await state.set_state(RegisterState.naming_station)

    await call.message.edit_text(
        f"{SCENARIO_TEXTS[scenario]}

"
        f"✍️ <b>Придумайте название вашей АЗС:</b>
"
        f"(Например: «Трасса-7», «Бензинка у Вани», «Золотая колонка»)

"
        f"Введите название ниже:",
        reply_markup=None
    )

@router.message(RegisterState.naming_station)
async def process_station_name(message: Message, state: FSMContext):
    name = message.text.strip()

    if len(name) < 2 or len(name) > 50:
        await message.answer("❌ Название должно быть от 2 до 50 символов. Попробуйте другое:")
        return

    db = await get_db()
    async with db.execute("SELECT 1 FROM stations WHERE name=?", (name,)) as cursor:
        exists = await cursor.fetchone()
    await db.close()

    if exists:
        await message.answer(
            f"❌ Название «<b>{name}</b>» уже занято другим игроком.
"
            f"Придумайте уникальное название для вашей АЗС:

"
            f"Введите название ниже:"
        )
        return

    data = await state.get_data()
    scenario = data['scenario']

    start_balance = 50000.00 if scenario == 'inheritance' else 100000.00 if scenario == 'partner' else 30000.00
    lease = 15000.00 if scenario == 'inheritance' else 20000.00 if scenario == 'partner' else 10000.00

    db = await get_db()
    cursor = await db.execute("""
        INSERT INTO users(telegram_id, username, full_name, scenario, balance)
        VALUES(?,?,?,?,?)
    """, (message.from_user.id, message.from_user.username, message.from_user.full_name, scenario, start_balance))
    user_id = cursor.lastrowid

    cursor = await db.execute("""
        INSERT INTO stations(owner_id, name, location_type, land_lease_cost)
        VALUES(?,?,?,?)
    """, (user_id, name, 'highway', lease))
    station_id = cursor.lastrowid

    fuels = ['AI92', 'AI95', 'DT']
    for f in fuels:
        await db.execute("""
            INSERT INTO tanks(station_id, fuel_type, volume_current)
            VALUES(?,?,?)
        """, (station_id, f, 5000))

    emp_name = "Анатолий" if scenario == 'inheritance' else "Сергей" if scenario == 'partner' else "Олег"
    await db.execute("""
        INSERT INTO employees(station_id, role, name, salary)
        VALUES(?,?,?,35000.00)
    """, (station_id, 'cashier', emp_name))

    await db.commit()
    await db.close()

    await state.clear()
    await message.answer(
        f"✅ <b>АЗС «{name}» открыта!</b>

"
        f"💰 Баланс: {start_balance:,.0f} ₽
"
        f"⛽ Топливо: 5 000 л каждого вида
"
        f"👤 Кассир: {emp_name}
"
        f"📍 Локация: трасса

"
        f"Начинайте зарабатывать!",
        reply_markup=main_menu_kb(user_id)
    )

# ====== АДМИНИСТРИРОВАНИЕ ======

@router.message(Command("admin"))
async def cmd_admin(message: Message):
    if not await is_admin(message.from_user.id):
        await message.answer("⛔ У вас нет прав администратора.")
        return
    await message.answer("🔧 <b>Панель администратора</b>", reply_markup=admin_kb())

@router.callback_query(F.data == "admin_give_money")
async def admin_give_money_start(call: CallbackQuery, state: FSMContext):
    if not await is_admin(call.from_user.id):
        return await call.answer("Нет прав")
    await state.set_state(AdminState.give_money)
    await call.message.edit_text(
        "💰 <b>Выдача денег</b>

"
        "Введите данные в формате:
"
        "<code>ID_игрока сумма</code>

"
        "Пример: <code>12345 50000</code>",
        reply_markup=back_kb()
    )

@router.message(AdminState.give_money)
async def admin_give_money_exec(message: Message, state: FSMContext):
    try:
        parts = message.text.strip().split()
        target_id = int(parts[0])
        amount = float(parts[1])

        db = await get_db()
        async with db.execute("SELECT * FROM users WHERE id=?", (target_id,)) as cursor:
            user = await cursor.fetchone()

        if not user:
            await db.close()
            await message.answer("❌ Игрок не найден. Попробуйте снова:", reply_markup=back_kb())
            return

        await db.execute("UPDATE users SET balance = balance + ? WHERE id=?", (amount, target_id))
        await db.commit()
        await db.close()

        await state.clear()
        await message.answer(
            f"✅ Выдано <b>{amount:,.0f} ₽</b> игроку {user['full_name']} (ID: {target_id})
"
            f"Новый баланс: {user['balance'] + amount:,.0f} ₽",
            reply_markup=admin_kb()
        )
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}. Формат: ID сумма", reply_markup=back_kb())

@router.callback_query(F.data == "admin_take_money")
async def admin_take_money_start(call: CallbackQuery, state: FSMContext):
    if not await is_admin(call.from_user.id):
        return await call.answer("Нет прав")
    await state.set_state(AdminState.take_money)
    await call.message.edit_text(
        "💰 <b>Забор денег</b>

"
        "Введите данные в формате:
"
        "<code>ID_игрока сумма</code>

"
        "Пример: <code>12345 50000</code>",
        reply_markup=back_kb()
    )

@router.message(AdminState.take_money)
async def admin_take_money_exec(message: Message, state: FSMContext):
    try:
        parts = message.text.strip().split()
        target_id = int(parts[0])
        amount = float(parts[1])

        db = await get_db()
        async with db.execute("SELECT * FROM users WHERE id=?", (target_id,)) as cursor:
            user = await cursor.fetchone()

        if not user:
            await db.close()
            await message.answer("❌ Игрок не найден. Попробуйте снова:", reply_markup=back_kb())
            return

        new_balance = max(0, user['balance'] - amount)
        await db.execute("UPDATE users SET balance = ? WHERE id=?", (new_balance, target_id))
        await db.commit()
        await db.close()

        await state.clear()
        await message.answer(
            f"✅ Забрано <b>{amount:,.0f} ₽</b> у игрока {user['full_name']} (ID: {target_id})
"
            f"Новый баланс: {new_balance:,.0f} ₽",
            reply_markup=admin_kb()
        )
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}. Формат: ID сумма", reply_markup=back_kb())

@router.callback_query(F.data == "admin_give_fuel")
async def admin_give_fuel_start(call: CallbackQuery, state: FSMContext):
    if not await is_admin(call.from_user.id):
        return await call.answer("Нет прав")
    await state.set_state(AdminState.give_fuel)
    await call.message.edit_text(
        "⛽ <b>Выдача топлива</b>

"
        "Введите данные в формате:
"
        "<code>ID_станции тип_топлива литры</code>

"
        "Пример: <code>1 AI95 10000</code>

"
        "Типы: AI92, AI95, AI98, DT, GAS",
        reply_markup=back_kb()
    )

@router.message(AdminState.give_fuel)
async def admin_give_fuel_exec(message: Message, state: FSMContext):
    try:
        parts = message.text.strip().split()
        station_id = int(parts[0])
        fuel_type = parts[1].upper()
        liters = int(parts[2])

        db = await get_db()
        async with db.execute(
            "SELECT * FROM tanks WHERE station_id=? AND fuel_type=?",
            (station_id, fuel_type)
        ) as cursor:
            tank = await cursor.fetchone()

        if not tank:
            await db.close()
            await message.answer("❌ Резервуар не найден. Проверьте ID станции и тип топлива.", reply_markup=back_kb())
            return

        new_vol = min(tank['volume_total'], tank['volume_current'] + liters)
        await db.execute(
            "UPDATE tanks SET volume_current = ? WHERE id=?",
            (new_vol, tank['id'])
        )
        await db.commit()
        await db.close()

        await state.clear()
        await message.answer(
            f"✅ Добавлено <b>{liters:,} л</b> {fuel_type} в резервуар станции #{station_id}
"
            f"Текущий запас: {new_vol:,} л",
            reply_markup=admin_kb()
        )
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}. Формат: ID_станции тип литры", reply_markup=back_kb())

@router.callback_query(F.data == "admin_take_fuel")
async def admin_take_fuel_start(call: CallbackQuery, state: FSMContext):
    if not await is_admin(call.from_user.id):
        return await call.answer("Нет прав")
    await state.set_state(AdminState.take_fuel)
    await call.message.edit_text(
        "⛽ <b>Забор топлива</b>

"
        "Введите данные в формате:
"
        "<code>ID_станции тип_топлива литры</code>

"
        "Пример: <code>1 AI95 5000</code>",
        reply_markup=back_kb()
    )

@router.message(AdminState.take_fuel)
async def admin_take_fuel_exec(message: Message, state: FSMContext):
    try:
        parts = message.text.strip().split()
        station_id = int(parts[0])
        fuel_type = parts[1].upper()
        liters = int(parts[2])

        db = await get_db()
        async with db.execute(
            "SELECT * FROM tanks WHERE station_id=? AND fuel_type=?",
            (station_id, fuel_type)
        ) as cursor:
            tank = await cursor.fetchone()

        if not tank:
            await db.close()
            await message.answer("❌ Резервуар не найден.", reply_markup=back_kb())
            return

        new_vol = max(0, tank['volume_current'] - liters)
        await db.execute(
            "UPDATE tanks SET volume_current = ? WHERE id=?",
            (new_vol, tank['id'])
        )
        await db.commit()
        await db.close()

        await state.clear()
        await message.answer(
            f"✅ Забрано <b>{liters:,} л</b> {fuel_type} из резервуара станции #{station_id}
"
            f"Текущий запас: {new_vol:,} л",
            reply_markup=admin_kb()
        )
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}. Формат: ID_станции тип литры", reply_markup=back_kb())

@router.callback_query(F.data == "admin_rep")
async def admin_rep_start(call: CallbackQuery, state: FSMContext):
    if not await is_admin(call.from_user.id):
        return await call.answer("Нет прав")
    await state.set_state(AdminState.change_rep)
    await call.message.edit_text(
        "⭐ <b>Изменение репутации</b>

"
        "Введите данные в формате:
"
        "<code>ID_станции новая_репутация(0-100)</code>

"
        "Пример: <code>1 85</code>",
        reply_markup=back_kb()
    )

@router.message(AdminState.change_rep)
async def admin_rep_exec(message: Message, state: FSMContext):
    try:
        parts = message.text.strip().split()
        station_id = int(parts[0])
        rep = max(0, min(100, int(parts[1])))

        db = await get_db()
        async with db.execute("SELECT * FROM stations WHERE id=?", (station_id,)) as cursor:
            station = await cursor.fetchone()

        if not station:
            await db.close()
            await message.answer("❌ Станция не найдена.", reply_markup=back_kb())
            return

        await db.execute("UPDATE stations SET reputation = ? WHERE id=?", (rep, station_id))
        await db.commit()
        await db.close()

        await state.clear()
        await message.answer(
            f"✅ Репутация АЗС «{station['name']}» изменена на <b>{rep}/100</b>",
            reply_markup=admin_kb()
        )
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}. Формат: ID_станции репутация", reply_markup=back_kb())

@router.callback_query(F.data == "admin_list")
async def admin_list(call: CallbackQuery):
    if not await is_admin(call.from_user.id):
        return await call.answer("Нет прав")

    db = await get_db()
    async with db.execute("SELECT * FROM admins ORDER BY added_at") as cursor:
        admins = await cursor.fetchall()
    await db.close()

    text = "👥 <b>Список администраторов</b>

"
    for i, a in enumerate(admins, 1):
        text += f"{i}. ID: <code>{a['telegram_id']}</code> | Роль: {a['role']}
"

    await call.message.edit_text(text, reply_markup=admin_kb())

@router.callback_query(F.data == "admin_find")
async def admin_find_start(call: CallbackQuery, state: FSMContext):
    if not await is_admin(call.from_user.id):
        return await call.answer("Нет прав")
    await state.set_state(AdminState.find_player)
    await call.message.edit_text(
        "🔍 <b>Поиск игрока</b>

"
        "Введите ID или @username:
"
        "Пример: <code>12345</code> или <code>@ivanov</code>",
        reply_markup=back_kb()
    )

@router.message(AdminState.find_player)
async def admin_find_exec(message: Message, state: FSMContext):
    try:
        query = message.text.strip()
        db = await get_db()

        if query.startswith('@'):
            async with db.execute("SELECT * FROM users WHERE username=?", (query[1:],)) as cursor:
                user = await cursor.fetchone()
        else:
            async with db.execute("SELECT * FROM users WHERE id=?", (int(query),)) as cursor:
                user = await cursor.fetchone()

        if not user:
            await db.close()
            await message.answer("❌ Игрок не найден.", reply_markup=back_kb())
            return

        async with db.execute("SELECT * FROM stations WHERE owner_id=?", (user['id'],)) as cursor:
            stations = await cursor.fetchall()

        stations_text = ""
        for s in stations:
            async with db.execute(
                "SELECT COALESCE(SUM(volume_current),0) FROM tanks WHERE station_id=?",
                (s['id'],)
            ) as cur:
                total_fuel = (await cur.fetchone())[0]
            stations_text += f"
• «{s['name']}» | Реп: {s['reputation']} | Топливо: {int(total_fuel):,} л"

        vip_status = 'Нет'
        if user['vip_until']:
            try:
                vip_dt = datetime.fromisoformat(user['vip_until'].replace('Z', '+00:00'))
                if vip_dt > datetime.now():
                    vip_status = 'Да'
            except:
                pass

        text = (
            f"👤 <b>Игрок: {user['full_name']}</b>
"
            f"ID: <code>{user['id']}</code>
"
            f"TG: @{user['username'] or 'нет'}
"
            f"Баланс: {user['balance']:,.0f} ₽
"
            f"Уровень: {user['level']}
"
            f"VIP: {vip_status}
"
            f"Сценарий: {user['scenario']}
"
            f"АЗС: {len(stations)}{stations_text}"
        )
        await db.close()
        await state.clear()
        await message.answer(text, reply_markup=admin_kb())
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}", reply_markup=back_kb())

from datetime import datetime
