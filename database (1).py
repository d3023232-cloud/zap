import asyncpg
from config import cfg

_pool = None

async def get_pool():
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(cfg.DB_URL, min_size=5, max_size=20)
    return _pool

async def init_db():
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                telegram_id BIGINT UNIQUE NOT NULL,
                username TEXT,
                full_name TEXT,
                balance DECIMAL(12,2) DEFAULT 50000.00,
                reputation INT DEFAULT 50 CHECK (reputation BETWEEN 0 AND 100),
                level INT DEFAULT 1,
                scenario TEXT DEFAULT 'inheritance',
                vip_until TIMESTAMP,
                created_at TIMESTAMP DEFAULT NOW(),
                last_active TIMESTAMP DEFAULT NOW()
            )
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS admins (
                id SERIAL PRIMARY KEY,
                telegram_id BIGINT UNIQUE NOT NULL,
                role TEXT DEFAULT 'admin',
                added_at TIMESTAMP DEFAULT NOW()
            )
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS stations (
                id SERIAL PRIMARY KEY,
                owner_id INT REFERENCES users(id) ON DELETE CASCADE,
                name TEXT UNIQUE NOT NULL,
                location_type TEXT CHECK (location_type IN ('highway', 'city', 'suburb')),
                land_lease_cost DECIMAL(10,2) DEFAULT 15000.00,
                reputation INT DEFAULT 50,
                cleanliness INT DEFAULT 40 CHECK (cleanliness BETWEEN 0 AND 100),
                security_level INT DEFAULT 1,
                has_wash BOOLEAN DEFAULT FALSE,
                has_shop BOOLEAN DEFAULT FALSE,
                shop_level INT DEFAULT 0,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS tanks (
                id SERIAL PRIMARY KEY,
                station_id INT REFERENCES stations(id) ON DELETE CASCADE,
                fuel_type TEXT CHECK (fuel_type IN ('AI92', 'AI95', 'AI98', 'AI100', 'DT', 'DT_winter', 'GAS')),
                volume_total INT DEFAULT 20000,
                volume_current INT DEFAULT 5000,
                temperature DECIMAL(4,1) DEFAULT 20.0,
                quality_score INT DEFAULT 95 CHECK (quality_score BETWEEN 0 AND 100),
                last_refill TIMESTAMP DEFAULT NOW()
            )
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS fuel_types (
                code TEXT PRIMARY KEY,
                name TEXT,
                base_wholesale_price DECIMAL(6,2),
                seasonality_factor DECIMAL(3,2) DEFAULT 1.00,
                demand_profile JSONB
            )
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS sales (
                id SERIAL PRIMARY KEY,
                station_id INT REFERENCES stations(id) ON DELETE CASCADE,
                fuel_type TEXT,
                liters DECIMAL(8,2),
                price_per_liter DECIMAL(6,2),
                total DECIMAL(10,2),
                payment_type TEXT DEFAULT 'card',
                timestamp TIMESTAMP DEFAULT NOW()
            )
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS employees (
                id SERIAL PRIMARY KEY,
                station_id INT REFERENCES stations(id) ON DELETE CASCADE,
                role TEXT CHECK (role IN ('cashier', 'filler', 'guard', 'accountant', 'manager', 'barista')),
                name TEXT,
                skill INT DEFAULT 50 CHECK (skill BETWEEN 0 AND 100),
                morale INT DEFAULT 70 CHECK (morale BETWEEN 0 AND 100),
                salary DECIMAL(8,2) DEFAULT 35000.00,
                hired_at TIMESTAMP DEFAULT NOW()
            )
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS suppliers (
                id SERIAL PRIMARY KEY,
                name TEXT,
                fuel_types TEXT[],
                reliability INT DEFAULT 80,
                delivery_hours INT DEFAULT 6,
                price_discount DECIMAL(4,2) DEFAULT 0.00,
                legal_risk INT DEFAULT 10,
                min_order_liters INT DEFAULT 5000
            )
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id SERIAL PRIMARY KEY,
                station_id INT REFERENCES stations(id) ON DELETE CASCADE,
                supplier_id INT REFERENCES suppliers(id),
                fuel_type TEXT,
                liters INT,
                cost DECIMAL(10,2),
                status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'transit', 'delivered', 'rejected')),
                delivery_eta TIMESTAMP,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS inspections (
                id SERIAL PRIMARY KEY,
                station_id INT REFERENCES stations(id) ON DELETE CASCADE,
                inspector_type TEXT CHECK (inspector_type IN ('rosstandart', 'tax', 'fire', 'ecology')),
                severity INT DEFAULT 1,
                deadline TIMESTAMP,
                fine_amount DECIMAL(10,2) DEFAULT 0,
                status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'passed', 'failed')),
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS upgrades (
                id SERIAL PRIMARY KEY,
                station_id INT REFERENCES stations(id) ON DELETE CASCADE,
                type TEXT CHECK (type IN ('led_sign', 'car_wash', 'coffee_shop', 'security_cam', 'fast_fuel', 'vip_lounge')),
                level INT DEFAULT 1,
                effect_multiplier DECIMAL(3,2) DEFAULT 1.00
            )
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS competitors (
                id SERIAL PRIMARY KEY,
                location_type TEXT,
                distance_km INT,
                price_ai92 DECIMAL(6,2),
                price_ai95 DECIMAL(6,2),
                price_dt DECIMAL(6,2),
                has_wash BOOLEAN DEFAULT FALSE,
                has_shop BOOLEAN DEFAULT FALSE,
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """)

        # Индексы
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_sales_station_time ON sales(station_id, timestamp)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_orders_station ON orders(station_id, status)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_tanks_station ON tanks(station_id)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_users_tg ON users(telegram_id)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_stations_owner ON stations(owner_id)")

        # Заполняем fuel_types если пусто
        count = await conn.fetchval("SELECT COUNT(*) FROM fuel_types")
        if count == 0:
            await conn.execute("""
                INSERT INTO fuel_types(code, name, base_wholesale_price, seasonality_factor, demand_profile) VALUES
                ('AI92', 'АИ-92', 42.50, 1.00, '{"0":0.3,"8":1.5,"12":1.2,"18":1.8,"23":0.4}'),
                ('AI95', 'АИ-95', 48.00, 1.00, '{"0":0.3,"8":1.5,"12":1.2,"18":1.8,"23":0.4}'),
                ('AI98', 'АИ-98', 55.00, 1.00, '{"0":0.2,"8":1.3,"12":1.1,"18":1.5,"23":0.3}'),
                ('AI100', 'АИ-100', 62.00, 1.05, '{"0":0.1,"8":1.2,"12":1.0,"18":1.3,"23":0.2}'),
                ('DT', 'Дизель', 46.00, 1.00, '{"0":0.5,"8":1.8,"12":1.5,"18":1.2,"23":0.6}'),
                ('DT_winter', 'ДТ Зимний', 49.00, 1.20, '{"0":0.6,"8":1.9,"12":1.6,"18":1.3,"23":0.7}'),
                ('GAS', 'Газ', 28.00, 1.00, '{"0":0.3,"8":1.4,"12":1.2,"18":1.6,"23":0.4}')
            """)

        # Заполняем suppliers если пусто
        count = await conn.fetchval("SELECT COUNT(*) FROM suppliers")
        if count == 0:
            await conn.execute("""
                INSERT INTO suppliers(name, fuel_types, reliability, delivery_hours, price_discount, legal_risk, min_order_liters) VALUES
                ('Роснефть', ARRAY['AI92','AI95','DT'], 95, 4, 0.00, 5, 10000),
                ('Лукойл', ARRAY['AI92','AI95','AI98','DT'], 90, 5, 0.50, 5, 8000),
                ('Газпромнефть', ARRAY['AI92','AI95','DT','GAS'], 92, 4, 0.30, 5, 10000),
                ('Татнефть', ARRAY['AI92','AI95','DT'], 85, 6, 1.50, 10, 5000),
                ('Башнефть', ARRAY['AI92','AI95','DT','DT_winter'], 88, 5, 1.00, 8, 6000),
                ('Серый опт (риск)', ARRAY['AI92','AI95','DT'], 60, 3, 5.00, 65, 3000)
            """)

        # Добавляем админа из конфига если указан (хостинг передаёт через env)
        if cfg.ADMIN_ID and cfg.ADMIN_ID != 0:
            await conn.execute("""
                INSERT INTO admins(telegram_id) VALUES($1)
                ON CONFLICT(telegram_id) DO NOTHING
            """, cfg.ADMIN_ID)

        print("База данных инициализирована")
