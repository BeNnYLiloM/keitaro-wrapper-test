"""Закреплённые доли офферов (хранятся в нашей БД, в Keitaro такого поля нет)."""

from collections import defaultdict
from collections.abc import Iterable

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import PinnedOffer


async def load_pins(session: AsyncSession, stream_ids: Iterable[int]) -> dict[int, set[int]]:
    """{stream_id: {offer_id, ...}} для указанных потоков."""
    ids = list(stream_ids)
    if not ids:
        return {}
    rows = await session.scalars(select(PinnedOffer).where(PinnedOffer.stream_id.in_(ids)))
    result: dict[int, set[int]] = defaultdict(set)
    for row in rows:
        result[row.stream_id].add(row.offer_id)
    return dict(result)


async def replace_pins(session: AsyncSession, stream_id: int, offer_ids: Iterable[int]) -> None:
    """Заменяет набор закреплённых офферов потока. Коммит — на вызывающей стороне."""
    await session.execute(delete(PinnedOffer).where(PinnedOffer.stream_id == stream_id))
    for offer_id in sorted(set(offer_ids)):
        session.add(PinnedOffer(stream_id=stream_id, offer_id=offer_id))
