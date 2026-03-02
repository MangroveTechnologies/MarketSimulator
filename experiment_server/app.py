"""FastAPI application factory for the Experiment Framework."""

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles


def create_app() -> FastAPI:
    app = FastAPI(
        title="MarketSimulator Experiment Framework",
        version="1.0.0",
        description="Backtest experimentation dashboard with DuckDB + Parquet storage",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5200", "http://127.0.0.1:5200"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    from experiment_server.routes.experiments import router as experiments_router
    from experiment_server.routes.datasets import router as datasets_router
    from experiment_server.routes.signals import router as signals_router
    from experiment_server.routes.results import router as results_router
    from experiment_server.routes.progress import router as progress_router
    from experiment_server.routes.templates import router as templates_router
    from experiment_server.routes.exec_config import router as exec_config_router

    app.include_router(experiments_router, prefix="/api/v1")
    app.include_router(datasets_router, prefix="/api/v1")
    app.include_router(signals_router, prefix="/api/v1")
    app.include_router(results_router, prefix="/api/v1")
    app.include_router(progress_router, prefix="/api/v1")
    app.include_router(templates_router, prefix="/api/v1")
    app.include_router(exec_config_router, prefix="/api/v1")

    # Serve frontend
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    react_dist = os.path.join(base_dir, "experiment_ui_dist")
    html_fallback = os.path.join(base_dir, "dashboard.html")

    # Serve React built assets if available
    if os.path.isdir(react_dist):
        app.mount("/assets", StaticFiles(directory=os.path.join(react_dist, "assets")), name="assets")

    @app.get("/old")
    async def serve_old_dashboard():
        """Legacy HTML dashboard."""
        path = os.path.join(base_dir, "dashboard.html")
        if os.path.exists(path):
            return FileResponse(path, media_type="text/html")
        return {"message": "dashboard.html not found"}

    @app.get("/old/explore")
    async def serve_old_explore():
        """Legacy HTML explore view."""
        path = os.path.join(base_dir, "explore.html")
        if os.path.exists(path):
            return FileResponse(path, media_type="text/html")
        return {"message": "explore.html not found"}

    @app.get("/{path:path}")
    async def serve_spa(path: str):
        """Serve React SPA -- all routes fall through to index.html."""
        if os.path.isdir(react_dist):
            index = os.path.join(react_dist, "index.html")
            if os.path.exists(index):
                return FileResponse(index, media_type="text/html")
        # Fallback to old HTML dashboard
        if os.path.exists(html_fallback):
            return FileResponse(html_fallback, media_type="text/html")
        return {"message": "No frontend found"}

    return app


app = create_app()
