"""Общие фикстуры: SQLite в памяти вместо Postgres и фейковый стенд Keitaro на respx."""

import json
from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest
import respx
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import Settings
from app.keitaro import KeitaroClient
from app.models import Base
from app.services.context import Ctx
from app.services.offers import OfferCatalog
from app.services.references import References

BASE_URL = "https://keitaro.test/admin_api/v1"

OFFERS = [
    {"id": 101, "name": "Miaflow [BEAUTY-RO-BE_0009]", "state": "active", "country": ["RO"]},
    {"id": 102, "name": "Miaflow [BEAUTY-RO-BE_0008]", "state": "active", "country": ["RO"]},
    {"id": 103, "name": "Slimfit MX", "state": "active", "country": ["MX"]},
    {"id": 3717, "name": "Cardio AU", "state": "active", "country": ["AU"]},
]


class FakeKeitaro:
    """Минимальная модель стенда: хранит кампании и потоки, понимает нужные эндпоинты."""

    def __init__(self, router: respx.MockRouter) -> None:
        self.router = router
        self.campaigns: dict[int, dict[str, Any]] = {}
        self.streams: dict[int, dict[str, Any]] = {}
        self._next_id = 1000
        self.fail_stream_create_on: int | None = None  # номер вызова POST /streams, который упадёт
        self._stream_creates = 0
        self._install()

    def _id(self) -> int:
        self._next_id += 1
        return self._next_id

    def add_stream(self, **fields: Any) -> dict[str, Any]:
        stream = {"id": self._id(), "type": "regular", "state": "active", "filters": [], "offers": [], **fields}
        self.streams[stream["id"]] = stream
        return stream

    def _install(self) -> None:
        r = self.router
        r.get("/offers").mock(side_effect=lambda req: httpx.Response(200, json=OFFERS))
        r.get(path__regex=r"/offers/(?P<oid>\d+)$").mock(side_effect=self._get_offer)
        r.get("/domains").respond(json=[{"id": 1813, "name": "in.posdk.xyz"}])
        r.get("/groups").respond(json=[{"id": 10332, "name": "FORTESTS", "type": "campaigns"}])
        r.get("/traffic_sources").respond(json=[{"id": 836, "name": "FORTESTS"}])

        r.get("/campaigns", name="list_campaigns").mock(side_effect=lambda req: httpx.Response(200, json=list(self.campaigns.values())[::-1]))
        r.post("/campaigns").mock(side_effect=self._create_campaign)
        r.get(path__regex=r"/campaigns/(?P<cid>\d+)$").mock(side_effect=self._get_campaign)
        r.delete(path__regex=r"/campaigns/(?P<cid>\d+)$").mock(side_effect=self._delete_campaign)
        r.get(path__regex=r"/campaigns/(?P<cid>\d+)/streams$").mock(side_effect=self._campaign_streams)

        r.post("/streams").mock(side_effect=self._create_stream)
        r.get(path__regex=r"/streams/(?P<sid>\d+)$").mock(side_effect=self._get_stream)
        r.put(path__regex=r"/streams/(?P<sid>\d+)$").mock(side_effect=self._update_stream)

    # --- обработчики -------------------------------------------------------

    def _get_offer(self, request: httpx.Request, oid: str) -> httpx.Response:
        offer = next((o for o in OFFERS if o["id"] == int(oid)), None)
        return httpx.Response(200, json=offer) if offer else httpx.Response(404, json={"error": "Not found"})

    def _create_campaign(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        campaign = {"id": self._id(), "alias": body.get("alias") or "abc123", "state": "active", **body}
        self.campaigns[campaign["id"]] = campaign
        return httpx.Response(200, json=campaign)

    def _get_campaign(self, request: httpx.Request, cid: str) -> httpx.Response:
        campaign = self.campaigns.get(int(cid))
        return httpx.Response(200, json=campaign) if campaign else httpx.Response(404, json={"error": "Not found"})

    def _delete_campaign(self, request: httpx.Request, cid: str) -> httpx.Response:
        self.campaigns.pop(int(cid), None)
        for sid in [s for s, v in self.streams.items() if v["campaign_id"] == int(cid)]:
            del self.streams[sid]
        return httpx.Response(204)

    def _campaign_streams(self, request: httpx.Request, cid: str) -> httpx.Response:
        streams = [s for s in self.streams.values() if s["campaign_id"] == int(cid)]
        return httpx.Response(200, json=sorted(streams, key=lambda s: s.get("position") or 0))

    def _create_stream(self, request: httpx.Request) -> httpx.Response:
        self._stream_creates += 1
        if self.fail_stream_create_on == self._stream_creates:
            return httpx.Response(500, json={"error": "Internal error"})
        body = json.loads(request.content)
        return httpx.Response(200, json=self.add_stream(**body))

    def _get_stream(self, request: httpx.Request, sid: str) -> httpx.Response:
        stream = self.streams.get(int(sid))
        return httpx.Response(200, json=stream) if stream else httpx.Response(404, json={"error": "Not found"})

    def _update_stream(self, request: httpx.Request, sid: str) -> httpx.Response:
        stream = self.streams.get(int(sid))
        if not stream:
            return httpx.Response(404, json={"error": "Not found"})
        stream.update(json.loads(request.content))
        return httpx.Response(200, json=stream)


@pytest.fixture
def settings() -> Settings:
    return Settings(
        keitaro_api_url=BASE_URL,
        keitaro_api_key="test-key",
        keitaro_admin_url="https://keitaro.test/admin",
        database_url="sqlite+aiosqlite://",
        frontend_dist="__no_frontend__",
    )


@pytest.fixture
async def session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        yield s
    await engine.dispose()


@pytest.fixture
def fake() -> FakeKeitaro:
    with respx.mock(base_url=BASE_URL, assert_all_called=False) as router:
        yield FakeKeitaro(router)


@pytest.fixture
async def client(fake: FakeKeitaro) -> AsyncIterator[KeitaroClient]:
    c = KeitaroClient(BASE_URL, "test-key")
    yield c
    await c.aclose()


@pytest.fixture
def ctx(session: AsyncSession, client: KeitaroClient, settings: Settings) -> Ctx:
    return Ctx(session=session, client=client, catalog=OfferCatalog(), refs=References(), settings=settings)
