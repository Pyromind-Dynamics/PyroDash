#!/usr/bin/env python3
"""Web UI for coding evals: swe / swe_20filter / deepswe / terminal."""
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
RESULT_MD = RUN_USE_ROOT / "result.md"
RUN_SH = RUN_USE_ROOT / "run_sh" / "run_coding.sh"

SAFE_RUN_ID = re.compile(r"^[A-Za-z0-9._-]{1,128}$")
SUPPORTED_MODES = ("swe", "swe_20filter", "deepswe", "terminal")

from metrics import (  # noqa: E402
    compute_run_metrics,
    format_metrics_row,
    parse_leaderboard,
    persist_run_to_result_md,
)

app = FastAPI(title="PyroDash run_use", version="0.2.0")


@app.middleware("http")
async def no_cache_ui_assets(request, call_next):
    """Avoid reverse-proxy/CDN serving stale index/js/css after UI fixes."""
    response = await call_next(request)
    path = request.url.path
    if path.endswith((".html", ".js", ".css")) or path in ("/", ""):
        response.headers["Cache-Control"] = "no-store, max-age=0"
    return response


class StartRunRequest(BaseModel):
    mode: str = Field(default="swe_20filter")
    cluster: str = Field(default="us")
    router_mode: str = Field(default="tag")
    model_path: str = ""
    slm_base_url: str = ""
    slm_api_key: str = "dummy"
    slm_model: str = ""
    llm_base_url: str = ""
    llm_api_key: str = ""
    llm_model: str = ""
    adapter_port: int = 18027
    slm_port: int = 8007
    vllm_port: int = 8007  # alias for slm_port
    slm_backend: str = "vllm"  # vllm | sglang
    slm_tp_size: int = 1  # legacy; prefer flags inside vllm/sglang_extra_args
    max_model_len: str = ""
    vllm_gpu_util: float = 0.90  # legacy
    sglang_mem_fraction: float = 0.90  # legacy
    tool_call_parser: str = "qwen3_coder"  # legacy
    reasoning_parser: str = "qwen3"  # legacy
    vllm_extra_args: str = (
        "--gpu-memory-utilization 0.90 --tensor-parallel-size 1 --trust-remote-code "
        "--reasoning-parser qwen3 --enable-auto-tool-choice --tool-call-parser qwen3_coder"
    )
    sglang_extra_args: str = (
        "--tp 1 --mem-fraction-static 0.90 --tool-call-parser qwen3_coder --reasoning-parser qwen3"
    )
    offload_mode: str = "handoff"
    workers: int = 4
    harness_workers: int = 8
    step_limit: int = 150  # SWE agent.step_limit
    n_concurrent: Optional[int] = None
    n_tasks: str = ""  # empty = all; number as string for optional
    deepswe_tasks: str = "/workspace/work/mjy/eval/deep-swe/tasks"
    tb_dataset: str = "terminal-bench/terminal-bench-2-1"
    cuda_visible_devices: str = "0"
    run_id: str = ""
    resume: bool = False


def _require_run_id(run_id: str) -> str:
    if not SAFE_RUN_ID.match(run_id):
        raise HTTPException(status_code=400, detail="invalid run_id")
    return run_id


