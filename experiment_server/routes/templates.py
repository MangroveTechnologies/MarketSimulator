"""Template CRUD API routes.

Templates are experiment configs stored as JSON files in data/templates/.
They exclude runtime fields (experiment_id, status, created_at, total_runs).
"""

from __future__ import annotations

import json
import os
from typing import Any

from fastapi import APIRouter, HTTPException

from experiment_server.config import settings

router = APIRouter(prefix="/templates", tags=["templates"])


def _templates_dir() -> str:
    path = os.path.join(settings.data_dir, "templates")
    os.makedirs(path, exist_ok=True)
    return path


def _template_path(name: str) -> str:
    safe_name = name.replace("/", "_").replace("..", "_")
    return os.path.join(_templates_dir(), f"{safe_name}.json")


@router.get("")
async def list_templates() -> list[dict[str, Any]]:
    """List saved experiment templates."""
    tpl_dir = _templates_dir()
    results = []
    for filename in sorted(os.listdir(tpl_dir)):
        if not filename.endswith(".json"):
            continue
        path = os.path.join(tpl_dir, filename)
        try:
            with open(path) as f:
                data = json.load(f)
            results.append({
                "name": filename[:-5],  # strip .json
                "description": data.get("description", ""),
                "search_mode": data.get("search_mode", "grid"),
                "datasets_count": len(data.get("datasets", [])),
            })
        except Exception:
            continue
    return results


@router.post("", status_code=201)
async def save_template(body: dict[str, Any]) -> dict[str, str]:
    """Save an experiment config as a named template."""
    name = body.get("name")
    if not name:
        raise HTTPException(status_code=400, detail="Template name is required")

    # Strip runtime fields
    config = dict(body.get("config", body))
    for key in ("experiment_id", "status", "created_at", "total_runs"):
        config.pop(key, None)

    path = _template_path(name)
    with open(path, "w") as f:
        json.dump(config, f, indent=2, default=str)

    return {"name": name, "status": "saved"}


@router.get("/{name}")
async def get_template(name: str) -> dict[str, Any]:
    """Load a template by name."""
    path = _template_path(name)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Template not found")

    with open(path) as f:
        return json.load(f)


@router.delete("/{name}")
async def delete_template(name: str) -> dict[str, str]:
    """Delete a template."""
    path = _template_path(name)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Template not found")

    os.unlink(path)
    return {"status": "deleted"}
