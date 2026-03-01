"""Execution config defaults API route."""

from __future__ import annotations

import json
import os
from typing import Any

from fastapi import APIRouter, HTTPException

from experiment_server.config import settings

router = APIRouter(prefix="/exec-config", tags=["exec-config"])


@router.get("/defaults")
async def get_exec_config_defaults() -> dict[str, Any]:
    """Return the full default execution config from trading_defaults.json.

    Merges all sections (risk_management, position_limits, volatility_settings,
    trading_rules, time_based_exits, backtest_defaults) into a flat dict.
    """
    path = settings.trading_defaults_path
    if not os.path.exists(path):
        raise HTTPException(
            status_code=503,
            detail=f"Trading defaults not found at {path}",
        )

    with open(path) as f:
        defaults = json.load(f)

    flat = {}
    for section in [
        "risk_management",
        "position_limits",
        "volatility_settings",
        "trading_rules",
        "time_based_exits",
        "backtest_defaults",
    ]:
        flat.update(defaults.get(section, {}))

    return flat