def _pid_alive(pid: Any) -> bool:
    try:
        pid_i = int(pid)
    except (TypeError, ValueError):
        return False
    if pid_i <= 0:
        return False
    try:
        os.kill(pid_i, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


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


def _list_relative_files(root: Path, limit: int = 800) -> list[str]:
    if not root.is_dir():
        return []
    out: list[str] = []
    for p in sorted(root.rglob("*")):
        if p.is_file():
            out.append(str(p.relative_to(root)))
            if len(out) >= limit:
                break
    return out


def _find_eval_dir(run_dir: Path, mode: str) -> Optional[Path]:
    for name in (mode, "swe_20filter", "swe", "deepswe", "terminal"):
        p = run_dir / name
        if p.is_dir():
            return p
    return None


SWE20_EXPECTED = 20


def _compute_progress(run_dir: Path, status: dict[str, Any]) -> dict[str, Any]:
    """Instance-level progress for the web UI (preds / traj / job dirs)."""
    mode = status.get("mode") or ""
    progress: dict[str, Any] = {
        "done": 0,
        "total": None,
        "label": "",
        "completed": [],
        "active_containers": 0,
    }
    eval_dir = _find_eval_dir(run_dir, mode)

    try:
        import subprocess as _sp

        out = _sp.check_output(
            ["docker", "ps", "--format", "{{.Names}}"],
            text=True,
            stderr=_sp.DEVNULL,
            timeout=3,
        )
        progress["active_containers"] = sum(
            1 for n in out.splitlines() if n.startswith("minisweagent-")
        )
    except Exception:
        pass

    if eval_dir is None:
        progress["label"] = "waiting for eval output…"
        return progress

    if mode in ("swe", "swe_20filter") or (eval_dir / "runs").is_dir():
        runs = eval_dir / "runs"
        done_ids: list[str] = []
        preds = runs / "preds.json"
        if preds.is_file():
            try:
                data = json.loads(preds.read_text())
                if isinstance(data, dict):
                    done_ids = sorted(data.keys())
            except Exception:
                done_ids = []
        if not done_ids and runs.is_dir():
            done_ids = sorted(p.name for p in runs.iterdir() if p.is_dir())
        progress["done"] = len(done_ids)
        progress["completed"] = done_ids
        if mode == "swe_20filter":
            progress["total"] = SWE20_EXPECTED
        progress["label"] = (
            f"{progress['done']}/{progress['total']} instances done"
            if progress["total"]
            else f"{progress['done']} instances done"
        )
        if progress["active_containers"]:
            progress["label"] += f" · {progress['active_containers']} containers running"
        return progress

    # deepswe / terminal: count leaf job trial dirs or result.json presence
    results = list(eval_dir.rglob("result.json"))
    rewards = list(eval_dir.rglob("reward.json"))
    progress["done"] = max(len(results), len(rewards))
    n_tasks = status.get("n_tasks")
    if isinstance(n_tasks, int):
        progress["total"] = n_tasks
    progress["label"] = (
        f"{progress['done']}/{progress['total']} jobs"
        if progress["total"]
        else f"{progress['done']} result.json found"
    )
    return progress


def _parse_harness_summary(eval_dir: Path) -> dict[str, Any]:
    # Delegate to metrics so verified/ + stray CWD reports + empty-preds → 0/N stay in sync.
    from metrics import _iter_harness_report_candidates, _harness_summary_from_report, _resolved_from_preds

    preds = eval_dir / "runs" / "preds.json"
    summary: dict[str, Any] = {
        "preds_exists": preds.is_file(),
        "preds_path": str(preds.relative_to(eval_dir)) if preds.is_file() else None,
        "resolved": None,
        "total": None,
        "report_files": [],
    }
    run_dir = eval_dir.parent
    reports = _iter_harness_report_candidates(eval_dir, run_dir=run_dir)
    summary["report_files"] = []
    for report in reports[:50]:
        try:
            summary["report_files"].append(str(report.relative_to(eval_dir)))
        except ValueError:
            summary["report_files"].append(str(report))

    for report in reports:
        data = None
        try:
            data = json.loads(report.read_text())
        except Exception:
            continue
        if not isinstance(data, dict):
            continue
        parsed = _harness_summary_from_report(data, report, root=eval_dir)
        if parsed.get("resolved") is not None:
            summary["resolved"] = parsed["resolved"]
            summary["total"] = parsed.get("total")
            summary["primary_report"] = parsed.get("primary_report")
            break

    if summary["resolved"] is None:
        pred_resolved, pred_n = _resolved_from_preds(eval_dir)
        if pred_resolved is not None:
            summary["resolved"] = pred_resolved
        if summary["total"] is None and pred_n is not None:
            summary["total"] = pred_n
    return summary


def _parse_job_summary(eval_dir: Path) -> dict[str, Any]:
    """Best-effort Pier/Harbor result.json under eval_dir."""
    summary: dict[str, Any] = {"result_files": [], "reward_mean": None, "n_trials": None}
    results = sorted(eval_dir.rglob("result.json"))
    summary["result_files"] = [str(p.relative_to(eval_dir)) for p in results[:20]]
    for report in results:
        try:
            data = json.loads(report.read_text())
        except Exception:
            continue
        if isinstance(data, dict):
            for key in ("mean_reward", "reward_mean", "accuracy", "pass_rate"):
                if key in data and isinstance(data[key], (int, float)):
                    summary["reward_mean"] = float(data[key])
            for key in ("n", "n_trials", "num_trials", "total"):
                if key in data and isinstance(data[key], (int, float)):
                    summary["n_trials"] = int(data[key])
            summary["primary_result"] = str(report.relative_to(eval_dir))
            break
    return summary


@app.get("/api/health")
def api_health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/modes")
def list_modes() -> dict[str, Any]:
    return {
        "modes": [
            {"id": "swe", "label": "SWE-bench Verified (full)"},
            {"id": "swe_20filter", "label": "SWE-bench 20filter (special)"},
            {"id": "deepswe", "label": "DeepSWE 1.1"},
            {"id": "terminal", "label": "Terminal-Bench"},
        ]
    }


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
                "mode": status.get("mode", "unknown"),
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
    if body.mode not in SUPPORTED_MODES:
        raise HTTPException(
            status_code=400,
            detail=f"mode must be one of {', '.join(SUPPORTED_MODES)}",
        )
    cluster = (body.cluster or "us").strip().lower()
    if cluster not in ("us", "shanghai"):
        raise HTTPException(status_code=400, detail="cluster must be us or shanghai")
    if body.router_mode not in ("tag", "entropy", "slm_only"):
        raise HTTPException(
            status_code=400, detail="router_mode must be tag, entropy, or slm_only"
        )
    if not body.model_path and not (body.slm_base_url and body.slm_model):
        raise HTTPException(
            status_code=400,
            detail="set model_path (local) or slm_base_url + slm_model (remote)",
        )
    if body.router_mode != "slm_only":
        if not body.llm_base_url or not body.llm_api_key or not body.llm_model:
            raise HTTPException(
                status_code=400,
                detail="llm_base_url, llm_api_key, llm_model required (unless router_mode=slm_only)",
            )
    if body.mode == "deepswe" and not Path(body.deepswe_tasks).is_dir():
        raise HTTPException(
            status_code=400,
            detail=f"deepswe_tasks not a directory: {body.deepswe_tasks}",
        )
    if not RUN_SH.is_file():
        raise HTTPException(status_code=500, detail=f"missing {RUN_SH}")

    explicit_run_id = body.run_id.strip()
    want_resume = bool(body.resume)
    if want_resume and not explicit_run_id:
        raise HTTPException(status_code=400, detail="resume=true requires an existing run_id")

    run_id = explicit_run_id or f"{body.mode}_{time.strftime('%Y%m%d_%H%M%S')}"
    _require_run_id(run_id)
    run_dir = OUTPUT_DIR / run_id
    resumed = False
    prev_status: dict[str, Any] = {}

    if run_dir.exists():
        prev_status = _read_json(run_dir / "status.json")
        if _pid_alive(prev_status.get("pid")):
            raise HTTPException(
                status_code=409,
                detail=f"run still running (pid={prev_status.get('pid')}): stop it before resume",
            )
        if not want_resume:
            raise HTTPException(
                status_code=409,
                detail=f"run_id already exists: {run_id} (set resume=true to continue)",
            )
        resumed = True
    elif want_resume:
        raise HTTPException(status_code=404, detail=f"run_id not found for resume: {run_id}")

    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "logs").mkdir(parents=True, exist_ok=True)

    n_concurrent = body.n_concurrent if body.n_concurrent is not None else body.workers
    use_llm = "false" if body.router_mode == "slm_only" else "true"
    slm_backend = (body.slm_backend or "vllm").strip().lower()
    if slm_backend not in ("vllm", "sglang"):
        raise HTTPException(status_code=400, detail="slm_backend must be vllm or sglang")
    # Prefer slm_port; fall back to legacy vllm_port when client only sends that.
    slm_port = int(body.slm_port or body.vllm_port or 8007)
    # Match env_paths.sh: .venv for vLLM/adapter; base conda for SWE harness.
    venv_dir = Path(os.environ.get("VENV_DIR") or "/workspace/work/mjy/.venv")
    harness_py = Path(os.environ.get("HARNESS_PYTHON") or "/workspace/.conda/bin/python")
    if not harness_py.is_file():
        harness_py = Path("/workspace/.conda/bin/python3")
    env = os.environ.copy()
    env.update(
        {
            "MODE": body.mode,
            "CLUSTER": cluster,
            "RUN_ID": run_id,
            "ROUTER_MODE": body.router_mode,
            "OFFLOAD_MODE": body.offload_mode,
            "USE_LLM": use_llm,
            "ADAPTER_PORT": str(body.adapter_port),
            "SLM_BACKEND": slm_backend,
            "SLM_PORT": str(slm_port),
            "VLLM_PORT": str(slm_port),
            "WORKERS": str(body.workers),
            "HARNESS_WORKERS": str(body.harness_workers),
            "STEP_LIMIT": str(max(1, int(body.step_limit or 150))),
            "N_CONCURRENT": str(n_concurrent),
            "CUDA_VISIBLE_DEVICES": body.cuda_visible_devices,
            "LLM_BASE_URL": body.llm_base_url or "http://127.0.0.1:0/v1",
            "LLM_API_KEY": body.llm_api_key or "unused",
            "LLM_MODEL": body.llm_model or "unused",
            "SLM_API_KEY": body.slm_api_key or "dummy",
            "DEEPSWE_TASKS": body.deepswe_tasks,
            "TB_DATASET": body.tb_dataset,
            "RESUME": "1" if resumed else "0",
            "VENV_DIR": str(venv_dir),
            "PYTHON_BIN": str(venv_dir / "bin" / "python"),
            "VLLM_BIN": str(venv_dir / "bin" / "vllm"),
            "HARNESS_PYTHON": str(harness_py),
        }
    )
    # Context length / any other engine flags belong inside EXTRA_ARGS (--max-model-len / --context-length).
    env.pop("MAX_MODEL_LEN", None)
    if (body.vllm_extra_args or "").strip():
        env["VLLM_EXTRA_ARGS"] = body.vllm_extra_args.strip()
    else:
        env.pop("VLLM_EXTRA_ARGS", None)
    if (body.sglang_extra_args or "").strip():
        env["SGLANG_EXTRA_ARGS"] = body.sglang_extra_args.strip()
    else:
        env.pop("SGLANG_EXTRA_ARGS", None)
    n_tasks = (body.n_tasks or "").strip()
    if n_tasks:
        env["N_TASKS"] = n_tasks
    else:
        env.pop("N_TASKS", None)

    if body.model_path:
        env["MODEL_PATH"] = body.model_path
        env.pop("SLM_BASE_URL", None)
    else:
        env["SLM_BASE_URL"] = body.slm_base_url
        env["SLM_MODEL"] = body.slm_model
        env.pop("MODEL_PATH", None)

    now = time.strftime("%Y-%m-%dT%H:%M:%S")
    web_log = run_dir / "logs" / "web_launch.log"
    with web_log.open("a" if resumed else "w") as logf:
        action = "resuming" if resumed else "starting"
        logf.write(
            f"{action} {RUN_SH} mode={body.mode} cluster={cluster} run_id={run_id}\n"
        )
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
        **prev_status,
        "run_id": run_id,
        "mode": body.mode,
        "cluster": cluster,
        "router_mode": body.router_mode,
        "offload_mode": body.offload_mode,
        "phase": "starting_adapter",
        "message": "resuming from web UI" if resumed else "launched from web UI",
        "updated_at": now,
        "pid": proc.pid,
    }
    status.setdefault("started_at", now)
    status.pop("finished_at", None)
    (run_dir / "status.json").write_text(json.dumps(status, indent=2) + "\n")

    return JSONResponse(
        {"run_id": run_id, "pid": proc.pid, "resumed": resumed, "status": status}
    )


