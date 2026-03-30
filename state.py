"""
État mutable du bot en temps réel.
Séparé de config.py (valeurs .env) pour permettre les changements live depuis Telegram.
"""
from config import settings


class TradingState:
    def __init__(self):
        # Trade control
        self.is_trading: bool = False

        # Live-configurable settings (initialisés depuis .env)
        self.trade_mode: str = settings.TRADE_MODE      # "demo" | "real"
        self.trade_amount: float = settings.TRADE_AMOUNT
        self.min_timeframe: int = settings.MIN_TIMEFRAME
        self.max_timeframe: int = settings.MAX_TIMEFRAME

        # Internal flags
        self.awaiting_amount_input: bool = False        # en attente de saisie montant
        self.po_connected: bool = False

    def toggle_mode(self):
        self.trade_mode = "real" if self.trade_mode == "demo" else "demo"

    def set_amount(self, amount: float) -> bool:
        if amount < 0.1:
            return False
        self.trade_amount = round(amount, 2)
        return True

    def can_trade(self, timeframe: int) -> tuple[bool, str]:
        if not self.is_trading:
            return False, "Trading arrêté"
        if not self.po_connected:
            return False, "Pocket Option non connecté"
        if timeframe < self.min_timeframe:
            return False, f"Timeframe {timeframe}min < minimum ({self.min_timeframe}min)"
        if timeframe > self.max_timeframe:
            return False, f"Timeframe {timeframe}min > maximum ({self.max_timeframe}min)"
        return True, "OK"

    @property
    def mode_emoji(self):
        return "🔵" if self.trade_mode == "demo" else "🔴"

    @property
    def trading_emoji(self):
        return "✅" if self.is_trading else "⏹"


# Instance globale partagée entre tous les modules
state = TradingState()
