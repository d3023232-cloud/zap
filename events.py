import random
from datetime import datetime, timedelta
from database import get_db

async def generate_inspection(station_id: int) -> bool:
    db = await get_db()

    async with db.execute(
        "SELECT quality_score, fuel_type FROM tanks WHERE station_id=?",
        (station_id,)
    ) as cursor:
        tanks = await cursor.fetchall()

    risk = 0.05
    for t in tanks:
        if t['quality_score'] < 70:
            risk += 0.08
        async with db.execute("""
            SELECT COUNT(*) FROM orders o
            JOIN suppliers s ON o.supplier_id = s.id
            WHERE o.station_id=? AND s.legal_risk > 30
            AND o.created_at > datetime('now', '-7 days')
        """, (station_id,)) as cursor:
            gray = (await cursor.fetchone())[0]
        if gray and gray > 0:
            risk += 0.12

    if random.random() < min(risk, 0.45):
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

    await db.commit()
    await db.close()
