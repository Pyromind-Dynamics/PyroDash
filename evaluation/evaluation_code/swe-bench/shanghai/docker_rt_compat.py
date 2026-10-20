"""Normalize docker-rt inspect responses for docker-py / SWE-bench harness.

docker-rt's GET /containers/{id}/json returns a custom schema (lowercase ``id``,
``status``, no ``State``/``Id``). docker-py's ``containers.create`` then does
``get(id)`` → inspect and ends up with ``container.id is None``, so
``container.start()`` fails with ``Resource ID was not provided``.

Install once before importing/running the harness.
"""

from __future__ import annotations

import copy
from typing import Any


def normalize_container_inspect(data: Any) -> Any:
    """Map docker-rt inspect JSON to a Docker Engine-shaped dict."""
    if not isinstance(data, dict):
        return data
    # Already Engine-shaped
    if "Id" in data and "State" in data:
        return data

    out = copy.deepcopy(data)
    cid = out.get("Id") or out.get("id") or ""
    name = out.get("Name") or out.get("name") or ""
    if name and not str(name).startswith("/"):
        name = "/" + str(name)
    status = (
        (out.get("State") or {}).get("Status")
        if isinstance(out.get("State"), dict)
        else None
    ) or out.get("status") or "created"
    status = str(status).lower()
    running = status in {"running", "up"}
    image = out.get("Image") or out.get("image") or ""

    out["Id"] = cid
    out["id"] = cid
    out["Name"] = name or out.get("Name") or ""
    out["Image"] = image
    out["Config"] = out.get("Config") if isinstance(out.get("Config"), dict) else {}
    out["Config"].setdefault("Image", image)
    out["Config"].setdefault("Hostname", "")
    out["Config"].setdefault("WorkingDir", "")
    out["HostConfig"] = out.get("HostConfig") if isinstance(out.get("HostConfig"), dict) else {}
    out["NetworkSettings"] = (
        out.get("NetworkSettings")
        if isinstance(out.get("NetworkSettings"), dict)
        else {"Ports": {}}
    )
    out["State"] = {
        "Status": "running" if running else status,
        "Running": running,
        "Paused": False,
        "Restarting": False,
        "OOMKilled": False,
        "Dead": status in {"dead", "removing"},
        "Pid": 1 if running else 0,
        "ExitCode": 0,
        "Error": "",
        "StartedAt": out.get("created_at") or "",
        "FinishedAt": "",
    }
    return out


_installed = False


def _patch_exec_run_honor_workdir() -> None:
    """docker-rt ignores docker-py ``exec_run(..., workdir=...)``.

    SWE-bench applies patches with ``workdir=/testbed``. Without an explicit
    ``cd``, ``git apply`` runs in ``/`` and fails with ``No file to patch``.
    Rewrite the command to ``cd <workdir> && ...`` before calling exec.
    """
    import shlex

    from docker.models.containers import Container

    _orig = Container.exec_run

    def exec_run(  # type: ignore[no-untyped-def]
        self,
        cmd,
        stdout=True,
        stderr=True,
        stdin=False,
        tty=False,
        privileged=False,
        user="",
        detach=False,
        stream=False,
        socket=False,
        environment=None,
        workdir=None,
        demux=False,
    ):
        if workdir:
            if isinstance(cmd, (list, tuple)):
                inner = f"cd {shlex.quote(str(workdir))} && {shlex.join([str(x) for x in cmd])}"
            else:
                inner = f"cd {shlex.quote(str(workdir))} && {cmd}"
            cmd = ["bash", "-c", inner]
            workdir = None
        return _orig(
            self,
            cmd,
            stdout=stdout,
            stderr=stderr,
            stdin=stdin,
            tty=tty,
            privileged=privileged,
            user=user,
            detach=detach,
            stream=stream,
            socket=socket,
            environment=environment,
            workdir=workdir,
            demux=demux,
        )

    Container.exec_run = exec_run  # type: ignore[method-assign,assignment]


def _patch_images_list_skip_missing() -> None:
    """docker-rt ``GET /images/json`` returns RepoTags, but inspect-by-Id 404s.

    docker-py's ``images.list()`` does ``get(Id)`` for every row; the first 404
    aborts swebench ``list_images`` before evaluation starts. Prefer inspect,
    otherwise synthesize an Image from the list row (keeps RepoTags).
    """
    from docker.errors import ImageNotFound, NotFound
    from docker.models.images import ImageCollection

    def list(self, name=None, all=False, filters=None):  # type: ignore[no-untyped-def]
        resp = self.client.api.images(name=name, all=all, filters=filters)
        out = []
        for row in resp:
            image_id = row.get("Id") or row.get("id")
            if not image_id:
                continue
            try:
                out.append(self.get(image_id))
                continue
            except (ImageNotFound, NotFound):
                pass
            attrs = {
                "Id": image_id,
                "RepoTags": row.get("RepoTags") or [],
                "RepoDigests": row.get("RepoDigests") or [],
                "Created": row.get("Created"),
                "Size": row.get("Size") or 0,
            }
            out.append(self.prepare_model(attrs))
        return out

    ImageCollection.list = list  # type: ignore[method-assign,assignment]


def install() -> None:
    """Patch docker-rt quirks for docker-py / SWE-bench harness (idempotent)."""
    global _installed
    if _installed:
        return

    from docker.api.container import ContainerApiMixin

    _orig = ContainerApiMixin.inspect_container

    def _inspect_container(self, container, *args, **kwargs):  # type: ignore[no-untyped-def]
        return normalize_container_inspect(_orig(self, container, *args, **kwargs))

    ContainerApiMixin.inspect_container = _inspect_container  # type: ignore[method-assign,assignment]
    _patch_exec_run_honor_workdir()
    _patch_images_list_skip_missing()
    _installed = True
    print(
        "[docker_rt_compat] installed (container inspect normalize, "
        "exec_run honors workdir via cd, images.list uses list RepoTags)",
        flush=True,
    )
