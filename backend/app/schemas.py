"""Схемы запросов и ответов нашего API (то, что видит фронтенд)."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.services.countries import normalize_geo


class CampaignCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255, examples=["AU test campaign"])
    geo: list[str] = Field(examples=[["AU", "MX"]], description="Коды стран: списком или строкой 'AU,MX'")
    offer_id: int = Field(gt=0, examples=[18001])

    @field_validator("name")
    @classmethod
    def _strip_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Название кампании не может быть пустым")
        return value

    @field_validator("geo", mode="before")
    @classmethod
    def _normalize_geo(cls, value: Any) -> list[str]:
        if not isinstance(value, (str, list)):
            raise ValueError("geo должен быть строкой 'AU,MX' или списком кодов")
        return normalize_geo(value)


class DraftOffer(BaseModel):
    """Оффер в черновике потока, который публикуется целиком."""

    offer_id: int = Field(gt=0)


class BaseOffer(BaseModel):
    offer_id: int
    share: int


class PublishOffers(BaseModel):
    """Итоговый состав офферов потока после редактирования.

    Удалённых офферов в списке нет, новые добавлены. Доли сервер считает сам:
    закреплённые офферы (закрепления хранятся у нас) сохраняют текущую долю,
    остальные поровну делят остаток.
    """

    offers: list[DraftOffer] = Field(min_length=1)
    base: list[BaseOffer] | None = Field(
        default=None,
        description="Состав потока, с которого начиналось редактирование. "
        "Если в Keitaro он успел измениться, публикация отклоняется с 409.",
    )

    @field_validator("offers")
    @classmethod
    def _unique(cls, offers: list[DraftOffer]) -> list[DraftOffer]:
        ids = [o.offer_id for o in offers]
        duplicates = sorted({i for i in ids if ids.count(i) > 1})
        if duplicates:
            raise ValueError(f"Офферы повторяются: {', '.join(map(str, duplicates))}")
        return offers


class OfferOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    state: str | None = None
    country: list[str] | None = None


class RefItem(BaseModel):
    id: int
    name: str | None = None


class MetaOut(BaseModel):
    keitaro_admin_url: str
    google_url: str
    domain: RefItem
    group: RefItem
    traffic_source: RefItem


class StreamOffer(BaseModel):
    offer_id: int
    name: str
    share: int
    state: str
    pinned: bool = False


class RemovedStreamOffer(BaseModel):
    """Удалённый из потока оффер, который можно восстановить."""

    offer_id: int
    name: str
    share: int  # доля на момент удаления
    state: str
    removed_at: datetime


class StreamOut(BaseModel):
    id: int
    name: str | None = None
    type: str | None = None
    stream_schema: str | None = None
    position: int | None = None
    state: str | None = None
    action_type: str | None = None
    action_payload: Any = None
    filters: list[dict[str, Any]] = []
    offers: list[StreamOffer] = []
    removed_offers: list[RemovedStreamOffer] = []
    total_share: int = 0
    editable: bool = False


class CampaignOut(BaseModel):
    id: int
    name: str
    alias: str | None = None
    state: str | None = None
    domain: RefItem | None = None
    group: RefItem | None = None
    traffic_source: RefItem | None = None
    keitaro_url: str
    tracking_url: str | None = None
    created_by_wrapper: bool = False
    geo: list[str] | None = None


class CampaignDetails(CampaignOut):
    streams: list[StreamOut] = []


class OperationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    operation: str
    campaign_id: int | None
    stream_id: int | None
    payload: dict[str, Any] | None
    success: bool
    error: str | None
    created_at: datetime
