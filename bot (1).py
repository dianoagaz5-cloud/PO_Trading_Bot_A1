"""
Bot Telegram — Interface de contrôle du trading automatique.

Commandes :
  /start  → Menu principal avec boutons
  /status → Statut rapide

Boutons inline :
  🟢 Start Trades / 🔴 Stop Trades
  ⚙️ Config  →  changer montant, mode demo/real, timeframe min/max
  📊 Logs    →  10 derniers trades
  📈 Status  →  connexion + stats
  📸 Screenshot → debug
"""
import logging
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup, Message
)
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, ContextTypes, filters
)
from config import settings
from state import state
from trade_logger import trade_logger

logger = logging.getLogger(__name__)


def _is_authorized(update: Update) -> bool:
    """Sécurité : seul ton chat ID peut commander le bot."""
    chat_id = (
        update.effective_chat.id if update.effective_chat
        else update.callback_query.message.chat.id
    )
    return chat_id == settings.TELEGRAM_CHAT_ID


# ── Claviers ─────────────────────────────────────────────────────────────────

def kb_main() -> InlineKeyboardMarkup:
    trade_btn = (
        InlineKeyboardButton("🔴 Stop Trades", callback_data="stop_trades")
        if state.is_trading else
        InlineKeyboardButton("🟢 Start Trades", callback_data="start_trades")
    )
    return InlineKeyboardMarkup([
        [trade_btn],
        [
            InlineKeyboardButton("⚙️ Config",      callback_data="config"),
            InlineKeyboardButton("📊 Logs",         callback_data="logs"),
        ],
        [
            InlineKeyboardButton("📈 Status",       callback_data="status"),
            InlineKeyboardButton("📸 Screenshot",   callback_data="screenshot"),
        ],
    ])


def kb_config() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(
            f"{state.mode_emoji} Mode: {state.trade_mode.upper()} → Changer",
            callback_data="toggle_mode"
        )],
        [
            InlineKeyboardButton("💰 Montant −1$",  callback_data="amount_minus"),
            InlineKeyboardButton(f"  ${state.trade_amount}  ", callback_data="noop"),
            InlineKeyboardButton("💰 Montant +1$",  callback_data="amount_plus"),
        ],
        [
            InlineKeyboardButton("💰 Montant −0.1$", callback_data="amount_minus_small"),
            InlineKeyboardButton("💰 Montant +0.1$", callback_data="amount_plus_small"),
        ],
        [
            InlineKeyboardButton(f"⏱ Min TF: {state.min_timeframe}min ▲▼", callback_data="tf_min"),
            InlineKeyboardButton(f"⏱ Max TF: {state.max_timeframe}min ▲▼", callback_data="tf_max"),
        ],
        [InlineKeyboardButton("◀️ Menu principal", callback_data="back_main")],
    ])


def kb_tf(which: str, current: int) -> InlineKeyboardMarkup:
    """Clavier pour choisir timeframe min ou max."""
    options = [1, 3, 5, 10, 15, 30, 60]
    buttons = [
        InlineKeyboardButton(
            f"{'✅' if v == current else ''}{v}min",
            callback_data=f"set_tf_{which}_{v}"
        )
        for v in options
    ]
    rows = [buttons[i:i+4] for i in range(0, len(buttons), 4)]
    rows.append([InlineKeyboardButton("◀️ Config", callback_data="config")])
    return InlineKeyboardMarkup(rows)


# ── Textes ────────────────────────────────────────────────────────────────────

def text_main() -> str:
    po_status = "✅ Connecté" if state.po_connected else "❌ Déconnecté"
    return (
        "🤖 *Bot Trading Pocket Option*\n\n"
        f"Pocket Option : {po_status}\n"
        f"Trading : {state.trading_emoji} {'Actif' if state.is_trading else 'Arrêté'}\n"
        f"Mode : `{state.trade_mode.upper()}`\n"
        f"Montant/trade : `${state.trade_amount}`\n"
        f"Timeframe : `{state.min_timeframe}–{state.max_timeframe} min`"
    )


