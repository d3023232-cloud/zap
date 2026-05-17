import asyncio
import logging
import os
import random
from datetime import datetime, timedelta, date

from aiogram import Bot, Dispatcher, Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import CommandStart, Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.enums import ParseMode
import aiosqlite

from dataclasses import dataclass

# ═══════════════════════════════════════════════════════════════
# CONFIG — реальные цены и экономика АЗС России (май 2026)
# ═══════════════════════════════════════════════════════════════
@dataclass(frozen=True)
class Config:
    BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")
    ADMIN_ID: int = int(os.getenv("ADMIN_ID", "0") or "0")
    DB_PATH: str = os.getenv("DB_PATH", "azs_bot.db")

    WHOLESALE_AI92: float = 52.00
    WHOLESALE_AI95: float = 56.00
    WHOLESALE_AI98: float = 72.00
    WHOLESALE_AI100: float = 78.00
    WHOLESALE_DT: float = 62.00
    WHOLESALE_DT_WINTER: float = 65.00
    WHOLESALE_GAS: float = 22.00

    BASE_MARGIN_AI92: float = 3.50
    BASE_MARGIN_AI95: float = 4.00
    BASE_MARGIN_AI98: float = 5.50
    BASE_MARGIN_AI100: float = 6.00
    BASE_MARGIN_DT: float = 3.00
    BASE_MARGIN_DT_WINTER: float = 3.50
    BASE_MARGIN_GAS: float = 2.50

    AVG_CHECK_RUB: float = 1288.0
    AVG_LITERS_PER_CAR: float = 22.0

    START_CAPITAL: float = 50000.0

    LEASE_HIGHWAY: float = 25000.0
    LEASE_CITY: float = 45000.0
    LEASE_SUBURB: float = 15000.0

    DELIVERY_COST_PER_LITER: float = 1.50

    DONATE_EXPRESS_DELIVERY: int = 49
    DONATE_AUTO_PRICING: int = 99
    DONATE_VIP_MONTH: int = 299
    DONATE_WASH: int = 199
    DONATE_COFFEE: int = 149
    DONATE_MANAGER: int = 399
    DONATE_BRANDING: int = 999

    TANK_UPGRADE_COST: float = 50000.0
    TANK_MAX_VOLUME: int = 100000

    LOCATION_COST_HIGHWAY: float = 500000.0
    LOCATION_COST_CITY: float = 1200000.0
    LOCATION_COST_SUBURB: float = 300000.0

cfg = Config()

# ═══════════════════════════════════════════════════════════════
# РЕАЛЬНЫЕ ЛОКАЦИИ РОССИИ
# ═══════════════════════════════════════════════════════════════
LOCATIONS = {
    "highway": {
        "name": "Трасса М-4 «Дон» (км 847)",
        "desc": "Краснодарский край, между Ростовом и Краснодаром. Плотный поток фур и дачников.",
        "lease": cfg.LEASE_HIGHWAY,
        "traffic_mult": 1.4,
        "competition": "high"
    },
    "city": {
        "name": "Самара, Московское шоссе",
        "desc": "Крупный город, высокая проходимость, дорогая аренда, но и высокие цены.",
        "lease": cfg.LEASE_CITY,
        "traffic_mult": 1.2,
        "competition": "very_high"
    },
    "suburb": {
        "name": "Тула, пригород (Щёкинский район)",
        "desc": "Спокойный пригород. Низкая аренда, умеренный трафик, меньше конкуренция.",
        "lease": cfg.LEASE_SUBURB,
        "traffic_mult": 0.8,
        "competition": "low"
    }
}

# ═══════════════════════════════════════════════════════════════
# ИМЕНА ПЕРСОНАЛА (30 штук)
# ═══════════════════════════════════════════════════════════════
EMPLOYEE_NAMES = [
    "Анатолий", "Сергей", "Олег", "Владимир", "Дмитрий",
    "Александр", "Михаил", "Андрей", "Иван", "Павел",
    "Николай", "Евгений", "Виктор", "Геннадий", "Борис",
    "Станислав", "Роман", "Константин", "Артём", "Максим",
    "Игорь", "Леонид", "Григорий", "Фёдор", "Семён",
    "Тимофей", "Захар", "Матвей", "Ярослав", "Тихон"
]

EMPLOYEE_ROLES = {
    'cashier':    {'name': 'Кассир',    'base_salary': 35000, 'bonus_pct': 0.02, 'desc': '+2% к чеку'},
    'filler':     {'name': 'Заправщик',  'base_salary': 32000, 'bonus_pct': 0.03, 'desc': '+3% к чеку'},
    'guard':      {'name': 'Охранник',    'base_salary': 30000, 'bonus_pct': 0.00, 'desc': 'Защита от вандалов'},
    'accountant': {'name': 'Бухгалтер',  'base_salary': 45000, 'bonus_pct': 0.01, 'desc': '+1% к чеку, налоги'},
    'manager':    {'name': 'Управляющий', 'base_salary': 60000, 'bonus_pct': 0.05, 'desc': '+5% к чеку, автозакупки'},
    'barista':    {'name': 'Бариста',    'base_salary': 40000, 'bonus_pct': 0.04, 'desc': '+4% к чеку магазина'}
}

DB_PATH = cfg.DB_PATH

async def get_db():
    db = await aiosqlite.connect(DB_PATH)
    await db.execute("PRAGMA foreign_keys = ON")
    db.row_factory = aiosqlite.Row
    return db

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        db.row_factory = aiosqlite.Row

        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER UNIQUE NOT NULL,
                username TEXT,
                full_name TEXT,
                balance REAL DEFAULT 50000.00,
                reputation INTEGER DEFAULT 50 CHECK (reputation BETWEEN 0 AND 100),
                level INTEGER DEFAULT 1,
                scenario TEXT DEFAULT 'inheritance',
                vip_until TEXT,
                has_truck INTEGER DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                last_active TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS admins (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER UNIQUE NOT NULL,
                role TEXT DEFAULT 'admin',
                added_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS stations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                owner_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                name TEXT UNIQUE NOT NULL,
                location_type TEXT CHECK (location_type IN ('highway', 'city', 'suburb')),
                land_lease_cost REAL DEFAULT 25000.00,
                reputation INTEGER DEFAULT 50,
                cleanliness INTEGER DEFAULT 40 CHECK (cleanliness BETWEEN 0 AND 100),
                security_level INTEGER DEFAULT 1,
                has_wash INTEGER DEFAULT 0,
                has_shop INTEGER DEFAULT 0,
                shop_level INTEGER DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS tanks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                station_id INTEGER NOT NULL REFERENCES stations(id) ON DELETE CASCADE,
                fuel_type TEXT CHECK (fuel_type IN ('AI92', 'AI95', 'AI98', 'AI100', 'DT', 'DT_winter', 'GAS')),
                volume_total INTEGER DEFAULT 20000,
                volume_current INTEGER DEFAULT 5000,
                temperature REAL DEFAULT 20.0,
                quality_score INTEGER DEFAULT 95 CHECK (quality_score BETWEEN 0 AND 100),
                last_refill TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS fuel_types (
                code TEXT PRIMARY KEY,
                name TEXT,
                base_wholesale_price REAL,
                seasonality_factor REAL DEFAULT 1.00,
                demand_profile TEXT
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS sales (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                station_id INTEGER NOT NULL REFERENCES stations(id) ON DELETE CASCADE,
                fuel_type TEXT,
                liters INTEGER,
                price_per_liter REAL,
                total REAL,
                payment_type TEXT DEFAULT 'card',
                timestamp TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS employees (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                station_id INTEGER NOT NULL REFERENCES stations(id) ON DELETE CASCADE,
                role TEXT CHECK (role IN ('cashier', 'filler', 'guard', 'accountant', 'manager', 'barista')),
                name TEXT,
                skill INTEGER DEFAULT 50 CHECK (skill BETWEEN 0 AND 100),
                morale INTEGER DEFAULT 70 CHECK (morale BETWEEN 0 AND 100),
                salary REAL DEFAULT 35000.00,
                bonus_pct REAL DEFAULT 0.0,
                hired_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS suppliers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT,
                fuel_types TEXT,
                reliability INTEGER DEFAULT 80,
                delivery_hours INTEGER DEFAULT 6,
                price_discount REAL DEFAULT 0.00,
                legal_risk INTEGER DEFAULT 10,
                min_order_liters INTEGER DEFAULT 5000
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                station_id INTEGER NOT NULL REFERENCES stations(id) ON DELETE CASCADE,
                supplier_id INTEGER REFERENCES suppliers(id),
                fuel_type TEXT,
                liters INTEGER,
                cost REAL,
                delivery_cost REAL DEFAULT 0,
                status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'transit', 'delivered', 'rejected')),
                delivery_eta TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS inspections (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                station_id INTEGER NOT NULL REFERENCES stations(id) ON DELETE CASCADE,
                inspector_type TEXT CHECK (inspector_type IN ('rosstandart', 'tax', 'fire', 'ecology')),
                severity INTEGER DEFAULT 1,
                deadline TEXT,
                fine_amount REAL DEFAULT 0,
                status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'passed', 'failed')),
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS upgrades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                station_id INTEGER NOT NULL REFERENCES stations(id) ON DELETE CASCADE,
                type TEXT CHECK (type IN ('led_sign', 'car_wash', 'coffee_shop', 'security_cam', 'fast_fuel', 'vip_lounge', 'tank_expansion')),
                level INTEGER DEFAULT 1,
                effect_multiplier REAL DEFAULT 1.00
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS competitors (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                location_type TEXT,
                distance_km INTEGER,
                price_ai92 REAL,
                price_ai95 REAL,
                price_dt REAL,
                price_ai98 REAL,
                price_gas REAL,
                has_wash INTEGER DEFAULT 0,
                has_shop INTEGER DEFAULT 0,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        await db.execute("CREATE INDEX IF NOT EXISTS idx_sales_station_time ON sales(station_id, timestamp)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_orders_station ON orders(station_id, status)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_tanks_station ON tanks(station_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_users_tg ON users(telegram_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_stations_owner ON stations(owner_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_stations_name ON stations(name)")

        cursor = await db.execute("SELECT COUNT(*) FROM fuel_types")
        count = (await cursor.fetchone())[0]
        if count == 0:
            fuel_data = [
                ('AI92', 'АИ-92', cfg.WHOLESALE_AI92, 1.00, '{"0":0.3,"6":0.8,"8":1.5,"12":1.2,"18":1.8,"23":0.4}'),
                ('AI95', 'АИ-95', cfg.WHOLESALE_AI95, 1.00, '{"0":0.3,"6":0.8,"8":1.5,"12":1.2,"18":1.8,"23":0.4}'),
                ('AI98', 'АИ-98', cfg.WHOLESALE_AI98, 1.00, '{"0":0.2,"6":0.6,"8":1.3,"12":1.1,"18":1.5,"23":0.3}'),
                ('AI100', 'АИ-100', cfg.WHOLESALE_AI100, 1.05, '{"0":0.1,"6":0.5,"8":1.2,"12":1.0,"18":1.3,"23":0.2}'),
                ('DT', 'Дизель', cfg.WHOLESALE_DT, 1.00, '{"0":0.5,"6":1.2,"8":1.8,"12":1.5,"18":1.2,"23":0.6}'),
                ('DT_winter', 'ДТ Зимний', cfg.WHOLESALE_DT_WINTER, 1.20, '{"0":0.6,"6":1.3,"8":1.9,"12":1.6,"18":1.3,"23":0.7}'),
                ('GAS', 'Газ', cfg.WHOLESALE_GAS, 1.00, '{"0":0.3,"6":0.7,"8":1.4,"12":1.2,"18":1.6,"23":0.4}')
            ]
            await db.executemany(
                "INSERT INTO fuel_types(code, name, base_wholesale_price, seasonality_factor, demand_profile) VALUES (?,?,?,?,?)",
                fuel_data
            )

        cursor = await db.execute("SELECT COUNT(*) FROM suppliers")
        count = (await cursor.fetchone())[0]
        if count == 0:
            sup_data = [
                ('Роснефть', 'AI92,AI95,DT', 95, 4, 0.00, 5, 10000),
                ('Лукойл', 'AI92,AI95,AI98,DT', 90, 5, 0.50, 5, 8000),
                ('Газпромнефть', 'AI92,AI95,DT,GAS', 92, 4, 0.30, 5, 10000),
                ('Татнефть', 'AI92,AI95,DT', 85, 6, 1.50, 10, 5000),
                ('Башнефть', 'AI92,AI95,DT,DT_winter', 88, 5, 1.00, 8, 6000),
                ('Серый опт (риск)', 'AI92,AI95,DT', 60, 3, 5.00, 65, 3000)
            ]
            await db.executemany(
                "INSERT INTO suppliers(name, fuel_types, reliability, delivery_hours, price_discount, legal_risk, min_order_liters) VALUES (?,?,?,?,?,?,?)",
                sup_data
            )

        cursor = await db.execute("SELECT COUNT(*) FROM competitors")
        count = (await cursor.fetchone())[0]
        if count == 0:
            comp_data = [
                ('highway', 5, 55.50, 60.00, 65.00, 78.00, 33.00, 0, 1),
                ('highway', 12, 56.20, 61.10, 66.50, 79.00, 34.00, 1, 1),
                ('city', 8, 58.50, 63.80, 69.00, 82.00, 35.00, 1, 1),
                ('suburb', 15, 53.80, 58.20, 62.30, 75.50, 31.50, 0, 0)
            ]
            await db.executemany(
                "INSERT INTO competitors(location_type, distance_km, price_ai92, price_ai95, price_dt, price_ai98, price_gas, has_wash, has_shop) VALUES (?,?,?,?,?,?,?,?,?)",
                comp_data
            )

        if cfg.ADMIN_ID and cfg.ADMIN_ID != 0:
            await db.execute("INSERT OR IGNORE INTO admins(telegram_id) VALUES(?)", (cfg.ADMIN_ID,))

        await db.commit()

# ═══════════════════════════════════════════════════════════════
# TEXTS
# ═══════════════════════════════════════════════════════════════
WELCOME_TEXT = """⛽ <b>Добро пожаловать в «ЗАПРАВКУ»</b>

Вы — бывший дальнобойщик. У вас есть шанс построить империю на трассе.

Каждые 5 минут клиенты заправляются. Вы управляете ценами, закупаете топливо, нанимаете персонал и расширяете сеть.

<b>Реальная экономика. Реальные риски. Реальные деньги.</b>

Выберите вашу стартовую историю:"""

SCENARIO_TEXTS = {
    "inheritance": """🏚 <b>Сценарий: Наследство отца</b>

Ваш отец 20 лет работал на этой АЗС. Умер 3 месяца назад. Оставил вам:
• Ржавые колонки
• Долг за аренду земли: 45 000 ₽
• Старого кассира Анатолия
• 50 000 ₽ на карманные расходы

Земля ваша по наследству, но аренду нужно платить. Это шанс начать с чистого листа.""",

    "partner": """🤝 <b>Сценарий: Партнёр с ГИБДД</b>

Ваш бывший напарник по дальнобоям теперь инспектор ДПС. Он нашёл вам:
• Идеальную точку на трассе М-4
• Заказ на обслуживание 15 служебных машин
• 100 000 ₽ стартового капитала
• Условие: 10% от прибыли ему каждый месяц

Связи — это власть. Но власть имеет цену.""",

    "franchise": """🏢 <b>Сценарий: Франшиза «Нефть-М»</b>

Крупная сеть предложила вам стать партнёром:
• Готовый дизайн и вывеска
• Поставки по фиксированной цене
• 30 000 ₽ стартового капитала
• Жёсткие условия: цены устанавливает сеть, маржа 8%

Меньше свободы, но меньше риска. Выбор за вами."""
}

# ═══════════════════════════════════════════════════════════════
# KEYBOARDS — КОМПАКТНЫЕ
# ═══════════════════════════════════════════════════════════════
def scenario_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏚 Наследство (50K)", callback_data="scenario_inheritance"),
         InlineKeyboardButton(text="🤝 Партнёр ГИБДД (100K)", callback_data="scenario_partner")],
        [InlineKeyboardButton(text="🏢 Франшиза (30K)", callback_data="scenario_franchise")]
    ])

