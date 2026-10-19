#!/usr/bin/env python3
"""Run `mini-extra swebench` with a rewriteable Docker image prefix.

mini-swe-agent hardcodes docker.io/swebench/sweb.eval...; docker-rt cannot
`docker tag`, so rewrite the image name before the CLI starts.

Does **not** force ``MSWEA_DOCKER_EXECUTABLE`` to ``docker_rt_testbed_exec.sh``.
Sandbox testbed activation is aligned with coding-training: ``bash -lc`` +
PATH/CONDA via ``env_testbed_path.yaml``. The old ln -sfn wrapper rewrites
``-lc`` → ``-c`` and undoes that path. Legacy pipelines that still want the
wrapper can export ``MSWEA_DOCKER_EXECUTABLE`` themselves (``sweb_docker.sh``
still does so by default; ``run_pipeline_20n.sh`` unsets it).
"""
from __future__ import annotations

import os
import sys


def _prefix() -> str:
    return os.environ.get(
        "SWEBENCH_DOCKER_IMAGE_PREFIX",
        "pyromind-registry-vpc.cn-shanghai.cr.aliyuncs.com/pyromind",
    ).rstrip("/")


def rewrite_image_name(name: str) -> str:
    prefix = _prefix()
    for old in ("docker.io/swebench/", "swebench/"):
        if name.startswith(old):
            return f"{prefix}/{name[len(old):]}"
    return name


def patch_image_name() -> None:
    import minisweagent.run.benchmarks.swebench as sb

    orig = sb.get_swebench_docker_image_name

    def wrapped(instance: dict) -> str:
        return rewrite_image_name(orig(instance))

    sb.get_swebench_docker_image_name = wrapped  # type: ignore[assignment]


def main() -> None:
    os.environ.setdefault("DOCKER_HOST", "unix:///tmp/docker-rt.sock")
    os.environ.setdefault(
        "SWEBENCH_DOCKER_IMAGE_PREFIX",
        "pyromind-registry-vpc.cn-shanghai.cr.aliyuncs.com/pyromind",
    )
    patch_image_name()
    from minisweagent.run.utilities.mini_extra import main as mini_extra_main

    sys.argv = [sys.argv[0], "swebench", *sys.argv[1:]]
    print(
        f"[mini_extra_shanghai] MSWEA_DOCKER_EXECUTABLE="
        f"{os.environ.get('MSWEA_DOCKER_EXECUTABLE', '<unset>')}",
        flush=True,
    )
    mini_extra_main()


if __name__ == "__main__":
    main()
