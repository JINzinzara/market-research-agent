"""Local console API. Bind to loopback; this MVP has no public multi-user auth."""

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse

from .evaluate import evaluate, save_report
from .records import ReplayMismatch, RunStore
from .runtime import PACKAGE, ResearchRequest, replay_run, run_research


def create_app(data_dir: Path | None = None) -> FastAPI:
    app = FastAPI(title="Market Research Agent · Reliability Lab", version="0.1.0")
    directory = data_dir or Path(".market-agent")
    store = RunStore(directory / "runs")

    @app.get("/", include_in_schema=False)
    async def index():
        return FileResponse(PACKAGE / "web/index.html")

    @app.get("/app.css", include_in_schema=False)
    async def stylesheet():
        return FileResponse(PACKAGE / "web/app.css", media_type="text/css")

    @app.get("/app.js", include_in_schema=False)
    async def script():
        return FileResponse(PACKAGE / "web/app.js", media_type="text/javascript")

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
    async def evaluation():
        report = await evaluate()
        save_report(report, directory / "evaluation.json")
        return report

    return app