def location_kb():
    kb = []
    for key, loc in LOCATIONS.items():
        kb.append([InlineKeyboardButton(
            text=f"📍 {loc['name']}",
            callback_data=f"location_{key}"
        )])
    return InlineKeyboardMarkup(inline_keyboard=kb)

def main_menu_kb(user_id: int):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⛽ Моя АЗС", callback_data="my_station"),
         InlineKeyboardButton(text="📦 Склад", callback_data="warehouse")],
        [InlineKeyboardButton(text="👥 Персонал", callback_data="staff"),
         InlineKeyboardButton(text="📊 Финансы", callback_data="finance")],
        [InlineKeyboardButton(text="🏆 ТОП-10", callback_data="top10"),
         InlineKeyboardButton(text="💎 Премиум", callback_data="premium")],
        [InlineKeyboardButton(text="🗺 Новая локация", callback_data="buy_location"),
         InlineKeyboardButton(text="🔧 Улучшения", callback_data="upgrades")]
    ])

def station_management_kb(station_id: int):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏷 Цены", callback_data=f"set_prices:{station_id}"),
         InlineKeyboardButton(text="📦 Заказать топливо", callback_data=f"order_fuel:{station_id}")],
        [InlineKeyboardButton(text="🧹 Уборка (-500₽)", callback_data=f"clean_station:{station_id}"),
         InlineKeyboardButton(text="📈 Статистика", callback_data=f"stats:{station_id}")],
        [InlineKeyboardButton(text="👤 Нанять персонал", callback_data=f"hire_staff:{station_id}"),
         InlineKeyboardButton(text="🔧 Улучшить", callback_data=f"upgrade_station:{station_id}")],
        [InlineKeyboardButton(text="🔙 Меню", callback_data="main_menu")]
    ])

def back_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад", callback_data="main_menu")]
    ])

def admin_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 Выдать ₽", callback_data="admin_give_money"),
         InlineKeyboardButton(text="💰 Забрать ₽", callback_data="admin_take_money")],
        [InlineKeyboardButton(text="⛽ Выдать топливо", callback_data="admin_give_fuel"),
         InlineKeyboardButton(text="⛽ Забрать топливо", callback_data="admin_take_fuel")],
        [InlineKeyboardButton(text="⭐ Репутация", callback_data="admin_rep"),
         InlineKeyboardButton(text="👤 Найти игрока", callback_data="admin_find")],
        [InlineKeyboardButton(text="⭐ Выдать VIP", callback_data="admin_give_vip"),
         InlineKeyboardButton(text="🚗 Выдать мойку", callback_data="admin_give_wash")],
        [InlineKeyboardButton(text="☕ Выдать кофейню", callback_data="admin_give_coffee"),
         InlineKeyboardButton(text="👔 Выдать управляющего", callback_data="admin_give_manager")],
        [InlineKeyboardButton(text="🏢 Выдать брендирование", callback_data="admin_give_branding")],
        [InlineKeyboardButton(text="📋 Админы", callback_data="admin_list")],
        [InlineKeyboardButton(text="🔙 Меню", callback_data="main_menu")]
    ])

# ═══════════════════════════════════════════════════════════════
# ECONOMY — РЕАЛИСТИЧНЫЕ ПОКАЗАТЕЛИ
# ═══════════════════════════════════════════════════════════════
TRAFFIC_PROFILE = {
    0:0.05, 1:0.03, 2:0.02, 3:0.02, 4:0.03, 5:0.08,
    6:0.25, 7:0.60, 8:1.00, 9:0.90, 10:0.70, 11:0.55,
    12:0.50, 13:0.45, 14:0.40, 15:0.45, 16:0.55,
    17:0.85, 18:1.00, 19:0.75, 20:0.45, 21:0.25, 22:0.15, 23:0.08
}

SEASON_MODS = {
    "winter": {"DT":1.4, "DT_winter":1.6, "AI92":0.9, "AI95":0.9, "AI98":0.8, "GAS":1.1},
    "spring": {"DT":1.1, "DT_winter":0.8, "AI92":1.0, "AI95":1.0, "AI98":1.0, "GAS":1.0},
    "summer": {"DT":0.9, "DT_winter":0.3, "AI92":1.3, "AI95":1.4, "AI98":1.3, "GAS":1.0},
    "autumn": {"DT":1.2, "DT_winter":0.9, "AI92":1.0, "AI95":1.0, "AI98":1.0, "GAS":1.1}
}

async def get_wholesale_price(fuel_type: str) -> float:
    db = await get_db()
    async with db.execute(
        "SELECT base_wholesale_price, seasonality_factor FROM fuel_types WHERE code=?",
        (fuel_type,)
    ) as cursor:
        row = await cursor.fetchone()
    await db.close()

    if not row:
        return 50.00
    base = row['base_wholesale_price']
    season = row['seasonality_factor']
    noise = random.uniform(0.985, 1.015)
    return round(base * season * noise, 2)

async def calculate_retail_price(station_id: int, fuel_type: str, competitor_price: float) -> float:
    wholesale = await get_wholesale_price(fuel_type)

    margins = {
        'AI92': cfg.BASE_MARGIN_AI92, 'AI95': cfg.BASE_MARGIN_AI95,
        'AI98': cfg.BASE_MARGIN_AI98, 'AI100': cfg.BASE_MARGIN_AI100,
        'DT': cfg.BASE_MARGIN_DT, 'DT_winter': cfg.BASE_MARGIN_DT_WINTER,
        'GAS': cfg.BASE_MARGIN_GAS
    }
    margin = margins.get(fuel_type, 3.00)

    db = await get_db()
    async with db.execute("""
        SELECT u.vip_until FROM users u
        JOIN stations s ON s.owner_id = u.id
        WHERE s.id = ?
    """, (station_id,)) as cursor:
        row = await cursor.fetchone()
    await db.close()

    if row and row['vip_until']:
        try:
            vip_dt = datetime.fromisoformat(row['vip_until'].replace('Z', '+00:00'))
            if vip_dt > datetime.now():
                margin += 1.50
        except:
            pass

    price = wholesale + margin
    competitive = min(price, (competitor_price or 999) + 2.0)
    competitive = max(competitive, wholesale + 1.0)
    return round(competitive, 2)

