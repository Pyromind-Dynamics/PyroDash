#!/usr/bin/env python3
"""Run SWE-bench harness (swebench==5.0.2) with a longer Docker API client timeout.

docker-py defaults to 60s for API calls (including container.start()).
Under parallel starts, the daemon can exceed that and mark instances as
errors. Raise it before importing/running the harness.

CLUSTER=shanghai also installs the docker-rt / GitHub-raw patches and rewrites
image names to the Aliyun registry. CLUSTER=us (default) only raises the Docker
API timeout.

swebench 5.x notes:
  - dataset: SWE-bench/SWE-bench_Verified (not princeton-nlp/*)
  - CLI dropped --cache_level / --clean / --force_rebuild / --namespace
  - image names live on each instance; shanghai rewrites swebench/ → registry
"""
from __future__ import annotations

import json
import os
import runpy
import sys
from pathlib import Path

import docker
from docker.client import DockerClient

DOCKER_API_TIMEOUT_SEC = 300

_orig_from_env = docker.from_env
_orig_client_from_env = DockerClient.from_env


def _from_env_with_timeout(*args, **kwargs):
    kwargs.setdefault("timeout", DOCKER_API_TIMEOUT_SEC)
    return _orig_from_env(*args, **kwargs)


@classmethod  # type: ignore[misc]
def _client_from_env_with_timeout(cls, *args, **kwargs):
    kwargs.setdefault("timeout", DOCKER_API_TIMEOUT_SEC)
    return _orig_client_from_env(*args, **kwargs)


docker.from_env = _from_env_with_timeout  # type: ignore[assignment]
DockerClient.from_env = _client_from_env_with_timeout  # type: ignore[method-assign,assignment]

_SHANGHAI_DIR = Path(__file__).resolve().parent / "shanghai"
_DEFAULT_NAMESPACE = "pyromind-registry-vpc.cn-shanghai.cr.aliyuncs.com/pyromind"

# 4.x CLI flags removed in swebench 5.x — strip if a caller still passes them.
_REMOVED_FLAGS_WITH_VALUE = {
    "--cache_level",
    "--clean",
    "--force_rebuild",
    "--namespace",
}
_REMOVED_FLAGS_BOOL = {
    "--force_rebuild",
}


def _is_shanghai() -> bool:
    return os.environ.get("CLUSTER", "us").strip().lower() == "shanghai"


def _install_shanghai_patches() -> None:
    if str(_SHANGHAI_DIR) not in sys.path:
        sys.path.insert(0, str(_SHANGHAI_DIR))
    os.environ.setdefault("DOCKER_HOST", "unix:///tmp/docker-rt.sock")
    os.environ.setdefault(
        "SWEBENCH_GITHUB_CACHE",
        str(Path(__file__).resolve().parent / "cache" / "github_raw"),
    )
    os.environ.setdefault("SWEBENCH_GITHUB_RAW_MIRRORS", "https://ghproxy.net/")
    os.environ.setdefault("SWEBENCH_GITHUB_RAW_TIMEOUT", "30")
    from github_raw_cache import install as install_github_raw_cache  # noqa: WPS433
    from docker_rt_compat import install as install_docker_rt_compat  # noqa: WPS433
    from harness_docker_rt_fix import install as install_harness_docker_rt_fix  # noqa: WPS433

    install_github_raw_cache()
    install_docker_rt_compat()
    install_harness_docker_rt_fix()


def _rewrite_image_name(name: str) -> str:
    prefix = os.environ.get("SWEBENCH_DOCKER_IMAGE_PREFIX", _DEFAULT_NAMESPACE).rstrip("/")
    for old in ("docker.io/swebench/", "swebench/"):
        if name.startswith(old):
            return f"{prefix}/{name[len(old):]}"
    return name


