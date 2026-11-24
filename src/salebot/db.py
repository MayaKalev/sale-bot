from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from .brands import SEED_BRANDS
from .models import Base, Brand

_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


async def init_db(url: str) -> None:
    global _engine, _sessionmaker
    _engine = create_async_engine(url)
    _sessionmaker = async_sessionmaker(_engine, expire_on_commit=False)
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await seed_brands()


def session() -> AsyncSession:
    if _sessionmaker is None:
        raise RuntimeError("init_db() was not called")
    return _sessionmaker()


async def dispose() -> None:
    if _engine is not None:
        await _engine.dispose()


async def seed_brands() -> None:
    """Idempotent upsert of the seed brand list (keyed by canonical name)."""
    async with session() as s:
        existing = {b.name: b for b in (await s.scalars(select(Brand))).all()}
        for seed in SEED_BRANDS:
            b = existing.get(seed.name)
            if b is None:
                s.add(Brand(name=seed.name, name_he=seed.name_he, aliases=list(seed.aliases),
                            sender_domains=list(seed.sender_domains)))
            else:
                b.name_he = seed.name_he
                b.aliases = list(seed.aliases)
                b.sender_domains = list(seed.sender_domains)
        await s.commit()