async def calculate_demand(station_id: int, hour: int, weather: str, fuel_type: str) -> int:
    db = await get_db()
    async with db.execute(
        "SELECT reputation, cleanliness, location_type FROM stations WHERE id=?",
        (station_id,)
    ) as cursor:
        row = await cursor.fetchone()
    await db.close()

    if not row:
        return 0

    base = TRAFFIC_PROFILE.get(hour, 0.3)
    weather_mod = 1.15 if weather in ("rain", "snow") else 1.0 if weather == "sunny" else 0.95

    loc_mult = LOCATIONS.get(row['location_type'], {}).get('traffic_mult', 1.0)

    month = datetime.now().month
    season = "winter" if month in (12,1,2) else "spring" if month in (3,4,5) else "summer" if month in (6,7,8) else "autumn"
    season_mod = SEASON_MODS[season].get(fuel_type, 1.0)

    rep_mod = 1 + (row['reputation'] - 50) / 200
    clean_mod = 1 + (row['cleanliness'] - 50) / 300

    demand = int(3 * base * weather_mod * loc_mult * season_mod * rep_mod * clean_mod)
    return max(0, min(demand, 15))

async def process_sales_tick(station_id: int) -> float:
    db = await get_db()
    now = datetime.now()
    hour = now.hour
    weather = random.choice(["sunny", "sunny", "sunny", "cloudy", "rain"])

    async with db.execute("""
        SELECT AVG(price_ai95) as p95, AVG(price_ai92) as p92, AVG(price_dt) as pdt,
               AVG(price_ai98) as p98, AVG(price_gas) as pgas
        FROM competitors
        WHERE location_type = (SELECT location_type FROM stations WHERE id=?)
    """, (station_id,)) as cursor:
        comp = await cursor.fetchone()

    if comp is None:
        comp = {'p95': 60.0, 'p92': 55.0, 'pdt': 65.0, 'p98': 78.0, 'pgas': 33.0}

    async with db.execute("""
        SELECT COALESCE(SUM(bonus_pct), 0) as total_bonus
        FROM employees WHERE station_id=?
    """, (station_id,)) as cursor:
        bonus_row = await cursor.fetchone()
    total_bonus = bonus_row['total_bonus'] or 0.0

    async with db.execute(
        "SELECT * FROM tanks WHERE station_id = ? AND volume_current > 50",
        (station_id,)
    ) as cursor:
        tanks = await cursor.fetchall()

    total_revenue = 0.0

    for tank in tanks:
        ft = tank['fuel_type']
        if '95' in ft:
            comp_price = (comp['p95'] or 60.0)
        elif '92' in ft:
            comp_price = (comp['p92'] or 55.0)
        elif 'DT' in ft or 'dt' in ft:
            comp_price = (comp['pdt'] or 65.0)
        elif '98' in ft:
            comp_price = (comp['p98'] or 78.0)
        elif 'GAS' in ft:
            comp_price = (comp['pgas'] or 33.0)
        else:
            comp_price = 55.0

        price = await calculate_retail_price(station_id, ft, comp_price)
        demand = await calculate_demand(station_id, hour, weather, ft)

        avg_liters = random.uniform(18, 28)
        possible_clients = min(demand, int(tank['volume_current'] / avg_liters))

        if possible_clients <= 0:
            continue

        sold_liters = int(round(possible_clients * avg_liters))
        sold_liters = min(sold_liters, tank['volume_current'])

        revenue = sold_liters * price * (1 + total_bonus)

        await db.execute(
            "UPDATE tanks SET volume_current = volume_current - ? WHERE id=?",
            (sold_liters, tank['id'])
        )

        await db.execute("""
            INSERT INTO sales(station_id, fuel_type, liters, price_per_liter, total)
            VALUES(?,?,?,?,?)
        """, (station_id, ft, sold_liters, round(price, 2), round(revenue, 2)))

        total_revenue += revenue

    if total_revenue > 0:
        await db.execute("""
            UPDATE users SET balance = balance + ?
            WHERE id = (SELECT owner_id FROM stations WHERE id=?)
        """, (round(total_revenue, 2), station_id))

    await db.commit()
    await db.close()
    return total_revenue

async def get_station_total_liters(station_id: int) -> int:
    db = await get_db()
    async with db.execute(
        "SELECT COALESCE(SUM(volume_current), 0) FROM tanks WHERE station_id=?",
        (station_id,)
    ) as cursor:
        row = await cursor.fetchone()
    await db.close()
    return int(row[0])

# ═══════════════════════════════════════════════════════════════
# EVENTS
# ═══════════════════════════════════════════════════════════════
async def generate_inspection(station_id: int) -> bool:
    db = await get_db()

    async with db.execute(
        "SELECT quality_score, fuel_type FROM tanks WHERE station_id=?",
        (station_id,)
    ) as cursor:
        tanks = await cursor.fetchall()

    risk = 0.03
    for t in tanks:
        if t['quality_score'] < 70:
            risk += 0.06

    async with db.execute("""
        SELECT COUNT(*) FROM orders o
        JOIN suppliers s ON o.supplier_id = s.id
        WHERE o.station_id=? AND s.legal_risk > 30
        AND o.created_at > datetime('now', '-7 days')
    """, (station_id,)) as cursor:
        gray = (await cursor.fetchone())[0]
    if gray and gray > 0:
        risk += 0.10

    if random.random() < min(risk, 0.35):
        types = ['rosstandart', 'tax', 'fire', 'ecology']
        weights = [0.5, 0.2, 0.2, 0.1]
        insp_type = random.choices(types, weights)[0]
        severity = random.randint(1, 4)
        fine = severity * random.choice([5000, 10000, 15000, 25000])
        deadline = (datetime.now() + timedelta(hours=24)).isoformat()

        await db.execute("""
            INSERT INTO inspections(station_id, inspector_type, severity, deadline, fine_amount)
            VALUES(?,?,?,?,?)
        """, (station_id, insp_type, severity, deadline, fine))
        await db.commit()
        await db.close()
        return True

    await db.close()
    return False

async def apply_daily_lease():
    db = await get_db()
    async with db.execute("SELECT id, owner_id, land_lease_cost FROM stations") as cursor:
        stations = await cursor.fetchall()

    for st in stations:
        await db.execute(
            "UPDATE users SET balance = balance - ? WHERE id=?",
            (st['land_lease_cost'], st['owner_id'])
        )

    async with db.execute("""
        SELECT station_id, COALESCE(SUM(salary), 0) as payroll 
        FROM employees GROUP BY station_id
    """) as cursor:
        payrolls = await cursor.fetchall()
    for p in payrolls:
        async with db.execute(
            "SELECT owner_id FROM stations WHERE id=?", (p['station_id'],)
        ) as cur:
            owner = await cur.fetchone()
        if owner:
            await db.execute(
                "UPDATE users SET balance = balance - ? WHERE id=?",
                (p['payroll'] / 30, owner['owner_id'])
            )

    await db.commit()
    await db.close()

# ═══════════════════════════════════════════════════════════════
# SCHEDULER
# ═══════════════════════════════════════════════════════════════
_scheduler_task = None

async def tick_job(bot: Bot):
    db = await get_db()
    async with db.execute("SELECT id FROM stations") as cursor:
        stations = await cursor.fetchall()
    await db.close()

    for st in stations:
        revenue = await process_sales_tick(st['id'])
        if revenue > 15000:
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
                        f"🔥 <b>Отличный час!</b> Выручка +{revenue:,.0f} ₽ за 5 минут!"
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
    import time
    last_tick = 0
    last_daily_date = None

    while True:
        now = time.time()
        today = date.today()

        if now - last_tick >= 300:
            await tick_job(bot)
            last_tick = now

        if today != last_daily_date:
            await daily_job(bot)
            last_daily_date = today

        await asyncio.sleep(30)

async def start_scheduler(bot: Bot):
    global _scheduler_task
    _scheduler_task = asyncio.create_task(scheduler_loop(bot))

# ═══════════════════════════════════════════════════════════════
# FSM
# ═══════════════════════════════════════════════════════════════
class RegisterState(StatesGroup):
    choosing_scenario = State()
    choosing_location = State()
    naming_station = State()
    naming_new_location = State()

class AdminState(StatesGroup):
    give_money = State()
    take_money = State()
    give_fuel = State()
    take_fuel = State()
    change_rep = State()
    find_player = State()
    give_vip = State()
    give_wash = State()
    give_coffee = State()
    give_manager = State()
    give_branding = State()

class OrderState(StatesGroup):
    entering_liters = State()

class HireState(StatesGroup):
    choosing_role = State()
    confirming = State()

# ═══════════════════════════════════════════════════════════════
# HANDLERS — START
# ═══════════════════════════════════════════════════════════════
start_router = Router()

async def is_admin(telegram_id: int) -> bool:
    db = await get_db()
    async with db.execute("SELECT 1 FROM admins WHERE telegram_id=?", (telegram_id,)) as cursor:
        row = await cursor.fetchone()
    await db.close()
    return row is not None

async def resolve_user_by_query(db, query: str):
    """Возвращает user row по ID или @username"""
    if query.startswith('@'):
        async with db.execute("SELECT * FROM users WHERE username=?", (query[1:],)) as cursor:
            return await cursor.fetchone()
    else:
        async with db.execute("SELECT * FROM users WHERE id=?", (int(query),)) as cursor:
            return await cursor.fetchone()


async def resolve_station_by_query(db, query: str):
    """Возвращает station row по ID или @username (первая станция пользователя)"""
    if query.startswith('@'):
        async with db.execute("""
            SELECT s.* FROM stations s
            JOIN users u ON u.id = s.owner_id
            WHERE u.username = ?
            ORDER BY s.id LIMIT 1
        """, (query[1:],)) as cursor:
            return await cursor.fetchone()
    else:
        async with db.execute("SELECT * FROM stations WHERE id=?", (int(query),)) as cursor:
            return await cursor.fetchone()


@start_router.message(CommandStart())
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

@start_router.callback_query(RegisterState.choosing_scenario, F.data.startswith("scenario_"))
async def process_scenario(call: CallbackQuery, state: FSMContext):
    scenario = call.data.split("_")[1]
    await state.update_data(scenario=scenario)
    await state.set_state(RegisterState.choosing_location)

    await call.message.edit_text(
        SCENARIO_TEXTS[scenario] + "\n\n📍 <b>Выберите локацию для вашей первой АЗС:</b>",
        reply_markup=location_kb()
    )
    await call.answer()

@start_router.callback_query(RegisterState.choosing_location, F.data.startswith("location_"))
async def process_location(call: CallbackQuery, state: FSMContext):
    loc_key = call.data.split("_")[1]
    loc = LOCATIONS.get(loc_key)
    if not loc:
        await call.answer("Ошибка локации", show_alert=True)
        return

    await state.update_data(location=loc_key, location_name=loc['name'])
    await state.set_state(RegisterState.naming_station)

    await call.message.edit_text(
        f"✅ Локация: <b>{loc['name']}</b>\n"
        f"📊 Аренда: {loc['lease']:,.0f} ₽/день\n"
        f"🚗 Трафик: {'Высокий' if loc['traffic_mult'] > 1.1 else 'Средний' if loc['traffic_mult'] > 0.9 else 'Низкий'}\n\n"
        f"✍️ <b>Придумайте название АЗС:</b>\n"
        f"(2-50 символов, например: «Трасса-7», «Золотая колонка»)",
        reply_markup=None
    )
    await call.answer()

