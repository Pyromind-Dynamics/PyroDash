#!/usr/bin/env python3
"""Web UI for coding evals: swe / swe_20filter / deepswe / terminal."""
from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import signal
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
    _planned_instance_count,
    compute_run_metrics,
    format_metrics_row,
    parse_leaderboard,
    persist_run_to_result_md,
    planned_count_from_mini_extra_args,
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
        "--gpu-memory-utilization 0.90\n"
        "--tensor-parallel-size 1\n"
        "--trust-remote-code\n"
        "--reasoning-parser qwen3\n"
        "--enable-auto-tool-choice\n"
        "--tool-call-parser qwen3_coder"
    )
    sglang_extra_args: str = (
        "--tp 1\n"
        "--mem-fraction-static 0.90\n"
        "--tool-call-parser qwen3_coder\n"
        "--reasoning-parser qwen3"
    )
    # Empty: eval.sh keeps WORKERS / STEP_LIMIT / INSTANCE_FILTER.
    mini_extra_args: str = ""
    offload_mode: str = "handoff"
    workers: int = 4
    harness_workers: int = 8
    step_limit: int = 150  # SWE agent.step_limit
    n_concurrent: Optional[int] = None
    n_tasks: str = ""  # empty = all; number as string for optional
    deepswe_tasks: str = ""  # required when mode=deepswe; set in web UI
    tb_dataset: str = "terminal-bench/terminal-bench-2-1"
    cuda_visible_devices: str = "0"
    run_id: str = ""
    resume: bool = False
    # Required from web UI (or process env when launching server with exports).
    vllm_env: str = ""  # vLLM / SLM conda env root
    harness_python: str = ""  # SWE harness: env root or .../bin/python


def _require_run_id(run_id: str) -> str:
    if not SAFE_RUN_ID.match(run_id):
        raise HTTPException(status_code=400, detail="invalid run_id")
    return run_id


def _resolve_env_prefix(raw: str) -> Optional[Path]:
    """Accept env root or .../bin/python → return env prefix Path, or None if empty/invalid."""
    text = (raw or "").strip()
    if not text:
        return None
    p = Path(text).expanduser()
    if p.is_file() and p.name.startswith("python"):
        # .../bin/python → env root
        if p.parent.name == "bin":
            return p.parent.parent
        return p.parent
    if p.is_dir():
        if (p / "bin" / "python").is_file() or (p / "bin" / "python3").is_file():
            return p
        if p.name == "bin" and (
            (p / "python").is_file() or (p / "python3").is_file()
        ):
            return p.parent
    return p if text else None


def _python_in_prefix(prefix: Path) -> Path:
    for name in ("python", "python3"):
        cand = prefix / "bin" / name
        if cand.is_file():
            return cand
    return prefix / "bin" / "python"


def _resolve_run_python_envs(body: StartRunRequest) -> tuple[Path, Path]:
    """Return (vllm_env, harness_python) from UI fields, else process env. No machine defaults."""
    vllm_raw = (body.vllm_env or "").strip() or os.environ.get("VLLM_ENV", "").strip()
    harness_raw = (body.harness_python or "").strip() or os.environ.get(
        "HARNESS_PYTHON", ""
    ).strip()

    if not vllm_raw:
        raise HTTPException(
            status_code=400,
            detail="vllm_env required (vLLM 环境路径，在网页「Python 环境」填写)",
        )
    if not harness_raw:
        raise HTTPException(
            status_code=400,
            detail="harness_python required (SWE harness 环境路径，在网页「Python 环境」填写)",
        )

    vllm_prefix = _resolve_env_prefix(vllm_raw)
    if vllm_prefix is None:
        raise HTTPException(
            status_code=400,
            detail=f"invalid vllm_env: {vllm_raw}",
        )

    harness_prefix = _resolve_env_prefix(harness_raw)
    if harness_prefix is not None:
        harness_py = _python_in_prefix(harness_prefix)
    else:
        harness_py = Path(harness_raw).expanduser()

    return vllm_prefix, harness_py


