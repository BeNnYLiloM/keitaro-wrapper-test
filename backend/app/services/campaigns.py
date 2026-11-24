"""Создание, просмотр и удаление кампаний."""

import asyncio
import logging
from typing import Any

from sqlalchemy import delete, select

from app.keitaro import KeitaroError
from app.models import Campaign, OperationLog, PinnedOffer, RemovedOffer
from app.schemas import CampaignCreate, CampaignDetails, CampaignOut
from app.services.context import Ctx
from app.services.errors import ServiceError
from app.services.operations import log_operation
from app.services.archive import load_removed
from app.services.pins import load_pins
from app.services.views import campaign_view, offer_ids, stream_view

logger = logging.getLogger(__name__)


def build_campaign_payload(ctx: Ctx, name: str) -> dict[str, Any]:
    s = ctx.settings
    return {
        "name": name,
        "type": "position",  # ротация потоков по позиции
        "domain_id": s.keitaro_domain_id,
        "group_id": s.keitaro_group_id,
        "traffic_source_id": s.keitaro_traffic_source_id,
        "cost_type": "CPC",
        "cost_auto": True,  # стоимость из параметра 'cost'
    }


def build_google_stream_payload(ctx: Ctx, campaign_id: int, geo: list[str]) -> dict[str, Any]:
    return {
        "campaign_id": campaign_id,
        "name": f"Geo {','.join(geo)} → Google",
        "type": "regular",
        "schema": "redirect",
        "position": 1,
        "action_type": "http",
        "action_payload": ctx.settings.google_url,
        "filters": [{"name": "country", "mode": "accept", "payload": geo}],
    }


def build_offers_stream_payload(campaign_id: int, offer_id: int) -> dict[str, Any]:
    return {
        "campaign_id": campaign_id,
        "name": "Офферы",
        "type": "default",
        "schema": "landings",
        "position": 2,
        "offers": [{"offer_id": offer_id, "share": 100, "state": "active"}],
    }


async def create_campaign(ctx: Ctx, data: CampaignCreate) -> CampaignDetails:
    offer = await ctx.catalog.get(ctx.session, ctx.client, data.offer_id)
    if offer is None:
        raise ServiceError(422, f"Оффер #{data.offer_id} не найден в Keitaro")

    request_info = {"name": data.name, "geo": data.geo, "offer_id": data.offer_id}

    try:
        campaign = await ctx.client.create_campaign(build_campaign_payload(ctx, data.name))
    except KeitaroError as exc:
        log_operation(ctx.session, "create_campaign", payload=request_info, error=exc.message)
        await ctx.session.commit()
        raise
    if not isinstance(campaign, dict) or campaign.get("id") is None:
        raise ServiceError(502, f"Keitaro вернул неожиданный ответ на создание кампании: {campaign!r}")
    campaign_id = int(campaign["id"])

    try:
        google_stream = await ctx.client.create_stream(build_google_stream_payload(ctx, campaign_id, data.geo))
        offers_stream = await ctx.client.create_stream(build_offers_stream_payload(campaign_id, data.offer_id))
    except KeitaroError as exc:
        # Не оставляем в Keitaro полусобранную кампанию без потоков
        rollback_note = await _rollback_campaign(ctx, campaign_id)
        log_operation(
            ctx.session, "create_campaign", campaign_id=campaign_id, payload=request_info, error=exc.message
        )
        await ctx.session.commit()
        raise ServiceError(502, f"Keitaro не создал поток: {exc.message}. {rollback_note}") from exc

    ctx.session.add(
        Campaign(
            keitaro_id=campaign_id,
            name=data.name,
            alias=campaign.get("alias"),
            geo=data.geo,
            initial_offer_id=data.offer_id,
            google_stream_id=_id(google_stream),
            offers_stream_id=_id(offers_stream),
        )
    )
    log_operation(
        ctx.session,
        "create_campaign",
        campaign_id=campaign_id,
        payload={**request_info, "streams": [_id(google_stream), _id(offers_stream)]},
    )
    await ctx.session.commit()
    return await get_campaign_details(ctx, campaign_id)


async def _rollback_campaign(ctx: Ctx, campaign_id: int) -> str:
    try:
        await ctx.client.delete_campaign(campaign_id)
    except KeitaroError as exc:
        logger.error("Не удалось удалить недосозданную кампанию %s: %s", campaign_id, exc)
        return f"Кампанию #{campaign_id} удалить не удалось — удалите её вручную"
    return f"Кампания #{campaign_id} удалена"


async def get_campaign_details(ctx: Ctx, campaign_id: int) -> CampaignDetails:
    campaign, streams = await asyncio.gather(
        ctx.client.get_campaign(campaign_id),
        ctx.client.list_campaign_streams(campaign_id),
    )
    refs = await ctx.refs.get(ctx.client)
    stream_ids = [int(s["id"]) for s in streams if s.get("id") is not None]
    pins = await load_pins(ctx.session, stream_ids)
    removed = await load_removed(ctx.session, stream_ids)
    removed_ids = {r.offer_id for rows in removed.values() for r in rows}
    names = await ctx.catalog.names(ctx.session, ctx.client, offer_ids(streams) | removed_ids)
    local = await ctx.session.scalar(select(Campaign).where(Campaign.keitaro_id == campaign_id))
    streams_sorted = sorted(streams, key=lambda s: (s.get("position") is None, s.get("position") or 0, s.get("id")))
    return CampaignDetails(
        **campaign_view(campaign, refs, local, ctx.settings),
        streams=[
            stream_view(s, names, pins.get(int(s["id"])), removed.get(int(s["id"]))) for s in streams_sorted
        ],
    )


async def list_campaigns(ctx: Ctx, offset: int, limit: int) -> list[CampaignOut]:
    campaigns = await ctx.client.list_campaigns(offset=offset, limit=limit)
    refs = await ctx.refs.get(ctx.client)
    ids = [int(c["id"]) for c in campaigns if c.get("id") is not None]
    local_rows = (await ctx.session.scalars(select(Campaign).where(Campaign.keitaro_id.in_(ids)))).all()
    local = {row.keitaro_id: row for row in local_rows}
    return [
        CampaignOut(**campaign_view(c, refs, local.get(int(c["id"])), ctx.settings))
        for c in campaigns
        if c.get("id") is not None
    ]


async def delete_campaign(ctx: Ctx, campaign_id: int) -> None:
    streams = await ctx.client.list_campaign_streams(campaign_id)
    await ctx.client.delete_campaign(campaign_id)
    stream_ids = [int(s["id"]) for s in streams if s.get("id") is not None]
    if stream_ids:
        await ctx.session.execute(delete(PinnedOffer).where(PinnedOffer.stream_id.in_(stream_ids)))
        await ctx.session.execute(delete(RemovedOffer).where(RemovedOffer.stream_id.in_(stream_ids)))
    await ctx.session.execute(delete(Campaign).where(Campaign.keitaro_id == campaign_id))
    log_operation(ctx.session, "delete_campaign", campaign_id=campaign_id)
    await ctx.session.commit()


async def campaign_operations(ctx: Ctx, campaign_id: int, limit: int = 50) -> list[OperationLog]:
    stmt = (
        select(OperationLog)
        .where(OperationLog.campaign_id == campaign_id)
        .order_by(OperationLog.created_at.desc(), OperationLog.id.desc())
        .limit(limit)
    )
    return list((await ctx.session.scalars(stmt)).all())


def _id(raw: Any) -> int | None:
    if isinstance(raw, dict) and raw.get("id") is not None:
        return int(raw["id"])
    return None