def _install_shanghai_image_rewrite() -> None:
    """5.x puts the full image on each instance; rewrite swebench/ → Aliyun prefix."""
    import swebench.harness.utils as harness_utils

    _orig = harness_utils.make_test_spec

    def _make_test_spec(instance: dict):
        if isinstance(instance, dict) and "image" in instance:
            rewritten = dict(instance)
            rewritten["image"] = _rewrite_image_name(str(instance["image"]))
            return _orig(rewritten)
        return _orig(instance)

    harness_utils.make_test_spec = _make_test_spec  # type: ignore[assignment]
    # run_evaluation may have imported the symbol by name
    try:
        import swebench.harness.run_evaluation as run_evaluation

        if getattr(run_evaluation, "make_test_spec", None) is not None:
            run_evaluation.make_test_spec = _make_test_spec  # type: ignore[attr-defined]
    except Exception:
        pass
    print(
        f"[run_harness] shanghai image rewrite prefix="
        f"{os.environ.get('SWEBENCH_DOCKER_IMAGE_PREFIX', _DEFAULT_NAMESPACE)}",
        flush=True,
    )


def _patch_make_run_report_fallback() -> None:
    """If image inventory needs Docker and fails, still write the report (5.x sig)."""
    import swebench.harness.reporting as reporting

    _orig = reporting.make_run_report

    def _safe_make_run_report(
        predictions,
        full_dataset,
        run_id,
        client=None,
        report_dir: str = ".",
    ):
        try:
            return _orig(predictions, full_dataset, run_id, client, report_dir)
        except Exception as e:
            if client is None:
                raise
            print(
                f"[run_harness] make_run_report image inventory failed "
                f"({type(e).__name__}: {e}); rewriting report without docker client",
                flush=True,
            )
            return _orig(predictions, full_dataset, run_id, None, report_dir)

    reporting.make_run_report = _safe_make_run_report  # type: ignore[assignment]


def _arg_value(args: list[str], flag: str) -> str | None:
    for i, a in enumerate(args):
        if a == flag and i + 1 < len(args):
            return args[i + 1]
        if a.startswith(flag + "="):
            return a.split("=", 1)[1]
    return None


def _inject_instance_ids_from_preds(args: list[str]) -> list[str]:
    if "--instance_ids" in args or "-i" in args:
        return args
    preds_path = _arg_value(args, "--predictions_path") or _arg_value(args, "-p")
    if not preds_path:
        return args
    path = Path(preds_path)
    if not path.is_file():
        return args
    try:
        data = json.loads(path.read_text())
    except Exception:
        return args
    if isinstance(data, dict):
        ids = [str(k) for k in data.keys()]
    elif isinstance(data, list):
        ids = [str(x["instance_id"]) for x in data if isinstance(x, dict) and "instance_id" in x]
    else:
        return args
    if not ids:
        return args
    print(f"[run_harness] injecting --instance_ids ({len(ids)} from preds)", flush=True)
    return [*args, "--instance_ids", *ids]


def _strip_removed_cli_flags(args: list[str]) -> list[str]:
    """Drop swebench 4.x flags that 5.x argparse rejects."""
    out: list[str] = []
    skip_next = False
    removed: list[str] = []
    for a in args:
        if skip_next:
            skip_next = False
            removed.append(a)
            continue
        if a in _REMOVED_FLAGS_WITH_VALUE:
            removed.append(a)
            skip_next = True
            continue
        key = a.split("=", 1)[0]
        if key in _REMOVED_FLAGS_WITH_VALUE or key in _REMOVED_FLAGS_BOOL:
            removed.append(a)
            continue
        out.append(a)
    if removed:
        print(f"[run_harness] stripped swebench-4.x flags: {' '.join(removed)}", flush=True)
    return out


def _default_dataset_if_missing(args: list[str]) -> list[str]:
    if _arg_value(args, "--dataset_name") or _arg_value(args, "-d"):
        return args
    # 5.x schema (has image/eval_script)
    return [*args, "--dataset_name", "SWE-bench/SWE-bench_Verified"]


if __name__ == "__main__":
    args = sys.argv[1:]
    args = _strip_removed_cli_flags(args)
    args = _default_dataset_if_missing(args)
    args = _inject_instance_ids_from_preds(args)
    if _is_shanghai():
        _install_shanghai_patches()
        _install_shanghai_image_rewrite()
        _patch_make_run_report_fallback()
    sys.argv = ["swebench.harness.run_evaluation", *args]
    runpy.run_module("swebench.harness.run_evaluation", run_name="__main__", alter_sys=True)
