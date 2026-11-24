import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse

from app.api import campaigns, meta, offers
from app.config import Settings, get_settings
from app.keitaro import KeitaroClient, KeitaroError
from app.services.errors import ServiceError
from app.services.offers import OfferCatalog
from app.services.references import References

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("app")


def create_app(settings: Settings | None = None, keitaro: KeitaroClient | None = None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if not settings.keitaro_api_key and keitaro is None:
            logger.warning("KEITARO_API_KEY не задан — все запросы к Keitaro будут возвращать 401")
        app.state.keitaro = keitaro or KeitaroClient(
            settings.keitaro_api_url, settings.keitaro_api_key, timeout=settings.keitaro_timeout
        )
        app.state.offer_catalog = OfferCatalog(ttl_seconds=settings.offers_cache_ttl)
        app.state.references = References()
        yield
        await app.state.keitaro.aclose()

    app = FastAPI(title="Keitaro wrapper", version="1.0.0", lifespan=lifespan)

    @app.exception_handler(ServiceError)
    async def _service_error(_: Request, exc: ServiceError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

    @app.exception_handler(KeitaroError)
    async def _keitaro_error(_: Request, exc: KeitaroError) -> JSONResponse:
        logger.warning("%s", exc)
        return JSONResponse(
            status_code=_map_keitaro_status(exc.status_code),
            content={
                "detail": _keitaro_detail(exc),
                "keitaro": {"status": exc.status_code, "method": exc.method, "path": exc.path},
            },
        )

    app.include_router(meta.router)
    app.include_router(offers.router)
    app.include_router(campaigns.router)

    _mount_frontend(app, Path(settings.frontend_dist))
    return app


def _map_keitaro_status(code: int) -> int:
    if code == 404:
        return 404
    if code in (400, 409, 422):
        return 422
    return 502  # 401/403 (ключ), 5xx и недоступность стенда — проблема «вышестоящего» сервиса


def _keitaro_detail(exc: KeitaroError) -> str:
    if exc.status_code in (401, 403):
        return "Keitaro отклонил API-ключ — проверьте KEITARO_API_KEY в .env"
    if exc.status_code == 404:
        return f"Не найдено в Keitaro: {exc.path}"
    return f"Ошибка Keitaro ({exc.status_code}): {exc.message}"


def _mount_frontend(app: FastAPI, dist: Path) -> None:
    """Раздаёт собранный React (SPA): существующие файлы как есть, остальное — index.html."""
    index = dist / "index.html"
    if not index.is_file():
        logger.info("Сборка фронтенда не найдена в %s — работает только API", dist)
        return
    root = dist.resolve()

    @app.get("/{path:path}", include_in_schema=False)
    async def spa(path: str) -> FileResponse:
        if path.startswith("api/"):
            raise HTTPException(status_code=404)
        candidate = (root / path).resolve()
        if path and candidate.is_file() and candidate.is_relative_to(root):
            return FileResponse(candidate)
        return FileResponse(index)


app = create_app()
