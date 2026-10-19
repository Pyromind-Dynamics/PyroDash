#!/usr/bin/env python3
"""Run SWE-bench harness with a longer Docker API client timeout.

docker-py defaults to 60s for API calls (including container.start()).
Under parallel starts, the daemon can exceed that and mark instances as
errors. Raise it before importing/running the harness.

CLUSTER=shanghai also installs the docker-rt / GitHub-raw patches and passes
--namespace. CLUSTER=us (default) only raises the Docker API timeout.
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


def _patch_make_run_report_fallback() -> None:
    """If image inventory needs GitHub and the network fails, still write the report."""
    import swebench.harness.reporting as reporting

    _orig = reporting.make_run_report

    def _safe_make_run_report(
        predictions,
        full_dataset,
        run_id,
        client=None,
        namespace=None,
        instance_image_tag="latest",
        env_image_tag="latest",
    ):
        try:
            return _orig(
                predictions,
                full_dataset,
                run_id,
                client,
                namespace,
                instance_image_tag,
                env_image_tag,
            )
        except Exception as e:
            if client is None:
                raise
            print(
                f"[run_harness] make_run_report image inventory failed "
                f"({type(e).__name__}: {e}); rewriting report without docker client",
                flush=True,
            )
            return _orig(
                predictions,
                full_dataset,
                run_id,
                None,
                namespace,
                instance_image_tag,
                env_image_tag,
            )

    reporting.make_run_report = _safe_make_run_report  # type: ignore[assignment]


def _arg_value(args: list[str], flag: str) -> str | None:
    for i, a in enumerate(args):
        if a == flag and i + 1 < len(args):
            return args[i + 1]
        if a.startswith(flag + "="):
            return a.split("=", 1)[1]
    return None


def _inject_instance_ids_from_preds(args: list[str]) -> list[str]:
    if "--instance_ids" in args:
        return args
    preds_path = _arg_value(args, "--predictions_path")
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


def _with_namespace(args: list[str]) -> list[str]:
    if "--namespace" in args:
        return args
    ns = os.environ.get("SWEBENCH_DOCKER_NAMESPACE", _DEFAULT_NAMESPACE)
    print(f"[run_harness] namespace={ns}", flush=True)
    return [*args, "--namespace", ns]


if __name__ == "__main__":
    args = sys.argv[1:]
    if _is_shanghai():
        _install_shanghai_patches()
        _patch_make_run_report_fallback()
        args = _with_namespace(_inject_instance_ids_from_preds(args))
    sys.argv = ["swebench.harness.run_evaluation", *args]
    runpy.run_module("swebench.harness.run_evaluation", run_name="__main__", alter_sys=True)
