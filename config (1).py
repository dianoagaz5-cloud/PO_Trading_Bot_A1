from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    # ── Telegram ──────────────────────────────────────────
    TELEGRAM_BOT_TOKEN: str
    TELEGRAM_CHAT_ID: int          # ton chat ID personnel

    # ── Pocket Option ─────────────────────────────────────
    PO_EMAIL: str
    PO_PASSWORD: str

    # ── Paramètres trade (valeurs par défaut) ─────────────
    TRADE_AMOUNT: float = 1.0      # montant initial par trade ($)
    TRADE_MODE: str = "demo"       # "demo" ou "real"
    MIN_TIMEFRAME: int = 1         # timeframe minimum accepté (min)
    MAX_TIMEFRAME: int = 60        # timeframe maximum accepté (min)
    MAX_CONCURRENT_TRADES: int = 1 # trades simultanés max

    # ── Serveur API ───────────────────────────────────────
    PORT: int = 8000
    SIGNAL_SECRET: Optional[str] = None   # clé secrète optionnelle pour sécuriser le webhook

    class Config:
        env_file = ".env"


settings = Settings()
