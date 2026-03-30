"""
Pocket Option Trader — Automatisation via Playwright (navigateur headless)
Pocket Option n'a pas d'API publique, on pilote le navigateur directement.

⚠️  Les sélecteurs CSS peuvent nécessiter un ajustement si PO change son interface.
    En cas d'erreur, le bot envoie un screenshot de debug dans Telegram.
"""
import asyncio
import logging
from playwright.async_api import async_playwright, Page, Browser, BrowserContext
from playwright_stealth import stealth_async
from config import settings
from state import state
from trade_logger import trade_logger

logger = logging.getLogger(__name__)

# ── Sélecteurs Pocket Option ───────────────────────────────────────────────────
# Chaque liste contient plusieurs fallbacks au cas où PO change son UI

SELECTORS = {
    # Login
    "email":     ['input[name="email"]', '#email', 'input[type="email"]'],
    "password":  ['input[name="password"]', '#password', 'input[type="password"]'],
    "login_btn": ['button[type="submit"]', '.btn-login', '.button--submit'],

    # Trade panel - montant
    "amount": [
        '.input-control__amount input',
        '.control-price input',
        'input[data-type="amount"]',
        '.deal-amount input',
        '.tradeAmount input',
    ],

    # Trade panel - durée/expiry (en minutes)
    "time_input": [
        '.input-control__value[data-target="time"] input',
        '.select-time input',
        '.expiry-input input',
        'input[data-type="time"]',
        '.deal-time input',
    ],

    # Bouton UP (BUY / CALL)
    "btn_call": [
        '.btn-call',
        '[data-action="call"]',
        '.deals-call',
        'button.call',
        '[data-direction="call"]',
        '.button--up',
    ],

    # Bouton DOWN (SELL / PUT)
    "btn_put": [
        '.btn-put',
        '[data-action="put"]',
        '.deals-put',
        'button.put',
        '[data-direction="put"]',
        '.button--down',
    ],

    # Sélecteur compte Demo / Real
    "account_switcher": [
        '.header-balance',
        '.account-type-switcher',
        '.balance-block',
    ],
}

PO_TRADE_URL = "https://po.trade/trade/"
PO_LOGIN_URL = "https://po.trade/login"


async def _find_and_fill(page: Page, selectors: list, value: str, timeout: int = 3000) -> bool:
    """Essaie chaque sélecteur jusqu'à trouver l'élément."""
    for sel in selectors:
        try:
            el = await page.wait_for_selector(sel, timeout=timeout)
            if el:
                await el.triple_click()
                await el.type(str(value), delay=50)
                return True
        except Exception:
            continue
    return False


async def _find_and_click(page: Page, selectors: list, timeout: int = 3000) -> bool:
    """Essaie chaque sélecteur jusqu'à trouver le bouton à cliquer."""
    for sel in selectors:
        try:
            el = await page.wait_for_selector(sel, timeout=timeout)
            if el:
                await el.click()
                return True
        except Exception:
            continue
    return False


