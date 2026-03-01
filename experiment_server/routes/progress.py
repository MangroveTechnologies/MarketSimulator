"""SSE progress streaming endpoint."""

from __future__ import annotations

import asyncio
import json
import os

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from experiment_server.config import settings
from experiment_server.services import executor

router = APIRouter(prefix="/experiments/{experiment_id}", tags=["progress"])


@router.get("/progress")
async def stream_progress(experiment_id: str):
    """Server-Sent Events stream for real-time experiment progress.

    Tries Redis Streams first. Falls back to polling Parquet file counts
    if Redis is unavailable.
    """
    config = executor.get_experiment(experiment_id)
    if not config:
        raise HTTPException(status_code=404, detail="Experiment not found")

    async def event_generator():
        try:
            import redis as redis_lib
            r = redis_lib.from_url(settings.redis_url)
            r.ping()
            # Redis available -- use Streams
            stream_key = f"exp:{experiment_id}:progress"
            last_id = "0"
            while True:
                entries = r.xread(
                    {stream_key: last_id}, block=2000, count=10,
                )
                if entries:
                    for stream, messages in entries:
                        for msg_id, data in messages:
                            last_id = msg_id.decode() if isinstance(msg_id, bytes) else msg_id
                            decoded = {
                                k.decode() if isinstance(k, bytes) else k:
                                v.decode() if isinstance(v, bytes) else v
                                for k, v in data.items()
                            }
                            yield f"data: {json.dumps(decoded)}\n\n"
                            if decoded.get("status") == "done":
                                return
                else:
                    # No new messages, send heartbeat
                    progress = executor.get_experiment_progress(experiment_id)
                    yield f"data: {json.dumps(progress)}\n\n"
        except Exception:
            # Redis unavailable -- poll Parquet files
            while True:
                progress = executor.get_experiment_progress(experiment_id)
                yield f"data: {json.dumps(progress)}\n\n"
                if progress.get("status") in ("completed", "failed"):
                    return
                await asyncio.sleep(3)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )
