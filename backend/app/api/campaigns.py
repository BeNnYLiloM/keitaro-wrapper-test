from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.deps import CtxDep
from app.schemas import CampaignCreate, CampaignDetails, CampaignOut, OperationOut, PublishOffers, StreamOut
from app.services import campaigns, editor

router = APIRouter(prefix="/api", tags=["campaigns"])


@router.get("/campaigns", response_model=list[CampaignOut], summary="Кампании из Keitaro, новые сверху")
async def list_campaigns(
    ctx: CtxDep,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[CampaignOut]:
    return await campaigns.list_campaigns(ctx, offset, limit)


@router.post(
    "/campaigns",
    response_model=CampaignDetails,
    status_code=status.HTTP_201_CREATED,
    summary="Создать кампанию: поток «гео → Google» и поток с оффером",
)
async def create_campaign(ctx: CtxDep, data: CampaignCreate) -> CampaignDetails:
    return await campaigns.create_campaign(ctx, data)


@router.get("/campaigns/{campaign_id}", response_model=CampaignDetails, summary="Кампания с потоками и офферами")
async def get_campaign(ctx: CtxDep, campaign_id: int) -> CampaignDetails:
    return await campaigns.get_campaign_details(ctx, campaign_id)


@router.delete("/campaigns/{campaign_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Удалить кампанию")
async def delete_campaign(ctx: CtxDep, campaign_id: int) -> None:
    await campaigns.delete_campaign(ctx, campaign_id)


@router.get(
    "/campaigns/{campaign_id}/operations",
    response_model=list[OperationOut],
    summary="История изменений кампании через обёртку",
)
async def campaign_operations(ctx: CtxDep, campaign_id: int) -> list[OperationOut]:
    rows = await campaigns.campaign_operations(ctx, campaign_id)
    return [OperationOut.model_validate(row) for row in rows]


@router.get("/streams/{stream_id}", response_model=StreamOut, summary="Поток с офферами и закреплениями")
async def get_stream(ctx: CtxDep, stream_id: int) -> StreamOut:
    return await editor.get_stream(ctx, stream_id)


@router.put(
    "/streams/{stream_id}/offers",
    response_model=StreamOut,
    summary="Опубликовать состав офферов потока",
    description="Принимает итоговый список офферов (черновик из редактора). Закреплённые офферы сохраняют "
    "свою долю, остальные поровну делят остаток. Удалённые офферы — те, которых нет в списке.",
)
async def publish_offers(ctx: CtxDep, stream_id: int, data: PublishOffers) -> StreamOut:
    return await editor.publish_offers(ctx, stream_id, data)


@router.put(
    "/streams/{stream_id}/offers/{offer_id}/pin",
    response_model=StreamOut,
    summary="Закрепить текущую долю оффера (сразу, без публикации)",
)
async def pin_offer(ctx: CtxDep, stream_id: int, offer_id: int) -> StreamOut:
    return await editor.pin_offer(ctx, stream_id, offer_id)


@router.delete(
    "/streams/{stream_id}/offers/{offer_id}/pin",
    response_model=StreamOut,
    summary="Открепить долю оффера",
)
async def unpin_offer(ctx: CtxDep, stream_id: int, offer_id: int) -> StreamOut:
    return await editor.unpin_offer(ctx, stream_id, offer_id)