@start_router.message(RegisterState.naming_station)
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
        await message.answer(f"❌ Название «<b>{name}</b>» уже занято. Придумайте уникальное:")
        return

    data = await state.get_data()
    scenario = data['scenario']
    loc_key = data['location']
    loc = LOCATIONS[loc_key]

    start_balance = 50000.00 if scenario == 'inheritance' else 100000.00 if scenario == 'partner' else 30000.00
    lease = loc['lease']

    db = await get_db()
    cursor = await db.execute("""
        INSERT INTO users(telegram_id, username, full_name, scenario, balance)
        VALUES(?,?,?,?,?)
    """, (message.from_user.id, message.from_user.username, message.from_user.full_name, scenario, start_balance))
    user_id = cursor.lastrowid

    cursor = await db.execute("""
        INSERT INTO stations(owner_id, name, location_type, land_lease_cost)
        VALUES(?,?,?,?)
    """, (user_id, name, loc_key, lease))
    station_id = cursor.lastrowid

    fuels = ['AI92', 'AI95', 'DT']
    for f in fuels:
        await db.execute("""
            INSERT INTO tanks(station_id, fuel_type, volume_current)
            VALUES(?,?,?)
        """, (station_id, f, 5000))

    emp_name = random.choice(EMPLOYEE_NAMES)
    await db.execute("""
        INSERT INTO employees(station_id, role, name, salary, bonus_pct)
        VALUES(?,?,?,35000.00, 0.02)
    """, (station_id, 'cashier', emp_name))

    await db.commit()
    await db.close()

    await state.clear()
    await message.answer(
        f"✅ <b>АЗС «{name}» открыта!</b>\n\n"
        f"📍 {loc['name']}\n"
        f"💰 Баланс: {start_balance:,.0f} ₽\n"
        f"⛽ Топливо: 5 000 л каждого вида\n"
        f"👤 Кассир: {emp_name}\n"
        f"💸 Аренда: {lease:,.0f} ₽/день\n\n"
        f"Начинайте зарабатывать!",
        reply_markup=main_menu_kb(user_id)
    )

# ═══════════════════════════════════════════════════════════════
# ГЛАВНОЕ МЕНЮ + РАЗДЕЛЫ
# ═══════════════════════════════════════════════════════════════

@start_router.callback_query(F.data == "main_menu")
async def cb_main_menu(call: CallbackQuery):
    db = await get_db()
    async with db.execute("SELECT id, balance FROM users WHERE telegram_id=?", (call.from_user.id,)) as cursor:
        user = await cursor.fetchone()
    await db.close()
    if not user:
        await call.answer("Сначала нажмите /start", show_alert=True)
        return
    await call.message.edit_text(
        f"⛽ <b>Главное меню</b>\n\n💰 Баланс: {user['balance']:,.0f} ₽\n\nВыберите раздел:",
        reply_markup=main_menu_kb(user['id'])
    )
    await call.answer()

@start_router.callback_query(F.data == "warehouse")
async def cb_warehouse(call: CallbackQuery):
    db = await get_db()
    async with db.execute("""
        SELECT s.id, s.name FROM stations s
        JOIN users u ON u.id = s.owner_id
        WHERE u.telegram_id = ? ORDER BY s.id LIMIT 1
    """, (call.from_user.id,)) as cursor:
        station = await cursor.fetchone()

    if not station:
        await db.close()
        await call.answer("Сначала создайте АЗС", show_alert=True)
        return

    async with db.execute(
        "SELECT fuel_type, volume_current, volume_total, quality_score FROM tanks WHERE station_id=?",
        (station['id'],)
    ) as cursor:
        tanks = await cursor.fetchall()

    async with db.execute("""
        SELECT o.id, s.name as sup_name, o.fuel_type, o.liters, o.cost, o.delivery_cost, o.status, o.delivery_eta
        FROM orders o
        LEFT JOIN suppliers s ON o.supplier_id = s.id
        WHERE o.station_id = ? AND o.status IN ('pending','transit')
        ORDER BY o.created_at DESC
    """, (station['id'],)) as cursor:
        orders = await cursor.fetchall()
    await db.close()

    text = f"📦 <b>Склад — {station['name']}</b>\n\n"
    text += "<b>⛽ Резервуары:</b>\n"
    for t in tanks:
        pct = int(t['volume_current'] / t['volume_total'] * 100)
        bar = "🟩" * (pct // 10) + "⬜" * (10 - pct // 10)
        quality = "✅" if t['quality_score'] > 80 else "⚠️" if t['quality_score'] > 60 else "❌"
        text += f"• {t['fuel_type']}: {int(t['volume_current']):,}/{int(t['volume_total']):,} л ({pct}%) {bar} {quality}\n"

    if orders:
        text += "\n<b>🚛 Активные заказы:</b>\n"
        for o in orders:
            eta = o['delivery_eta'] or "—"
            deliv = f" (+дост. {int(o['delivery_cost']):,}₽)" if o['delivery_cost'] else ""
            text += f"• {o['sup_name'] or 'Неизв.'} | {o['fuel_type']} {int(o['liters']):,} л | {o['status']}{deliv}\n"
    else:
        text += "\n<i>Нет активных заказов</i>"

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📦 Заказать топливо", callback_data=f"order_fuel:{station['id']}")],
        [InlineKeyboardButton(text="🔧 Расширить резервуары", callback_data=f"expand_tanks:{station['id']}")],
        [InlineKeyboardButton(text="🔙 Меню", callback_data="main_menu")]
    ])
    await call.message.edit_text(text, reply_markup=kb)
    await call.answer()

@start_router.callback_query(F.data.startswith("expand_tanks:"))
async def cb_expand_tanks(call: CallbackQuery):
    station_id = int(call.data.split(":")[1])
    db = await get_db()
    async with db.execute("SELECT * FROM stations WHERE id=?", (station_id,)) as cursor:
        station = await cursor.fetchone()
    async with db.execute("SELECT * FROM users WHERE telegram_id=?", (call.from_user.id,)) as cursor:
        user = await cursor.fetchone()
    await db.close()

    if not user or not station:
        await call.answer("Ошибка", show_alert=True)
        return

    cost = cfg.TANK_UPGRADE_COST
    if user['balance'] < cost:
        await call.answer(f"❌ Нужно {cost:,.0f} ₽", show_alert=True)
        return

    db = await get_db()
    async with db.execute("SELECT * FROM tanks WHERE station_id=?", (station_id,)) as cursor:
        tanks = await cursor.fetchall()

    maxed = True
    for t in tanks:
        if t['volume_total'] < cfg.TANK_MAX_VOLUME:
            maxed = False
            new_total = min(cfg.TANK_MAX_VOLUME, t['volume_total'] + 20000)
            await db.execute("UPDATE tanks SET volume_total=? WHERE id=?", (new_total, t['id']))

    if maxed:
        await db.close()
        await call.answer("❌ Максимальный объём достигнут (100 000 л)", show_alert=True)
        return

    await db.execute("UPDATE users SET balance = balance - ? WHERE id=?", (cost, user['id']))
    await db.commit()
    await db.close()

    await call.answer(f"✅ Резервуары расширены! -{cost:,.0f} ₽", show_alert=True)
    await cb_warehouse(call)

@start_router.callback_query(F.data == "staff")
async def cb_staff(call: CallbackQuery):
    db = await get_db()
    async with db.execute("""
        SELECT s.id, s.name FROM stations s
        JOIN users u ON u.id = s.owner_id
        WHERE u.telegram_id = ? ORDER BY s.id LIMIT 1
    """, (call.from_user.id,)) as cursor:
        station = await cursor.fetchone()

    if not station:
        await db.close()
        await call.answer("Сначала создайте АЗС", show_alert=True)
        return

    async with db.execute(
        "SELECT id, role, name, skill, morale, salary, bonus_pct FROM employees WHERE station_id=?",
        (station['id'],)
    ) as cursor:
        staff = await cursor.fetchall()
    await db.close()

    text = f"👥 <b>Персонал — {station['name']}</b>\n\n"
    total_salary = 0
    for s in staff:
        total_salary += s['salary']
        mood = "😊" if s['morale'] > 70 else "😐" if s['morale'] > 40 else "😠"
        role_info = EMPLOYEE_ROLES.get(s['role'], {})
        bonus_text = f" (+{int(s['bonus_pct']*100)}% к чеку)" if s['bonus_pct'] > 0 else ""
        text += f"• {role_info.get('name', s['role'])} <b>{s['name']}</b>{bonus_text}\n"
        text += f"  Навык: {s['skill']}/100 | Мораль: {s['morale']}/100 {mood} | {s['salary']:,.0f} ₽/мес\n\n"

    text += f"<b>💸 Фонд зарплаты: {total_salary:,.0f} ₽/мес ({total_salary/30:,.0f} ₽/день)</b>"

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Нанять сотрудника", callback_data=f"hire_staff:{station['id']}")],
        [InlineKeyboardButton(text="🔙 Меню", callback_data="main_menu")]
    ])
    await call.message.edit_text(text, reply_markup=kb)
    await call.answer()

@start_router.callback_query(F.data.startswith("hire_staff:"))
async def cb_hire_staff(call: CallbackQuery):
    station_id = int(call.data.split(":")[1])

    text = "👤 <b>Найм персонала</b>\n\nВыберите должность:\n"
    kb = []
    for role_key, role_info in EMPLOYEE_ROLES.items():
        text += f"\n<b>{role_info['name']}</b> — {role_info['base_salary']:,.0f} ₽/мес\n"
        text += f"  {role_info['desc']}\n"
        kb.append([InlineKeyboardButton(
            text=f"{role_info['name']} — {role_info['base_salary']:,.0f} ₽",
            callback_data=f"hire_role:{station_id}:{role_key}"
        )])
    kb.append([InlineKeyboardButton(text="🔙 Назад", callback_data="staff")])

    await call.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    await call.answer()

@start_router.callback_query(F.data.startswith("hire_role:"))
async def cb_hire_role(call: CallbackQuery):
    parts = call.data.split(":")
    station_id = int(parts[1])
    role_key = parts[2]

    role_info = EMPLOYEE_ROLES.get(role_key)
    if not role_info:
        await call.answer("Ошибка роли", show_alert=True)
        return

    db = await get_db()
    async with db.execute("SELECT * FROM users WHERE telegram_id=?", (call.from_user.id,)) as cursor:
        user = await cursor.fetchone()
    await db.close()

    cost = role_info['base_salary'] * 2
    if user['balance'] < cost:
        await call.answer(f"❌ Нужно {cost:,.0f} ₽ (залог 2 мес)", show_alert=True)
        return

    name = random.choice(EMPLOYEE_NAMES)
    db = await get_db()
    async with db.execute("SELECT name FROM employees WHERE station_id=?", (station_id,)) as cursor:
        existing = [r['name'] for r in await cursor.fetchall()]
    attempts = 0
    while name in existing and attempts < 10:
        name = random.choice(EMPLOYEE_NAMES)
        attempts += 1

    skill = random.randint(40, 90)
    bonus = role_info['bonus_pct']

    await db.execute("""
        INSERT INTO employees(station_id, role, name, skill, salary, bonus_pct)
        VALUES(?,?,?,?,?,?)
    """, (station_id, role_key, name, skill, role_info['base_salary'], bonus))
    await db.execute("UPDATE users SET balance = balance - ? WHERE id=?", (cost, user['id']))
    await db.commit()
    await db.close()

    await call.answer(f"✅ Нанят {role_info['name']} {name}! -{cost:,.0f} ₽", show_alert=True)
    await cb_staff(call)

