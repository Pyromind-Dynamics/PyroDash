#!/usr/bin/env python3
"""Lightweight web UI for swe_20filter eval: start runs, poll progress, browse results."""
from __future__ import annotations

import json
import os
import re
import subprocess
import time
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

HTML_DIR = Path(__file__).resolve().parent
RUN_USE_ROOT = HTML_DIR.parent
OUTPUT_DIR = RUN_USE_ROOT / "output"
RUN_SH = RUN_USE_ROOT / "run_sh" / "run_swe_20filter.sh"

SAFE_RUN_ID = re.compile(r"^[A-Za-z0-9._-]{1,128}$")

app = FastAPI(title="PyroDash run_use", version="0.1.0")


class StartRunRequest(BaseModel):
    mode: str = Field(default="swe_20filter")
    router_mode: str = Field(default="tag")
    model_path: str = ""
    slm_base_url: str = ""
    slm_api_key: str = "dummy"
    slm_model: str = ""
    llm_base_url: str = ""
    llm_api_key: str = ""
    llm_model: str = ""
    adapter_port: int = 18027
    vllm_port: int = 8007
    offload_mode: str = "handoff"
    workers: int = 4
    harness_workers: int = 8
    cuda_visible_devices: str = "0"
    run_id: str = ""


def _require_run_id(run_id: str) -> str:
    if not SAFE_RUN_ID.match(run_id):
        raise HTTPException(status_code=400, detail="invalid run_id")
    return run_id


def _run_dir(run_id: str) -> Path:
    rid = _require_run_id(run_id)
    path = (OUTPUT_DIR / rid).resolve()
    if not str(path).startswith(str(OUTPUT_DIR.resolve())):
        raise HTTPException(status_code=400, detail="path escape")
    return path


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text())
    except Exception:
        return {}


def _tail_file(path: Path, max_bytes: int = 24_000) -> str:
    if not path.is_file():
        return ""
    data = path.read_bytes()
    if len(data) > max_bytes:
        data = data[-max_bytes:]
    return data.decode("utf-8", errors="replace")


def _list_relative_files(root: Path, limit: int = 200) -> list[str]:
    if not root.is_dir():
        return []
    out: list[str] = []
    for p in sorted(root.rglob("*")):
        if p.is_file():
            out.append(str(p.relative_to(root)))
            if len(out) >= limit:
                break
    return out


def _parse_harness_summary(eval_dir: Path) -> dict[str, Any]:
    """Best-effort parse of SWE-bench harness reports under verified/."""
    verified = eval_dir / "verified"
    preds = eval_dir / "runs" / "preds.json"
    summary: dict[str, Any] = {
        "preds_exists": preds.is_file(),
        "preds_path": str(preds.relative_to(eval_dir)) if preds.is_file() else None,
        "resolved": None,
        "total": None,
        "report_files": [],
    }
    if not verified.is_dir():
        return summary

    reports = sorted(verified.rglob("*.json"))
    summary["report_files"] = [str(p.relative_to(eval_dir)) for p in reports[:50]]

    for report in reports:
        try:
            data = json.loads(report.read_text())
        except Exception:
            continue
        # Common harness shapes: {"resolved_instances": N, ...} or nested totals
        if isinstance(data, dict):
            for key in ("resolved_instances", "resolved", "num_resolved"):
                if key in data and isinstance(data[key], (int, float)):
                    summary["resolved"] = int(data[key])
            for key in ("total_instances", "total", "num_instances", "submitted_instances"):
                if key in data and isinstance(data[key], (int, float)):
                    summary["total"] = int(data[key])
            if summary["resolved"] is not None:
                summary["primary_report"] = str(report.relative_to(eval_dir))
                break
            # sometimes {"instance_id": {"resolved": true}, ...}
            if data and all(isinstance(v, dict) for v in data.values()):
                resolved = sum(1 for v in data.values() if v.get("resolved") is True)
                summary["resolved"] = resolved
                summary["total"] = len(data)
                summary["primary_report"] = str(report.relative_to(eval_dir))
                break
    return summary


