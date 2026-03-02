"""Config hashing for run deduplication.

Computes a deterministic hash of the full run configuration so that
identical runs can be detected across experiments. The hash covers:
entry signals + params, exit signals + params, execution config,
asset, timeframe, and date range.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any


def compute_config_hash(
    entry_json: str | list,
    exit_json: str | list,
    exec_config: dict[str, Any],
    asset: str,
    timeframe: str,
    start_date: str,
    end_date: str,
) -> str:
    """Compute a deterministic SHA256 hash (16-char hex) of a run config.

    The hash is independent of run_index, experiment_id, or any runtime
    metadata. Two runs with identical configs will always produce the
    same hash.
    """
    entry = json.loads(entry_json) if isinstance(entry_json, str) else entry_json
    exit_sigs = json.loads(exit_json) if isinstance(exit_json, str) else exit_json

    canonical = json.dumps({
        "entry": entry,
        "exit": exit_sigs,
        "exec": exec_config,
        "asset": asset,
        "timeframe": timeframe,
        "start": start_date,
        "end": end_date,
    }, sort_keys=True, default=str)

    return hashlib.sha256(canonical.encode()).hexdigest()[:16]
