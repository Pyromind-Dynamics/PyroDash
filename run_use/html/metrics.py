"""Unified run metrics + result.md leaderboard I/O for run_use history."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Optional

# Fixed prices used by result.md (USD per million tokens)
SLM_IN_PER_M = 0.016
SLM_OUT_PER_M = 0.23
LLM_IN_PER_M = 0.44
LLM_OUT_PER_M = 1.32

MODE_SECTIONS: dict[str, str] = {
    "swe_20filter": "# SWE-bench Verified（representative 20filter）",
    "swe": "# SWE-bench Verified（500）",
    "terminal": "# Terminal-Bench",
    "deepswe": "# DeepSWE 1.1",
}

MODE_EXPECTED_TOTAL: dict[str, Optional[int]] = {
    "swe_20filter": 20,
    "swe": 500,
    "terminal": 89,
    "deepswe": None,
}

SCORE_IS_RATE = frozenset({"terminal", "deepswe"})

COLUMNS = [
    "model",
    "score",
    "call_rate",
    "turn_call_rate",
    "offload_count",
    "turns",
    "slm_prompt",
    "slm_output",
    "llm_input",
    "llm_output",
    "slm_cost",
    "llm_cost",
    "cost_sum",
]


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text())
    except Exception:
        return None


def _fmt_int(n: int) -> str:
    return f"{int(n):,}"


def _fmt_pct(x: float) -> str:
    if x >= 0.9995:
        return "100%"
    return f"{x * 100:.1f}%"


def _fmt_cost(x: float) -> str:
    return f"{x:.2f}"


def _cost(slm_in: int, slm_out: int, llm_in: int, llm_out: int) -> tuple[float, float, float]:
    slm = slm_in / 1e6 * SLM_IN_PER_M + slm_out / 1e6 * SLM_OUT_PER_M
    llm = llm_in / 1e6 * LLM_IN_PER_M + llm_out / 1e6 * LLM_OUT_PER_M
    return slm, llm, slm + llm


def find_eval_dir(run_dir: Path, mode: str) -> Optional[Path]:
    for name in (mode, "swe_20filter", "swe", "deepswe", "terminal"):
        p = run_dir / name
        if p.is_dir():
            return p
    return None


def find_adapter_stats_dir(run_dir: Path) -> Optional[Path]:
    candidates = [
        run_dir / "logs" / "adapter_stats",
        run_dir / "adapter_stats",
    ]
    for c in candidates:
        if c.is_dir():
            return c
    # nested under logs/*
    log_dir = run_dir / "logs"
    if log_dir.is_dir():
        for p in sorted(log_dir.rglob("summary.json")):
            parent = p.parent
            if parent.name == "adapter_stats" or (parent / "sessions").is_dir():
                return parent
            if p.name == "summary.json" and "adapter" in str(parent):
                return parent
    return None


def _load_adapter_totals(stats_dir: Path) -> dict[str, Any]:
    """Aggregate turns / offloads / tokens from summary or session files."""
    out = {
        "sessions": 0,
        "sessions_with_offload": 0,
        "turns": 0,
        "offload_count": 0,
        "slm_prompt": 0,
        "slm_output": 0,
        "llm_input": 0,
        "llm_output": 0,
    }
    summary_path = stats_dir / "summary.json"
    data = _read_json(summary_path) if summary_path.is_file() else None
    sessions: list[dict[str, Any]] = []
    if isinstance(data, dict):
        totals = data.get("totals") or {}
        if isinstance(totals, dict) and totals:
            out["sessions"] = int(totals.get("sessions") or 0)
            out["turns"] = int(totals.get("turns") or 0)
            out["offload_count"] = int(totals.get("offload_count") or 0)
            out["slm_prompt"] = int(totals.get("slm_prompt_tokens") or 0)
            out["slm_output"] = int(totals.get("slm_completion_tokens") or 0)
            out["llm_input"] = int(totals.get("llm_prompt_tokens") or 0)
            out["llm_output"] = int(totals.get("llm_completion_tokens") or 0)
        raw_sessions = data.get("sessions")
        if isinstance(raw_sessions, list):
            sessions = [s for s in raw_sessions if isinstance(s, dict)]

    sess_dir = stats_dir / "sessions"
    if not sessions and sess_dir.is_dir():
        for p in sorted(sess_dir.glob("*.json")):
            s = _read_json(p)
            if isinstance(s, dict):
                sessions.append(s)

    # token_usage/summary.json alternate shape
    tu = stats_dir / "token_usage" / "summary.json"
    tu_data = _read_json(tu) if tu.is_file() else None
    if isinstance(tu_data, dict):
        totals = tu_data.get("totals") or {}
        if isinstance(totals, dict):
            if not out["turns"]:
                out["turns"] = int(totals.get("turns") or 0)
            if not out["offload_count"]:
                out["offload_count"] = int(
                    totals.get("offload_turns") or totals.get("offload_count") or 0
                )
            if not out["slm_prompt"]:
                out["slm_prompt"] = int(totals.get("slm_prompt_tokens") or 0)
                out["slm_output"] = int(totals.get("slm_completion_tokens") or 0)
                out["llm_input"] = int(totals.get("llm_prompt_tokens") or 0)
                out["llm_output"] = int(totals.get("llm_completion_tokens") or 0)
        tasks = tu_data.get("tasks")
        if isinstance(tasks, list) and not sessions:
            for t in tasks:
                if not isinstance(t, dict):
                    continue
                off = int(t.get("offload_turns") or t.get("offload_count") or 0)
                out["sessions"] += 1
                if off > 0:
                    out["sessions_with_offload"] += 1

    if sessions:
        out["sessions"] = len(sessions)
        with_off = 0
        if not out["turns"]:
            for s in sessions:
                out["turns"] += int(s.get("turns") or 0)
                off = int(s.get("offload_count") or s.get("offload_turns") or 0)
                out["offload_count"] += off
                out["slm_prompt"] += int(s.get("slm_prompt_tokens") or 0)
                out["slm_output"] += int(s.get("slm_completion_tokens") or 0)
                out["llm_input"] += int(s.get("llm_prompt_tokens") or 0)
                out["llm_output"] += int(s.get("llm_completion_tokens") or 0)
                if off > 0:
                    with_off += 1
            out["sessions_with_offload"] = with_off
        else:
            for s in sessions:
                off = int(s.get("offload_count") or s.get("offload_turns") or 0)
                if off > 0:
                    with_off += 1
            out["sessions_with_offload"] = with_off

    return out


def _harness_summary_from_report(data: dict[str, Any], report: Path, *, root: Path) -> dict[str, Any]:
    """Extract resolved/submitted totals from a swebench run report JSON."""
    summary: dict[str, Any] = {"resolved": None, "total": None, "primary_report": None}
    for key in ("resolved_instances", "resolved", "num_resolved"):
        if key in data and isinstance(data[key], (int, float)):
            summary["resolved"] = int(data[key])
            break
    # Denominator = instances we actually ran/submitted — NEVER full-dataset
    # total_instances (500 for Verified) which swebench always puts in the report.
    for key in ("submitted_instances", "submitted"):
        if key in data and isinstance(data[key], (int, float)) and int(data[key]) > 0:
            summary["total"] = int(data[key])
            break
    if summary["total"] is None:
        empty_n = data.get("empty_patch_instances")
        if isinstance(empty_n, (int, float)) and int(empty_n) > 0:
            # Empty-patch-only runs still submitted N instances.
            submitted_ids = data.get("submitted_ids") or data.get("empty_patch_ids")
            if isinstance(submitted_ids, list) and submitted_ids:
                summary["total"] = len(submitted_ids)
            else:
                summary["total"] = int(empty_n)
    if summary["resolved"] is not None:
        try:
            summary["primary_report"] = str(report.relative_to(root))
        except ValueError:
            summary["primary_report"] = str(report)
        return summary
    if data and all(isinstance(v, dict) for v in data.values()):
        summary["resolved"] = sum(1 for v in data.values() if v.get("resolved") is True)
        summary["total"] = len(data)
        try:
            summary["primary_report"] = str(report.relative_to(root))
        except ValueError:
            summary["primary_report"] = str(report)
    return summary


def _iter_harness_report_candidates(eval_dir: Path, run_dir: Optional[Path] = None) -> list[Path]:
    """Locate swebench harness reports (verified/ or stray CWD dumps)."""
    seen: set[Path] = set()
    out: list[Path] = []

    def _add(p: Path) -> None:
        try:
            key = p.resolve()
        except Exception:
            key = p
        if key in seen or not p.is_file():
            return
        seen.add(key)
        out.append(p)

    verified = eval_dir / "verified"
    if verified.is_dir():
        for report in sorted(verified.rglob("*.json")):
            _add(report)
    for report in sorted(eval_dir.glob("*.json")):
        _add(report)

    # Older swebench ignores --report_dir and writes <model>.<run_id>.json to CWD
    # (run_use/) or next to the run. Prefer files that look like harness summaries.
    search_roots: list[Path] = []
    if run_dir is not None:
        search_roots.extend([run_dir, run_dir.parent])
    search_roots.append(eval_dir.parent)
    for root in search_roots:
        if not root.is_dir():
            continue
        for report in sorted(root.glob("*.json")):
            data = _read_json(report)
            if isinstance(data, dict) and (
                "resolved_instances" in data or "empty_patch_instances" in data
            ):
                _add(report)
    return out


def _parse_harness(eval_dir: Path, *, run_dir: Optional[Path] = None) -> dict[str, Any]:
    summary: dict[str, Any] = {"resolved": None, "total": None, "primary_report": None}
    for report in _iter_harness_report_candidates(eval_dir, run_dir=run_dir):
        data = _read_json(report)
        if not isinstance(data, dict):
            continue
        parsed = _harness_summary_from_report(data, report, root=eval_dir)
        if parsed.get("resolved") is not None:
            return parsed
    return summary


def _resolved_from_preds(eval_dir: Path) -> tuple[Optional[int], Optional[int]]:
    """If preds exist and all patches are empty, score is 0/N (harness skipped verify)."""
    preds_path = eval_dir / "runs" / "preds.json"
    data = _read_json(preds_path)
    if not isinstance(data, dict) or not data:
        return None, None
    n = len(data)
    nonempty = 0
    for v in data.values():
        if not isinstance(v, dict):
            continue
        patch = v.get("model_patch")
        if patch is None:
            patch = v.get("model_patch_text")
        if isinstance(patch, str) and patch.strip():
            nonempty += 1
    if nonempty == 0:
        return 0, n
    return None, n


def _parse_harbor(eval_dir: Path) -> dict[str, Any]:
    summary: dict[str, Any] = {"reward_mean": None, "n_trials": None, "primary_result": None}
    for report in sorted(eval_dir.rglob("result.json")):
        data = _read_json(report)
        if not isinstance(data, dict):
            continue
        for key in ("mean_reward", "reward_mean", "accuracy", "pass_rate"):
            if key in data and isinstance(data[key], (int, float)):
                summary["reward_mean"] = float(data[key])
        for key in ("n", "n_trials", "num_trials", "total"):
            if key in data and isinstance(data[key], (int, float)):
                summary["n_trials"] = int(data[key])
        summary["primary_result"] = str(report.relative_to(eval_dir))
        if summary["reward_mean"] is not None:
            return summary
    # fallback: average reward.json leaves
    rewards = list(eval_dir.rglob("reward.json"))
    if rewards:
        vals = []
        for p in rewards:
            data = _read_json(p)
            if isinstance(data, dict):
                for key in ("reward", "score", "value"):
                    if key in data and isinstance(data[key], (int, float)):
                        vals.append(float(data[key]))
                        break
            elif isinstance(data, (int, float)):
                vals.append(float(data))
        if vals:
            summary["reward_mean"] = sum(vals) / len(vals)
            summary["n_trials"] = len(vals)
    return summary


_RUNNING_ON = re.compile(r"Running on (\d+) instances")
# eval.sh dumps argv one token per line: "--slice" then "0:1", or "--slice=0:1".
_SLICE_SPEC = re.compile(
    r"(?:--slice(?:=|\s+)|--slice\n\s*)(\d*):(\d*)",
    re.MULTILINE,
)
_FILTER_SPEC = re.compile(
    r"(?:--filter(?:=|\s+)|--filter\n\s*)(\S+)",
    re.MULTILINE,
)


def _count_from_slice_spec(spec_start: str, spec_end: str) -> Optional[int]:
    """Map mini-extra ``--slice start:end`` to instance count when computable."""
    if spec_start == "" and spec_end.isdigit():
        return int(spec_end)
    if spec_end == "":
        return None
    if spec_start.isdigit() and spec_end.isdigit():
        start, end = int(spec_start), int(spec_end)
        if end >= start:
            return end - start
    return None


def planned_count_from_mini_extra_args(text: str) -> Optional[int]:
    """Parse ``--slice`` / ``--filter`` from MINI_EXTRA_ARGS (one flag per line OK)."""
    if not text or not str(text).strip():
        return None
    raw = str(text)
    # Prefer slice when both appear (UI often keeps an old filter line).
    slice_count: Optional[int] = None
    for match in _SLICE_SPEC.finditer(raw):
        n = _count_from_slice_spec(match.group(1), match.group(2))
        if n is not None:
            slice_count = n
    if slice_count is not None:
        return slice_count
    filter_count: Optional[int] = None
    for match in _FILTER_SPEC.finditer(raw):
        ids = [x for x in match.group(1).split("|") if x]
        if ids:
            filter_count = len(ids)
    return filter_count


def _planned_instance_count(run_dir: Path) -> Optional[int]:
    """Instances mini-extra actually scheduled, e.g. after --slice 0:1.

    Order: live ``Running on N`` → eval.log argv → status.json
    ``planned_instances`` / ``mini_extra_args`` (set at launch, before eval.log exists).
    """
    candidates = [run_dir / "logs" / "eval.log"]
    candidates.extend(run_dir.glob("*/runs/minisweagent.log"))
    found: Optional[int] = None
    argv_count: Optional[int] = None
    for path in candidates:
        if not path.is_file():
            continue
        try:
            text = path.read_text(errors="replace")
        except OSError:
            continue
        for match in _RUNNING_ON.finditer(text):
            found = int(match.group(1))
        n = planned_count_from_mini_extra_args(text)
        if n is not None:
            argv_count = n
    if found is not None:
        return found
    if argv_count is not None:
        return argv_count

    status = _read_json(run_dir / "status.json") or {}
    if isinstance(status, dict):
        raw_planned = status.get("planned_instances")
        if raw_planned is not None:
            try:
                return int(raw_planned)
            except (TypeError, ValueError):
                pass
        return planned_count_from_mini_extra_args(str(status.get("mini_extra_args") or ""))
    return None


def compute_run_metrics(run_dir: Path, *, model_name: Optional[str] = None) -> dict[str, Any]:
    """Compute one leaderboard-style metrics dict for a run_use output dir."""
    status = _read_json(run_dir / "status.json") or {}
    if not isinstance(status, dict):
        status = {}
    mode = str(status.get("mode") or "")
    run_id = str(status.get("run_id") or run_dir.name)
    name = model_name or run_id

    eval_dir = find_eval_dir(run_dir, mode)
    stats_dir = find_adapter_stats_dir(run_dir)
    adapter = _load_adapter_totals(stats_dir) if stats_dir else {
        "sessions": 0,
        "sessions_with_offload": 0,
        "turns": 0,
        "offload_count": 0,
        "slm_prompt": 0,
        "slm_output": 0,
        "llm_input": 0,
        "llm_output": 0,
    }

    expected = MODE_EXPECTED_TOTAL.get(mode)
    planned = _planned_instance_count(run_dir)
    resolved: Optional[int] = None
    # Prefer the count mini-extra scheduled (slice/filter) over the full benchmark size.
    total: Optional[int] = planned if planned is not None else expected
    reward_mean: Optional[float] = None

    if eval_dir is not None:
        if mode in ("swe", "swe_20filter") or (eval_dir / "verified").is_dir():
            h = _parse_harness(eval_dir, run_dir=run_dir)
            if h.get("resolved") is not None:
                resolved = int(h["resolved"])
            # Actual run size: scheduled count > preds count > harness submitted > mode expected.
            # Never use report total_instances (full SWE-bench Verified = 500).
            pred_resolved, pred_n = _resolved_from_preds(eval_dir)
            if planned is not None:
                total = planned
            elif pred_n is not None:
                total = pred_n
            elif h.get("total") is not None:
                total = int(h["total"])
            elif expected is not None:
                total = expected
            if resolved is None and pred_resolved is not None:
                resolved = pred_resolved
        if mode in ("terminal", "deepswe") or resolved is None:
            job = _parse_harbor(eval_dir)
            if job.get("reward_mean") is not None:
                reward_mean = float(job["reward_mean"])
            if job.get("n_trials") is not None and total is None:
                total = int(job["n_trials"])

    sessions = int(adapter["sessions"] or 0)
    if total is None and sessions:
        total = sessions
    with_off = int(adapter["sessions_with_offload"] or 0)
    turns = int(adapter["turns"] or 0)
    offloads = int(adapter["offload_count"] or 0)
    slm_in = int(adapter["slm_prompt"] or 0)
    slm_out = int(adapter["slm_output"] or 0)
    llm_in = int(adapter["llm_input"] or 0)
    llm_out = int(adapter["llm_output"] or 0)
    slm_c, llm_c, cost_sum = _cost(slm_in, slm_out, llm_in, llm_out)

    denom = total if total is not None else sessions
    if mode in SCORE_IS_RATE:
        if reward_mean is not None:
            # Harbor mean may be 0–1 or already percent
            pct = reward_mean * 100.0 if reward_mean <= 1.0 else float(reward_mean)
            score_str = f"{pct:.2f}%"
        else:
            score_str = "—"
        call_denom = denom if denom else 0
        call_rate = f"{with_off}/{call_denom}" if call_denom else f"{with_off}/?"
    else:
        # Explicit 0 is a valid score (all wrong / empty patches) — never hide as "—".
        if resolved is not None and denom:
            score_str = f"{resolved}/{denom}"
        elif resolved is not None:
            score_str = f"{resolved}/?"
        else:
            score_str = "—"
        call_denom = denom if denom else 0
        call_rate = f"{with_off}/{call_denom}" if call_denom else f"{with_off}/?"

    turn_rate = _fmt_pct(offloads / turns) if turns else "0.0%"

    row = {
        "model": name,
        "mode": mode,
        "router_mode": status.get("router_mode") or "—",
        "offload_mode": status.get("offload_mode") or "—",
        "phase": status.get("phase") or "—",
        "score": score_str,
        "call_rate": call_rate,
        "turn_call_rate": turn_rate,
        "offload_count": offloads,
        "turns": turns,
        "slm_prompt": slm_in,
        "slm_output": slm_out,
        "llm_input": llm_in,
        "llm_output": llm_out,
        "slm_cost": slm_c,
        "llm_cost": llm_c,
        "cost_sum": cost_sum,
        "resolved": resolved,
        "total": total,
        "reward_mean": reward_mean,
        "stats_dir": str(stats_dir) if stats_dir else None,
    }
    return row


def format_metrics_row(row: dict[str, Any]) -> str:
    """Markdown table body row matching result.md columns."""
    cells = [
        str(row.get("model") or ""),
        str(row.get("score") or "—"),
        str(row.get("call_rate") or "—"),
        str(row.get("turn_call_rate") or "—"),
        str(int(row.get("offload_count") or 0)),
        str(int(row.get("turns") or 0)),
        _fmt_int(int(row.get("slm_prompt") or 0)),
        _fmt_int(int(row.get("slm_output") or 0)),
        _fmt_int(int(row.get("llm_input") or 0)),
        _fmt_int(int(row.get("llm_output") or 0)),
        _fmt_cost(float(row.get("slm_cost") or 0)),
        _fmt_cost(float(row.get("llm_cost") or 0)),
        _fmt_cost(float(row.get("cost_sum") or 0)),
    ]
    return "| " + " | ".join(cells) + " |"


def parse_leaderboard(result_md: Path, mode: str) -> dict[str, Any]:
    """Parse one mode section from result.md into headers + rows."""
    header = MODE_SECTIONS.get(mode)
    if not header:
        return {"mode": mode, "columns": [], "rows": [], "error": f"unknown mode {mode}"}
    if not result_md.is_file():
        return {"mode": mode, "columns": [], "rows": [], "error": "result.md missing"}

    lines = result_md.read_text().splitlines()
    start = None
    for i, line in enumerate(lines):
        if line.strip() == header:
            start = i
            break
    if start is None:
        return {"mode": mode, "columns": [], "rows": [], "error": f"section missing: {header}"}

    table_start = None
    for i in range(start + 1, len(lines)):
        if lines[i].startswith("|") and "模型" in lines[i]:
            table_start = i
            break
        if lines[i].startswith("# "):
            break
    if table_start is None:
        return {"mode": mode, "columns": [], "rows": [], "error": "no table"}

    table_lines: list[str] = []
    for i in range(table_start, len(lines)):
        if lines[i].startswith("|"):
            table_lines.append(lines[i])
        else:
            break

    def split_row(line: str) -> list[str]:
        parts = [c.strip() for c in line.strip().strip("|").split("|")]
        return parts

    if len(table_lines) < 2:
        return {"mode": mode, "columns": [], "rows": []}

    columns = split_row(table_lines[0])
    rows: list[dict[str, str]] = []
    for line in table_lines[2:]:
        cells = split_row(line)
        if not cells or not cells[0] or set(cells[0]) <= {"-", " "}:
            continue
        # pad / trim
        while len(cells) < len(columns):
            cells.append("")
        rows.append({columns[i]: cells[i] for i in range(len(columns))})

    return {
        "mode": mode,
        "section": header,
        "columns": columns,
        "rows": rows,
        "score_is_rate": mode in SCORE_IS_RATE,
    }


def append_or_update_result_md(
    result_md: Path,
    mode: str,
    row: dict[str, Any],
) -> bool:
    """Insert or replace a model row in the mode's table. Returns True if written."""
    header = MODE_SECTIONS.get(mode)
    if not header:
        return False
    result_md.parent.mkdir(parents=True, exist_ok=True)
    if not result_md.is_file():
        # minimal skeleton
        result_md.write_text(
            "\n".join(
                [
                    "- **价格（汇总固定）**：SLM Qwen3.5-4B `$0.016/M` in / `$0.23/M` out；"
                    "LLM DeepSeek-V4-Flash `$0.44/M` in / `$1.32/M` out（cache miss）。",
                    "",
                    header,
                    "",
                    _table_header_line(mode),
                    _table_sep_line(mode),
                    format_metrics_row(row),
                    "",
                ]
            )
            + "\n"
        )
        return True

    text = result_md.read_text()
    lines = text.splitlines()
    start = None
    for i, line in enumerate(lines):
        if line.strip() == header:
            start = i
            break
    if start is None:
        # append new section
        block = [
            "",
            header,
            "",
            f"- run_use mode=`{mode}`。",
            "",
            _table_header_line(mode),
            _table_sep_line(mode),
            format_metrics_row(row),
            "",
        ]
        result_md.write_text(text.rstrip() + "\n" + "\n".join(block) + "\n")
        return True

    table_start = None
    for i in range(start + 1, len(lines)):
        if lines[i].startswith("|") and "模型" in lines[i]:
            table_start = i
            break
        if lines[i].startswith("# "):
            break
    if table_start is None:
        # insert table after section header
        insert_at = start + 1
        while insert_at < len(lines) and not lines[insert_at].startswith("# "):
            insert_at += 1
        chunk = [
            "",
            _table_header_line(mode),
            _table_sep_line(mode),
            format_metrics_row(row),
            "",
        ]
        lines[insert_at:insert_at] = chunk
        result_md.write_text("\n".join(lines) + "\n")
        return True

    table_end = table_start
    for i in range(table_start, len(lines)):
        if lines[i].startswith("|"):
            table_end = i
        else:
            break

    model_name = str(row.get("model") or "").strip()
    new_line = format_metrics_row(row)
    replaced = False
    for i in range(table_start + 2, table_end + 1):
        cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
        if cells and cells[0] == model_name:
            lines[i] = new_line
            replaced = True
            break
    if not replaced:
        lines.insert(table_end + 1, new_line)

    result_md.write_text("\n".join(lines) + "\n")
    return True


