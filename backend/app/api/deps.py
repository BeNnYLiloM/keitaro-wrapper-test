from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.db import get_session
from app.keitaro import KeitaroClient
from app.services.context import Ctx
from app.services.offers import OfferCatalog
from app.services.references import References


def get_keitaro(request: Request) -> KeitaroClient:
    return request.app.state.keitaro


def get_catalog(request: Request) -> OfferCatalog:
    return request.app.state.offer_catalog


def get_references(request: Request) -> References:
    return request.app.state.references


def get_ctx(
    session: Annotated[AsyncSession, Depends(get_session)],
    client: Annotated[KeitaroClient, Depends(get_keitaro)],
    catalog: Annotated[OfferCatalog, Depends(get_catalog)],
    refs: Annotated[References, Depends(get_references)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> Ctx:
    return Ctx(session=session, client=client, catalog=catalog, refs=refs, settings=settings)


CtxDep = Annotated[Ctx, Depends(get_ctx)]
