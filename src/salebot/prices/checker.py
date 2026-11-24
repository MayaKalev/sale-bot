"""Scheduled price check over all active tracked products."""
import asyncio
import logging
from collections import defaultdict
from urllib.parse import urlsplit

from sqlalchemy import select
from telegram.ext import ContextTypes

from .. import db, notify
from ..bot import texts
from ..config import get_settings
from ..models import PriceHistory, TrackedProduct, User, utcnow
from .fetcher import FetchError, fetch_html, make_client
from .parser import parse_product

log = logging.getLogger(__name__)

PER_DOMAIN_DELAY_S = 3.0
MAX_PARALLEL_DOMAINS = 4


def is_drop(last_price: float, new_price: float, min_pct: float) -> bool:
    return new_price < last_price and (last_price - new_price) / last_price * 100 >= min_pct


async def check_prices(context: ContextTypes.DEFAULT_TYPE) -> None:
    async with db.session() as s:
        products = (await s.scalars(
            select(TrackedProduct).join(User, User.chat_id == TrackedProduct.chat_id)
            .where(TrackedProduct.active.is_(True), User.active.is_(True))
        )).all()
    by_domain: dict[str, list[int]] = defaultdict(list)
    for p in products:
        by_domain[urlsplit(p.url).hostname or ""].append(p.id)
    log.info("price check: %d products on %d domains", len(products), len(by_domain))

    sem = asyncio.Semaphore(MAX_PARALLEL_DOMAINS)
    async with make_client() as client:
        async def run_domain(ids: list[int]) -> None:
            async with sem:
                for pid in ids:
                    try:
                        await check_one(context, client, pid)
                    except Exception:
                        log.exception("price check failed for product %s", pid)
                    await asyncio.sleep(PER_DOMAIN_DELAY_S)

        await asyncio.gather(*(run_domain(ids) for ids in by_domain.values()))


async def check_one(context, client, product_id: int) -> None:
    settings = get_settings()
    async with db.session() as s:
        p = await s.get(TrackedProduct, product_id)
        if p is None or not p.active:
            return
        try:
            info = parse_product(await fetch_html(client, p.url))
        except FetchError as e:
            log.warning("fetch failed: %s", e)
            info = None

        p.last_checked_at = utcnow()
        if info is None:
            p.fail_count += 1
            if p.fail_count >= settings.max_fetch_failures:
                p.active = False
                await s.commit()
                await notify.send(context.bot, p.chat_id, texts.TRACKING_STOPPED.format(
                    title=texts.escape(texts.shorten(p.title or texts.DEFAULT_PRODUCT_TITLE)),
                    url=texts.escape(p.url)))
                return
            await s.commit()
            return

        p.fail_count = 0
        old = p.last_price
        s.add(PriceHistory(product_id=p.id, price=info.price))
        p.last_price = info.price
        p.lowest_price = min(p.lowest_price, info.price)
        if info.title and not p.title:
            p.title = info.title
        await s.commit()

    if is_drop(old, info.price, settings.price_drop_min_pct):
        await notify.send(context.bot, p.chat_id, texts.price_drop(p.title, old, info.price, p.currency, p.url))
