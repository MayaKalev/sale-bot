"""process_email / check_one against an in-memory DB with fake bot and fake extractor."""
from datetime import datetime, timezone
from types import SimpleNamespace

from sqlalchemy import func, select

from salebot.models import Brand, BrandFollow, PriceHistory, ProcessedEmail, SaleEvent, TrackedProduct, User
from salebot.newsletters import imap_poller
from salebot.newsletters.extractor import ExtractionError, SaleInfo
from salebot.prices import checker


class FakeBot:
    def __init__(self):
        self.sent = []

    async def send_message(self, chat_id, text, **kw):
        self.sent.append((chat_id, text))


class FakeExtractor:
    def __init__(self, result):
        self.result = result

    async def extract(self, **kw):
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def email(mid="<1@zara>", sender="news@email.zara.com"):
    return imap_poller.RawEmail("1", mid, sender, "SALE", "<p>50% off</p>", "", datetime.now(timezone.utc))


SALE = SaleInfo(is_sale=True, brand="Zara", max_discount_pct=50, categories=["מעילים", "סריגים"],
                end_date=None, headline_he="סוף עונה")


async def _setup_followers(db, brand_name="Zara"):
    async with db.session() as s:
        brand = await s.scalar(select(Brand).where(Brand.name == brand_name))
        s.add_all([User(chat_id=1), User(chat_id=2), User(chat_id=3, active=False)])
        s.add_all([BrandFollow(chat_id=1, brand_id=brand.id), BrandFollow(chat_id=3, brand_id=brand.id)])
        await s.commit()


async def test_seed_brands(memdb):
    async with memdb.session() as s:
        names = set((await s.scalars(select(Brand.name))).all())
    assert {"Zara", "Mango", "H&M", "Nike", "Castro", "Fox", "Terminal X"} <= names
    await memdb.seed_brands()  # idempotent
    async with memdb.session() as s:
        assert await s.scalar(select(func.count()).select_from(Brand)) == len(names)


async def test_sale_email_alerts_active_followers_once(memdb):
    await _setup_followers(memdb)
    bot = FakeBot()
    ctx = SimpleNamespace(bot=bot)
    assert await imap_poller.process_email(ctx, FakeExtractor(SALE), email())
    assert bot.sent == [(1, "🔥 <b>זארה – עד 50% הנחה</b> על מעילים וסריגים")]

    # same email again -> idempotent
    assert await imap_poller.process_email(ctx, FakeExtractor(SALE), email())
    # different email, same sale within window -> deduped
    assert await imap_poller.process_email(ctx, FakeExtractor(SALE), email(mid="<2@zara>"))
    assert len(bot.sent) == 1
    async with memdb.session() as s:
        assert await s.scalar(select(func.count()).select_from(SaleEvent)) == 1
        assert await s.scalar(select(func.count()).select_from(ProcessedEmail)) == 2


async def test_sender_domain_wins_over_llm_brand(memdb):
    await _setup_followers(memdb, "Castro")
    bot = FakeBot()
    info = SALE.model_copy(update={"brand": "Zara"})
    await imap_poller.process_email(SimpleNamespace(bot=bot), FakeExtractor(info), email(sender="club@castro.com"))
    assert len(bot.sent) == 1 and "קסטרו" in bot.sent[0][1]


async def test_non_sale_is_recorded_without_alert(memdb):
    await _setup_followers(memdb)
    bot = FakeBot()
    info = SaleInfo(is_sale=False, brand="Zara", max_discount_pct=None, categories=[], end_date=None, headline_he="")
    assert await imap_poller.process_email(SimpleNamespace(bot=bot), FakeExtractor(info), email())
    assert bot.sent == []


async def test_extraction_error_leaves_email_for_retry(memdb):
    bot = FakeBot()
    assert not await imap_poller.process_email(SimpleNamespace(bot=bot), FakeExtractor(ExtractionError("x")), email())
    async with memdb.session() as s:
        assert await s.get(ProcessedEmail, "<1@zara>") is None


def test_is_drop():
    assert checker.is_drop(399, 249, 1.0)
    assert not checker.is_drop(399, 399, 1.0)
    assert not checker.is_drop(399, 400, 1.0)
    assert not checker.is_drop(100, 99.5, 1.0)  # 0.5% is noise


async def _add_product(db, price=399.0):
    async with db.session() as s:
        s.add(User(chat_id=10))
        p = TrackedProduct(chat_id=10, url="https://shop.example/coat", title="מעיל", initial_price=price,
                           last_price=price, lowest_price=price)
        s.add(p)
        await s.commit()
        return p.id


async def test_check_one_price_drop(memdb, monkeypatch, fixture_text):
    pid = await _add_product(memdb, 499.0)

    async def fake_fetch(client, url):
        return fixture_text("product_jsonld.html")  # ₪399
    monkeypatch.setattr(checker, "fetch_html", fake_fetch)
    bot = FakeBot()
    await checker.check_one(SimpleNamespace(bot=bot), None, pid)
    assert bot.sent == [(10, "📉 <b>מעיל ירד מ־₪499 ל־₪399</b>\nhttps://shop.example/coat")]
    async with memdb.session() as s:
        p = await s.get(TrackedProduct, pid)
        assert p.last_price == 399 and p.lowest_price == 399
        assert await s.scalar(select(func.count()).select_from(PriceHistory)) == 1


async def test_check_one_failures_deactivate(memdb, monkeypatch, fixture_text):
    pid = await _add_product(memdb)

    async def fake_fetch(client, url):
        return fixture_text("product_none.html")
    monkeypatch.setattr(checker, "fetch_html", fake_fetch)
    bot = FakeBot()
    for _ in range(5):
        await checker.check_one(SimpleNamespace(bot=bot), None, pid)
    async with memdb.session() as s:
        assert not (await s.get(TrackedProduct, pid)).active
    assert len(bot.sent) == 1 and "הפסקתי לעקוב" in bot.sent[0][1]
