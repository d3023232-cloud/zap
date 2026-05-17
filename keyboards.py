from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

def scenario_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏚 Наследство отца (50K ₽, долги, но своя земля)", callback_data="scenario_inheritance")],
        [InlineKeyboardButton(text="🤝 Партнёр с ГИБДД (100K ₽, связи)", callback_data="scenario_partner")],
        [InlineKeyboardButton(text="🏢 Франшиза «Нефть-М» (30K ₽, жёсткие условия)", callback_data="scenario_franchise")]
    ])

def main_menu_kb(user_id: int):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⛽ Моя АЗС", callback_data="my_station")],
        [InlineKeyboardButton(text="📦 Склад и закупки", callback_data="warehouse")],
        [InlineKeyboardButton(text="👥 Персонал", callback_data="staff")],
        [InlineKeyboardButton(text="📊 Финансы", callback_data="finance")],
        [InlineKeyboardButton(text="🏆 ТОП-10 АЗС", callback_data="top10")],
        [InlineKeyboardButton(text="🌐 WebApp-терминал", web_app={"url": f"https://yourdomain.com/webapp?u={user_id}"})],
        [InlineKeyboardButton(text="💎 Премиум", callback_data="premium")]
    ])

def station_management_kb(station_id: int):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏷 Цены", callback_data=f"set_prices:{station_id}")],
        [InlineKeyboardButton(text="📦 Заказать топливо", callback_data=f"order_fuel:{station_id}")],
        [InlineKeyboardButton(text="🧹 Уборка (-500 ₽, +репутация)", callback_data=f"clean_station:{station_id}")],
        [InlineKeyboardButton(text="📈 Статистика", callback_data=f"stats:{station_id}")],
        [InlineKeyboardButton(text="🔙 Главное меню", callback_data="main_menu")]
    ])

def back_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад", callback_data="main_menu")]
    ])

def admin_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 Выдать деньги", callback_data="admin_give_money")],
        [InlineKeyboardButton(text="💰 Забрать деньги", callback_data="admin_take_money")],
        [InlineKeyboardButton(text="⛽ Выдать топливо", callback_data="admin_give_fuel")],
        [InlineKeyboardButton(text="⛽ Забрать топливо", callback_data="admin_take_fuel")],
        [InlineKeyboardButton(text="⭐ Изменить репутацию", callback_data="admin_rep")],
        [InlineKeyboardButton(text="📋 Список админов", callback_data="admin_list")],
        [InlineKeyboardButton(text="👤 Найти игрока", callback_data="admin_find")],
        [InlineKeyboardButton(text="🔙 Главное меню", callback_data="main_menu")]
    ])
