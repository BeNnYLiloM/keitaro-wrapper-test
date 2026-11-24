from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class Campaign(Base):
    """Кампания, созданная через обёртку. Источник правды по потокам и долям — сам Keitaro."""

    __tablename__ = "campaigns"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    keitaro_id: Mapped[int] = mapped_column(Integer, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    alias: Mapped[str | None] = mapped_column(String(64))
    geo: Mapped[list[str]] = mapped_column(JSON, default=list)
    initial_offer_id: Mapped[int] = mapped_column(Integer)
    google_stream_id: Mapped[int | None] = mapped_column(Integer)
    offers_stream_id: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class OfferCache(Base):
    """Локальная копия каталога офферов Keitaro — для быстрого автокомплита."""

    __tablename__ = "offers_cache"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    name: Mapped[str] = mapped_column(String(512), index=True)
    state: Mapped[str | None] = mapped_column(String(32))
    group_id: Mapped[int | None] = mapped_column(Integer)
    country: Mapped[list[str] | None] = mapped_column(JSON)
    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class PinnedOffer(Base):
    """Оффер, чья доля в потоке закреплена: при пересчёте её не трогаем.

    В Keitaro такого понятия нет, поэтому закрепления хранятся у нас.
    Саму долю храним как источник правды в Keitaro, здесь — только факт закрепления.
    """

    __tablename__ = "pinned_offers"
    __table_args__ = (UniqueConstraint("stream_id", "offer_id", name="uq_pinned_offers_stream_offer"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    stream_id: Mapped[int] = mapped_column(Integer, index=True)
    offer_id: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class RemovedOffer(Base):
    """Оффер, удалённый из потока через обёртку. Его можно восстановить в любой момент.

    Keitaro удаляет оффер из потока безвозвратно, поэтому «корзину» ведём сами:
    запоминаем, какая была доля и статус, чтобы показать их и вернуть оффер обратно.
    """

    __tablename__ = "removed_offers"
    __table_args__ = (UniqueConstraint("stream_id", "offer_id", name="uq_removed_offers_stream_offer"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    stream_id: Mapped[int] = mapped_column(Integer, index=True)
    offer_id: Mapped[int] = mapped_column(Integer)
    share: Mapped[int] = mapped_column(Integer)  # доля на момент удаления
    state: Mapped[str] = mapped_column(String(32), default="active")
    removed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class OperationLog(Base):
    """История действий обёртки: создание кампаний, добавление и удаление офферов."""

    __tablename__ = "operations_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    operation: Mapped[str] = mapped_column(String(32))
    campaign_id: Mapped[int | None] = mapped_column(Integer, index=True)
    stream_id: Mapped[int | None] = mapped_column(Integer)
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    success: Mapped[bool] = mapped_column(Boolean, default=True)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
