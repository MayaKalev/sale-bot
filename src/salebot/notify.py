"""Sending messages with a global throttle; users who blocked the bot are deactivated."""
import asyncio
import logging

from telegram import Bot
from telegram.constants import ParseMode
from telegram.error import Forbidden, RetryAfter, TelegramError

from . import db
from .models import User

log = logging.getLogger(__name__)

_lock = asyncio.Lock()
_MIN_INTERVAL = 1 / 25  # stay under Telegram's ~30 msg/s global limit


async def send(bot: Bot, chat_id: int, text: str) -> bool:
    async with _lock:
        await asyncio.sleep(_MIN_INTERVAL)
    for _ in range(2):
        try:
            await bot.send_message(chat_id, text, parse_mode=ParseMode.HTML, disable_web_page_preview=False)
            return True
        except RetryAfter as e:
            await asyncio.sleep(float(getattr(e.retry_after, "total_seconds", lambda: e.retry_after)()) + 1)
        except Forbidden:
            log.info("chat %s blocked the bot; deactivating", chat_id)
            async with db.session() as s:
                user = await s.get(User, chat_id)
                if user:
                    user.active = False
                    await s.commit()
            return False
        except TelegramError:
            log.exception("failed to send to %s", chat_id)
            return False
    return False
