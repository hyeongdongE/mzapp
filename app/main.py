from fastapi import FastAPI

app = FastAPI(title="AI Personal Trend Radar Data PoC")


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}
