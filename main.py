"""
Point d'entrée principal — Lance tous les composants en parallèle :
  1. Navigateur Playwright → connexion à Pocket Option
  2. Bot Telegram           → interface de contrôle
  3. Serveur FastAPI        → réception des signaux MT5 / TradingView
"""
import asyncio
import logging
import uvicorn
from config import settings
from trader import PocketOptionTrader
from bot import TradingBot
import signal_receiver as sr

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)-20s | %(levelname)-8s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("playwright").setLevel(logging.WARNING)
logger = logging.getLogger("main")


async def run_api_server():
    """Lance le serveur FastAPI (webhook signal receiver)."""
    config = uvicorn.Config(
        app=sr.app,
        host="0.0.0.0",
        port=settings.PORT,
        log_level="warning",
    )
    server = uvicorn.Server(config)
    logger.info(f"FastAPI server démarré → port {settings.PORT}")
    await server.serve()


async def main():
    logger.info("═══════════════════════════════════════")
    logger.info("  PO Trading Bot — Démarrage")
    logger.info("═══════════════════════════════════════")

    # ── Init ──────────────────────────────────────────────────────────────────
    trader = PocketOptionTrader()
    bot    = TradingBot(trader=trader)

    # Lie le callback de notification du trader vers Telegram
    trader.set_notify(bot.notify)

    # Lie le callback de signal vers le bot
    sr.set_callback(bot.process_signal)

    # ── Démarrage navigateur ──────────────────────────────────────────────────
    logger.info("Démarrage du navigateur Playwright...")
    await trader.start()

    # ── Démarrage Telegram bot ────────────────────────────────────────────────
    logger.info("Connexion au bot Telegram...")
    await bot.run()

    # ── Login Pocket Option ───────────────────────────────────────────────────
    logger.info("Connexion à Pocket Option...")
    login_ok = await trader.login()

    startup_msg = (
        "🤖 *Bot démarré!*\n\n"
        f"{'✅ Pocket Option connecté' if login_ok else '⚠️ Connexion PO échouée — vérifier les credentials'}\n\n"
        f"Mode : `{settings.TRADE_MODE.upper()}`\n"
        f"Montant initial : `${settings.TRADE_AMOUNT}`\n\n"
        "Tape /start pour ouvrir le menu de contrôle."
    )
    await bot.notify(startup_msg)

    # ── Boucle principale — maintien connexion PO ─────────────────────────────
    async def health_check_loop():
        """Vérifie la session PO toutes les 5 minutes."""
        while True:
            await asyncio.sleep(300)  # 5 min
            if not await trader.reconnect_if_needed():
                logger.warning("Reconnexion PO échouée lors du health check")

    # ── Lancement parallèle ───────────────────────────────────────────────────
    try:
        await asyncio.gather(
            run_api_server(),
            health_check_loop(),
        )
    except (KeyboardInterrupt, asyncio.CancelledError):
        logger.info("Arrêt demandé...")
    finally:
        await bot.notify("⏹ Bot arrêté.")
        await bot.stop()
        await trader.stop()
        logger.info("Bot arrêté proprement.")


if __name__ == "__main__":
    asyncio.run(main())
