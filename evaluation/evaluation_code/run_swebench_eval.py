#!/usr/bin/env python3
"""Run SWE-bench harness with a longer Docker API client timeout.

docker-py defaults to 60s for API calls (including container.start()).
Under --max_workers parallel starts, the daemon can exceed that and mark
instances as errors. Raise it before importing/running the harness.
"""
from __future__ import annotations

import runpy
import sys

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


if __name__ == "__main__":
    sys.argv = ["swebench.harness.run_evaluation", *sys.argv[1:]]
    runpy.run_module("swebench.harness.run_evaluation", run_name="__main__", alter_sys=True)
