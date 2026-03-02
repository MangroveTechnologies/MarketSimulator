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

    # Serve the dashboard HTML at root
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    dashboard_path = os.path.join(base_dir, "dashboard.html")

    @app.get("/")
    async def serve_dashboard():
        if os.path.exists(dashboard_path):
            return FileResponse(dashboard_path, media_type="text/html")
        return {"message": "Dashboard not found. Place dashboard.html in MarketSimulator root."}

    return app


app = create_app()
