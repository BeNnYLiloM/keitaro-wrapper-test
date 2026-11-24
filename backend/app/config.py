from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Настройки приложения. Читаются из переменных окружения и файла .env."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Keitaro Admin API
    keitaro_api_url: str = "https://keitaro-for-tests.etolegko.com/admin_api/v1"
    keitaro_api_key: str = ""
    keitaro_admin_url: str = "https://keitaro-for-tests.etolegko.com/admin"
    keitaro_timeout: float = 20.0

    # Что проставляется каждой новой кампании (значения со стенда, см. ТЗ)
    keitaro_domain_id: int = 1813
    keitaro_group_id: int = 10332
    keitaro_traffic_source_id: int = 836

    # Куда ведёт первый поток
    google_url: str = "https://google.com"

    # Как долго считать локальный кэш офферов свежим (секунды)
    offers_cache_ttl: int = 600

    database_url: str = "postgresql+asyncpg://keitaro:keitaro@localhost:5432/keitaro"

    # Каталог со сборкой фронтенда (если он есть, FastAPI раздаёт его на /)
    frontend_dist: str = "frontend_dist"

    def campaign_admin_link(self, campaign_id: int) -> str:
        return f"{self.keitaro_admin_url.rstrip('/')}/#!/campaign.editor/{campaign_id}"


@lru_cache
def get_settings() -> Settings:
    return Settings()