def _conda_env_roots_from_env() -> list[Path]:
    """Derive conda envs directories from CONDA_* only (no hardcoded machine paths)."""
    roots: list[Path] = []
    seen: set[str] = set()

    def _add(p: Path) -> None:
        key = str(p)
        if key in seen or not p.is_dir():
            return
        seen.add(key)
        roots.append(p)

    envs_path = os.environ.get("CONDA_ENVS_PATH", "").strip()
    if envs_path:
        for part in envs_path.split(os.pathsep):
            part = part.strip()
            if part:
                _add(Path(part))

    for key in ("CONDA_PREFIX", "CONDA_ROOT", "CONDA_EXE"):
        raw = os.environ.get(key, "").strip()
        if not raw:
            continue
        p = Path(raw)
        if key == "CONDA_EXE":
            # .../bin/conda → install root → envs
            install = p.parent.parent if p.parent.name == "bin" else p.parent
            _add(install / "envs")
        elif key == "CONDA_PREFIX":
            # active env: .../envs/name → .../envs ; or base → base/envs
            if p.parent.name == "envs":
                _add(p.parent)
            else:
                _add(p / "envs")
        else:  # CONDA_ROOT
            _add(p / "envs")

    return roots


def _discover_conda_envs() -> list[str]:
    """Best-effort list of conda env prefixes for UI datalist (dynamic, no hardcodes)."""
    out: list[str] = []
    seen: set[str] = set()

    # Prefer `conda env list --json` when available
    try:
        proc = subprocess.run(
            ["conda", "env", "list", "--json"],
            capture_output=True,
            text=True,
            timeout=8,
            check=False,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            data = json.loads(proc.stdout)
            for p in data.get("envs") or []:
                key = str(p)
                if key in seen:
                    continue
                prefix = Path(key)
                if (prefix / "bin" / "python").is_file() or (
                    prefix / "bin" / "python3"
                ).is_file():
                    seen.add(key)
                    out.append(key)
    except (OSError, json.JSONDecodeError, subprocess.TimeoutExpired):
        pass

    for root in _conda_env_roots_from_env():
        try:
            for child in sorted(root.iterdir()):
                if not child.is_dir():
                    continue
                if not (child / "bin" / "python").is_file() and not (
                    child / "bin" / "python3"
                ).is_file():
                    continue
                key = str(child)
                if key in seen:
                    continue
                seen.add(key)
                out.append(key)
        except OSError:
            continue
    return out


def _tmux_session_name(run_id: str) -> str:
    return f"pyrodash_{run_id}"


def _tmux_socket(run_dir: Path) -> Path:
    return run_dir / "tmux.sock"


def _require_tmux() -> str:
    path = shutil.which("tmux")
    if not path:
        raise HTTPException(
            status_code=500,
            detail="tmux not found. Install tmux before starting a run.",
        )
    return path


def _tmux_has_session(sock: Path, session: str) -> bool:
    tmux = shutil.which("tmux")
    if not tmux or not sock.exists() or not session:
        return False
    proc = subprocess.run(
        [tmux, "-S", str(sock), "has-session", "-t", session],
        capture_output=True,
        text=True,
    )
    return proc.returncode == 0


def _live_pane_pid(status: dict[str, Any], run_dir: Path) -> Any:
    """Prefer status.json pid; if that process is gone, read the tmux pane pid."""
    pid = status.get("pid")
    if _pid_alive(pid):
        return pid
    session = str(status.get("tmux_session") or "")
    sock = _tmux_socket(run_dir)
    tmux = shutil.which("tmux")
    if not tmux or not session or not _tmux_has_session(sock, session):
        return pid
    proc = subprocess.run(
        [tmux, "-S", str(sock), "list-panes", "-t", session, "-F", "#{pane_pid}"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    if proc.returncode != 0:
        return pid
    lines = (proc.stdout or "").strip().splitlines()
    if lines and lines[0].isdigit():
        return int(lines[0])
    return pid


def _run_alive(status: dict[str, Any], run_dir: Path) -> bool:
    if _pid_alive(status.get("pid")):
        return True
    session = str(status.get("tmux_session") or "")
    return bool(session) and _tmux_has_session(_tmux_socket(run_dir), session)


def _signal_group(pid: Any, sig: int) -> bool:
    try:
        pid_i = int(pid)
    except (TypeError, ValueError):
        return False
    if pid_i <= 0:
        return False
    try:
        pgid = os.getpgid(pid_i)
    except ProcessLookupError:
        return False
    os.killpg(pgid, sig)
    return True


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
        planned = _planned_instance_count(run_dir)
        if planned:
            progress["total"] = planned
        elif mode == "swe_20filter":
            progress["total"] = SWE20_EXPECTED
        elif status.get("phase") in ("done", "stopped", "failed") and progress["done"]:
            progress["total"] = progress["done"]
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
    from metrics import _iter_harness_report_candidates, _parse_harness, _resolved_from_preds

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

    parsed = _parse_harness(eval_dir, run_dir=run_dir)
    summary["resolved"] = parsed.get("resolved")
    summary["total"] = parsed.get("total")
    if parsed.get("primary_report"):
        summary["primary_report"] = parsed["primary_report"]

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


@app.get("/api/envs")
def list_envs() -> dict[str, Any]:
    """Suggest conda env prefixes for the Python-env form fields."""
    envs = _discover_conda_envs()
    return {
        "envs": envs,
        "defaults": {
            "vllm_env": os.environ.get("VLLM_ENV", ""),
            "harness_python": os.environ.get("HARNESS_PYTHON", ""),
        },
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
    if body.mode == "deepswe":
        tasks = (body.deepswe_tasks or "").strip()
        if not tasks:
            raise HTTPException(
                status_code=400,
                detail="deepswe_tasks required when mode=deepswe (set in web UI)",
            )
        if not Path(tasks).is_dir():
            raise HTTPException(
                status_code=400,
                detail=f"deepswe_tasks not a directory: {tasks}",
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
        if _run_alive(prev_status, run_dir):
            raise HTTPException(
                status_code=409,
                detail=(
                    f"run still running (pid={prev_status.get('pid')}, "
                    f"tmux={prev_status.get('tmux_session') or '-'}): stop it before resume"
                ),
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
    # Python envs: UI fields first, then process env (resolved in run_use only).
    vllm_env, harness_py = _resolve_run_python_envs(body)
    python_bin = _python_in_prefix(vllm_env)
    vllm_bin = vllm_env / "bin" / "vllm"
    if not python_bin.is_file():
        raise HTTPException(
            status_code=400,
            detail=f"vLLM env missing python: {python_bin} (check VLLM_ENV)",
        )
    if body.model_path and slm_backend == "vllm" and not vllm_bin.is_file():
        raise HTTPException(
            status_code=400,
            detail=f"vllm binary not found: {vllm_bin} (check vLLM 环境路径)",
        )
    if not harness_py.is_file():
        raise HTTPException(
            status_code=400,
            detail=f"SWE harness python not found: {harness_py} (check HARNESS_PYTHON)",
        )
    path_parts = [str(vllm_env / "bin"), str(harness_py.parent)]
    if os.environ.get("PATH"):
        path_parts.append(os.environ["PATH"])
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
            "VLLM_ENV": str(vllm_env),
            "PYTHON_BIN": str(python_bin),
            "VLLM_BIN": str(vllm_bin),
            "VLLM_CONDA_PREFIX": str(vllm_env),
            "HARNESS_PYTHON": str(harness_py),
            "PATH": ":".join(path_parts),
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
    if (body.mini_extra_args or "").strip():
        env["MINI_EXTRA_ARGS"] = body.mini_extra_args.strip()
    else:
        env.pop("MINI_EXTRA_ARGS", None)
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
    tmux = _require_tmux()
    session = _tmux_session_name(run_id)
    sock = _tmux_socket(run_dir)
    if _tmux_has_session(sock, session):
        raise HTTPException(
            status_code=409,
            detail=f"tmux session still running: {session}",
        )
    if sock.exists():
        sock.unlink()
    web_log = run_dir / "logs" / "web_launch.log"
    action = "resuming" if resumed else "starting"
    with web_log.open("a" if resumed else "w") as logf:
        logf.write(
            f"{action} {RUN_SH} mode={body.mode} cluster={cluster} "
            f"run_id={run_id} tmux={session}\n"
        )
    mini_extra = (body.mini_extra_args or "").strip()
    planned = planned_count_from_mini_extra_args(mini_extra)
    if planned is None and body.mode == "swe_20filter":
        planned = SWE20_EXPECTED
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
        "tmux_session": session,
        "pid": None,
        "mini_extra_args": mini_extra,
    }
    if planned is not None:
        status["planned_instances"] = planned
    else:
        status.pop("planned_instances", None)
    status.setdefault("started_at", now)
    status.pop("finished_at", None)
    status_path = run_dir / "status.json"
    status_path.write_text(json.dumps(status, indent=2) + "\n")

    shell_cmd = (
        f"exec bash {shlex.quote(str(RUN_SH))} >> {shlex.quote(str(web_log))} 2>&1"
    )
    launched = subprocess.run(
        [
            tmux,
            "-S",
            str(sock),
            "new-session",
            "-d",
            "-s",
            session,
            "-c",
            str(RUN_USE_ROOT),
            shell_cmd,
        ],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if launched.returncode != 0:
        detail = (launched.stderr or launched.stdout or "tmux new-session failed").strip()
        status["phase"] = "failed"
        status["message"] = detail
        status["finished_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        status_path.write_text(json.dumps(status, indent=2) + "\n")
        raise HTTPException(status_code=500, detail=detail)
    subprocess.run(
        [
            tmux,
            "-S",
            str(sock),
            "set-option",
            "-w",
            "-t",
            session,
            "remain-on-exit",
            "off",
        ],
        capture_output=True,
        text=True,
        timeout=10,
    )
    pane = subprocess.run(
        [
            tmux,
            "-S",
            str(sock),
            "list-panes",
            "-t",
            session,
            "-F",
            "#{pane_pid}",
        ],
        capture_output=True,
        text=True,
        timeout=10,
    )
    pane_pid = None
    if pane.returncode == 0:
        first = (pane.stdout or "").strip().splitlines()
        if first and first[0].isdigit():
            pane_pid = int(first[0])
    # Re-read so a fast script update is not replaced by the pre-launch snapshot.
    current = _read_json(status_path) or status
    current["tmux_session"] = session
    current["pid"] = pane_pid
    status_path.write_text(json.dumps(current, indent=2) + "\n")

    return JSONResponse(
        {
            "run_id": run_id,
            "pid": pane_pid,
            "tmux_session": session,
            "resumed": resumed,
            "status": current,
        }
    )


@app.post("/api/runs/{run_id}/stop")
def stop_run(run_id: str) -> dict[str, Any]:
    """Stop one run: SIGTERM its process group, then drop the tmux session."""
    run_dir = _run_dir(run_id)
    status_path = run_dir / "status.json"
    if not status_path.is_file():
        raise HTTPException(status_code=404, detail="run not found")
    status = _read_json(status_path)
    alive = _run_alive(status, run_dir)
    phase = str(status.get("phase") or "")
    if not alive and phase not in ("starting_adapter", "evaluating"):
        return {"run_id": run_id, "phase": phase, "stopped": False}

    now = time.strftime("%Y-%m-%dT%H:%M:%S")
    status["phase"] = "stopped"
    status["message"] = "stopped from web UI"
    status["updated_at"] = now
    status["finished_at"] = now
    status_path.write_text(json.dumps(status, indent=2) + "\n")

    pid = _live_pane_pid(status, run_dir)
    status["pid"] = pid
    if _pid_alive(pid):
        try:
            _signal_group(pid, signal.SIGTERM)
        except PermissionError as exc:
            raise HTTPException(status_code=500, detail=f"cannot signal pid {pid}: {exc}") from exc

    deadline = time.time() + 8
    while time.time() < deadline and _run_alive(status, run_dir):
        time.sleep(0.4)

    if _run_alive(status, run_dir):
        session = str(status.get("tmux_session") or "")
        sock = _tmux_socket(run_dir)
        tmux = shutil.which("tmux")
        if tmux and session and sock.exists():
            subprocess.run(
                [tmux, "-S", str(sock), "kill-session", "-t", session],
                capture_output=True,
                text=True,
                timeout=10,
            )
        if _pid_alive(pid):
            try:
                _signal_group(pid, signal.SIGKILL)
            except OSError:
                pass
    return {"run_id": run_id, "phase": "stopped", "stopped": True, "pid": pid}


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
