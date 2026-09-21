from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.dashboard import router as dashboard_router
from app.api.public import router as public_router
from app.api.reviews import router as reviews_router
from app.config.settings import Settings, get_settings


def create_app(
    settings: Settings | None = None, *, spa_path: Path | None = None
) -> FastAPI:
    resolved = settings or get_settings()
    is_local = resolved.dashboard_host in {"127.0.0.1", "localhost", "::1"}
    if not is_local and not resolved.dashboard_allow_public:
        raise ValueError("public dashboard bind requires DASHBOARD_ALLOW_PUBLIC=true")
    if not is_local and resolved.dashboard_api_key is None:
        raise ValueError("public dashboard bind requires a dashboard API key")

    created = FastAPI(title="AI Personal Trend Radar")
    created.state.settings = resolved
    static_path = Path(__file__).resolve().parent.parent / "dashboard" / "static"
    created.mount("/static", StaticFiles(directory=static_path), name="static")
    created.include_router(dashboard_router)
    created.include_router(reviews_router)
    created.include_router(public_router)

    @created.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    frontend_path = spa_path or Path(__file__).resolve().parent.parent / "frontend" / "dist"
    frontend_root = frontend_path.resolve()
    index_path = frontend_root / "index.html"

    @created.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str) -> FileResponse:
        if full_path.split("/", 1)[0] in {"api", "internal", "static", "healthz"}:
            raise HTTPException(status_code=404, detail="not found")
        if not index_path.is_file():
            raise HTTPException(
                status_code=503,
                detail="frontend build is unavailable; run npm run build",
            )
        requested = (frontend_root / full_path).resolve()
        if requested.is_relative_to(frontend_root) and requested.is_file():
            return FileResponse(requested)
        return FileResponse(index_path)

    return created


app = create_app()
