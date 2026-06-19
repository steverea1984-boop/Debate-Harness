"""FastAPI web UI for the debate harness — a thin shell over ``runs.py``.

Launch:  python -m debate_harness.web   (then open http://127.0.0.1:8000)

Needs the web extra:  pip install fastapi uvicorn   (kept out of the core
requirements so the offline test suite stays dependency-free). All the
non-trivial logic lives in ``runs.py`` and ``models.py``, which import no web
dependencies and are unit-tested directly.
"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse

from .models import curated_model_dicts
from . import runs

_STATIC = Path(__file__).resolve().parent / "static"

app = FastAPI(title="Debate Harness")


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return (_STATIC / "index.html").read_text(encoding="utf-8")


@app.get("/api/models")
def api_models() -> JSONResponse:
    return JSONResponse({"models": curated_model_dicts()})


@app.get("/api/runs")
def api_runs() -> JSONResponse:
    return JSONResponse({"runs": runs.list_runs()})


@app.get("/api/runs/{run_id}")
def api_run(run_id: str) -> JSONResponse:
    data = runs.load_run(run_id)
    if data is None:
        raise HTTPException(status_code=404, detail="run not found")
    return JSONResponse(data)


@app.post("/api/runs")
def api_start(req: dict) -> JSONResponse:
    try:
        run_id = runs.start_debate(req)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return JSONResponse({"id": run_id}, status_code=201)


def main() -> None:
    import uvicorn

    host = os.environ.get("DEBATE_WEB_HOST", "127.0.0.1")
    port = int(os.environ.get("DEBATE_WEB_PORT", "8000"))
    print(f"Debate Harness UI -> http://{host}:{port}")
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
