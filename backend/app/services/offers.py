"""Каталог офферов: локальный кэш в БД поверх GET /offers.

Каталог на стенде небольшой (~170 офферов) и только для чтения, поэтому проще всего
периодически забирать его целиком и искать по своей таблице — автокомплит тогда
не дёргает Keitaro на каждую букву.
"""

import asyncio
import time
from collections.abc import Iterable

from sqlalchemy import String, case, cast, delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.keitaro import KeitaroClient, KeitaroError
from app.models import OfferCache, utcnow


class OfferCatalog:
    def __init__(self, ttl_seconds: int = 600) -> None:
        self.ttl_seconds = ttl_seconds
        self._synced_at: float | None = None
        self._lock = asyncio.Lock()

    def is_fresh(self) -> bool:
        return self._synced_at is not None and time.monotonic() - self._synced_at < self.ttl_seconds

    async def refresh(self, session: AsyncSession, client: KeitaroClient, force: bool = False) -> int:
        """Перезаливает кэш, если он устарел (или force=True). Возвращает число офферов в кэше."""
        async with self._lock:
            if not force and self.is_fresh():
                return await session.scalar(select(func.count()).select_from(OfferCache)) or 0

            offers = await client.list_offers()
            now = utcnow()
            existing = {o.id: o for o in (await session.scalars(select(OfferCache))).all()}
            seen: set[int] = set()
            for raw in offers:
                if raw.get("id") is None:
                    continue
                offer_id = int(raw["id"])
                seen.add(offer_id)
                row = existing.get(offer_id) or OfferCache(id=offer_id)
                _fill(row, raw)
                row.synced_at = now
                session.add(row)
            stale = set(existing) - seen
            if stale:
                await session.execute(delete(OfferCache).where(OfferCache.id.in_(stale)))
            await session.commit()
            self._synced_at = time.monotonic()
            return len(seen)

    async def search(
        self, session: AsyncSession, client: KeitaroClient, query: str = "", limit: int = 20
    ) -> list[OfferCache]:
        await self.refresh(session, client)
        stmt = select(OfferCache)
        query = query.strip()
        if query:
            conditions = [OfferCache.name.ilike(f"%{query}%")]
            if query.isdigit():
                # "37" находит и оффер #37, и #3717, и офферы с "37" в названии
                conditions.append(cast(OfferCache.id, String).like(f"{query}%"))
            stmt = stmt.where(or_(*conditions))
            if query.isdigit():
                # точное совпадение по id — первым
                stmt = stmt.order_by(case((OfferCache.id == int(query), 0), else_=1), OfferCache.id)
            else:
                stmt = stmt.order_by(OfferCache.id)
        else:
            stmt = stmt.order_by(OfferCache.id)
        return list((await session.scalars(stmt.limit(limit))).all())

    async def get(self, session: AsyncSession, client: KeitaroClient, offer_id: int) -> OfferCache | None:
        """Оффер по id: из кэша, а если его там нет — напрямую из Keitaro."""
        row = await session.get(OfferCache, offer_id)
        if row is not None:
            return row
        try:
            raw = await client.get_offer(offer_id)
        except KeitaroError as exc:
            if exc.status_code == 404:
                return None
            raise
        if not raw or raw.get("id") is None:
            return None
        row = OfferCache(id=int(raw["id"]))
        _fill(row, raw)
        session.add(row)
        await session.commit()
        return row

    async def names(self, session: AsyncSession, client: KeitaroClient, ids: Iterable[int]) -> dict[int, str]:
        ids = {int(i) for i in ids}
        if not ids:
            return {}
        await self.refresh(session, client)
        rows = await session.scalars(select(OfferCache).where(OfferCache.id.in_(ids)))
        return {row.id: row.name for row in rows}


def _fill(row: OfferCache, raw: dict) -> None:
    row.name = str(raw.get("name") or f"Offer #{raw.get('id')}")
    row.state = raw.get("state")
    row.group_id = _int_or_none(raw.get("group_id"))
    country = raw.get("country")
    row.country = country if isinstance(country, list) else None


def _int_or_none(value: object) -> int | None:
    try:
        return int(value) if value is not None else None  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
