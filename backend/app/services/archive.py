"""Удалённые из потоков офферы («корзина»), которые можно восстановить.

Keitaro удаляет оффер из потока безвозвратно, поэтому корзину храним в своей таблице.
"""

from collections import defaultdict
from collections.abc import Iterable
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import RemovedOffer, utcnow


async def load_removed(session: AsyncSession, stream_ids: Iterable[int]) -> dict[int, list[RemovedOffer]]:
    """{stream_id: [RemovedOffer, ...]} — недавно удалённые первыми."""
    ids = list(stream_ids)
    if not ids:
        return {}
    rows = await session.scalars(
        select(RemovedOffer)
        .where(RemovedOffer.stream_id.in_(ids))
        .order_by(RemovedOffer.removed_at.desc(), RemovedOffer.id.desc())
    )
    result: dict[int, list[RemovedOffer]] = defaultdict(list)
    for row in rows:
        result[row.stream_id].append(row)
    return dict(result)


async def archive_offers(session: AsyncSession, stream_id: int, offers: Iterable[dict[str, Any]]) -> None:
    """Кладёт удалённые офферы в корзину (повторное удаление обновляет запись). Коммит — снаружи."""
    offers = list(offers)
    if not offers:
        return
    existing = {
        row.offer_id: row
        for row in await session.scalars(
            select(RemovedOffer).where(
                RemovedOffer.stream_id == stream_id,
                RemovedOffer.offer_id.in_([o["offer_id"] for o in offers]),
            )
        )
    }
    now = utcnow()
    for offer in offers:
        row = existing.get(offer["offer_id"]) or RemovedOffer(stream_id=stream_id, offer_id=offer["offer_id"])
        row.share = offer["share"]
        row.state = offer.get("state") or "active"
        row.removed_at = now
        session.add(row)


async def unarchive_offers(session: AsyncSession, stream_id: int, offer_ids: Iterable[int]) -> None:
    """Убирает офферы из корзины (их восстановили или добавили заново). Коммит — снаружи."""
    ids = list(offer_ids)
    if ids:
        await session.execute(
            delete(RemovedOffer).where(RemovedOffer.stream_id == stream_id, RemovedOffer.offer_id.in_(ids))
        )
