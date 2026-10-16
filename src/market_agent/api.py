"""Local console API. Bind to loopback; this MVP has no public multi-user auth."""

from pathlib import Path
import os

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from .benchmark import load_benchmark, run_benchmark
from .records import ReplayMismatch, RunStore
from .runtime import PACKAGE, ResearchRequest, code_fingerprint, replay_run, run_research

API_CONTRACT = "research-live-v1"


class BenchmarkRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    limit: int | None = Field(default=2, ge=1)
    repeats: int = Field(default=1, ge=1, le=5)


def create_app(data_dir: Path | None = None) -> FastAPI:
    app = FastAPI(title="Market Research Agent · Reliability Lab", version="0.1.0")
    directory = data_dir or Path(".market-agent")
    store = RunStore(directory / "runs")
    loaded_code = code_fingerprint()

    @app.get("/api/status")
    async def status():
        return JSONResponse({"api_contract": API_CONTRACT, "loaded_code_sha256": loaded_code,
                             "openai_key_configured": bool(os.environ.get("OPENAI_API_KEY")),
                             "default_mode": "live", "default_planner": "openai", "default_web": True},
                            headers={"Cache-Control": "no-store"})

    @app.get("/api/benchmark")
    async def benchmark_info():
        data = load_benchmark()
        return {"suite": data["suite"], "case_count": len(data["cases"]),
                "event_groups": len({case["event_id"] for case in data["cases"]}),
                "provenance": data["provenance"]}

    @app.get("/", include_in_schema=False)
    async def index():
        return FileResponse(PACKAGE / "web/index.html", headers={"Cache-Control": "no-cache"})

    @app.get("/app.css", include_in_schema=False)
    async def stylesheet():
        return FileResponse(PACKAGE / "web/app.css", media_type="text/css", headers={"Cache-Control": "no-cache"})

    @app.get("/app.js", include_in_schema=False)
    async def script():
        return FileResponse(PACKAGE / "web/app.js", media_type="text/javascript", headers={"Cache-Control": "no-cache"})

    @app.post("/api/research")
    async def research(request: ResearchRequest):
        return await run_research(request, store=store)

    @app.get("/api/runs")
    async def runs():
        return store.list()

    def get_record(run_id):
        try:
            return store.get(run_id)
        except (ValueError, FileNotFoundError) as exc:
            raise HTTPException(status_code=404, detail="Run not found") from exc

    @app.get("/api/runs/{run_id}")
    async def run(run_id: str):
        return get_record(run_id)

    @app.post("/api/runs/{run_id}/replay")
    async def replay(run_id: str):
        try:
            return await replay_run(get_record(run_id), store=store)
        except (ReplayMismatch, ValueError, KeyError) as exc:
            raise HTTPException(status_code=409, detail=f"Replay rejected: {exc}") from exc

    @app.post("/api/evaluate")
    async def evaluation(request: BenchmarkRequest | None = None):
        request = request or BenchmarkRequest()
        try:
            return await run_benchmark(limit=request.limit, repeats=request.repeats, store=store,
                                       checkpoint=directory / "research-benchmark.json")
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    return app
