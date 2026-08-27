"""FastAPI de Rio_Search (§3.9, docs/rio_search_plan.md). Fase 0 solo expone `/api/health`
para verificar el cableado backend <-> frontend; los routers de dominio (experiments, runs,
datasets, features, predictions, research, jobs) llegan en la Fase 4."""

from __future__ import annotations

from fastapi import FastAPI

APP_VERSION = "0.1.0"


def create_app() -> FastAPI:
    app = FastAPI(title="rio_search", version=APP_VERSION)

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "service": "rio_search-backend", "version": APP_VERSION}

    return app


app = create_app()
