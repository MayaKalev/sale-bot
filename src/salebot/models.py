from datetime import date, datetime, timezone

from sqlalchemy import JSON, BigInteger, Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    chat_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Brand(Base):
    __tablename__ = "brands"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String, unique=True)
    name_he: Mapped[str] = mapped_column(String)
    aliases: Mapped[list] = mapped_column(JSON, default=list)
    sender_domains: Mapped[list] = mapped_column(JSON, default=list)


class BrandFollow(Base):
    __tablename__ = "brand_follows"
    __table_args__ = (UniqueConstraint("chat_id", "brand_id"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    chat_id: Mapped[int] = mapped_column(ForeignKey("users.chat_id", ondelete="CASCADE"))
    brand_id: Mapped[int] = mapped_column(ForeignKey("brands.id", ondelete="CASCADE"))


class TrackedProduct(Base):
    __tablename__ = "tracked_products"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    chat_id: Mapped[int] = mapped_column(ForeignKey("users.chat_id", ondelete="CASCADE"))
    url: Mapped[str] = mapped_column(Text)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    currency: Mapped[str] = mapped_column(String, default="ILS")
    initial_price: Mapped[float] = mapped_column(Float)
    last_price: Mapped[float] = mapped_column(Float)
    lowest_price: Mapped[float] = mapped_column(Float)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    fail_count: Mapped[int] = mapped_column(Integer, default=0)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class PriceHistory(Base):
    __tablename__ = "price_history"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("tracked_products.id", ondelete="CASCADE"))
    price: Mapped[float] = mapped_column(Float)
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ProcessedEmail(Base):
    __tablename__ = "processed_emails"
    message_id: Mapped[str] = mapped_column(String, primary_key=True)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    is_sale: Mapped[bool] = mapped_column(Boolean, default=False)
    brand_id: Mapped[int | None] = mapped_column(ForeignKey("brands.id"), nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)


class SaleEvent(Base):
    __tablename__ = "sale_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    brand_id: Mapped[int] = mapped_column(ForeignKey("brands.id"))
    discount_max: Mapped[int | None] = mapped_column(Integer, nullable=True)
    categories: Mapped[list] = mapped_column(JSON, default=list)
    ends_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    email_message_id: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
