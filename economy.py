import random
from datetime import datetime
from database import get_db

TRAFFIC_PROFILE = {
    0:0.2, 1:0.1, 2:0.1, 3:0.15, 4:0.3, 5:0.5, 6:0.8,
    7:1.2, 8:1.5, 9:1.3, 10:1.1, 11:1.0, 12:1.2, 13:1.1,
    14:1.0, 15:1.1, 16:1.3, 17:1.6, 18:1.8, 19:1.5, 20:1.2,
    21:0.9, 22:0.6, 23:0.4
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
        return 45.00
    base = row['base_wholesale_price']
    season = row['seasonality_factor']
    noise = random.uniform(0.97, 1.03)
    return round(base * season * noise, 2)

async def calculate_retail_price(station_id: int, fuel_type: str, competitor_price: float) -> float:
    wholesale = await get_wholesale_price(fuel_type)
    margin = wholesale * 0.15

    db = await get_db()
    async with db.execute("""
        SELECT u.vip_until FROM users u
        JOIN stations s ON s.owner_id = u.id
        WHERE s.id = ?
    """, (station_id,)) as cursor:
        row = await cursor.fetchone()
    await db.close()

    if row and row['vip_until']:
        vip_time = datetime.fromisoformat(row['vip_until'].replace('Z', '+00:00')) if isinstance(row['vip_until'], str) else row['vip_until']
        if vip_time > datetime.now():
            margin = wholesale * 0.25

    price = wholesale + margin
    competitive = min(price, (competitor_price or 999) * 1.02)
    competitive = max(competitive, wholesale * 1.02)
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

    base = TRAFFIC_PROFILE.get(hour, 0.5)
    weather_mod = 1.2 if weather in ("rain", "snow") else 1.0 if weather == "sunny" else 0.9
    loc_mod = 1.3 if row['location_type'] == 'highway' else 1.0 if row['location_type'] == 'city' else 0.7

    month = datetime.now().month
    season = "winter" if month in (12,1,2) else "spring" if month in (3,4,5) else "summer" if month in (6,7,8) else "autumn"
    season_mod = SEASON_MODS[season].get(fuel_type, 1.0)

    rep_mod = 1 + (row['reputation'] - 50) / 100
    clean_mod = 1 + (row['cleanliness'] - 50) / 200

    demand = int(20 * base * weather_mod * loc_mod * season_mod * rep_mod * clean_mod)
    return max(0, demand)

async def process_sales_tick(station_id: int) -> float:
    db = await get_db()
    now = datetime.now()
    hour = now.hour
    weather = "sunny"

    async with db.execute("""
        SELECT AVG(price_ai95) as p95, AVG(price_ai92) as p92, AVG(price_dt) as pdt,
               AVG(price_ai98) as p98, AVG(price_gas) as pgas
        FROM competitors
        WHERE location_type = (SELECT location_type FROM stations WHERE id=?)
    """, (station_id,)) as cursor:
        comp = await cursor.fetchone()

    async with db.execute(
        "SELECT * FROM tanks WHERE station_id = ? AND volume_current > 100",
        (station_id,)
    ) as cursor:
        tanks = await cursor.fetchall()

    total_revenue = 0.0

    for tank in tanks:
        ft = tank['fuel_type']
        if '95' in ft:
            comp_price = comp['p95'] or 52.0
        elif '92' in ft:
            comp_price = comp['p92'] or 48.0
        elif 'DT' in ft or 'dt' in ft:
            comp_price = comp['pdt'] or 50.0
        elif '98' in ft:
            comp_price = comp['p98'] or 58.0
        elif 'GAS' in ft:
            comp_price = comp['pgas'] or 30.0
        else:
            comp_price = 50.0

        price = await calculate_retail_price(station_id, ft, comp_price)
        demand = await calculate_demand(station_id, hour, weather, ft)
        avg_liters = random.uniform(25, 45)
        possible_clients = min(demand, int(tank['volume_current'] / avg_liters))

        sold_liters = possible_clients * avg_liters
        revenue = sold_liters * price

        await db.execute(
            "UPDATE tanks SET volume_current = volume_current - ? WHERE id=?",
            (sold_liters, tank['id'])
        )

        await db.execute("""
            INSERT INTO sales(station_id, fuel_type, liters, price_per_liter, total)
            VALUES(?,?,?,?,?)
        """, (station_id, ft, round(sold_liters, 2), price, round(revenue, 2)))

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

async def get_player_stations(telegram_id: int):
    db = await get_db()
    async with db.execute("""
        SELECT s.* FROM stations s
        JOIN users u ON u.id = s.owner_id
        WHERE u.telegram_id = ?
        ORDER BY s.id
    """, (telegram_id,)) as cursor:
        rows = await cursor.fetchall()
    await db.close()
    return rows