@start_router.callback_query(F.data == "finance")
async def cb_finance(call: CallbackQuery):
    db = await get_db()
    async with db.execute("SELECT id, balance, has_truck FROM users WHERE telegram_id=?", (call.from_user.id,)) as cursor:
        user = await cursor.fetchone()

    if not user:
        await db.close()
        await call.answer("Сначала /start", show_alert=True)
        return

    async with db.execute("""
        SELECT COALESCE(SUM(total),0) as rev_24 FROM sales
        WHERE station_id IN (SELECT id FROM stations WHERE owner_id=?) AND timestamp > datetime('now','-24 hours')
    """, (user['id'],)) as cursor:
        rev_24 = (await cursor.fetchone())[0]

    async with db.execute("""
        SELECT COALESCE(SUM(total),0) as rev_7 FROM sales
        WHERE station_id IN (SELECT id FROM stations WHERE owner_id=?) AND timestamp > datetime('now','-7 days')
    """, (user['id'],)) as cursor:
        rev_7 = (await cursor.fetchone())[0]

    async with db.execute(
        "SELECT COALESCE(SUM(land_lease_cost),0) as lease FROM stations WHERE owner_id=?",
        (user['id'],)
    ) as cursor:
        lease = (await cursor.fetchone())[0]

    async with db.execute(
        "SELECT COALESCE(SUM(salary),0) as payroll FROM employees WHERE station_id IN (SELECT id FROM stations WHERE owner_id=?)",
        (user['id'],)
    ) as cursor:
        payroll = (await cursor.fetchone())[0]

    async with db.execute("SELECT COUNT(*) as cnt FROM stations WHERE owner_id=?", (user['id'],)) as cursor:
        stations_count = (await cursor.fetchone())[0]
    await db.close()

    truck_status = "🚛 Свой бензовоз (доставка бесплатна)" if user['has_truck'] else f"❌ Нет бензовоза (+{cfg.DELIVERY_COST_PER_LITER:.2f} ₽/л за доставку)"

    text = (
        f"📊 <b>Финансы</b>\n\n"
        f"💰 Текущий баланс: <b>{user['balance']:,.0f} ₽</b>\n"
        f"⛽ АЗС в сети: {stations_count}\n\n"
        f"<b>Доходы:</b>\n"
        f"• 24 часа: {rev_24:,.0f} ₽\n"
        f"• 7 дней: {rev_7:,.0f} ₽\n\n"
        f"<b>Расходы (ежедневно):</b>\n"
        f"• Аренда земли: {lease:,.0f} ₽\n"
        f"• Зарплаты: {payroll/30:,.0f} ₽\n\n"
        f"{truck_status}"
    )

    kb_lines = []
    if not user['has_truck']:
        kb_lines.append([InlineKeyboardButton(text="🚛 Купить бензовоз (500K ₽)", callback_data="buy_truck")])
    kb_lines.append([InlineKeyboardButton(text="🔙 Меню", callback_data="main_menu")])

    await call.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_lines))
    await call.answer()

@start_router.callback_query(F.data == "buy_truck")
async def cb_buy_truck(call: CallbackQuery):
    db = await get_db()
    async with db.execute("SELECT * FROM users WHERE telegram_id=?", (call.from_user.id,)) as cursor:
        user = await cursor.fetchone()
    await db.close()

    if user['has_truck']:
        await call.answer("У вас уже есть бензовоз!", show_alert=True)
        return

    cost = 500000
    if user['balance'] < cost:
        await call.answer(f"❌ Нужно {cost:,.0f} ₽", show_alert=True)
        return

    db = await get_db()
    await db.execute("UPDATE users SET balance = balance - ?, has_truck = 1 WHERE id=?", (cost, user['id']))
    await db.commit()
    await db.close()

    await call.answer("✅ Бензовоз куплен! Доставка теперь бесплатна!", show_alert=True)
    await cb_finance(call)

@start_router.callback_query(F.data == "premium")
async def cb_premium(call: CallbackQuery):
    text = (
        "💎 <b>Премиум-магазин</b>\n\n"
        f"🚀 Экспресс-доставка — <b>{cfg.DONATE_EXPRESS_DELIVERY} ₽</b>\n"
        f"🤖 Автоценообразование — <b>{cfg.DONATE_AUTO_PRICING} ₽/мес</b>\n"
        f"⭐ VIP-статус — <b>{cfg.DONATE_VIP_MONTH} ₽/мес</b>\n"
        f"🚗 Мойка Kärcher — <b>{cfg.DONATE_WASH} ₽</b>\n"
        f"☕ Кофейня Barista — <b>{cfg.DONATE_COFFEE} ₽</b>\n"
        f"👔 Управляющий — <b>{cfg.DONATE_MANAGER} ₽</b>\n"
        f"🏢 Брендирование — <b>{cfg.DONATE_BRANDING} ₽</b>\n\n"
        f"<i>Покупка временно недоступна (демо-режим).</i>"
    )
    await call.message.edit_text(text, reply_markup=back_kb())
    await call.answer()

@start_router.callback_query(F.data == "buy_location")
async def cb_buy_location(call: CallbackQuery):
    db = await get_db()
    async with db.execute("SELECT * FROM users WHERE telegram_id=?", (call.from_user.id,)) as cursor:
        user = await cursor.fetchone()
    await db.close()

    text = "🗺 <b>Покупка новой локации</b>\n\n"
    kb = []
    for key, loc in LOCATIONS.items():
        cost = cfg.LOCATION_COST_HIGHWAY if key == 'highway' else cfg.LOCATION_COST_CITY if key == 'city' else cfg.LOCATION_COST_SUBURB
        text += f"📍 <b>{loc['name']}</b>\n"
        text += f"   {loc['desc']}\n"
        text += f"   Аренда: {loc['lease']:,.0f} ₽/день | Цена: {cost:,.0f} ₽\n\n"
        kb.append([InlineKeyboardButton(
            text=f"Купить {loc['name']} ({cost:,.0f} ₽)",
            callback_data=f"buy_loc_confirm:{key}"
        )])
    kb.append([InlineKeyboardButton(text="🔙 Меню", callback_data="main_menu")])

    await call.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    await call.answer()

@start_router.callback_query(F.data.startswith("buy_loc_confirm:"))
async def cb_buy_loc_confirm(call: CallbackQuery, state: FSMContext):
    loc_key = call.data.split(":")[1]
    loc = LOCATIONS.get(loc_key)
    if not loc:
        await call.answer("Ошибка", show_alert=True)
        return

    cost = cfg.LOCATION_COST_HIGHWAY if loc_key == 'highway' else cfg.LOCATION_COST_CITY if loc_key == 'city' else cfg.LOCATION_COST_SUBURB

    db = await get_db()
    async with db.execute("SELECT * FROM users WHERE telegram_id=?", (call.from_user.id,)) as cursor:
        user = await cursor.fetchone()
    await db.close()

    if user['balance'] < cost:
        await call.answer(f"❌ Нужно {cost:,.0f} ₽", show_alert=True)
        return

    await state.set_state(RegisterState.naming_new_location)
    await state.update_data(new_loc_key=loc_key, new_loc_cost=cost)
    await call.message.edit_text(
        f"✍️ <b>Новая АЗС на {loc['name']}</b>\n\n"
        f"Введите название новой АЗС (2-50 символов):",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отмена", callback_data="main_menu")]
        ])
    )
    await call.answer()

@start_router.message(RegisterState.naming_new_location)
async def msg_new_location_name(message: Message, state: FSMContext):
    data = await state.get_data()
    loc_key = data['new_loc_key']
    cost = data['new_loc_cost']
    loc = LOCATIONS[loc_key]
    name = message.text.strip()

    if len(name) < 2 or len(name) > 50:
        await message.answer("❌ Название должно быть от 2 до 50 символов.")
        return

    db = await get_db()
    async with db.execute("SELECT 1 FROM stations WHERE name=?", (name,)) as cursor:
        exists = await cursor.fetchone()
    if exists:
        await db.close()
        await message.answer("❌ Это название уже занято. Придумайте другое:")
        return

    async with db.execute("SELECT * FROM users WHERE telegram_id=?", (message.from_user.id,)) as cursor:
        user = await cursor.fetchone()

    if user['balance'] < cost:
        await db.close()
        await message.answer(f"❌ Недостаточно средств! Нужно {cost:,.0f} ₽.")
        await state.clear()
        return

    cursor = await db.execute("""
        INSERT INTO stations(owner_id, name, location_type, land_lease_cost)
        VALUES(?,?,?,?)
    """, (user['id'], name, loc_key, loc['lease']))
    station_id = cursor.lastrowid

    fuels = ['AI92', 'AI95', 'DT']
    for f in fuels:
        await db.execute("""
            INSERT INTO tanks(station_id, fuel_type, volume_current)
            VALUES(?,?,?)
        """, (station_id, f, 5000))

    await db.execute("UPDATE users SET balance = balance - ? WHERE id=?", (cost, user['id']))
    await db.commit()
    await db.close()

    await state.clear()
    await message.answer(
        f"✅ <b>АЗС «{name}» куплена!</b>\n\n"
        f"📍 {loc['name']}\n"
        f"💸 Аренда: {loc['lease']:,.0f} ₽/день\n"
        f"⛽ Топливо: 5 000 л каждого вида\n\n"
        f"Ваша сеть растёт!",
        reply_markup=main_menu_kb(user['id'])
    )

# ====== АДМИНИСТРИРОВАНИЕ ======

@start_router.message(Command("admin"))
async def cmd_admin(message: Message):
    if not await is_admin(message.from_user.id):
        await message.answer("⛔ У вас нет прав администратора.")
        return
    await message.answer("🔧 <b>Панель администратора</b>", reply_markup=admin_kb())

@start_router.callback_query(F.data == "admin_give_money")
async def admin_give_money_start(call: CallbackQuery, state: FSMContext):
    if not await is_admin(call.from_user.id):
        return await call.answer("Нет прав")
    await state.set_state(AdminState.give_money)
    await call.message.edit_text(
        "💰 <b>Выдача денег</b>\n\nФормат: <code>ID_игрока сумма</code>\nПример: <code>12345 50000</code>",
        reply_markup=back_kb()
    )
    await call.answer()

