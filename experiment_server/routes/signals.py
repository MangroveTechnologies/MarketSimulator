"""Signal metadata API routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from experiment_server.config import settings
from experiment_server.services.signal import load_signals

router = APIRouter(prefix="/signals", tags=["signals"])


@router.get("")
async def list_signals(
    type: str | None = None,
    search: str | None = None,
) -> list[dict[str, Any]]:
    """List available signals from the knowledge base.

    Query params:
        type: Filter by signal type (TRIGGER or FILTER).
        search: Substring filter on signal name.
    """
    return load_signals(
        settings.signals_metadata_path,
        signal_type=type,
        search=search,
    )