def _table_header_line(mode: str) -> str:
    score = "正确率" if mode in SCORE_IS_RATE else "正确数"
    return (
        f"| 模型 | {score} | 调用率 | 轮次调用率 | 调用次数 | 总轮次 | "
        "SLM prompt | SLM output | LLM input | LLM output | slm_cost | llm_cost | cost_sum |"
    )


def _table_sep_line(mode: str) -> str:
    return (
        "| ---- | ------ | ------ | ---------- | -------- | ------ | "
        "---------- | ---------- | --------- | ---------- | -------- | -------- | -------- |"
    )


def _row_has_signal(row: dict[str, Any]) -> bool:
    """Skip empty failed launches that would only write dashes."""
    if row.get("resolved") is not None:
        return True
    if row.get("reward_mean") is not None:
        return True
    if int(row.get("turns") or 0) > 0:
        return True
    if int(row.get("slm_prompt") or 0) or int(row.get("llm_input") or 0):
        return True
    return False


def persist_run_to_result_md(
    run_dir: Path,
    result_md: Path,
    *,
    force: bool = False,
) -> dict[str, Any]:
    """Compute metrics and append/update result.md. Safe to call on failed runs."""
    row = compute_run_metrics(run_dir)
    mode = str(row.get("mode") or "")
    ok = False
    skipped = False
    if mode in MODE_SECTIONS:
        if force or _row_has_signal(row):
            ok = append_or_update_result_md(result_md, mode, row)
        else:
            skipped = True
    return {"written": ok, "skipped": skipped, "row": row, "mode": mode}
