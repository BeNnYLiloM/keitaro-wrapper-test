import json

import pytest
from sqlalchemy import select

from app.models import Campaign, OperationLog
from app.schemas import CampaignCreate
from app.services import campaigns
from app.services.errors import ServiceError
from tests.conftest import FakeKeitaro


async def test_create_campaign_builds_two_streams(ctx, fake: FakeKeitaro) -> None:
    result = await campaigns.create_campaign(ctx, CampaignCreate(name="Test AU", geo="AU,MX", offer_id=3717))

    # кампания: домен, группа, источник
    create_call = fake.router.calls[_index_of(fake, "POST", "/campaigns")]
    body = json.loads(create_call.request.content)
    assert body["name"] == "Test AU"
    assert (body["domain_id"], body["group_id"], body["traffic_source_id"]) == (1813, 10332, 836)

    assert result.name == "Test AU"
    assert result.domain.name == "in.posdk.xyz"
    assert result.group.name == "FORTESTS"
    assert result.traffic_source.name == "FORTESTS"
    assert result.tracking_url == "https://in.posdk.xyz/abc123"
    assert result.keitaro_url == f"https://keitaro.test/admin/#!/campaign.editor/{result.id}"
    assert result.created_by_wrapper is True
    assert result.geo == ["AU", "MX"]

    google, offers = result.streams
    # поток 1: страны → редирект на Google
    assert google.position == 1
    assert google.stream_schema == "redirect"
    assert google.action_payload == "https://google.com"
    assert google.filters == [{"name": "country", "mode": "accept", "payload": ["AU", "MX"]}]
    assert google.editable is False
    # поток 2: выбранный оффер на 100%
    assert offers.position == 2
    assert offers.stream_schema == "landings"
    assert [(o.offer_id, o.name, o.share) for o in offers.offers] == [(3717, "Cardio AU", 100)]
    assert offers.editable is True

    row = await ctx.session.scalar(select(Campaign))
    assert row.keitaro_id == result.id
    assert row.google_stream_id == google.id
    assert row.offers_stream_id == offers.id
    log = (await ctx.session.scalars(select(OperationLog))).all()
    assert [(e.operation, e.success) for e in log] == [("create_campaign", True)]


async def test_create_campaign_rolls_back_when_stream_fails(ctx, fake: FakeKeitaro) -> None:
    fake.fail_stream_create_on = 2  # второй поток не создастся

    with pytest.raises(ServiceError) as exc_info:
        await campaigns.create_campaign(ctx, CampaignCreate(name="Broken", geo="AU", offer_id=101))

    assert exc_info.value.status_code == 502
    assert "удалена" in exc_info.value.detail
    assert fake.campaigns == {}  # кампания удалена в Keitaro
    assert fake.streams == {}
    assert await ctx.session.scalar(select(Campaign)) is None
    log = (await ctx.session.scalars(select(OperationLog))).all()
    assert [(e.operation, e.success) for e in log] == [("create_campaign", False)]


async def test_create_campaign_unknown_offer(ctx, fake: FakeKeitaro) -> None:
    with pytest.raises(ServiceError) as exc_info:
        await campaigns.create_campaign(ctx, CampaignCreate(name="X", geo="AU", offer_id=999999))
    assert exc_info.value.status_code == 422
    assert fake.campaigns == {}


async def test_list_campaigns_marks_own(ctx, fake: FakeKeitaro) -> None:
    created = await campaigns.create_campaign(ctx, CampaignCreate(name="Mine", geo="RO", offer_id=101))
    fake.campaigns[1] = {"id": 1, "name": "Foreign", "alias": "zzz", "domain_id": 1813}

    items = await campaigns.list_campaigns(ctx, 0, 50)
    by_id = {c.id: c for c in items}
    assert by_id[created.id].created_by_wrapper is True
    assert by_id[created.id].geo == ["RO"]
    assert by_id[1].created_by_wrapper is False


def _index_of(fake: FakeKeitaro, method: str, path: str) -> int:
    for i, call in enumerate(fake.router.calls):
        if call.request.method == method and call.request.url.path.endswith(path):
            return i
    raise AssertionError(f"{method} {path} не вызывался")
