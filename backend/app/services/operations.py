from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import OperationLog


def log_operation(
    session: AsyncSession,
    operation: str,
    *,
    campaign_id: int | None = None,
    stream_id: int | None = None,
    payload: dict[str, Any] | None = None,
    error: str | None = None,
) -> OperationLog:
    """Добавляет запись в журнал операций. Коммит — на вызывающей стороне."""
    entry = OperationLog(
        operation=operation,
        campaign_id=campaign_id,
        stream_id=stream_id,
        payload=payload,
        success=error is None,
        error=error,
    )
    session.add(entry)
    return entry
