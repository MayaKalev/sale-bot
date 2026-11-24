import logging
from html import escape

from sqlalchemy import delete, select
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler, filters

from .. import db
from ..models import Brand, BrandFollow, TrackedProduct, User
from ..prices.fetcher import FetchError, fetch_html, make_client
from ..prices.parser import parse_product
from . import texts
from .nlu import Intent, extract_url, match_brands, normalize, parse_intent

log = logging.getLogger(__name__)
HTML = ParseMode.HTML


async def _ensure_user(chat_id: int) -> None:
    async with db.session() as s:
        user = await s.get(User, chat_id)
        if user is None:
            s.add(User(chat_id=chat_id))
        elif not user.active:
            user.active = True
        await s.commit()


async def _all_brands() -> list[Brand]:
    async with db.session() as s:
        return list((await s.scalars(select(Brand).order_by(Brand.id))).all())


def _brand_names(brands) -> str:
    return texts.join_he([escape(b.name_he) for b in brands])


async def _reply(update: Update, text: str, **kw) -> None:
    await update.effective_message.reply_text(text, parse_mode=HTML, disable_web_page_preview=True, **kw)


# ---------- commands ----------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _ensure_user(update.effective_chat.id)
    await _reply(update, texts.START.format(brands=_brand_names(await _all_brands())))


async def follow_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _ensure_user(update.effective_chat.id)
    await follow(update, " ".join(context.args))


async def unfollow_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _ensure_user(update.effective_chat.id)
    await unfollow(update, " ".join(context.args))


async def list_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _ensure_user(update.effective_chat.id)
    await show_list(update)


# ---------- free text ----------

async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _ensure_user(update.effective_chat.id)
    text = update.effective_message.text or ""
    url = extract_url(text)
    if url:
        await track_product(update, url)
        return
    intent, rest = parse_intent(text)
    if intent is Intent.FOLLOW:
        await follow(update, rest)
    elif intent is Intent.UNFOLLOW:
        await unfollow(update, rest)
    elif intent is Intent.LIST:
        await show_list(update)
    else:
        # A bare brand name ("זארה") is treated as a follow request.
        brands = await _all_brands()
        m = match_brands(rest, brands)
        if m.brands and not m.unknown:
            await follow(update, rest)
        else:
            await _reply(update, texts.DIDNT_UNDERSTAND)


# ---------- brands ----------

async def follow(update: Update, text: str) -> None:
    chat_id = update.effective_chat.id
    brands = await _all_brands()
    m = match_brands(text, brands)
    if not m.brands:
        if m.unknown:
            await _reply(update, texts.UNKNOWN_BRANDS.format(names=escape(", ".join(m.unknown)),
                                                              brands=_brand_names(brands)))
        else:
            await _reply(update, texts.NO_BRANDS_GIVEN.format(brands=_brand_names(brands)))
        return

    async with db.session() as s:
        existing = set((await s.scalars(select(BrandFollow.brand_id).where(BrandFollow.chat_id == chat_id))).all())
        new = [b for b in m.brands if b.id not in existing]
        for b in new:
            s.add(BrandFollow(chat_id=chat_id, brand_id=b.id))
        await s.commit()

    already = [b for b in m.brands if b.id in existing]
    parts = []
    if new:
        parts.append(texts.FOLLOWED.format(brands=_brand_names(new)))
    if already:
        parts.append(texts.ALREADY_FOLLOWING.format(brands=_brand_names(already)))
    if m.unknown:
        parts.append(texts.UNKNOWN_BRANDS.format(names=escape(", ".join(m.unknown)), brands=_brand_names(brands)))
    await _reply(update, "\n".join(parts))


async def unfollow(update: Update, text: str) -> None:
    chat_id = update.effective_chat.id
    brands = await _all_brands()
    m = match_brands(text, brands)
    if not m.brands:
        await show_list(update)  # let them tap ❌ instead
        return
    async with db.session() as s:
        existing = set((await s.scalars(select(BrandFollow.brand_id).where(BrandFollow.chat_id == chat_id))).all())
        removed = [b for b in m.brands if b.id in existing]
        await s.execute(delete(BrandFollow).where(BrandFollow.chat_id == chat_id,
                                                  BrandFollow.brand_id.in_([b.id for b in removed])))
        await s.commit()
    parts = []
    if removed:
        parts.append(texts.UNFOLLOWED.format(brands=_brand_names(removed)))
    missing = [b for b in m.brands if b not in removed]
    if missing:
        parts.append(texts.NOT_FOLLOWING.format(brands=_brand_names(missing)))
    await _reply(update, "\n".join(parts))


