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


def install() -> None:
    """Patch docker APIClient.inspect_container (idempotent)."""
    global _installed
    if _installed:
        return

    from docker.api.container import ContainerApiMixin

    _orig = ContainerApiMixin.inspect_container

    def _inspect_container(self, container, *args, **kwargs):  # type: ignore[no-untyped-def]
        return normalize_container_inspect(_orig(self, container, *args, **kwargs))

    ContainerApiMixin.inspect_container = _inspect_container  # type: ignore[method-assign,assignment]
    _installed = True
