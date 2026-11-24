"""Poll the newsletter inbox, extract sales, and alert followers."""
import asyncio
import hashlib
import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from imap_tools import AND, MailBox
from sqlalchemy import select
from telegram.ext import ContextTypes

from .. import db, notify
from ..bot import texts
from ..brands import brand_for_sender
from ..config import get_settings
from ..models import Brand, BrandFollow, ProcessedEmail, SaleEvent, User, utcnow
from .extractor import ExtractionError, Extractor, Refused, email_to_text, parse_end_date

log = logging.getLogger(__name__)

SALE_DEDUPE_WINDOW = timedelta(days=3)
FETCH_LIMIT = 50


@dataclass
class RawEmail:
    uid: str
    message_id: str
    sender: str
    subject: str
    html: str
    text: str
    received: datetime


def _fetch_unseen(host: str, user: str, password: str) -> list[RawEmail]:
    out: list[RawEmail] = []
    with MailBox(host).login(user, password) as mb:
        for msg in mb.fetch(AND(seen=False), mark_seen=False, limit=FETCH_LIMIT, bulk=True):
            mid = (msg.headers.get("message-id") or ("",))[0].strip()
            if not mid:
                mid = "sha1:" + hashlib.sha1(f"{msg.from_}|{msg.subject}|{msg.date}".encode()).hexdigest()
            out.append(RawEmail(msg.uid, mid, msg.from_, msg.subject, msg.html, msg.text,
                                msg.date if msg.date.tzinfo else msg.date.replace(tzinfo=timezone.utc)))
    return out


def _mark_seen(host: str, user: str, password: str, uids: list[str]) -> None:
    if not uids:
        return
    with MailBox(host).login(user, password) as mb:
        mb.flag(uids, "\\Seen", True)


async def poll_newsletters(context: ContextTypes.DEFAULT_TYPE) -> None:
    settings = get_settings()
    extractor: Extractor = context.bot_data["extractor"]
    try:
        emails = await asyncio.to_thread(_fetch_unseen, settings.imap_host, settings.imap_user, settings.imap_password)
    except Exception:
        log.exception("IMAP fetch failed")
        return

    done: list[str] = []
    for em in emails:
        try:
            if await process_email(context, extractor, em):
                done.append(em.uid)
        except Exception:
            log.exception("processing email %s failed", em.message_id)
    if emails:
        log.info("newsletters: %d fetched, %d processed", len(emails), len(done))
    try:
        await asyncio.to_thread(_mark_seen, settings.imap_host, settings.imap_user, settings.imap_password, done)
    except Exception:
        log.exception("IMAP mark-seen failed")


async def process_email(context, extractor: Extractor, em: RawEmail) -> bool:
    """Returns True when the email is finished with (mark seen); False to retry next run."""
    async with db.session() as s:
        if await s.get(ProcessedEmail, em.message_id):
            return True
        brands = (await s.scalars(select(Brand))).all()

    sender_brand = brand_for_sender(em.sender, brands)
    try:
        info = await extractor.extract(
            sender=em.sender, subject=em.subject, body=email_to_text(em.html, em.text),
            received=em.received.date(), brand_names=[b.name for b in brands],
        )
    except Refused as e:
        log.warning("model refused email %s: %s", em.message_id, e)
        async with db.session() as s:
            s.add(ProcessedEmail(message_id=em.message_id, is_sale=False, summary="refused"))
            await s.commit()
        return True
    except ExtractionError as e:
        log.warning("extraction failed for %s, will retry: %s", em.message_id, e)
        return False

    brand = sender_brand or next((b for b in brands if b.name == info.brand), None)
    end = parse_end_date(info.end_date)
    is_new_sale = False

    async with db.session() as s:
        s.add(ProcessedEmail(message_id=em.message_id, is_sale=info.is_sale,
                             brand_id=brand.id if brand else None, summary=info.model_dump_json()))
        if info.is_sale and brand:
            is_new_sale = not await _recent_duplicate(s, brand.id, info.max_discount_pct)
            if is_new_sale:
                s.add(SaleEvent(brand_id=brand.id, discount_max=info.max_discount_pct, categories=info.categories,
                                ends_at=end, email_message_id=em.message_id))
        await s.commit()

    if is_new_sale:
        await fan_out(context, brand, info.max_discount_pct, info.headline_he, info.categories, end)
    return True


async def _recent_duplicate(s, brand_id: int, discount: int | None) -> bool:
    since = utcnow() - SALE_DEDUPE_WINDOW
    recent = (await s.scalars(select(SaleEvent).where(SaleEvent.brand_id == brand_id))).all()
    for ev in recent:
        created = ev.created_at if ev.created_at.tzinfo else ev.created_at.replace(tzinfo=timezone.utc)
        if created >= since and ev.discount_max == discount:
            return True
    return False


async def fan_out(context, brand: Brand, discount: int | None, headline: str, categories: list[str],
                  end: date | None) -> None:
    async with db.session() as s:
        chat_ids = (await s.scalars(
            select(BrandFollow.chat_id).join(User, User.chat_id == BrandFollow.chat_id)
            .where(BrandFollow.brand_id == brand.id, User.active.is_(True))
        )).all()
    text = texts.sale_alert(brand.name_he, discount, headline, categories, end, date.today())
    log.info("sale alert for %s -> %d users", brand.name, len(chat_ids))
    for chat_id in chat_ids:
        await notify.send(context.bot, chat_id, text)