@start_router.message(AdminState.give_money)
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
            await message.answer("❌ Игрок не найден.", reply_markup=back_kb())
            return

        await db.execute("UPDATE users SET balance = balance + ? WHERE id=?", (amount, target_id))
        await db.commit()
        await db.close()

        await state.clear()
        await message.answer(
            f"✅ Выдано <b>{amount:,.0f} ₽</b> игроку {user['full_name']} (ID: {target_id})\n"
            f"Новый баланс: {user['balance'] + amount:,.0f} ₽",
            reply_markup=admin_kb()
        )
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}", reply_markup=back_kb())

@start_router.callback_query(F.data == "admin_take_money")
async def admin_take_money_start(call: CallbackQuery, state: FSMContext):
    if not await is_admin(call.from_user.id):
        return await call.answer("Нет прав")
    await state.set_state(AdminState.take_money)
    await call.message.edit_text(
        "💰 <b>Забор денег</b>\n\nФормат: <code>ID_игрока/@username сумма</code>\nПример: <code>12345 50000</code> или <code>@ivan 50000</code>",
        reply_markup=back_kb()
    )
    await call.answer()

@start_router.message(AdminState.take_money)
async def admin_take_money_exec(message: Message, state: FSMContext):
    try:
        parts = message.text.strip().split()
        query = parts[0]
        amount = float(parts[1])

        db = await get_db()
        user = await resolve_user_by_query(db, query)

        if not user:
            await db.close()
            await message.answer("❌ Игрок не найден.", reply_markup=back_kb())
            return

        new_balance = max(0, user['balance'] - amount)
        await db.execute("UPDATE users SET balance = ? WHERE id=?", (new_balance, user['id']))
        await db.commit()
        await db.close()

        await state.clear()
        await message.answer(
            f"✅ Забрано <b>{amount:,.0f} ₽</b> у {user['full_name']} (ID: {user['id']})\n"
            f"Новый баланс: {new_balance:,.0f} ₽",
            reply_markup=admin_kb()
        )
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}", reply_markup=back_kb())

@start_router.callback_query(F.data == "admin_give_fuel")
async def admin_give_fuel_start(call: CallbackQuery, state: FSMContext):
    if not await is_admin(call.from_user.id):
        return await call.answer("Нет прав")
    await state.set_state(AdminState.give_fuel)
    await call.message.edit_text(
        "⛽ <b>Выдача топлива</b>\n\nФормат: <code>ID_станции/@username тип_топлива литры</code>\nПример: <code>1 AI95 10000</code> или <code>@ivan AI95 10000</code>",
        reply_markup=back_kb()
    )
    await call.answer()

@start_router.message(AdminState.give_fuel)
async def admin_give_fuel_exec(message: Message, state: FSMContext):
    try:
        parts = message.text.strip().split()
        query = parts[0]
        fuel_type = parts[1].upper()
        liters = int(parts[2])

        db = await get_db()
        station = await resolve_station_by_query(db, query)

        if not station:
            await db.close()
            await message.answer("❌ Станция не найдена.", reply_markup=back_kb())
            return

        async with db.execute(
            "SELECT * FROM tanks WHERE station_id=? AND fuel_type=?",
            (station['id'], fuel_type)
        ) as cursor:
            tank = await cursor.fetchone()

        if not tank:
            await db.close()
            await message.answer("❌ Резервуар не найден.", reply_markup=back_kb())
            return

        new_vol = int(min(tank['volume_total'], tank['volume_current'] + liters))
        await db.execute(
            "UPDATE tanks SET volume_current = ? WHERE id=?",
            (new_vol, tank['id'])
        )
        await db.commit()
        await db.close()

        await state.clear()
        await message.answer(
            f"✅ Добавлено <b>{liters:,} л</b> {fuel_type}\n"
            f"АЗС: «{station['name']}» (ID: {station['id']})\n"
            f"Текущий запас: {new_vol:,} л",
            reply_markup=admin_kb()
        )
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}", reply_markup=back_kb())

@start_router.callback_query(F.data == "admin_take_fuel")
async def admin_take_fuel_start(call: CallbackQuery, state: FSMContext):
    if not await is_admin(call.from_user.id):
        return await call.answer("Нет прав")
    await state.set_state(AdminState.take_fuel)
    await call.message.edit_text(
        "⛽ <b>Забор топлива</b>\n\nФормат: <code>ID_станции/@username тип_топлива литры</code>\nПример: <code>1 AI95 10000</code> или <code>@ivan AI95 10000</code>",
        reply_markup=back_kb()
    )
    await call.answer()

@start_router.message(AdminState.take_fuel)
async def admin_take_fuel_exec(message: Message, state: FSMContext):
    try:
        parts = message.text.strip().split()
        query = parts[0]
        fuel_type = parts[1].upper()
        liters = int(parts[2])

        db = await get_db()
        station = await resolve_station_by_query(db, query)

        if not station:
            await db.close()
            await message.answer("❌ Станция не найдена.", reply_markup=back_kb())
            return

        async with db.execute(
            "SELECT * FROM tanks WHERE station_id=? AND fuel_type=?",
            (station['id'], fuel_type)
        ) as cursor:
            tank = await cursor.fetchone()

        if not tank:
            await db.close()
            await message.answer("❌ Резервуар не найден.", reply_markup=back_kb())
            return

        new_vol = int(max(0, tank['volume_current'] - liters))
        await db.execute(
            "UPDATE tanks SET volume_current = ? WHERE id=?",
            (new_vol, tank['id'])
        )
        await db.commit()
        await db.close()

        await state.clear()
        await message.answer(
            f"✅ Забрано <b>{liters:,} л</b> {fuel_type}\n"
            f"АЗС: «{station['name']}» (ID: {station['id']})\n"
            f"Текущий запас: {new_vol:,} л",
            reply_markup=admin_kb()
        )
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}", reply_markup=back_kb())

@start_router.callback_query(F.data == "admin_rep")
async def admin_rep_start(call: CallbackQuery, state: FSMContext):
    if not await is_admin(call.from_user.id):
        return await call.answer("Нет прав")
    await state.set_state(AdminState.change_rep)
    await call.message.edit_text(
        "⭐ <b>Изменение репутации</b>\n\nФормат: <code>ID_станции/@username новая_репутация(0-100)</code>\nПример: <code>1 80</code> или <code>@ivan 80</code>",
        reply_markup=back_kb()
    )
    await call.answer()

@start_router.message(AdminState.change_rep)
async def admin_rep_exec(message: Message, state: FSMContext):
    try:
        parts = message.text.strip().split()
        query = parts[0]
        rep = max(0, min(100, int(parts[1])))

        db = await get_db()
        station = await resolve_station_by_query(db, query)

        if not station:
            await db.close()
            await message.answer("❌ Станция не найдена.", reply_markup=back_kb())
            return

        await db.execute("UPDATE stations SET reputation = ? WHERE id=?", (rep, station['id']))
        await db.commit()
        await db.close()

        await state.clear()
        await message.answer(
            f"✅ Репутация АЗС «{station['name']}» (ID: {station['id']}) изменена на <b>{rep}/100</b>",
            reply_markup=admin_kb()
        )
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}", reply_markup=back_kb())

@start_router.callback_query(F.data == "admin_list")
async def admin_list(call: CallbackQuery):
    if not await is_admin(call.from_user.id):
        return await call.answer("Нет прав")

    db = await get_db()
    async with db.execute("SELECT * FROM admins ORDER BY added_at") as cursor:
        admins = await cursor.fetchall()
    await db.close()

    text = "👥 <b>Администраторы</b>\n\n"
    for i, a in enumerate(admins, 1):
        text += f"{i}. ID: <code>{a['telegram_id']}</code> | {a['role']}\n"

    await call.message.edit_text(text, reply_markup=admin_kb())
    await call.answer()

@start_router.callback_query(F.data == "admin_find")
async def admin_find_start(call: CallbackQuery, state: FSMContext):
    if not await is_admin(call.from_user.id):
        return await call.answer("Нет прав")
    await state.set_state(AdminState.find_player)
    await call.message.edit_text(
        "🔍 <b>Поиск игрока</b>\n\nВведите ID или @username:",
        reply_markup=back_kb()
    )
    await call.answer()

@start_router.message(AdminState.find_player)
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
            stations_text += f"\n• ID: {s['id']} | «{s['name']}» | Реп: {s['reputation']} | {int(total_fuel):,} л"

        vip_status = 'Нет'
        if user['vip_until']:
            try:
                vip_dt = datetime.fromisoformat(user['vip_until'].replace('Z', '+00:00'))
                if vip_dt > datetime.now():
                    vip_status = 'Да'
            except:
                pass

        text = (
            f"👤 <b>{user['full_name']}</b>\n"
            f"ID: <code>{user['id']}</code> | @{user['username'] or 'нет'}\n"
            f"Баланс: {user['balance']:,.0f} ₽ | Уровень: {user['level']}\n"
            f"VIP: {vip_status} | Бензовоз: {'✅' if user['has_truck'] else '❌'}\n"
            f"АЗС: {len(stations)}{stations_text}"
        )
        await db.close()
        await state.clear()
        await message.answer(text, reply_markup=admin_kb())
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}", reply_markup=back_kb())



@start_router.callback_query(F.data == "admin_give_vip")
async def admin_give_vip_start(call: CallbackQuery, state: FSMContext):
    if not await is_admin(call.from_user.id):
        return await call.answer("Нет прав")
    await state.set_state(AdminState.give_vip)
    await call.message.edit_text(
        "⭐ <b>Выдача VIP</b>\n\nФормат: <code>ID_игрока/@username дни</code>\nПример: <code>12345 30</code> или <code>@ivan 30</code>",
        reply_markup=back_kb()
    )
    await call.answer()

@start_router.message(AdminState.give_vip)
async def admin_give_vip_exec(message: Message, state: FSMContext):
    try:
        parts = message.text.strip().split()
        query = parts[0]
        days = int(parts[1]) if len(parts) > 1 else 30

        db = await get_db()
        user = await resolve_user_by_query(db, query)
        if not user:
            await db.close()
            await message.answer("❌ Игрок не найден.", reply_markup=back_kb())
            return

        vip_until = (datetime.now() + timedelta(days=days)).isoformat()
        await db.execute("UPDATE users SET vip_until = ? WHERE id=?", (vip_until, user['id']))
        await db.commit()
        await db.close()

        await state.clear()
        await message.answer(
            f"✅ VIP выдан игроку <b>{user['full_name']}</b> (ID: {user['id']}) на {days} дней!",
            reply_markup=admin_kb()
        )
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}", reply_markup=back_kb())

@start_router.callback_query(F.data == "admin_give_wash")
async def admin_give_wash_start(call: CallbackQuery, state: FSMContext):
    if not await is_admin(call.from_user.id):
        return await call.answer("Нет прав")
    await state.set_state(AdminState.give_wash)
    await call.message.edit_text(
        "🚗 <b>Выдача мойки</b>\n\nФормат: <code>ID_станции/@username</code>",
        reply_markup=back_kb()
    )
    await call.answer()

