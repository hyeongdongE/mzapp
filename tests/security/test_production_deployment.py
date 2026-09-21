from pathlib import Path

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from app.api.public_dependencies import enforce_same_origin

ROOT = Path(__file__).parents[2]


def test_production_image_excludes_secrets_and_database_backups() -> None:
    ignored = {
        line.strip()
        for line in (ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()
    }

    assert {".env.production", "backups", "*.sql"} <= ignored


def test_https_same_origin_is_preserved_behind_the_trusted_proxy() -> None:
    app = FastAPI(dependencies=[Depends(enforce_same_origin)])

    @app.post("/probe")
    def probe() -> dict[str, bool]:
        return {"ok": True}

    proxied = ProxyHeadersMiddleware(app, trusted_hosts="*")
    client = TestClient(proxied, base_url="http://trend.example")

    allowed = client.post(
        "/probe",
        headers={"Origin": "https://trend.example", "X-Forwarded-Proto": "https"},
    )
    denied = client.post(
        "/probe",
        headers={"Origin": "https://evil.example", "X-Forwarded-Proto": "https"},
    )

    assert allowed.status_code == 200
    assert denied.status_code == 403


def test_production_api_enables_proxy_headers_behind_loopback_binding() -> None:
    compose = (ROOT / "compose.prod.yaml").read_text(encoding="utf-8")

    assert '"127.0.0.1:${INTERNAL_API_PORT:-8000}:8000"' in compose
    assert "--proxy-headers" in compose
    assert "--forwarded-allow-ips=*" in compose
