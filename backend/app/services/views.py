"""Преобразование сырого JSON Keitaro в схемы нашего API."""

from typing import Any

from app.config import Settings
from app.models import Campaign, RemovedOffer
from app.schemas import CampaignOut, RefItem, RemovedStreamOffer, StreamOffer, StreamOut
from app.services.references import ReferenceData, domain_url

OFFERS_SCHEMA = "landings"


def is_offers_stream(raw: dict[str, Any]) -> bool:
    """Поток, в котором можно редактировать офферы (схема «Лендинги и офферы»)."""
    return raw.get("schema") == OFFERS_SCHEMA


def stream_offers(raw: dict[str, Any]) -> list[dict[str, Any]]:
    """Офферы потока в нормализованном виде: offer_id, share, state."""
    result = []
    for item in raw.get("offers") or []:
        if not isinstance(item, dict) or item.get("offer_id") is None:
            continue
        result.append(
            {
                "offer_id": int(item["offer_id"]),
                "share": int(item.get("share") or 0),
                "state": item.get("state") or "active",
            }
        )
    return result


def offer_ids(streams: list[dict[str, Any]]) -> set[int]:
    return {o["offer_id"] for s in streams for o in stream_offers(s)}


def stream_view(
    raw: dict[str, Any],
    names: dict[int, str],
    pinned: set[int] | None = None,
    removed: list[RemovedOffer] | None = None,
) -> StreamOut:
    pinned = pinned or set()
    present = {o["offer_id"] for o in stream_offers(raw)}
    removed_offers = [
        RemovedStreamOffer(
            offer_id=r.offer_id,
            name=names.get(r.offer_id, f"Offer #{r.offer_id}"),
            share=r.share,
            state=r.state,
            removed_at=r.removed_at,
        )
        for r in removed or []
        if r.offer_id not in present  # оффер успели вернуть в поток в обход обёртки
    ]
    offers = [
        StreamOffer(
            offer_id=o["offer_id"],
            name=names.get(o["offer_id"], f"Offer #{o['offer_id']}"),
            share=o["share"],
            state=o["state"],
            pinned=o["offer_id"] in pinned,
        )
        for o in stream_offers(raw)
    ]
    filters = [f for f in raw.get("filters") or [] if isinstance(f, dict)]
    return StreamOut(
        id=int(raw["id"]),
        name=raw.get("name"),
        type=raw.get("type"),
        stream_schema=raw.get("schema"),
        position=_int(raw.get("position")),
        state=raw.get("state"),
        action_type=raw.get("action_type"),
        action_payload=raw.get("action_payload"),
        filters=filters,
        offers=offers,
        removed_offers=removed_offers,
        total_share=sum(o.share for o in offers),
        editable=is_offers_stream(raw),
    )


def campaign_view(
    raw: dict[str, Any], refs: ReferenceData, local: Campaign | None, settings: Settings
) -> dict[str, Any]:
    campaign_id = int(raw["id"])
    domain_id = _int(raw.get("domain_id"))
    group_id = _int(raw.get("group_id"))
    source_id = _int(raw.get("traffic_source_id"))
    alias = raw.get("alias")
    base = domain_url(refs.domains.get(domain_id)) if domain_id else None
    return CampaignOut(
        id=campaign_id,
        name=str(raw.get("name") or ""),
        alias=alias,
        state=raw.get("state"),
        domain=_ref(domain_id, refs.domains),
        group=_ref(group_id, refs.groups),
        traffic_source=_ref(source_id, refs.traffic_sources),
        keitaro_url=settings.campaign_admin_link(campaign_id),
        tracking_url=f"{base}/{alias}" if base and alias else None,
        created_by_wrapper=local is not None,
        geo=local.geo if local else None,
    ).model_dump()


def _ref(item_id: int | None, index: dict[int, str]) -> RefItem | None:
    if not item_id:
        return None
    return RefItem(id=item_id, name=index.get(item_id))


def _int(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None