@app.get("/api/health")
def api_health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/runs")
def list_runs() -> dict[str, Any]:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    runs = []
    for d in sorted(OUTPUT_DIR.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
        if not d.is_dir() or d.name.startswith("."):
            continue
        status = _read_json(d / "status.json")
        runs.append(
            {
                "run_id": d.name,
                "phase": status.get("phase", "unknown"),
                "mode": status.get("mode", "swe_20filter"),
                "router_mode": status.get("router_mode"),
                "message": status.get("message"),
                "started_at": status.get("started_at"),
                "updated_at": status.get("updated_at"),
                "finished_at": status.get("finished_at"),
            }
        )
    return {"runs": runs}


@app.post("/api/runs")
def start_run(body: StartRunRequest) -> JSONResponse:
    if body.mode != "swe_20filter":
        raise HTTPException(status_code=400, detail="only mode=swe_20filter is supported")
    if body.router_mode not in ("tag", "entropy"):
        raise HTTPException(status_code=400, detail="router_mode must be tag or entropy")
    if not body.model_path and not (body.slm_base_url and body.slm_model):
        raise HTTPException(
            status_code=400,
            detail="set model_path (local) or slm_base_url + slm_model (remote)",
        )
    if not body.llm_base_url or not body.llm_api_key or not body.llm_model:
        raise HTTPException(status_code=400, detail="llm_base_url, llm_api_key, llm_model required")
    if not RUN_SH.is_file():
        raise HTTPException(status_code=500, detail=f"missing {RUN_SH}")

    run_id = body.run_id.strip() or f"swe20_{time.strftime('%Y%m%d_%H%M%S')}"
    _require_run_id(run_id)
    run_dir = OUTPUT_DIR / run_id
    if run_dir.exists():
        raise HTTPException(status_code=409, detail=f"run_id already exists: {run_id}")

    run_dir.mkdir(parents=True, exist_ok=False)
    (run_dir / "logs").mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    env.update(
        {
            "RUN_ID": run_id,
            "ROUTER_MODE": body.router_mode,
            "OFFLOAD_MODE": body.offload_mode,
            "ADAPTER_PORT": str(body.adapter_port),
            "VLLM_PORT": str(body.vllm_port),
            "WORKERS": str(body.workers),
            "HARNESS_WORKERS": str(body.harness_workers),
            "CUDA_VISIBLE_DEVICES": body.cuda_visible_devices,
            "LLM_BASE_URL": body.llm_base_url,
            "LLM_API_KEY": body.llm_api_key,
            "LLM_MODEL": body.llm_model,
            "SLM_API_KEY": body.slm_api_key or "dummy",
        }
    )
    if body.model_path:
        env["MODEL_PATH"] = body.model_path
        env.pop("SLM_BASE_URL", None)
    else:
        env["SLM_BASE_URL"] = body.slm_base_url
        env["SLM_MODEL"] = body.slm_model
        env.pop("MODEL_PATH", None)

    web_log = run_dir / "logs" / "web_launch.log"
    with web_log.open("w") as logf:
        logf.write(f"starting {RUN_SH} run_id={run_id}\n")
        logf.flush()
        proc = subprocess.Popen(
            ["bash", str(RUN_SH)],
            cwd=str(RUN_USE_ROOT),
            env=env,
            stdout=logf,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )

    status = {
        "run_id": run_id,
        "mode": "swe_20filter",
        "router_mode": body.router_mode,
        "phase": "starting_adapter",
        "message": "launched from web UI",
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "pid": proc.pid,
    }
    (run_dir / "status.json").write_text(json.dumps(status, indent=2) + "\n")

    return JSONResponse({"run_id": run_id, "pid": proc.pid, "status": status})


@app.get("/api/runs/{run_id}")
def get_run(run_id: str, log_tail: int = 20000) -> dict[str, Any]:
    run_dir = _run_dir(run_id)
    if not run_dir.is_dir():
        raise HTTPException(status_code=404, detail="run not found")
    status = _read_json(run_dir / "status.json")
    logs = {
        "eval": _tail_file(run_dir / "logs" / "eval.log", log_tail),
        "adapter_api": _tail_file(run_dir / "logs" / "adapter_api.log", log_tail),
        "web_launch": _tail_file(run_dir / "logs" / "web_launch.log", log_tail),
    }
    return {
        "run_id": run_id,
        "status": status,
        "phase": status.get("phase", "unknown"),
        "logs": logs,
        "files": _list_relative_files(run_dir),
    }


@app.get("/api/runs/{run_id}/results")
def get_results(run_id: str) -> dict[str, Any]:
    run_dir = _run_dir(run_id)
    if not run_dir.is_dir():
        raise HTTPException(status_code=404, detail="run not found")
    status = _read_json(run_dir / "status.json")
    eval_dir = run_dir / "swe_20filter"
    summary = _parse_harness_summary(eval_dir) if eval_dir.is_dir() else {}
    return {
        "run_id": run_id,
        "status": status,
        "eval_dir": "swe_20filter" if eval_dir.is_dir() else None,
        "summary": summary,
        "files": _list_relative_files(run_dir),
    }


@app.get("/api/runs/{run_id}/files/{file_path:path}")
def get_file(run_id: str, file_path: str) -> FileResponse:
    run_dir = _run_dir(run_id)
    if not run_dir.is_dir():
        raise HTTPException(status_code=404, detail="run not found")
    target = (run_dir / file_path).resolve()
    if not str(target).startswith(str(run_dir.resolve())):
        raise HTTPException(status_code=400, detail="path escape")
    if not target.is_file():
        raise HTTPException(status_code=404, detail="file not found")
    return FileResponse(target)


# Static assets last so /api wins
app.mount("/", StaticFiles(directory=str(HTML_DIR), html=True), name="static")


def main() -> None:
    import uvicorn

    host = os.environ.get("RUN_USE_HOST", "0.0.0.0")
    port = int(os.environ.get("RUN_USE_PORT", "8787"))
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"[run_use html] http://{host}:{port}/  output={OUTPUT_DIR}")
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
