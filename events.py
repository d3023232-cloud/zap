import random
from datetime import datetime, timedelta
from database import get_pool

async def generate_inspection(station_id: int) -> bool:
    pool = await get_pool()
    tanks = await pool.fetch(
        "SELECT quality_score, fuel_type FROM tanks WHERE station_id = $1",
        station_id
    )

    risk = 0.05
    for t in tanks:
        if t['quality_score'] < 70:
            risk += 0.08
        gray = await pool.fetchval("""
            SELECT COUNT(*) FROM orders o
            JOIN suppliers s ON o.supplier_id = s.id
            WHERE o.station_id = $1 AND s.legal_risk > 30
            AND o.created_at > NOW() - INTERVAL '7 days'
        """, station_id)
        if gray and gray > 0:
            risk += 0.12

    if random.random() < min(risk, 0.45):
        types = ['rosstandart', 'tax', 'fire', 'ecology']
        weights = [0.5, 0.2, 0.2, 0.1]
        insp_type = random.choices(types, weights)[0]
        severity = random.randint(1, 4)
        fine = severity * random.choice([5000, 10000, 15000, 25000])

        await pool.execute("""
            INSERT INTO inspections(station_id, inspector_type, severity, deadline, fine_amount)
            VALUES($1, $2, $3, $4, $5)
        """, station_id, insp_type, severity, datetime.now()+timedelta(hours=24), fine)
        return True
    return False

async def apply_daily_lease():
    pool = await get_pool()
    stations = await pool.fetch("SELECT id, owner_id, land_lease_cost FROM stations")
    for st in stations:
        await pool.execute(
            "UPDATE users SET balance = balance - $1 WHERE id = $2",
            st['land_lease_cost'], st['owner_id']
        )
