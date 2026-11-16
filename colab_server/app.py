"""FastAPI entrypoint exposing Google Colab remote inference endpoints."""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
import json
import os
from pathlib import Path
import secrets
import threading
import time
from typing import Any

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .cache_sync import sync_local_to_drive
from .worker_host import ColabJobRecord, ColabWorkerHost

SSE_KEEPALIVE_SECONDS = 12.0


class VideoCheckRequest(BaseModel):
    sha256: str = Field(..., min_length=64, max_length=64)
    filename: str = ""
    size: int = 0


class JobCreateRequest(BaseModel):
    video_sha256: str = Field(..., min_length=64, max_length=64)
    settings: dict[str, Any] = Field(default_factory=dict)
    output_mode: str = "data_only"


def create_app(
    *,
    work_dir: Path | str | None = None,
    api_token: str | None = None,
    drive_cache_dir: Path | str | None = None,
    local_cache_dir: Path | str | None = None,
    prewarm_worker: bool = True,
) -> FastAPI:
    resolved_token = (
        api_token
        or os.environ.get("COLAB_API_TOKEN", "").strip()
        or secrets.token_urlsafe(24)
    )
    resolved_work = Path(
        work_dir or os.environ.get("COLAB_WORK_DIR", "/content/colab_work")
    )
    resolved_drive_cache = str(
        drive_cache_dir or os.environ.get("COLAB_DRIVE_CACHE_DIR", "").strip()
    )
    resolved_local_cache = Path(
        local_cache_dir or os.environ.get("COLAB_LOCAL_CACHE_DIR", "/content/.cache")
    )

    def _on_job_finished(_record: ColabJobRecord) -> None:
        if resolved_drive_cache:
            threading.Thread(
                target=sync_local_to_drive,
                args=(resolved_local_cache, Path(resolved_drive_cache)),
                daemon=True,
                name="ColabDriveCacheSync",
            ).start()

    host = ColabWorkerHost(
        resolved_work,
        on_job_finished=_on_job_finished if resolved_drive_cache else None,
    )

    def _verify_token(authorization: str | None = Header(default=None)) -> None:
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing Bearer API token",
            )
        presented = authorization[len("Bearer ") :].strip()
        if not secrets.compare_digest(presented, resolved_token):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Invalid API token",
            )

    @asynccontextmanager
    async def lifespan(app_instance: FastAPI):
        app_instance.state.api_token = resolved_token
        app_instance.state.worker_host = host
        if prewarm_worker:
            host.start()
            await asyncio.to_thread(host._ensure_worker_ready)
        try:
            yield
        finally:
            host.shutdown()

    app = FastAPI(title="RTMLib Pose Estimation Colab Worker", lifespan=lifespan)

    @app.get("/health", dependencies=[Depends(_verify_token)])
    async def get_health() -> dict[str, Any]:
        return await asyncio.to_thread(host.health_info)

    @app.post("/videos/check", dependencies=[Depends(_verify_token)])
    async def check_video(payload: VideoCheckRequest) -> dict[str, Any]:
        try:
            existing = host.find_video_by_sha256(payload.sha256)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {
            "exists": existing is not None,
            "video_sha256": payload.sha256.lower(),
            "filename": existing.name if existing is not None else payload.filename,
        }

    @app.post("/videos/upload", dependencies=[Depends(_verify_token)])
    async def upload_video_chunk(
        sha256: str = Form(...),
        filename: str = Form(...),
        chunk_index: int = Form(...),
        total_chunks: int = Form(...),
        chunk: UploadFile = File(...),
    ) -> dict[str, Any]:
        data = await chunk.read()
        try:
            return await asyncio.to_thread(
                host.receive_chunk, sha256, filename, chunk_index, total_chunks, data
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/jobs", dependencies=[Depends(_verify_token)])
    async def create_job(payload: JobCreateRequest) -> dict[str, Any]:
        try:
            record = await asyncio.to_thread(
                host.submit_job,
                payload.video_sha256,
                payload.settings,
                payload.output_mode,
            )
            return record.snapshot_status()
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/jobs/{job_id}/status", dependencies=[Depends(_verify_token)])
    async def job_status(job_id: str) -> dict[str, Any]:
        try:
            return host.get_job_status(job_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/jobs/{job_id}/events", dependencies=[Depends(_verify_token)])
    async def stream_job_events(
        job_id: str,
        from_seq: int = Query(default=0, ge=0),
        last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
    ) -> StreamingResponse:
        if host.get_job(job_id) is None:
            raise HTTPException(status_code=404, detail=f"Unknown job_id: {job_id}")

        cursor = from_seq
        if last_event_id is not None and str(last_event_id).isdigit():
            cursor = max(cursor, int(last_event_id))

        sse_flush_pad = f": {' ' * 2048}\n\n"

        async def _event_generator():
            nonlocal cursor
            last_heartbeat = time.monotonic()
            # Initial padding flushes proxy response headers immediately over Cloudflare tunnels
            yield sse_flush_pad
            while True:
                events, is_terminal = await asyncio.to_thread(
                    host.get_events_since, job_id, cursor, wait_timeout=0.25
                )
                if events:
                    chunks: list[str] = []
                    for ev in events:
                        seq = int(ev.get("seq", 0))
                        cursor = max(cursor, seq)
                        ev_type = str(ev.get("type", "message"))
                        chunks.append(
                            f"id: {seq}\nevent: {ev_type}\ndata: {json.dumps(ev, ensure_ascii=False)}\n\n"
                        )
                    payload_block = "".join(chunks)
                    if len(payload_block) < 2048:
                        payload_block += sse_flush_pad
                    yield payload_block
                    last_heartbeat = time.monotonic()
                elif (time.monotonic() - last_heartbeat) >= SSE_KEEPALIVE_SECONDS:
                    yield f": keepalive\n{sse_flush_pad}"
                    last_heartbeat = time.monotonic()

                if is_terminal:
                    break

        return StreamingResponse(
            _event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    @app.post("/jobs/{job_id}/cancel", dependencies=[Depends(_verify_token)])
    async def cancel_job(job_id: str) -> dict[str, Any]:
        try:
            return host.cancel_job(job_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/jobs/{job_id}/result", dependencies=[Depends(_verify_token)])
    async def download_result(job_id: str) -> FileResponse:
        try:
            zip_path = await asyncio.to_thread(host.build_result_zip, job_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return FileResponse(
            path=str(zip_path),
            media_type="application/zip",
            filename=f"{job_id}_result.zip",
        )

    @app.delete("/jobs/{job_id}", dependencies=[Depends(_verify_token)])
    async def delete_job(job_id: str) -> dict[str, Any]:
        try:
            deleted = host.cleanup_job(job_id)
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        if not deleted:
            raise HTTPException(status_code=404, detail=f"Unknown job_id: {job_id}")
        return {"deleted": True, "job_id": job_id}

    # Optional hook for future remote/mobile web UI serving
    if os.environ.get("COLAB_SERVE_FRONTEND", "").strip() == "1":
        dist_dir = Path(gui.__file__).resolve().parent / "frontend" / "dist"
        if dist_dir.is_dir():
            app.mount("/", StaticFiles(directory=str(dist_dir), html=True), name="frontend")

    return app


def _get_default_app() -> FastAPI:
    return create_app()


if __name__ == "__main__":
    import uvicorn

    app_instance = create_app()
    port = int(os.environ.get("COLAB_PORT", "8000"))
    uvicorn.run(app_instance, host="127.0.0.1", port=port, log_level="warning")
else:
    app = _get_default_app() if os.environ.get("COLAB_ASGI_AUTOLOAD", "").strip() == "1" else None
