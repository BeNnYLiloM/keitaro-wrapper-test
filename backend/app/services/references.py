"""Справочники Keitaro (домены, группы кампаний, источники) с кэшем в памяти.

Они только для чтения и меняются редко, поэтому достаточно держать их в памяти
несколько минут. Используются, чтобы показывать названия вместо голых id.
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field

from app.keitaro import KeitaroClient, KeitaroError

logger = logging.getLogger(__name__)


@dataclass
class ReferenceData:
    domains: dict[int, str] = field(default_factory=dict)
    groups: dict[int, str] = field(default_factory=dict)
    traffic_sources: dict[int, str] = field(default_factory=dict)


class References:
    def __init__(self, ttl_seconds: int = 600) -> None:
        self.ttl_seconds = ttl_seconds
        self._data: ReferenceData | None = None
        self._loaded_at = 0.0
        self._lock = asyncio.Lock()

    async def get(self, client: KeitaroClient) -> ReferenceData:
        async with self._lock:
            if self._data is not None and time.monotonic() - self._loaded_at < self.ttl_seconds:
                return self._data
            domains, groups, sources = await asyncio.gather(
                client.list_domains(),
                client.list_campaign_groups(),
                client.list_traffic_sources(),
                return_exceptions=True,
            )
            data = ReferenceData(
                domains=_index(domains, "domains"),
                groups=_index(groups, "groups"),
                traffic_sources=_index(sources, "traffic_sources"),
            )
            # Кэшируем только полностью успешную загрузку, иначе попробуем снова в следующий раз
            if not any(isinstance(x, Exception) for x in (domains, groups, sources)):
                self._data = data
                self._loaded_at = time.monotonic()
            return data


def _index(result: object, label: str) -> dict[int, str]:
    if isinstance(result, KeitaroError):
        logger.warning("Не удалось загрузить справочник %s: %s", label, result)
        return {}
    if isinstance(result, Exception):
        raise result
    index: dict[int, str] = {}
    for item in result or []:  # type: ignore[union-attr]
        if isinstance(item, dict) and item.get("id") is not None:
            index[int(item["id"])] = str(item.get("name") or "")
    return index


def domain_url(domain_name: str | None) -> str | None:
    """'in.posdk.xyz' / 'https://in.posdk.xyz/' → 'https://in.posdk.xyz'."""
    if not domain_name:
        return None
    name = domain_name.strip().rstrip("/")
    if not name.startswith(("http://", "https://")):
        name = f"https://{name}"
    return name
