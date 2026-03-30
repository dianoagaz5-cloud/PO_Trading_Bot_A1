"""
Serveur FastAPI — Réception des signaux de trade.

Deux sources supportées :
  1. TradingView Alert Webhook  →  POST /signal
  2. MT5 EA (Expert Advisor)    →  POST /signal  (même endpoint)

Format JSON attendu :
  {
    "type":      "BUY" | "SELL",   # obligatoire
    "timeframe": 5,                 # en minutes, obligatoire
    "symbol":    "EURUSD",          # optionnel
    "source":    "tradingview"      # optionnel, juste pour le log
  }

Sécurité optionnelle : ajoute SIGNAL_SECRET dans .env
et envoie le header X-Secret dans chaque requête.
"""
import logging
from fastapi import FastAPI, HTTPException, Header, Request
from pydantic import BaseModel, validator
from typing import Optional, Callable, Awaitable

logger = logging.getLogger(__name__)

# Callback assigné par main.py
_signal_callback: Optional[Callable] = None


def set_callback(callback: Callable):
    global _signal_callback
    _signal_callback = callback


# ── Modèles ─────────────────────────────────────────────────────────────────

class SignalPayload(BaseModel):
    type: str           # "BUY" | "SELL" | "buy" | "sell"
    timeframe: int      # durée en minutes
    symbol: str = "EURUSD"
    source: str = "manual"

    @validator("type")
    def validate_type(cls, v):
        v = v.upper()
        if v not in ("BUY", "SELL"):
            raise ValueError("type doit être BUY ou SELL")
        return v

    @validator("timeframe")
    def validate_tf(cls, v):
        if v <= 0 or v > 1440:
            raise ValueError("timeframe doit être entre 1 et 1440 minutes")
        return v


# ── App ──────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="PO Signal Receiver",
    description="Reçoit des signaux MT5 / TradingView et les transmet au bot de trading",
    version="1.0.0"
)


@app.post("/signal")
async def receive_signal(
    payload: SignalPayload,
    x_secret: Optional[str] = Header(None)
):
    from config import settings

    # Vérification du secret si configuré
    if settings.SIGNAL_SECRET and x_secret != settings.SIGNAL_SECRET:
        logger.warning(f"Signal rejeté: mauvais secret depuis source={payload.source}")
        raise HTTPException(status_code=401, detail="Secret invalide")

    logger.info(f"Signal reçu: {payload.type} {payload.timeframe}min {payload.symbol} [{payload.source}]")

    if _signal_callback is None:
        raise HTTPException(status_code=503, detail="Bot pas encore prêt")

    # On appelle le callback de manière non-bloquante
    import asyncio
    asyncio.create_task(_signal_callback(payload))

    return {
        "status": "received",
        "type": payload.type,
        "timeframe": payload.timeframe,
        "symbol": payload.symbol,
    }


@app.get("/health")
async def health():
    from state import state
    return {
        "status": "ok",
        "trading_active": state.is_trading,
        "po_connected": state.po_connected,
        "mode": state.trade_mode,
    }


@app.get("/")
async def root():
    return {"message": "PO Trading Bot API — POST /signal pour envoyer un signal"}
