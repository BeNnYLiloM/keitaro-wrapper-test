from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import CtxDep
from app.schemas import OfferOut

router = APIRouter(prefix="/api/offers", tags=["offers"])


@router.get("", response_model=list[OfferOut], summary="Поиск офферов для автокомплита")
async def search_offers(
    ctx: CtxDep,
    q: Annotated[str, Query(max_length=200, description="Часть названия или id")] = "",
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> list[OfferOut]:
    rows = await ctx.catalog.search(ctx.session, ctx.client, q, limit)
    return [OfferOut.model_validate(row) for row in rows]


@router.post("/refresh", summary="Принудительно перечитать каталог офферов из Keitaro")
async def refresh_offers(ctx: CtxDep) -> dict[str, int]:
    count = await ctx.catalog.refresh(ctx.session, ctx.client, force=True)
    return {"count": count}
