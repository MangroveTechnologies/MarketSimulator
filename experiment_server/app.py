"""FastAPI application factory for the Experiment Framework."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware


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

    app.include_router(experiments_router, prefix="/api/v1")
    app.include_router(datasets_router, prefix="/api/v1")
    app.include_router(signals_router, prefix="/api/v1")

    return app


app = create_app()