def _slm_log_path_from_adapter_api(adapter_api_text: str) -> Optional[Path]:
    for line in adapter_api_text.splitlines():
        if any(name in line for name in ("slm_serve.log", "vllm_serve.log", "sglang_serve.log")):
            if "log ->" in line or "log=" in line or "->" in line:
                m = re.search(r"(/[^\s]+(?:slm|vllm|sglang)_serve\.log)", line)
                if m:
                    p = Path(m.group(1))
                    if p.is_file() or p.is_symlink():
                        return p
    return None


def _collect_run_logs(run_dir: Path, status: dict[str, Any], log_tail: int = 48_000) -> dict[str, str]:
    log_dir = run_dir / "logs"
    logs: dict[str, str] = {
        "adapter_api": _tail_file(log_dir / "adapter_api.log", log_tail),
        "slm_serve": "",
        "vllm_serve": "",  # legacy alias filled below
        "adapter": _tail_file(log_dir / "adapter.log", log_tail),
        "eval": _tail_file(log_dir / "eval.log", log_tail),
        "web_launch": _tail_file(log_dir / "web_launch.log", log_tail),
        "minisweagent": "",
    }
    for name in ("slm_serve.log", "vllm_serve.log", "sglang_serve.log"):
        text = _tail_file(log_dir / name, log_tail)
        if text:
            logs["slm_serve"] = text
            break
    if not logs["slm_serve"] and log_dir.is_dir():
        for pattern in ("slm_serve.log", "vllm_serve.log", "sglang_serve.log"):
            for p in sorted(log_dir.rglob(pattern)):
                logs["slm_serve"] = _tail_file(p, log_tail)
                if logs["slm_serve"]:
                    break
            if logs["slm_serve"]:
                break
    if not logs["slm_serve"]:
        hinted = _slm_log_path_from_adapter_api(logs.get("adapter_api") or "")
        if hinted is not None:
            logs["slm_serve"] = _tail_file(hinted, log_tail)
    logs["vllm_serve"] = logs["slm_serve"]
    if not logs["adapter"] and log_dir.is_dir():
        for p in sorted(log_dir.rglob("adapter.log")):
            if p.name == "adapter_api.log":
                continue
            logs["adapter"] = _tail_file(p, log_tail)
            break

    # mini-extra writes progress here (Saved trajectory / container starts)
    mode = status.get("mode") or ""
    eval_dir = _find_eval_dir(run_dir, mode)
    if eval_dir is not None:
        for cand in (
            eval_dir / "runs" / "minisweagent.log",
            eval_dir / "minisweagent.log",
        ):
            if cand.is_file():
                logs["minisweagent"] = _tail_file(cand, log_tail)
                break
        if not logs["minisweagent"]:
            for p in sorted(eval_dir.rglob("minisweagent.log")):
                logs["minisweagent"] = _tail_file(p, log_tail)
                break

    chunks: list[str] = []
    for key, title in (
        ("adapter_api", "adapter_api (api.sh stdout)"),
        ("slm_serve", "slm_serve (vllm/sglang)"),
        ("minisweagent", "minisweagent (instance progress)"),
        ("eval", "eval"),
        ("adapter", "adapter"),
    ):
        body = (logs.get(key) or "").strip()
        if body:
            chunks.append(f"===== {title} =====\n{body}")
    logs["live"] = "\n\n".join(chunks) if chunks else "(waiting for logs…)"
    return logs


