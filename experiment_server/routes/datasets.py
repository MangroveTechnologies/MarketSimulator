"""Dataset listing API routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from experiment_server.config import settings
from experiment_server.services.dataset import discover_datasets

router = APIRouter(prefix="/datasets", tags=["datasets"])


@router.get("")
async def list_datasets() -> list[dict[str, Any]]:
    """List available OHLCV data files."""
    datasets = discover_datasets(settings.mangrove_data_dir)
    return [d.model_dump() for d in datasets]
