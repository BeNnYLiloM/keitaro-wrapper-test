"""Редактор офферов в потоке.

Две независимые операции:

* **Публикация черновика** (`publish_offers`). Пользователь в интерфейсе добавляет, удаляет
  и восстанавливает офферы локально, затем публикует итоговый список одним запросом. Сервер:
  1. сверяет список с текущим состоянием потока в Keitaro (не изменился ли он за время редактирования);
  2. считает доли: закреплённые офферы сохраняют текущую долю, остальные поровну делят остаток;
  3. записывает список в Keitaro через PUT /streams/{id} (поле `offers` заменяет состав целиком);
  4. кладёт удалённые офферы в корзину (`removed_offers`), откуда их можно восстановить когда угодно,
     а восстановленные из неё убирает.

* **Закрепление доли** (`pin_offer` / `unpin_offer`). Применяется сразу, без черновика:
  запоминает в нашей БД, что текущая доля оффера заморожена. В Keitaro ничего не меняется.

Операции над одним потоком выполняются по очереди (лок на поток), чтобы не затирать друг друга.
"""

import asyncio
from collections import defaultdict
from typing import Any

from sqlalchemy import delete

from app.keitaro import KeitaroError
from app.models import PinnedOffer
from app.schemas import BaseOffer, PublishOffers, StreamOut
from app.services.archive import archive_offers, load_removed, unarchive_offers
from app.services.context import Ctx
from app.services.errors import ServiceError
from app.services.operations import log_operation
from app.services.pins import load_pins, replace_pins
from app.services.shares import ShareError, ShareSlot, allocate_shares
from app.services.views import is_offers_stream, stream_offers, stream_view

_stream_locks: defaultdict[int, asyncio.Lock] = defaultdict(asyncio.Lock)


async def get_stream(ctx: Ctx, stream_id: int) -> StreamOut:
    stream = await _load_editable_stream(ctx, stream_id)
    return await _view(ctx, stream)


async def publish_offers(ctx: Ctx, stream_id: int, data: PublishOffers) -> StreamOut:
    async with _stream_locks[stream_id]:
        stream = await _load_editable_stream(ctx, stream_id)
        current = stream_offers(stream)

        if data.base is not None and _signature(current) != _signature(data.base):
            raise ServiceError(
                409, "Поток изменился в Keitaro, пока вы его редактировали. Обновите страницу и повторите изменения."
            )

        current_by_id = {o["offer_id"]: o for o in current}
        draft_ids = [o.offer_id for o in data.offers]
        added = [oid for oid in draft_ids if oid not in current_by_id]
        removed = [oid for oid in current_by_id if oid not in set(draft_ids)]
        for offer_id in added:
            if await ctx.catalog.get(ctx.session, ctx.client, offer_id) is None:
                raise ServiceError(422, f"Оффер #{offer_id} не найден в Keitaro")
        # оффер из корзины возвращается с тем статусом, который был у него до удаления
        archived = {r.offer_id: r for r in (await load_removed(ctx.session, [stream_id])).get(stream_id, [])}
        restored = [oid for oid in added if oid in archived]

        # закреплённые офферы, которые остаются в потоке, сохраняют свою текущую долю
        pinned = (await load_pins(ctx.session, [stream_id])).get(stream_id, set()) & set(current_by_id)
        kept_pinned = [oid for oid in draft_ids if oid in pinned]
        slots = [
            ShareSlot(pinned=True, share=current_by_id[oid]["share"]) if oid in pinned else ShareSlot()
            for oid in draft_ids
        ]
        try:
            shares = allocate_shares(slots)
        except ShareError as exc:
            raise ServiceError(422, str(exc)) from exc

        def state_of(oid: int) -> str:
            if oid in current_by_id:
                return current_by_id[oid].get("state") or "active"
            if oid in archived:
                return archived[oid].state or "active"
            return "active"

        after = [
            {"offer_id": oid, "share": share, "state": state_of(oid)}
            for oid, share in zip(draft_ids, shares, strict=True)
        ]
        campaign_id = stream.get("campaign_id")
        payload = {
            "before": current,
            "after": after,
            "added": [oid for oid in added if oid not in archived],
            "restored": restored,
            "removed": removed,
            "pinned": kept_pinned,
        }

        if after != current:
            try:
                await ctx.client.update_stream(stream_id, {"offers": after})
            except KeitaroError as exc:
                log_operation(
                    ctx.session,
                    "publish_offers",
                    campaign_id=campaign_id,
                    stream_id=stream_id,
                    payload=payload,
                    error=exc.message,
                )
                await ctx.session.commit()
                raise
            # Перечитываем поток, чтобы показать ровно то, что сохранил Keitaro
            stream = await ctx.client.get_stream(stream_id)

        # закрепления удалённых офферов больше не нужны; удалённые — в корзину, вернувшиеся — из неё
        await replace_pins(ctx.session, stream_id, kept_pinned)
        await archive_offers(ctx.session, stream_id, [current_by_id[oid] for oid in removed])
        await unarchive_offers(ctx.session, stream_id, added)
        log_operation(ctx.session, "publish_offers", campaign_id=campaign_id, stream_id=stream_id, payload=payload)
        await ctx.session.commit()
        return await _view(ctx, stream)


