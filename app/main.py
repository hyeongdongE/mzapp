from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api.dashboard import router as dashboard_router
from app.api.public import router as public_router
from app.api.reviews import router as reviews_router
from app.config.settings import Settings, get_settings


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved = settings or get_settings()
    is_local = resolved.dashboard_host in {"127.0.0.1", "localhost", "::1"}
    if not is_local and not resolved.dashboard_allow_public:
        raise ValueError("public dashboard bind requires DASHBOARD_ALLOW_PUBLIC=true")
    if not is_local and resolved.dashboard_api_key is None:
        raise ValueError("public dashboard bind requires a dashboard API key")

    created = FastAPI(title="AI Personal Trend Radar Data PoC")
    created.state.settings = resolved
    static_path = Path(__file__).resolve().parent.parent / "dashboard" / "static"
    created.mount("/static", StaticFiles(directory=static_path), name="static")
    created.include_router(dashboard_router)
    created.include_router(reviews_router)
    created.include_router(public_router)

    @created.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    return created


app = create_app()
