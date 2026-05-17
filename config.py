import os
from dataclasses import dataclass

@dataclass(frozen=True)
class Config:
    BOT_TOKEN: str = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
    DB_URL: str = os.getenv("DB_URL", "postgresql://user:pass@localhost/azs_bot")
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379")
    WEATHER_API_KEY: str = os.getenv("WEATHER_API_KEY", "")
    ADMIN_ID: int = int(os.getenv("ADMIN_ID", "0"))

    # Игровые константы
    START_CAPITAL: float = 50000.0
    LEASE_DAILY: float = 15000.0
    BASE_MARGIN: float = 0.15
    INSPECTION_BASE_RISK: float = 0.05

    # Цены донатов (в рублях)
    DONATE_EXPRESS_DELIVERY: int = 49
    DONATE_AUTO_PRICING: int = 99
    DONATE_VIP_MONTH: int = 299
    DONATE_WASH: int = 199
    DONATE_COFFEE: int = 149
    DONATE_MANAGER: int = 399
    DONATE_BRANDING: int = 999

cfg = Config()
