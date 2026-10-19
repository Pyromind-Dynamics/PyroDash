"""Disk cache for swebench GitHub raw fetches (requirements / environment.yml).

Install early (before swebench harness) so offline / flaky networks do not break
``make_run_report`` / env-script generation.

Cache root: ``$SWEBENCH_GITHUB_CACHE`` (default:
``<swe-bench>/cache/github_raw``).

When ``raw.githubusercontent.com`` is blocked, set
``SWEBENCH_GITHUB_RAW_MIRRORS`` (comma-separated prefixes). Default is
``https://ghproxy.net/``. Mirror URLs are tried **before** the direct URL.
Unset the var or set it empty to disable mirrors.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from urllib.parse import urlparse

import requests

_DEFAULT_PREFIXES = (
    "https://raw.githubusercontent.com/",
    "http://raw.githubusercontent.com/",
)

# Used when direct raw.githubusercontent.com is blocked (common in CN clouds).
_DEFAULT_MIRRORS = (
    "https://ghproxy.net/",
)

_DEFAULT_TIMEOUT_SEC = 30

_installed = False
_orig_get = None


def cache_root() -> Path:
    env = os.environ.get("SWEBENCH_GITHUB_CACHE", "").strip()
    if env:
        return Path(env)
    here = Path(__file__).resolve().parent.parent
    return here / "cache" / "github_raw"


def _is_cached_url(url: str) -> bool:
    prefixes = os.environ.get("SWEBENCH_GITHUB_CACHE_PREFIXES", "").strip()
    if prefixes:
        return any(url.startswith(p) for p in prefixes.split(","))
    return any(url.startswith(p) for p in _DEFAULT_PREFIXES)


def _mirrors() -> list[str]:
    # Explicit empty disables mirrors; unset → defaults.
    if "SWEBENCH_GITHUB_RAW_MIRRORS" in os.environ:
        env = os.environ.get("SWEBENCH_GITHUB_RAW_MIRRORS", "").strip()
        if not env:
            return []
        return [m.strip() for m in env.split(",") if m.strip()]
    return list(_DEFAULT_MIRRORS)


def _fetch_timeout(kwargs: dict) -> dict:
    """Ensure a finite timeout so blocked GitHub does not hang the harness."""
    out = dict(kwargs)
    if out.get("timeout") is None:
        raw = os.environ.get("SWEBENCH_GITHUB_RAW_TIMEOUT", "").strip()
        try:
            out["timeout"] = float(raw) if raw else _DEFAULT_TIMEOUT_SEC
        except ValueError:
            out["timeout"] = _DEFAULT_TIMEOUT_SEC
    return out


def _candidate_urls(url: str) -> list[str]:
    """Mirrors first (when configured), then the original URL."""
    out: list[str] = []
    for mirror in _mirrors():
        # ghproxy style: https://ghproxy.net/https://raw.githubusercontent.com/...
        mirrored = f"{mirror.rstrip('/')}/{url}"
        if mirrored not in out:
            out.append(mirrored)
    if url not in out:
        out.append(url)
    return out


def _cache_path(url: str) -> Path:
    # Keep path readable when possible: host/path → file; fall back to hash.
    parsed = urlparse(url)
    rel = f"{parsed.netloc}{parsed.path}"
    if parsed.query:
        rel = f"{rel}__{hashlib.sha1(parsed.query.encode()).hexdigest()[:10]}"
    # Avoid overly long paths
    if len(rel) > 200:
        digest = hashlib.sha1(url.encode()).hexdigest()
        rel = f"_hashed/{digest[:2]}/{digest}"
    return cache_root() / rel


def _save_cache(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def _fake_ok(url: str, text: str) -> requests.models.Response:
    resp = requests.models.Response()
    resp.status_code = 200
    resp._content = text.encode("utf-8")
    resp.url = url
    resp.headers["Content-Type"] = "text/plain; charset=utf-8"
    resp.encoding = "utf-8"
    return resp


def cached_get(url: str, *args, **kwargs):
    """requests.get with disk cache + optional GitHub-raw mirrors."""
    if not _is_cached_url(url):
        return _orig_get(url, *args, **kwargs)

    path = _cache_path(url)
    if path.is_file() and path.stat().st_size > 0:
        return _fake_ok(url, path.read_text(encoding="utf-8", errors="replace"))

    kwargs = _fetch_timeout(kwargs)
    last_err: Exception | None = None
    for candidate in _candidate_urls(url):
        try:
            resp = _orig_get(candidate, *args, **kwargs)
        except Exception as e:  # noqa: BLE001 — try next candidate
            last_err = e
            continue
        if getattr(resp, "status_code", None) == 200 and getattr(resp, "text", None) is not None:
            _save_cache(path, resp.text)
            if candidate != url:
                print(
                    f"[github_raw_cache] fetched via mirror -> cache: {url}",
                    flush=True,
                )
            resp.url = url
            return resp
        last_err = RuntimeError(f"HTTP {getattr(resp, 'status_code', '?')} for {candidate}")

    if path.is_file():
        return _fake_ok(url, path.read_text(encoding="utf-8", errors="replace"))
    if last_err is not None:
        raise last_err
    raise RuntimeError(f"failed to fetch GitHub raw URL: {url}")


def install() -> None:
    global _installed, _orig_get
    if _installed:
        return
    _orig_get = requests.get
    requests.get = cached_get  # type: ignore[assignment]
    _installed = True
    cache_root().mkdir(parents=True, exist_ok=True)
    mirrors = _mirrors()
    print(
        f"[github_raw_cache] installed cache={cache_root()} "
        f"mirrors={mirrors or '(none)'}",
        flush=True,
    )


def uninstall() -> None:
    global _installed, _orig_get
    if not _installed or _orig_get is None:
        return
    requests.get = _orig_get  # type: ignore[assignment]
    _installed = False
    _orig_get = None
