"""
Model switching and pricing utilities for the benchmark.

Reads/writes the ``llm_model_configs`` table and reads pricing from the
``llm_models`` catalogue.  After every write the in-process LLM config
cache is invalidated so the next ``get_model()`` call picks up the change.
"""

from __future__ import annotations

import sys
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, "/app")

from MangroveAI.utils.db_utils import DatabaseUtils
from MangroveAI.domains.ai_copilot.llm_config_cache import invalidate_cache


# ---------------------------------------------------------------------------
# Read helpers
# ---------------------------------------------------------------------------

def get_current_copilot_main() -> Tuple[str, str]:
    """Return ``(provider, model)`` for the current ``copilot_main`` config."""
    conn = DatabaseUtils.db_connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT provider, model FROM llm_model_configs "
                "WHERE call_site = 'copilot_main'"
            )
            row = cur.fetchone()
            if not row:
                raise RuntimeError("No copilot_main row in llm_model_configs")
            return (row[0], row[1])
    finally:
        conn.close()


def get_model_pricing(model_id: str) -> Dict[str, float]:
    """Read per-million-token costs from ``llm_models``.

    Returns:
        Dict with ``cost_input_per_mtok`` and ``cost_output_per_mtok``.
        Values default to ``0.0`` when the catalogue row is missing or NULL.
    """
    conn = DatabaseUtils.db_connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT cost_input_per_mtok, cost_output_per_mtok "
                "FROM llm_models WHERE id = %s",
                (model_id,),
            )
            row = cur.fetchone()
            if row:
                return {
                    "cost_input_per_mtok": float(row[0]) if row[0] else 0.0,
                    "cost_output_per_mtok": float(row[1]) if row[1] else 0.0,
                }
            return {"cost_input_per_mtok": 0.0, "cost_output_per_mtok": 0.0}
    finally:
        conn.close()


def load_eligible_models(
    include_pro: bool = False,
    include_previous_gen: bool = False,
) -> List[Dict[str, Any]]:
    """Load all benchmark-eligible models from ``llm_models``.

    Applies exclusion rules (Responses API, embedding, vision, aliases,
    models missing from litellm).

    Returns:
        List of dicts with keys: ``id``, ``provider_id``, ``display_name``,
        ``cost_input_per_mtok``, ``cost_output_per_mtok``.
    """
    # Models that cannot be used with Chat Completions (Responses API mode)
    # or are not in litellm's model map, or are aliases/duplicates.
    excluded = {
        # Responses API
        "gpt-5.1-codex-max", "gpt-5.1-codex", "gpt-5.2-codex",
        "gpt-5-codex",
        # Chat-latest aliases (duplicates of base model)
        "gpt-5.2-chat-latest", "gpt-5.1-chat-latest", "gpt-5-chat-latest",
        # Embedding models
        "text-embedding-3-small", "text-embedding-3-large",
        # Vision-only
        "grok-2-vision-1212",
        # Not in litellm model map
        "MiniMax-M2.5-highspeed", "MiniMax-M2.1",
    }

    if not include_pro:
        excluded.update({"gpt-5.2-pro", "gpt-5-pro"})

    if not include_previous_gen:
        excluded.update({
            "claude-opus-4-5-20251101",
            "claude-sonnet-4-5-20250929",
        })

    conn = DatabaseUtils.db_connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, provider_id, display_name, "
                "       cost_input_per_mtok, cost_output_per_mtok "
                "FROM llm_models ORDER BY provider_id, id"
            )
            rows = cur.fetchall()

        models = []
        for row in rows:
            model_id = row[0]
            if model_id in excluded:
                continue
            models.append({
                "id": model_id,
                "provider_id": row[1],
                "display_name": row[2],
                "cost_input_per_mtok": float(row[3]) if row[3] else 0.0,
                "cost_output_per_mtok": float(row[4]) if row[4] else 0.0,
            })
        return models
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Write helpers
# ---------------------------------------------------------------------------

def switch_copilot_main(provider: str, model: str) -> None:
    """Update ``copilot_main`` in the DB and invalidate the config cache.

    Args:
        provider: Provider string (e.g. ``"openai"``, ``"anthropic"``).
        model: Model ID (e.g. ``"gpt-5.1"``, ``"claude-sonnet-4-6-20260217"``).
    """
    conn = DatabaseUtils.db_connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE llm_model_configs "
                "SET model = %s, provider = %s, "
                "    updated_at = now(), updated_by = 'benchmark' "
                "WHERE call_site = 'copilot_main'",
                (model, provider),
            )
            conn.commit()
    finally:
        conn.close()

    invalidate_cache()
