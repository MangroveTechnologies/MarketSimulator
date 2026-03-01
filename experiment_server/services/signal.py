"""Signal metadata loading service.

Loads signal definitions from the MangroveKnowledgeBase signals_metadata.json.
Returns structured dicts with name, type (TRIGGER/FILTER), parameters (with
type, min, max, default), and constraints.
"""

from __future__ import annotations

import json
from typing import Any


def load_signals(
    metadata_path: str,
    signal_type: str | None = None,
    search: str | None = None,
) -> list[dict[str, Any]]:
    """Load signal metadata from a JSON file.

    Args:
        metadata_path: Path to signals_metadata.json.
        signal_type: Filter to TRIGGER or FILTER (None = both).
        search: Substring filter on signal name (case-insensitive).

    Returns:
        List of signal dicts, each with keys: name, type, params, constraints.
        params is a dict of {param_name: {type, min, max, default, optional}}.
    """
    with open(metadata_path) as f:
        metadata = json.load(f)

    results = []
    for name, meta in metadata.items():
        sig_type = meta.get("type", "")

        if signal_type and sig_type != signal_type:
            continue
        if search and search.lower() not in name.lower():
            continue

        params = {}
        for pname, pspec in meta.get("params", {}).items():
            params[pname] = {
                "type": pspec.get("type", "float"),
                "min": pspec.get("min"),
                "max": pspec.get("max"),
                "default": pspec.get("default"),
                "optional": pspec.get("optional", False),
                "description": pspec.get("description", ""),
            }

        # Constraints from metadata (e.g., [["window_fast", "<", "window_slow"]])
        constraints = meta.get("constraints", [])
        # Also infer fast/slow constraint if not explicit
        if not constraints:
            pnames = list(params.keys())
            if "window_fast" in pnames and "window_slow" in pnames:
                constraints = [["window_fast", "<", "window_slow"]]

        results.append({
            "name": name,
            "type": sig_type,
            "params": params,
            "constraints": constraints,
            "description": meta.get("description", ""),
            "requires": meta.get("requires", []),
        })

    results.sort(key=lambda s: s["name"])
    return results