@start_router.message(AdminState.give_wash)
async def admin_give_wash_exec(message: Message, state: FSMContext):
    try:
        query = message.text.strip()
        db = await get_db()
        station = await resolve_station_by_query(db, query)
        if not station:
            await db.close()
            await message.answer("❌ Станция не найдена.", reply_markup=back_kb())
            return

        await db.execute("UPDATE stations SET has_wash = 1 WHERE id=?", (station['id'],))
        await db.execute("""
            INSERT OR IGNORE INTO upgrades(station_id, type, level, effect_multiplier)
            VALUES(?, 'car_wash', 1, 1.00)
        """, (station['id'],))
        await db.commit()
        await db.close()

        await state.clear()
        await message.answer(
            f"✅ Мойка выдана АЗС «{station['name']}» (ID: {station['id']})",
            reply_markup=admin_kb()
        )
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}", reply_markup=back_kb())

@start_router.callback_query(F.data == "admin_give_coffee")
async def admin_give_coffee_start(call: CallbackQuery, state: FSMContext):
    if not await is_admin(call.from_user.id):
        return await call.answer("Нет прав")
    await state.set_state(AdminState.give_coffee)
    await call.message.edit_text(
        "☕ <b>Выдача кофейни</b>\n\nФормат: <code>ID_станции/@username</code>",
        reply_markup=back_kb()
    )
    await call.answer()

@start_router.message(AdminState.give_coffee)
async def admin_give_coffee_exec(message: Message, state: FSMContext):
    try:
        query = message.text.strip()
        db = await get_db()
        station = await resolve_station_by_query(db, query)
        if not station:
            await db.close()
            await message.answer("❌ Станция не найдена.", reply_markup=back_kb())
            return

        await db.execute("UPDATE stations SET has_shop = 1, shop_level = 1 WHERE id=?", (station['id'],))
        await db.execute("""
            INSERT OR IGNORE INTO upgrades(station_id, type, level, effect_multiplier)
            VALUES(?, 'coffee_shop', 1, 1.00)
        """, (station['id'],))
        await db.commit()
        await db.close()

        await state.clear()
        await message.answer(
            f"✅ Кофейня выдана АЗС «{station['name']}» (ID: {station['id']})",
            reply_markup=admin_kb()
        )
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}", reply_markup=back_kb())

@start_router.callback_query(F.data == "admin_give_manager")
async def admin_give_manager_start(call: CallbackQuery, state: FSMContext):
    if not await is_admin(call.from_user.id):
        return await call.answer("Нет прав")
    await state.set_state(AdminState.give_manager)
    await call.message.edit_text(
        "👔 <b>Выдача управляющего</b>\n\nФормат: <code>ID_станции/@username</code>",
        reply_markup=back_kb()
    )
    await call.answer()

@start_router.message(AdminState.give_manager)
async def admin_give_manager_exec(message: Message, state: FSMContext):
    try:
        query = message.text.strip()
        db = await get_db()
        station = await resolve_station_by_query(db, query)
        if not station:
            await db.close()
            await message.answer("❌ Станция не найдена.", reply_markup=back_kb())
            return

        name = random.choice(EMPLOYEE_NAMES)
        async with db.execute("SELECT name FROM employees WHERE station_id=?", (station['id'],)) as cursor:
            existing = [r['name'] for r in await cursor.fetchall()]
        attempts = 0
        while name in existing and attempts < 10:
            name = random.choice(EMPLOYEE_NAMES)
            attempts += 1

        await db.execute("""
            INSERT INTO employees(station_id, role, name, skill, salary, bonus_pct)
            VALUES(?,?,?,?,?,?)
        """, (station['id'], 'manager', name, 80, 60000, 0.05))
        await db.commit()
        await db.close()

        await state.clear()
        await message.answer(
            f"✅ Управляющий <b>{name}</b> нанят на АЗС «{station['name']}» (ID: {station['id']})",
            reply_markup=admin_kb()
        )
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}", reply_markup=back_kb())

@start_router.callback_query(F.data == "admin_give_branding")
async def admin_give_branding_start(call: CallbackQuery, state: FSMContext):
    if not await is_admin(call.from_user.id):
        return await call.answer("Нет прав")
    await state.set_state(AdminState.give_branding)
    await call.message.edit_text(
        "🏢 <b>Выдача брендирования</b>\n\nФормат: <code>ID_станции/@username</code>",
        reply_markup=back_kb()
    )
    await call.answer()

@start_router.message(AdminState.give_branding)
async def admin_give_branding_exec(message: Message, state: FSMContext):
    try:
        query = message.text.strip()
        db = await get_db()
        station = await resolve_station_by_query(db, query)
        if not station:
            await db.close()
            await message.answer("❌ Станция не найдена.", reply_markup=back_kb())
            return

        await db.execute("""
            INSERT OR IGNORE INTO upgrades(station_id, type, level, effect_multiplier)
            VALUES(?, 'led_sign', 1, 1.20)
        """, (station['id'],))
        await db.commit()
        await db.close()

        await state.clear()
        await message.answer(
            f"✅ Брендирование выдано АЗС «{station['name']}» (ID: {station['id']})",
            reply_markup=admin_kb()
        )
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}", reply_markup=back_kb())

# ═══════════════════════════════════════════════════════════════
# HANDLERS — STATION
# ═══════════════════════════════════════════════════════════════
station_router = Router()

@station_router.callback_query(F.data == "my_station")
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
        await call.answer("Сначала создайте АЗС через /start", show_alert=True)
        return

    async with db.execute(
        "SELECT fuel_type, volume_current, volume_total FROM tanks WHERE station_id=?",
        (station['id'],)
    ) as cursor:
        tanks = await cursor.fetchall()
    await db.close()

    tanks_text = "\n".join([
        f"• {t['fuel_type']}: {int(t['volume_current']):,}/{int(t['volume_total']):,} л"
        for t in tanks
    ])

    total_liters = sum(int(t['volume_current']) for t in tanks)

    text = (
        f"⛽ <b>{station['name']}</b>\n"
        f"📍 {LOCATIONS.get(station['location_type'], {}).get('name', station['location_type'])}\n"
        f"💰 Баланс: {station['balance']:,.0f} ₽\n"
        f"⭐ Репутация: {station['reputation']}/100 | 🧹 Чистота: {station['cleanliness']}/100\n"
        f"🚗 Мойка: {'✅' if station['has_wash'] else '❌'} | 🏪 Магазин: {'✅' if station['has_shop'] else '❌'}\n\n"
        f"<b>⛽ Резервуары ({total_liters:,} л):</b>\n{tanks_text}\n\n"
        f"💸 Аренда: {station['land_lease_cost']:,.0f} ₽/день"
    )

    await call.message.edit_text(text, reply_markup=station_management_kb(station['id']))
    await call.answer()

@station_router.callback_query(F.data.startswith("set_prices:"))
async def price_menu(call: CallbackQuery):
    station_id = int(call.data.split(":")[1])
    db = await get_db()

    async with db.execute(
        "SELECT fuel_type, volume_current FROM tanks WHERE station_id=?",
        (station_id,)
    ) as cursor:
        tanks = await cursor.fetchall()
    await db.close()

    text = "🏷 <b>Цены на сегодня</b>\n\n"
    for t in tanks:
        wp = await get_wholesale_price(t['fuel_type'])
        text += f"• {t['fuel_type']}: опт {wp:.2f} ₽/л | запас {int(t['volume_current']):,} л\n"

    text += "\n<i>Цены обновляются автоматически. VIP — ручное управление.</i>"

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 К АЗС", callback_data="my_station")]
    ])
    await call.message.edit_text(text, reply_markup=kb)
    await call.answer()

# ─── ЗАКАЗ ТОПЛИВА С ДОСТАВКОЙ ───
@station_router.callback_query(F.data.startswith("order_fuel:"))
async def cb_order_fuel_start(call: CallbackQuery):
    station_id = int(call.data.split(":")[1])
    db = await get_db()
    async with db.execute("SELECT * FROM suppliers ORDER BY price_discount DESC") as cursor:
        suppliers = await cursor.fetchall()

    async with db.execute("SELECT has_truck FROM users WHERE telegram_id=?", (call.from_user.id,)) as cursor:
        user = await cursor.fetchone()
    has_truck = user['has_truck'] if user else 0
    await db.close()

    text = f"📦 <b>Заказ топлива</b>\n"
    text += f"{'🚛 Свой бензовоз' if has_truck else f'❌ Доставка +{cfg.DELIVERY_COST_PER_LITER:.2f} ₽/л'}\n\n"
    text += "Выберите поставщика:\n"

    kb = []
    for s in suppliers:
        risk = "⚠️" if s['legal_risk'] > 30 else "✅"
        text += f"\n{risk} <b>{s['name']}</b>\n"
        text += f"   Скидка: {s['price_discount']:.2f} ₽/л | Надёжность: {s['reliability']}%\n"
        text += f"   Доставка: {s['delivery_hours']}ч | Мин. заказ: {int(s['min_order_liters']):,} л\n"
        kb.append([InlineKeyboardButton(
            text=f"🚛 {s['name']}",
            callback_data=f"order_sup:{station_id}:{s['id']}"
        )])
    kb.append([InlineKeyboardButton(text="🔙 Назад", callback_data="my_station")])

    await call.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    await call.answer()

@station_router.callback_query(F.data.startswith("order_sup:"))
async def cb_order_supplier(call: CallbackQuery):
    _, station_id, supplier_id = call.data.split(":")
    station_id = int(station_id)
    supplier_id = int(supplier_id)

    db = await get_db()
    async with db.execute("SELECT * FROM suppliers WHERE id=?", (supplier_id,)) as cursor:
        supplier = await cursor.fetchone()
    async with db.execute("SELECT has_truck FROM users WHERE telegram_id=?", (call.from_user.id,)) as cursor:
        user = await cursor.fetchone()
    has_truck = user['has_truck'] if user else 0
    await db.close()

    if not supplier:
        await call.answer("Поставщик не найден", show_alert=True)
        return

    fuel_types = supplier['fuel_types'].split(",")
    text = f"⛽ <b>{supplier['name']}</b> — выберите топливо:\n"
    if not has_truck:
        text += f"<i>Доставка: +{cfg.DELIVERY_COST_PER_LITER:.2f} ₽/л (купите бензовоз в финансах)</i>\n"
    text += "\n"

    kb = []
    for ft in fuel_types:
        wp = await get_wholesale_price(ft)
        price = round(wp - supplier['price_discount'], 2)
        deliv = " (без доставки)" if has_truck else f" (+{cfg.DELIVERY_COST_PER_LITER:.2f} ₽ доставка)"
        text += f"• {ft}: <b>{price:.2f} ₽/л</b>{deliv}\n"
        kb.append([InlineKeyboardButton(
            text=f"⛽ {ft} — {price:.2f} ₽/л",
            callback_data=f"order_fuel_type:{station_id}:{supplier_id}:{ft}"
        )])
    kb.append([InlineKeyboardButton(text="🔙 К поставщикам", callback_data=f"order_fuel:{station_id}")])

    await call.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    await call.answer()