# ---------- products ----------

async def track_product(update: Update, url: str) -> None:
    chat_id = update.effective_chat.id
    async with db.session() as s:
        dup = await s.scalar(select(TrackedProduct).where(TrackedProduct.chat_id == chat_id,
                                                          TrackedProduct.url == url,
                                                          TrackedProduct.active.is_(True)))
    if dup:
        await _reply(update, texts.ALREADY_TRACKING.format(price=texts.format_price(dup.last_price, dup.currency)))
        return

    status = await update.effective_message.reply_text(texts.CHECKING_LINK)
    try:
        async with make_client() as client:
            info = parse_product(await fetch_html(client, url))
    except FetchError as e:
        log.info("could not fetch %s: %s", url, e)
        info = None
    if info is None:
        await status.edit_text(texts.CANT_READ_PRICE, parse_mode=HTML)
        return

    async with db.session() as s:
        s.add(TrackedProduct(chat_id=chat_id, url=url, title=info.title, currency=info.currency,
                             initial_price=info.price, last_price=info.price, lowest_price=info.price))
        await s.commit()
    await status.edit_text(texts.SAVED.format(price=texts.format_price(info.price, info.currency)), parse_mode=HTML)


# ---------- list + remove buttons ----------

async def _build_list(chat_id: int) -> tuple[str, InlineKeyboardMarkup | None]:
    async with db.session() as s:
        brands = (await s.scalars(select(Brand).join(BrandFollow, BrandFollow.brand_id == Brand.id)
                                  .where(BrandFollow.chat_id == chat_id).order_by(Brand.id))).all()
        products = (await s.scalars(select(TrackedProduct).where(TrackedProduct.chat_id == chat_id,
                                                                 TrackedProduct.active.is_(True))
                                    .order_by(TrackedProduct.id))).all()
    if not brands and not products:
        return texts.LIST_EMPTY, None

    lines = [texts.LIST_HEADER]
    buttons: list[list[InlineKeyboardButton]] = []
    if brands:
        lines.append(texts.LIST_BRANDS.format(brands=_brand_names(brands)))
        row = [InlineKeyboardButton(f"❌ {b.name_he}", callback_data=f"rm:brand:{b.id}") for b in brands]
        buttons += [row[i:i + 3] for i in range(0, len(row), 3)]
    if products:
        lines.append(texts.LIST_PRODUCTS)
        prow = []
        for i, p in enumerate(products, 1):
            title = escape(texts.shorten(p.title or texts.DEFAULT_PRODUCT_TITLE, 45))
            lines.append(texts.LIST_PRODUCT_LINE.format(
                i=i, title=f'<a href="{escape(p.url)}">{title}</a>',
                price=texts.format_price(p.last_price, p.currency)))
            prow.append(InlineKeyboardButton(f"❌ {i}", callback_data=f"rm:prod:{p.id}"))
        buttons += [prow[i:i + 5] for i in range(0, len(prow), 5)]
    return "\n".join(lines), InlineKeyboardMarkup(buttons)


async def show_list(update: Update) -> None:
    text, markup = await _build_list(update.effective_chat.id)
    await _reply(update, text, reply_markup=markup)


async def on_remove(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    chat_id = update.effective_chat.id
    try:
        _, kind, raw_id = query.data.split(":")
        item_id = int(raw_id)
    except ValueError:
        await query.answer()
        return

    note = texts.REMOVED_ALREADY
    async with db.session() as s:
        if kind == "brand":
            res = await s.execute(delete(BrandFollow).where(BrandFollow.chat_id == chat_id,
                                                            BrandFollow.brand_id == item_id))
            if res.rowcount:
                brand = await s.get(Brand, item_id)
                note = texts.REMOVED_BRAND.format(name=brand.name_he if brand else "")
        elif kind == "prod":
            p = await s.get(TrackedProduct, item_id)
            if p and p.chat_id == chat_id and p.active:
                p.active = False
                note = texts.REMOVED_PRODUCT
        await s.commit()

    await query.answer(note)
    text, markup = await _build_list(chat_id)
    await query.edit_message_text(text, parse_mode=HTML, reply_markup=markup, disable_web_page_preview=True)


def register(app: Application) -> None:
    app.add_handler(CommandHandler(["start", "help"], start))
    app.add_handler(CommandHandler("follow", follow_cmd))
    app.add_handler(CommandHandler("unfollow", unfollow_cmd))
    app.add_handler(CommandHandler("list", list_cmd))
    app.add_handler(CallbackQueryHandler(on_remove, pattern=r"^rm:"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