@app.get("/api/runs/{run_id}")
def get_run(run_id: str, log_tail: int = 48000) -> dict[str, Any]:
    run_dir = _run_dir(run_id)
    if not run_dir.is_dir():
        raise HTTPException(status_code=404, detail="run not found")
    status = _read_json(run_dir / "status.json")
    logs = _collect_run_logs(run_dir, status, log_tail)
    progress = _compute_progress(run_dir, status)
    return {
        "run_id": run_id,
        "status": status,
        "phase": status.get("phase", "unknown"),
        "progress": progress,
        "logs": logs,
        "files": _list_relative_files(run_dir),
    }


@app.get("/api/leaderboard")
def api_leaderboard(mode: str = "swe_20filter") -> dict[str, Any]:
    if mode not in SUPPORTED_MODES:
        raise HTTPException(
            status_code=400,
            detail=f"mode must be one of {', '.join(SUPPORTED_MODES)}",
        )
    data = parse_leaderboard(RESULT_MD, mode)
    data["result_md"] = str(RESULT_MD)
    return data


@app.post("/api/runs/{run_id}/sync_result")
def sync_run_result(run_id: str) -> dict[str, Any]:
    """Recompute metrics and upsert into result.md (manual refresh)."""
    run_dir = _run_dir(run_id)
    if not run_dir.is_dir():
        raise HTTPException(status_code=404, detail="run not found")
    try:
        out = persist_run_to_result_md(run_dir, RESULT_MD, force=True)
    except Exception as ex:
        raise HTTPException(status_code=500, detail=str(ex)) from ex
    return out


@app.get("/api/runs/{run_id}/results")
def get_results(run_id: str) -> dict[str, Any]:
    run_dir = _run_dir(run_id)
    if not run_dir.is_dir():
        raise HTTPException(status_code=404, detail="run not found")
    status = _read_json(run_dir / "status.json")
    mode = status.get("mode") or ""
    eval_dir = _find_eval_dir(run_dir, mode)
    summary: dict[str, Any] = {}
    if eval_dir is not None:
        if mode in ("swe", "swe_20filter") or (eval_dir / "runs").is_dir():
            summary = _parse_harness_summary(eval_dir)
        if mode in ("deepswe", "terminal") or not summary.get("preds_exists"):
            job = _parse_job_summary(eval_dir)
            summary = {**summary, **job}
    metrics = compute_run_metrics(run_dir)
    return {
        "run_id": run_id,
        "status": status,
        "eval_dir": eval_dir.name if eval_dir else None,
        "summary": summary,
        "metrics": metrics,
        "metrics_row": format_metrics_row(metrics),
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
