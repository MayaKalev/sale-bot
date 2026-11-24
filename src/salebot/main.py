import logging
from datetime import timedelta

import anthropic
from telegram import BotCommand
from telegram.ext import Application

from . import db
from .bot import handlers
from .config import get_settings
from .newsletters.extractor import Extractor
from .newsletters.imap_poller import poll_newsletters
from .prices.checker import check_prices

log = logging.getLogger("salebot")

BOT_COMMANDS = [
    BotCommand("follow", "עקוב אחרי מותג (למשל: /follow זארה מנגו)"),
    BotCommand("unfollow", "הפסק לעקוב אחרי מותג"),
    BotCommand("list", "מה אני עוקב?"),
    BotCommand("help", "עזרה"),
]


async def _post_init(app: Application) -> None:
    settings = get_settings()
    await db.init_db(settings.db_url)
    await app.bot.set_my_commands(BOT_COMMANDS)

    jq = app.job_queue
    jq.run_repeating(check_prices, interval=timedelta(hours=settings.price_check_interval_hours), first=60,
                     name="check_prices")
    if settings.imap_user and settings.imap_password and settings.anthropic_api_key:
        app.bot_data["extractor"] = Extractor(anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key),
                                              settings.llm_model)
        jq.run_repeating(poll_newsletters, interval=timedelta(minutes=settings.newsletter_interval_min), first=10,
                         name="poll_newsletters")
    else:
        log.warning("IMAP or Anthropic credentials missing - newsletter polling disabled")


async def _post_shutdown(app: Application) -> None:
    await db.dispose()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    settings = get_settings()
    if not settings.telegram_token:
        raise SystemExit("TELEGRAM_TOKEN is not set (see .env.example)")
    app = (Application.builder().token(settings.telegram_token)
           .post_init(_post_init).post_shutdown(_post_shutdown).build())
    handlers.register(app)
    app.run_polling()


if __name__ == "__main__":
    main()