class PocketOptionTrader:

    def __init__(self):
        self.playwright = None
        self.browser: Browser = None
        self.context: BrowserContext = None
        self.page: Page = None
        self._lock = asyncio.Lock()          # un seul trade à la fois
        self._notify_callback = None         # set by main to send Telegram messages

    def set_notify(self, callback):
        """Callback pour envoyer des messages Telegram depuis le trader."""
        self._notify_callback = callback

    async def _notify(self, msg: str):
        if self._notify_callback:
            await self._notify_callback(msg)

    # ── Lifecycle ────────────────────────────────────────────────────────────

    async def start(self):
        """Démarre le navigateur headless."""
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-accelerated-2d-canvas",
                "--no-first-run",
                "--no-zygote",
                "--disable-gpu",
                "--disable-blink-features=AutomationControlled",
            ]
        )
        self.context = await self.browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/121.0.0.0 Safari/537.36"
            ),
            locale="en-US",
            timezone_id="Europe/Paris",
        )
        self.page = await self.context.new_page()
        await stealth_async(self.page)       # anti-détection bot
        logger.info("Browser started (headless Chromium)")

    async def stop(self):
        """Ferme le navigateur."""
        state.po_connected = False
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()
        logger.info("Browser stopped")

    # ── Login ────────────────────────────────────────────────────────────────

    async def login(self) -> bool:
        """Se connecte au compte Pocket Option."""
        try:
            logger.info(f"Navigating to {PO_LOGIN_URL} ...")
            await self.page.goto(PO_LOGIN_URL, wait_until="domcontentloaded", timeout=30_000)
            await asyncio.sleep(2)

            # Email
            ok_email = await _find_and_fill(self.page, SELECTORS["email"], settings.PO_EMAIL, 5000)
            if not ok_email:
                raise Exception("Champ email introuvable")

            await asyncio.sleep(0.3)

            # Password
            ok_pass = await _find_and_fill(self.page, SELECTORS["password"], settings.PO_PASSWORD, 5000)
            if not ok_pass:
                raise Exception("Champ mot de passe introuvable")

            await asyncio.sleep(0.3)

            # Submit
            ok_btn = await _find_and_click(self.page, SELECTORS["login_btn"], 5000)
            if not ok_btn:
                # Fallback : touche Entrée
                await self.page.keyboard.press("Enter")

            # Attendre la redirection après login
            await self.page.wait_for_url("**/trade/**", timeout=20_000)
            await asyncio.sleep(2)

            # Switcher vers demo ou real
            await self._set_account_mode(state.trade_mode)

            state.po_connected = True
            logger.info("✅ Login Pocket Option réussi!")
            return True

        except Exception as e:
            logger.error(f"Login failed: {e}")
            await self._notify(f"⚠️ Connexion PO échouée: `{str(e)[:100]}`\nLe bot continue — trading désactivé.")
            return False

    async def _set_account_mode(self, mode: str):
        """Bascule entre compte Démo et Réel."""
        try:
            ok = await _find_and_click(self.page, SELECTORS["account_switcher"], 3000)
            if ok:
                await asyncio.sleep(1)
                keyword = "demo" if mode == "demo" else "real"
                # Cherche l'option correspondante dans le dropdown
                option = await self.page.query_selector(f'text=/{keyword}/i')
                if option:
                    await option.click()
                    await asyncio.sleep(1)
                    logger.info(f"Compte basculé vers {mode.upper()}")
        except Exception as e:
            logger.warning(f"Impossible de changer le mode compte: {e}")

    # ── Trading ──────────────────────────────────────────────────────────────

    async def place_trade(self, trade_type: str, timeframe: int,
                          symbol: str = "EURUSD") -> dict:
        """
        Place un trade sur Pocket Option.
        trade_type : "BUY" ou "SELL"
        timeframe  : durée en minutes
        """
        async with self._lock:
            return await self._execute_trade(trade_type, timeframe, symbol)

    async def _execute_trade(self, trade_type: str, timeframe: int, symbol: str) -> dict:
        try:
            # S'assurer qu'on est sur la page de trade
            if "trade" not in self.page.url:
                await self.page.goto(PO_TRADE_URL, wait_until="domcontentloaded", timeout=30_000)
                await asyncio.sleep(2)

            # 1. Montant
            amount_set = await _find_and_fill(
                self.page, SELECTORS["amount"], state.trade_amount, 5000
            )
            if not amount_set:
                logger.warning("Impossible de définir le montant — valeur par défaut conservée")

            await asyncio.sleep(0.5)

            # 2. Durée (en secondes pour PO, certaines versions en minutes)
            time_set = await _find_and_fill(
                self.page, SELECTORS["time_input"], timeframe * 60, 5000
            )
            if not time_set:
                # Essai avec minutes directement
                await _find_and_fill(self.page, SELECTORS["time_input"], timeframe, 5000)

            await asyncio.sleep(0.5)

            # 3. Log le trade avant clic (pour avoir l'ID)
            trade_id = trade_logger.log_trade(
                trade_type=trade_type,
                timeframe=timeframe,
                amount=state.trade_amount,
                mode=state.trade_mode,
                symbol=symbol
            )

            # 4. Clic UP ou DOWN
            if trade_type == "BUY":
                clicked = await _find_and_click(self.page, SELECTORS["btn_call"], 5000)
            else:
                clicked = await _find_and_click(self.page, SELECTORS["btn_put"], 5000)

            if not clicked:
                trade_logger.update_result(trade_id, "ERROR")
                raise Exception(f"Bouton {'UP' if trade_type == 'BUY' else 'DOWN'} introuvable")

            await asyncio.sleep(1)

            logger.info(f"✅ Trade #{trade_id}: {trade_type} {timeframe}min ${state.trade_amount} [{state.trade_mode.upper()}]")

            return {
                "success": True,
                "trade_id": trade_id,
                "type": trade_type,
                "timeframe": timeframe,
                "amount": state.trade_amount,
                "mode": state.trade_mode,
                "symbol": symbol,
            }

        except Exception as e:
            logger.error(f"Trade execution failed: {e}")
            # Screenshot de debug
            try:
                screenshot = await self.page.screenshot()
                await self._notify(f"❌ Erreur trade: `{e}`\n_Screenshot joint_")
            except Exception:
                pass
            return {"success": False, "error": str(e)}

    async def reconnect_if_needed(self) -> bool:
        """Vérifie la session et reconnecte si nécessaire."""
        try:
            if "login" in self.page.url or "trade" not in self.page.url:
                logger.warning("Session PO expirée, reconnexion...")
                state.po_connected = False
                await self._notify("⚠️ Session PO expirée — Reconnexion en cours...")
                success = await self.login()
                if success:
                    await self._notify("✅ Reconnexion PO réussie!")
                return success
            return True
        except Exception as e:
            logger.error(f"Reconnect check failed: {e}")
            return False

    async def get_screenshot(self) -> bytes:
        """Prend un screenshot pour debug."""
        return await self.page.screenshot()

    async def switch_mode(self, mode: str):
        """Change le mode compte depuis Telegram."""
        state.trade_mode = mode
        await self._set_account_mode(mode)
