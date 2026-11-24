from fastapi import APIRouter

from app.api.deps import CtxDep
from app.schemas import MetaOut, RefItem
from app.services.countries import COUNTRY_CODES

router = APIRouter(prefix="/api", tags=["meta"])


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/countries", response_model=list[str], summary="Коды стран ISO 3166-1 alpha-2")
async def countries() -> tuple[str, ...]:
    return COUNTRY_CODES


@router.get("/meta", response_model=MetaOut, summary="Домен, группа и источник для новых кампаний")
async def meta(ctx: CtxDep) -> MetaOut:
    refs = await ctx.refs.get(ctx.client)
    s = ctx.settings
    return MetaOut(
        keitaro_admin_url=s.keitaro_admin_url,
        google_url=s.google_url,
        domain=RefItem(id=s.keitaro_domain_id, name=refs.domains.get(s.keitaro_domain_id)),
        group=RefItem(id=s.keitaro_group_id, name=refs.groups.get(s.keitaro_group_id)),
        traffic_source=RefItem(
            id=s.keitaro_traffic_source_id, name=refs.traffic_sources.get(s.keitaro_traffic_source_id)
        ),
    )