async def pin_offer(ctx: Ctx, stream_id: int, offer_id: int) -> StreamOut:
    return await _set_pin(ctx, stream_id, offer_id, pinned=True)


async def unpin_offer(ctx: Ctx, stream_id: int, offer_id: int) -> StreamOut:
    return await _set_pin(ctx, stream_id, offer_id, pinned=False)


async def _set_pin(ctx: Ctx, stream_id: int, offer_id: int, *, pinned: bool) -> StreamOut:
    async with _stream_locks[stream_id]:
        stream = await _load_editable_stream(ctx, stream_id)
        offer = next((o for o in stream_offers(stream) if o["offer_id"] == offer_id), None)
        if offer is None:
            raise ServiceError(404, f"Оффера #{offer_id} нет в потоке #{stream_id}. Сначала опубликуйте его")

        current = (await load_pins(ctx.session, [stream_id])).get(stream_id, set())
        if pinned and offer_id not in current:
            ctx.session.add(PinnedOffer(stream_id=stream_id, offer_id=offer_id))
        elif not pinned and offer_id in current:
            await ctx.session.execute(
                delete(PinnedOffer).where(PinnedOffer.stream_id == stream_id, PinnedOffer.offer_id == offer_id)
            )
        log_operation(
            ctx.session,
            "pin_offer" if pinned else "unpin_offer",
            campaign_id=stream.get("campaign_id"),
            stream_id=stream_id,
            payload={"offer_id": offer_id, "share": offer["share"]},
        )
        await ctx.session.commit()
        return await _view(ctx, stream)


async def _load_editable_stream(ctx: Ctx, stream_id: int) -> dict[str, Any]:
    stream = await ctx.client.get_stream(stream_id)
    if not isinstance(stream, dict) or stream.get("id") is None:
        raise ServiceError(404, f"Поток #{stream_id} не найден")
    if not is_offers_stream(stream):
        raise ServiceError(400, f"Поток #{stream_id} не работает с офферами (схема «{stream.get('schema')}»)")
    return stream


async def _view(ctx: Ctx, stream: dict[str, Any]) -> StreamOut:
    stream_id = int(stream["id"])
    pins = await load_pins(ctx.session, [stream_id])
    removed = (await load_removed(ctx.session, [stream_id])).get(stream_id, [])
    ids = [o["offer_id"] for o in stream_offers(stream)] + [r.offer_id for r in removed]
    names = await ctx.catalog.names(ctx.session, ctx.client, ids)
    return stream_view(stream, names, pins.get(stream_id), removed)


def _signature(offers: list[dict[str, Any]] | list[BaseOffer]) -> list[tuple[int, int]]:
    items = [(o.offer_id, o.share) if isinstance(o, BaseOffer) else (o["offer_id"], o["share"]) for o in offers]
    return sorted(items)
