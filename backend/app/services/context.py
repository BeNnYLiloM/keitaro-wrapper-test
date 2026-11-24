from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.keitaro import KeitaroClient
from app.services.offers import OfferCatalog
from app.services.references import References


@dataclass
class Ctx:
    """Всё, что нужно сервисам для работы: БД, клиент Keitaro, кэши и настройки."""

    session: AsyncSession
    client: KeitaroClient
    catalog: OfferCatalog
    refs: References
    settings: Settings