@station_router.callback_query(F.data.startswith("order_fuel_type:"))
async def cb_order_fuel_type(call: CallbackQuery, state: FSMContext):
    _, station_id, supplier_id, fuel_type = call.data.split(":")
    station_id = int(station_id)
    supplier_id = int(supplier_id)

    db = await get_db()
    async with db.execute("SELECT * FROM suppliers WHERE id=?", (supplier_id,)) as cursor:
        supplier = await cursor.fetchone()
    await db.close()

    if not supplier:
        await call.answer("Ошибка", show_alert=True)
        return

    await state.update_data(
        order_station_id=station_id,
        order_supplier_id=supplier_id,
        order_fuel_type=fuel_type,
        order_min_liters=supplier['min_order_liters']
    )
    await state.set_state(OrderState.entering_liters)

    wp = await get_wholesale_price(fuel_type)
    price = round(wp - supplier['price_discount'], 2)

    await call.message.edit_text(
        f"📦 <b>Заказ {fuel_type}</b> от {supplier['name']}\n"
        f"Цена: <b>{price:.2f} ₽/л</b> | Минимум: {int(supplier['min_order_liters']):,} л\n\n"
        f"✍️ Введите количество литров:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отмена", callback_data="my_station")]
        ])
    )
    await call.answer()

@station_router.message(OrderState.entering_liters)
async def msg_order_liters(message: Message, state: FSMContext):
    data = await state.get_data()
    station_id = data['order_station_id']
    supplier_id = data['order_supplier_id']
    fuel_type = data['order_fuel_type']
    min_liters = data['order_min_liters']

    try:
        liters = int(message.text.strip().replace(" ", "").replace(",", ""))
    except ValueError:
        await message.answer("❌ Введите целое число литров.")
        return

    if liters < min_liters:
        await message.answer(f"❌ Минимальный заказ — {int(min_liters):,} л.")
        return

    db = await get_db()
    async with db.execute("SELECT * FROM suppliers WHERE id=?", (supplier_id,)) as cursor:
        supplier = await cursor.fetchone()
    async with db.execute("SELECT * FROM users WHERE telegram_id=?", (message.from_user.id,)) as cursor:
        user = await cursor.fetchone()
    await db.close()

    wp = await get_wholesale_price(fuel_type)
    unit_price = round(wp - supplier['price_discount'], 2)
    fuel_cost = round(liters * unit_price, 2)

    delivery_cost = 0 if user['has_truck'] else round(liters * cfg.DELIVERY_COST_PER_LITER, 2)
    total_cost = fuel_cost + delivery_cost

    if user['balance'] < total_cost:
        await message.answer(
            f"❌ Недостаточно средств! Нужно <b>{total_cost:,.0f} ₽</b> (топливо {fuel_cost:,.0f} ₽ + доставка {delivery_cost:,.0f} ₽)\n"
            f"У вас: {user['balance']:,.0f} ₽",
            reply_markup=back_kb()
        )
        await state.clear()
        return

    await state.update_data(order_liters=liters, order_total=total_cost, order_delivery=delivery_cost)

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="✅ Подтвердить",
            callback_data=f"order_confirm:{station_id}:{supplier_id}:{fuel_type}:{liters}"
        )],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="my_station")]
    ])

    deliv_text = f"\n🚛 Доставка: {delivery_cost:,.0f} ₽" if delivery_cost > 0 else "\n🚛 Доставка: бесплатно (свой бензовоз)"

    await message.answer(
        f"📋 <b>Подтверждение заказа</b>\n\n"
        f"Поставщик: {supplier['name']}\n"
        f"Топливо: {fuel_type} | {int(liters):,} л\n"
        f"Цена: {unit_price:.2f} ₽/л\n"
        f"Стоимость топлива: {fuel_cost:,.0f} ₽{deliv_text}\n"
        f"<b>Итого: {total_cost:,.0f} ₽</b>\n\n"
        f"Со счёта спишется {total_cost:,.0f} ₽. Подтверждаете?",
        reply_markup=kb
    )

@station_router.callback_query(F.data.startswith("order_confirm:"))
async def cb_order_confirm(call: CallbackQuery):
    parts = call.data.split(":")
    if len(parts) < 5:
        await call.answer("Ошибка данных", show_alert=True)
        return
    station_id = int(parts[1])
    supplier_id = int(parts[2])
    fuel_type = parts[3]
    liters = int(parts[4])

    db = await get_db()
    async with db.execute("SELECT * FROM suppliers WHERE id=?", (supplier_id,)) as cursor:
        supplier = await cursor.fetchone()
    async with db.execute("SELECT * FROM users WHERE telegram_id=?", (call.from_user.id,)) as cursor:
        user = await cursor.fetchone()

    if not user or not supplier:
        await db.close()
        await call.answer("Ошибка", show_alert=True)
        return

    wp = await get_wholesale_price(fuel_type)
    unit_price = round(wp - supplier['price_discount'], 2)
    fuel_cost = round(liters * unit_price, 2)
    delivery_cost = 0 if user['has_truck'] else round(liters * cfg.DELIVERY_COST_PER_LITER, 2)
    total_cost = fuel_cost + delivery_cost

    if user['balance'] < total_cost:
        await db.close()
        await call.answer("❌ Недостаточно средств!", show_alert=True)
        return

    await db.execute("UPDATE users SET balance = balance - ? WHERE id=?", (total_cost, user['id']))

    eta = (datetime.now() + timedelta(hours=supplier['delivery_hours'])).isoformat()
    await db.execute("""
        INSERT INTO orders(station_id, supplier_id, fuel_type, liters, cost, delivery_cost, status, delivery_eta)
        VALUES(?,?,?,?,?,'delivered',?)
    """, (station_id, supplier_id, fuel_type, liters, fuel_cost, delivery_cost, eta))

    async with db.execute(
        "SELECT * FROM tanks WHERE station_id=? AND fuel_type=?",
        (station_id, fuel_type)
    ) as cursor:
        tank = await cursor.fetchone()

    if tank:
        new_vol = int(min(tank['volume_total'], tank['volume_current'] + liters))
        await db.execute(
            "UPDATE tanks SET volume_current=?, last_refill=datetime('now'), quality_score=? WHERE id=?",
            (new_vol, max(50, 95 - supplier['legal_risk'] // 3), tank['id'])
        )
    else:
        await db.execute("""
            INSERT INTO tanks(station_id, fuel_type, volume_total, volume_current, quality_score)
            VALUES(?,?,20000,?,?)
        """, (station_id, fuel_type, liters, max(50, 95 - supplier['legal_risk'] // 3)))

    await db.commit()
    await db.close()

    deliv_text = f" (+{delivery_cost:,.0f} ₽ доставка)" if delivery_cost > 0 else " (доставка бесплатно)"

    await call.message.edit_text(
        f"✅ <b>Заказ выполнен!</b>\n\n"
        f"🚛 {supplier['name']}\n"
        f"⛽ {fuel_type} — {int(liters):,} л\n"
        f"💰 Списано: {total_cost:,.0f} ₽{deliv_text}\n"
        f"📦 Топливо поступило на склад.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 К АЗС", callback_data="my_station")]
        ])
    )
    await call.answer()

@station_router.callback_query(F.data.startswith("clean_station:"))
async def clean_station(call: CallbackQuery):
    station_id = int(call.data.split(":")[1])
    db = await get_db()

    async with db.execute("SELECT * FROM stations WHERE id=?", (station_id,)) as cursor:
        station = await cursor.fetchone()

    async with db.execute("SELECT * FROM users WHERE telegram_id=?", (call.from_user.id,)) as cursor:
        user = await cursor.fetchone()

    if user['balance'] < 500:
        await db.close()
        await call.answer("❌ Нужно 500 ₽", show_alert=True)
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

    await call.answer(f"✅ Уборка! Чистота {new_clean}/100, репутация +3", show_alert=True)
    await show_station(call)

@station_router.callback_query(F.data.startswith("stats:"))
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
        f"📈 <b>Статистика АЗС #{station_id}</b>\n\n"
        f"<b>24 часа:</b>\n"
        f"💰 {total_rev_24h:,.0f} ₽ | ⛽ {int(total_lit_24h):,} л\n\n"
        f"<b>7 дней:</b>\n"
        f"💰 {total_rev_7d:,.0f} ₽\n\n"
        f"<b>По видам топлива:</b>\n"
    )

    for s in sales_24h:
        text += f"• {s['fuel_type']}: {int(s['total_liters']):,} л / {s['total_revenue']:,.0f} ₽\n"

    if not sales_24h:
        text += "<i>Нет данных</i>\n"

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 К АЗС", callback_data="my_station")]
    ])
    await call.message.edit_text(text, reply_markup=kb)
    await call.answer()

@station_router.callback_query(F.data.startswith("upgrade_station:"))
async def cb_upgrade_station(call: CallbackQuery):
    station_id = int(call.data.split(":")[1])
    text = (
        f"🔧 <b>Улучшения АЗС #{station_id}</b>\n\n"
        f"🚗 Мойка — 500K ₽\n"
        f"🏪 Магазин — 300K ₽\n"
        f"🔧 Расширить резервуары — 50K ₽ (+20K л)\n"
        f"💡 LED-вывеска — 200K ₽\n\n"
        f"<i>В демо-режиме покупка через премиум-магазин.</i>"
    )
    await call.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 К АЗС", callback_data="my_station")]
    ]))
    await call.answer()

# ═══════════════════════════════════════════════════════════════
# HANDLERS — TOP10
# ═══════════════════════════════════════════════════════════════
top_router = Router()

@top_router.callback_query(F.data == "top10")
async def show_top10(call: CallbackQuery):
    db = await get_db()

    async with db.execute("""
        SELECT s.id, s.name, s.reputation, s.owner_id,
               u.balance as owner_balance, u.full_name as owner_name
        FROM stations s
        JOIN users u ON u.id = s.owner_id
    """) as cursor:
        stations = await cursor.fetchall()

    station_list = []
    for st in stations:
        async with db.execute(
            "SELECT COALESCE(SUM(volume_current), 0) FROM tanks WHERE station_id=?",
            (st['id'],)
        ) as cur:
            total_fuel = (await cur.fetchone())[0]

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

    station_list.sort(key=lambda x: x['rating'], reverse=True)
    top10 = station_list[:10]

    text = "🏆 <b>ТОП-10 АЗС</b>\n"
    text += "<i>Рейтинг по капиталу, репутации и запасам</i>\n\n"

    for i, row in enumerate(top10, 1):
        medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
        text += (
            f"{medal} <b>{row['name']}</b>\n"
            f"   👤 {row['owner_name']}\n"
            f"   💰 {row['owner_balance']:,.0f} ₽ | ⭐ {row['reputation']}/100 | ⛽ {row['total_fuel']:,} л\n\n"
        )

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
                f"━ ━ ━ ━ ━ ━ ━ ━ ━\n"
                f"📍 <b>Ваша позиция: #{position}</b>\n"
                f"⛽ {user_station['name']}\n"
                f"💰 {user_station['balance']:,.0f} ₽ | ⭐ {user_station['reputation']}/100 | ⛽ {int(user_station['total_fuel']):,} л\n"
            )

    await call.message.edit_text(text, reply_markup=back_kb())
    await call.answer()

# ═══════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════
async def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    if not cfg.BOT_TOKEN:
        raise ValueError("BOT_TOKEN не задан!")

    await init_db()

    bot = Bot(token=cfg.BOT_TOKEN, parse_mode=ParseMode.HTML)
    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)

    dp.include_routers(start_router, station_router, top_router)

    await start_scheduler(bot)

    logging.info("Бот ЗАПРАВКА v2 запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
