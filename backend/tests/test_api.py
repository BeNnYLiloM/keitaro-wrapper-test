"""Проверка HTTP-слоя: маршруты, валидация, маппинг ошибок Keitaro."""

from collections.abc import AsyncIterator

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import get_session
from app.keitaro import KeitaroClient
from app.main import create_app
from app.services.offers import OfferCatalog
from app.services.references import References
from tests.conftest import FakeKeitaro


@pytest.fixture
async def api(settings, session: AsyncSession, client: KeitaroClient) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app(settings, keitaro=client)
    # ASGITransport не запускает lifespan, поэтому состояние выставляем сами
    app.state.keitaro = client
    app.state.offer_catalog = OfferCatalog()
    app.state.references = References()

    async def _session() -> AsyncIterator[AsyncSession]:
        yield session

    app.dependency_overrides[get_session] = _session
    app.dependency_overrides[get_settings] = lambda: settings
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://app") as c:
        yield c


async def test_offer_search(api: httpx.AsyncClient, fake: FakeKeitaro) -> None:
    resp = await api.get("/api/offers", params={"q": "miaflow"})
    assert resp.status_code == 200
    assert [o["id"] for o in resp.json()] == [101, 102]

    resp = await api.get("/api/offers", params={"q": "37"})
    assert [o["id"] for o in resp.json()] == [3717]


async def test_create_and_edit_flow(api: httpx.AsyncClient, fake: FakeKeitaro) -> None:
    resp = await api.post("/api/campaigns", json={"name": "Flow", "geo": "au", "offer_id": 101})
    assert resp.status_code == 201, resp.text
    campaign = resp.json()
    offers_stream = campaign["streams"][1]
    assert offers_stream["offers"][0]["share"] == 100

    url = f"/api/streams/{offers_stream['id']}/offers"
    base = [{"offer_id": 101, "share": 100}]
    resp = await api.put(url, json={"offers": [{"offer_id": 101}, {"offer_id": 102}], "base": base})
    assert resp.status_code == 200, resp.text
    assert [o["share"] for o in resp.json()["offers"]] == [50, 50]

    # закрепляем 102 (сразу, без публикации), затем удаляем 101 и добавляем 103 и 3717
    resp = await api.put(f"{url}/102/pin")
    assert resp.status_code == 200, resp.text
    assert [(o["offer_id"], o["pinned"]) for o in resp.json()["offers"]] == [(101, False), (102, True)]

    resp = await api.put(url, json={"offers": [{"offer_id": 102}, {"offer_id": 103}, {"offer_id": 3717}]})
    assert resp.status_code == 200, resp.text
    assert [(o["offer_id"], o["share"], o["pinned"]) for o in resp.json()["offers"]] == [
        (102, 50, True),
        (103, 25, False),
        (3717, 25, False),
    ]

    resp = await api.get(f"/api/campaigns/{campaign['id']}")
    assert [o["pinned"] for o in resp.json()["streams"][1]["offers"]] == [True, False, False]

    resp = await api.put(url, json={"offers": [{"offer_id": 102}], "base": base})
    assert resp.status_code == 409

    resp = await api.get(f"/api/campaigns/{campaign['id']}/operations")
    assert [op["operation"] for op in resp.json()] == [
        "publish_offers",
        "pin_offer",
        "publish_offers",
        "create_campaign",
    ]

    resp = await api.delete(f"{url}/102/pin")
    assert resp.status_code == 200
    assert not any(o["pinned"] for o in resp.json()["offers"])


async def test_validation_error(api: httpx.AsyncClient, fake: FakeKeitaro) -> None:
    resp = await api.post("/api/campaigns", json={"name": "X", "geo": "QQ", "offer_id": 101})
    assert resp.status_code == 422
    assert "QQ" in resp.text


async def test_keitaro_errors_are_mapped(api: httpx.AsyncClient, fake: FakeKeitaro) -> None:
    resp = await api.get("/api/campaigns/424242")
    assert resp.status_code == 404

    route = fake.router["list_campaigns"]
    route.side_effect = None
    route.return_value = httpx.Response(401, json={"error": "Unauthorized"})
    resp = await api.get("/api/campaigns")
    assert resp.status_code == 502
    assert "API-ключ" in resp.json()["detail"]


async def test_meta(api: httpx.AsyncClient, fake: FakeKeitaro) -> None:
    resp = await api.get("/api/meta")
    assert resp.json()["group"] == {"id": 10332, "name": "FORTESTS"}
    assert resp.json()["domain"] == {"id": 1813, "name": "in.posdk.xyz"}
