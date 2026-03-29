import sqlite3
import logging
from datetime import datetime
from dataclasses import dataclass
from typing import Optional, List

logger = logging.getLogger(__name__)
DB_PATH = "trades.db"


@dataclass
class Trade:
    id: Optional[int]
    timestamp: str
    trade_type: str       # BUY | SELL
    timeframe: int        # durée en minutes
    amount: float
    mode: str             # demo | real
    symbol: str
    result: str           # PENDING | WIN | LOSS | ERROR


class TradeLogger:

    def __init__(self):
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS trades (
                    id        INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT    NOT NULL,
                    trade_type TEXT   NOT NULL,
                    timeframe INTEGER NOT NULL,
                    amount    REAL    NOT NULL,
                    mode      TEXT    NOT NULL,
                    symbol    TEXT    NOT NULL DEFAULT 'EURUSD',
                    result    TEXT    NOT NULL DEFAULT 'PENDING'
                )
            """)
        logger.info("Trade database initialized")

    def log_trade(self, trade_type: str, timeframe: int, amount: float,
                  mode: str, symbol: str = "EURUSD") -> int:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.execute(
                """INSERT INTO trades (timestamp, trade_type, timeframe, amount, mode, symbol)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                 trade_type, timeframe, amount, mode, symbol)
            )
            trade_id = cursor.lastrowid
        logger.info(f"Trade #{trade_id} logged: {trade_type} {timeframe}min {mode.upper()}")
        return trade_id

    def update_result(self, trade_id: int, result: str):
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute(
                "UPDATE trades SET result = ? WHERE id = ?",
                (result, trade_id)
            )

    def get_recent_trades(self, limit: int = 10) -> List[Trade]:
        with sqlite3.connect(DB_PATH) as conn:
            rows = conn.execute(
                """SELECT id, timestamp, trade_type, timeframe, amount, mode, symbol, result
                   FROM trades ORDER BY id DESC LIMIT ?""",
                (limit,)
            ).fetchall()
        return [Trade(*r) for r in rows]

    def get_stats(self) -> dict:
        with sqlite3.connect(DB_PATH) as conn:
            total   = conn.execute("SELECT COUNT(*) FROM trades").fetchone()[0]
            wins    = conn.execute("SELECT COUNT(*) FROM trades WHERE result='WIN'").fetchone()[0]
            losses  = conn.execute("SELECT COUNT(*) FROM trades WHERE result='LOSS'").fetchone()[0]
            pending = conn.execute("SELECT COUNT(*) FROM trades WHERE result='PENDING'").fetchone()[0]
        winrate = round(wins / (wins + losses) * 100, 1) if (wins + losses) > 0 else 0
        return {
            "total": total, "wins": wins, "losses": losses,
            "pending": pending, "winrate": winrate
        }


# Instance globale
trade_logger = TradeLogger()