def text_status() -> str:
    stats = trade_logger.get_stats()
    po_status = "✅ Connecté" if state.po_connected else "❌ Déconnecté"
    return (
        "📈 *Statut complet*\n\n"
        f"🔗 Pocket Option : {po_status}\n"
        f"⚡ Trading : {state.trading_emoji} {'Actif' if state.is_trading else 'Arrêté'}\n"
        f"🎯 Mode : `{state.trade_mode.upper()}`\n"
        f"💰 Montant : `${state.trade_amount}`\n"
        f"⏱ Timeframe : `{state.min_timeframe}–{state.max_timeframe} min`\n\n"
        "📊 *Statistiques*\n"
        f"Total : {stats['total']} trades\n"
        f"✅ Wins : {stats['wins']}   ❌ Losses : {stats['losses']}\n"
        f"⏳ En attente : {stats['pending']}\n"
        f"🏆 Win rate : {stats['winrate']}%"
    )


# ── Bot class ─────────────────────────────────────────────────────────────────

class TradingBot:

    def __init__(self, trader=None):
        self.trader = trader
        self.app = Application.builder().token(settings.TELEGRAM_BOT_TOKEN).build()
        self._setup_handlers()

    def _setup_handlers(self):
        self.app.add_handler(CommandHandler("start",  self._cmd_start))
        self.app.add_handler(CommandHandler("status", self._cmd_status))
        self.app.add_handler(CallbackQueryHandler(self._handle_callback))

    # ── Commands ──────────────────────────────────────────────────────────────

    async def _cmd_start(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not _is_authorized(update): return
        await update.message.reply_text(
            text_main(), parse_mode="Markdown", reply_markup=kb_main()
        )

    async def _cmd_status(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not _is_authorized(update): return
        await update.message.reply_text(
            text_status(), parse_mode="Markdown", reply_markup=kb_main()
        )

    # ── Callbacks ─────────────────────────────────────────────────────────────

    async def _handle_callback(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        if query.message.chat.id != settings.TELEGRAM_CHAT_ID:
            return
        await query.answer()
        data = query.data

        # ── Navigation ────────────────────────────────────────────────────────
        if data == "back_main":
            await query.edit_message_text(
                text_main(), parse_mode="Markdown", reply_markup=kb_main()
            )

        elif data == "noop":
            pass  # bouton décoratif (affichage montant)

        # ── Trade control ─────────────────────────────────────────────────────
        elif data == "start_trades":
            if not state.po_connected:
                await query.answer("⚠️ Pocket Option non connecté!", show_alert=True)
                return
            state.is_trading = True
            await query.edit_message_text(
                "✅ *Trading démarré!*\n\nEn attente de signaux...\n\n"
                f"Mode : `{state.trade_mode.upper()}` | Montant : `${state.trade_amount}`",
                parse_mode="Markdown", reply_markup=kb_main()
            )

        elif data == "stop_trades":
            state.is_trading = False
            await query.edit_message_text(
                "⏹ *Trading arrêté*\n\nAucun nouveau trade ne sera exécuté.",
                parse_mode="Markdown", reply_markup=kb_main()
            )

        # ── Config ────────────────────────────────────────────────────────────
        elif data == "config":
            await query.edit_message_text(
                "⚙️ *Configuration*\n\nAjuste tes paramètres de trading :",
                parse_mode="Markdown", reply_markup=kb_config()
            )

        elif data == "toggle_mode":
            state.toggle_mode()
            if self.trader:
                await self.trader.switch_mode(state.trade_mode)
            await query.edit_message_text(
                f"✅ Mode changé → *{state.trade_mode.upper()}*",
                parse_mode="Markdown", reply_markup=kb_config()
            )

        elif data == "amount_plus":
            state.set_amount(state.trade_amount + 1)
            await query.edit_message_reply_markup(reply_markup=kb_config())

        elif data == "amount_minus":
            state.set_amount(max(0.1, state.trade_amount - 1))
            await query.edit_message_reply_markup(reply_markup=kb_config())

        elif data == "amount_plus_small":
            state.set_amount(state.trade_amount + 0.1)
            await query.edit_message_reply_markup(reply_markup=kb_config())

        elif data == "amount_minus_small":
            state.set_amount(max(0.1, state.trade_amount - 0.1))
            await query.edit_message_reply_markup(reply_markup=kb_config())

        elif data == "tf_min":
            await query.edit_message_text(
                "⏱ Choisis le *timeframe minimum* à exécuter :",
                parse_mode="Markdown",
                reply_markup=kb_tf("min", state.min_timeframe)
            )

        elif data == "tf_max":
            await query.edit_message_text(
                "⏱ Choisis le *timeframe maximum* à exécuter :",
                parse_mode="Markdown",
                reply_markup=kb_tf("max", state.max_timeframe)
            )

        elif data.startswith("set_tf_"):
            # set_tf_min_5  ou  set_tf_max_60
            parts = data.split("_")
            which, value = parts[2], int(parts[3])
            if which == "min":
                state.min_timeframe = value
            else:
                state.max_timeframe = value
            await query.edit_message_text(
                "⚙️ *Configuration*", parse_mode="Markdown", reply_markup=kb_config()
            )

        # ── Logs ──────────────────────────────────────────────────────────────
        elif data == "logs":
            trades = trade_logger.get_recent_trades(10)
            if not trades:
                txt = "📊 Aucun trade enregistré pour l'instant."
            else:
                lines = ["📊 *10 derniers trades :*\n"]
                for t in trades:
                    emoji = {"WIN": "✅", "LOSS": "❌", "PENDING": "⏳", "ERROR": "💥"}.get(t.result, "❓")
                    arrow = "⬆️" if t.trade_type == "BUY" else "⬇️"
                    lines.append(f"{emoji} `{t.timestamp}` {arrow} {t.timeframe}min — ${t.amount} [{t.mode.upper()}]")
                txt = "\n".join(lines)
            await query.edit_message_text(txt, parse_mode="Markdown", reply_markup=kb_main())

        # ── Status ────────────────────────────────────────────────────────────
        elif data == "status":
            await query.edit_message_text(
                text_status(), parse_mode="Markdown", reply_markup=kb_main()
            )

        # ── Screenshot ────────────────────────────────────────────────────────
        elif data == "screenshot":
            if self.trader:
                try:
                    img = await self.trader.get_screenshot()
                    await query.message.reply_photo(photo=img, caption="📸 État actuel de Pocket Option")
                except Exception as e:
                    await query.answer(f"Erreur screenshot: {e}", show_alert=True)
            else:
                await query.answer("Trader non disponible", show_alert=True)

    # ── Signal processing ─────────────────────────────────────────────────────

    async def process_signal(self, signal) -> None:
        """Reçoit un signal et exécute le trade si le trading est actif."""
        ok, reason = state.can_trade(signal.timeframe)

        if not ok:
            logger.info(f"Signal ignoré: {reason} ({signal.type} {signal.timeframe}min)")
            return

        # Vérification session PO
        if self.trader:
            await self.trader.reconnect_if_needed()

        # Exécution du trade
        result = await self.trader.place_trade(
            trade_type=signal.type,
            timeframe=signal.timeframe,
            symbol=signal.symbol
        )

        # Notification Telegram
        await self.notify(self._trade_notification(result))

    def _trade_notification(self, result: dict) -> str:
        if not result["success"]:
            return f"❌ *Trade échoué*\n\n`{result.get('error', 'Erreur inconnue')}`"

        direction = "⬆️ CALL (BUY)" if result["type"] == "BUY" else "⬇️ PUT (SELL)"
        return (
            f"🎯 *Trade exécuté!*\n\n"
            f"Direction : {direction}\n"
            f"Durée : `{result['timeframe']} min`\n"
            f"Montant : `${result['amount']}`\n"
            f"Actif : `{result['symbol']}`\n"
            f"Mode : `{result['mode'].upper()}`\n"
            f"ID : `#{result.get('trade_id', '?')}`"
        )

    # ── Notifications ─────────────────────────────────────────────────────────

    async def notify(self, text: str):
        """Envoie un message dans ton chat Telegram."""
        try:
            await self.app.bot.send_message(
                chat_id=settings.TELEGRAM_CHAT_ID,
                text=text,
                parse_mode="Markdown"
            )
        except Exception as e:
            logger.error(f"Telegram notify error: {e}")

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def run(self):
        await self.app.initialize()
        await self.app.start()
        await self.app.updater.start_polling(drop_pending_updates=True)
        logger.info("Telegram bot started (polling)")

    async def stop(self):
        await self.app.updater.stop()
        await self.app.stop()
        await self.app.shutdown()
