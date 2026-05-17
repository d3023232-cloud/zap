import aiosqlite
import os
from config import cfg

DB_PATH = cfg.DB_PATH

async def get_db():
    """Возвращает соединение с SQLite."""
    db = await aiosqlite.connect(DB_PATH)
    await db.execute("PRAGMA foreign_keys = ON")
    db.row_factory = aiosqlite.Row
    return db

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        db.row_factory = aiosqlite.Row

        # Пользователи
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
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                last_active TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Администраторы
        await db.execute("""
            CREATE TABLE IF NOT EXISTS admins (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER UNIQUE NOT NULL,
                role TEXT DEFAULT 'admin',
                added_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # АЗС (уникальное название)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS stations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                owner_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                name TEXT UNIQUE NOT NULL,
                location_type TEXT CHECK (location_type IN ('highway', 'city', 'suburb')),
                land_lease_cost REAL DEFAULT 15000.00,
                reputation INTEGER DEFAULT 50,
                cleanliness INTEGER DEFAULT 40 CHECK (cleanliness BETWEEN 0 AND 100),
                security_level INTEGER DEFAULT 1,
                has_wash INTEGER DEFAULT 0,
                has_shop INTEGER DEFAULT 0,
                shop_level INTEGER DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Резервуары
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

        # Типы топлива
        await db.execute("""
            CREATE TABLE IF NOT EXISTS fuel_types (
                code TEXT PRIMARY KEY,
                name TEXT,
                base_wholesale_price REAL,
                seasonality_factor REAL DEFAULT 1.00,
                demand_profile TEXT
            )
        """)

        # Продажи
        await db.execute("""
            CREATE TABLE IF NOT EXISTS sales (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                station_id INTEGER NOT NULL REFERENCES stations(id) ON DELETE CASCADE,
                fuel_type TEXT,
                liters REAL,
                price_per_liter REAL,
                total REAL,
                payment_type TEXT DEFAULT 'card',
                timestamp TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Персонал
        await db.execute("""
            CREATE TABLE IF NOT EXISTS employees (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                station_id INTEGER NOT NULL REFERENCES stations(id) ON DELETE CASCADE,
                role TEXT CHECK (role IN ('cashier', 'filler', 'guard', 'accountant', 'manager', 'barista')),
                name TEXT,
                skill INTEGER DEFAULT 50 CHECK (skill BETWEEN 0 AND 100),
                morale INTEGER DEFAULT 70 CHECK (morale BETWEEN 0 AND 100),
                salary REAL DEFAULT 35000.00,
                hired_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Поставщики
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

        # Заказы
        await db.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                station_id INTEGER NOT NULL REFERENCES stations(id) ON DELETE CASCADE,
                supplier_id INTEGER REFERENCES suppliers(id),
                fuel_type TEXT,
                liters INTEGER,
                cost REAL,
                status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'transit', 'delivered', 'rejected')),
                delivery_eta TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Проверки
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

        # Апгрейды
        await db.execute("""
            CREATE TABLE IF NOT EXISTS upgrades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                station_id INTEGER NOT NULL REFERENCES stations(id) ON DELETE CASCADE,
                type TEXT CHECK (type IN ('led_sign', 'car_wash', 'coffee_shop', 'security_cam', 'fast_fuel', 'vip_lounge')),
                level INTEGER DEFAULT 1,
                effect_multiplier REAL DEFAULT 1.00
            )
        """)

        # Конкуренты
        await db.execute("""
            CREATE TABLE IF NOT EXISTS competitors (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                location_type TEXT,
                distance_km INTEGER,
                price_ai92 REAL,
                price_ai95 REAL,
                price_dt REAL,
                has_wash INTEGER DEFAULT 0,
                has_shop INTEGER DEFAULT 0,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Индексы
        await db.execute("CREATE INDEX IF NOT EXISTS idx_sales_station_time ON sales(station_id, timestamp)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_orders_station ON orders(station_id, status)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_tanks_station ON tanks(station_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_users_tg ON users(telegram_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_stations_owner ON stations(owner_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_stations_name ON stations(name)")

        # Заполняем fuel_types если пусто
        cursor = await db.execute("SELECT COUNT(*) FROM fuel_types")
        count = (await cursor.fetchone())[0]
        if count == 0:
            fuel_data = [
                ('AI92', 'АИ-92', 42.50, 1.00, '{"0":0.3,"8":1.5,"12":1.2,"18":1.8,"23":0.4}'),
                ('AI95', 'АИ-95', 48.00, 1.00, '{"0":0.3,"8":1.5,"12":1.2,"18":1.8,"23":0.4}'),
                ('AI98', 'АИ-98', 55.00, 1.00, '{"0":0.2,"8":1.3,"12":1.1,"18":1.5,"23":0.3}'),
                ('AI100', 'АИ-100', 62.00, 1.05, '{"0":0.1,"8":1.2,"12":1.0,"18":1.3,"23":0.2}'),
                ('DT', 'Дизель', 46.00, 1.00, '{"0":0.5,"8":1.8,"12":1.5,"18":1.2,"23":0.6}'),
                ('DT_winter', 'ДТ Зимний', 49.00, 1.20, '{"0":0.6,"8":1.9,"12":1.6,"18":1.3,"23":0.7}'),
                ('GAS', 'Газ', 28.00, 1.00, '{"0":0.3,"8":1.4,"12":1.2,"18":1.6,"23":0.4}')
            ]
            await db.executemany(
                "INSERT INTO fuel_types(code, name, base_wholesale_price, seasonality_factor, demand_profile) VALUES (?,?,?,?,?)",
                fuel_data
            )

        # Заполняем suppliers если пусто
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

        # Добавляем админа из env если указан
        if cfg.ADMIN_ID and cfg.ADMIN_ID != 0:
            await db.execute("INSERT OR IGNORE INTO admins(telegram_id) VALUES(?)", (cfg.ADMIN_ID,))

        await db.commit()
