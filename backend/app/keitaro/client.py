"""Тонкий асинхронный клиент Keitaro Admin API.

Методы возвращают JSON стенда как есть (dict / list). Разбор полей и бизнес-логика
живут в сервисах, чтобы клиент оставался простой обёрткой над HTTP.
"""

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

JSON = dict[str, Any]


class KeitaroError(Exception):
    """Ошибка обращения к Keitaro: HTTP-код ответа (или 0, если стенд недоступен) и текст."""

    def __init__(self, status_code: int, message: str, method: str = "", path: str = "") -> None:
        self.status_code = status_code
        self.message = message
        self.method = method
        self.path = path
        super().__init__(f"Keitaro {method} {path} -> {status_code}: {message}")


class KeitaroClient:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        timeout: float = 20.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/") + "/",
            headers={"Api-Key": api_key, "Accept": "application/json"},
            timeout=timeout,
            transport=transport,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        try:
            response = await self._client.request(method, path.lstrip("/"), **kwargs)
        except httpx.HTTPError as exc:
            raise KeitaroError(0, f"Keitaro недоступен: {exc!r}", method, path) from exc

        if response.status_code >= 400:
            raise KeitaroError(response.status_code, _error_message(response), method, path)

        if not response.content:
            return None
        try:
            return response.json()
        except ValueError:
            return response.text

    # --- кампании -----------------------------------------------------------

    async def list_campaigns(self, offset: int = 0, limit: int = 50) -> list[JSON]:
        return _as_list(await self._request("GET", "campaigns", params={"offset": offset, "limit": limit}))

    async def get_campaign(self, campaign_id: int) -> JSON:
        return await self._request("GET", f"campaigns/{campaign_id}")

    async def create_campaign(self, payload: JSON) -> JSON:
        return await self._request("POST", "campaigns", json=payload)

    async def update_campaign(self, campaign_id: int, payload: JSON) -> JSON:
        return await self._request("PUT", f"campaigns/{campaign_id}", json=payload)

    async def delete_campaign(self, campaign_id: int) -> None:
        await self._request("DELETE", f"campaigns/{campaign_id}")

    async def list_campaign_streams(self, campaign_id: int) -> list[JSON]:
        return _as_list(await self._request("GET", f"campaigns/{campaign_id}/streams"))

    # --- потоки -------------------------------------------------------------

    async def create_stream(self, payload: JSON) -> JSON:
        return await self._request("POST", "streams", json=payload)

    async def get_stream(self, stream_id: int) -> JSON:
        return await self._request("GET", f"streams/{stream_id}")

    async def update_stream(self, stream_id: int, payload: JSON) -> JSON:
        return await self._request("PUT", f"streams/{stream_id}", json=payload)

    async def delete_stream(self, stream_id: int) -> None:
        await self._request("DELETE", f"streams/{stream_id}")

    # --- справочники (только чтение) ---------------------------------------

    async def list_offers(self) -> list[JSON]:
        return _as_list(await self._request("GET", "offers"))

    async def get_offer(self, offer_id: int) -> JSON:
        return await self._request("GET", f"offers/{offer_id}")

    async def list_campaign_groups(self) -> list[JSON]:
        return _as_list(await self._request("GET", "groups", params={"type": "campaigns"}))

    async def list_domains(self) -> list[JSON]:
        return _as_list(await self._request("GET", "domains"))

    async def list_traffic_sources(self) -> list[JSON]:
        return _as_list(await self._request("GET", "traffic_sources"))


def _as_list(data: Any) -> list[JSON]:
    """Keitaro отдаёт списки массивом; на всякий случай понимаем и обёртку {"data": [...]}."""
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("data", "items", "rows"):
            if isinstance(data.get(key), list):
                return data[key]
    return []


def _error_message(response: httpx.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        return response.text[:500] or response.reason_phrase
    if isinstance(body, dict):
        for key in ("error", "message", "errors", "detail"):
            if body.get(key):
                value = body[key]
                return value if isinstance(value, str) else str(value)
    return str(body)[:500]
