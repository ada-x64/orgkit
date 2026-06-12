"""Repo enumeration: load the list of `owner/name` repos for an org.

Sources, in priority order:
- ``[repos].inline`` (list literal in `.ok.toml`)
- ``[repos].url`` (fetched JSON; cached under ``$XDG_CACHE_HOME/orgkit/``)

Plus optional ``[repos].extra`` repos always appended (e.g. nanvix's
PRIMARY_REPOS — repos that aren't consumers but should be operated on).
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from pathlib import Path

from orgkit import cache, log
from orgkit.config import OrgConfig

_MAX_BYTES = 1 * 1024 * 1024  # 1 MiB cap on repo-list payloads


def _cache_path(cfg: OrgConfig) -> Path:
    return cache.cache_dir() / cache.config_hash(cfg.path) / "repos.json"


def _fetch_url(url: str, dest: Path) -> list[str] | None:
    if not url.startswith("https://"):
        log.error(f"[repos].url must be https://; got {url!r}")
        return None
    log.info(f"GET {url}")
    try:
        with urllib.request.urlopen(url, timeout=15) as resp:
            body = resp.read(_MAX_BYTES + 1)
    except (urllib.error.URLError, TimeoutError) as e:
        log.warn(f"fetch failed: {e}")
        return None
    if len(body) > _MAX_BYTES:
        log.error(f"{url}: response exceeds {_MAX_BYTES} bytes")
        return None
    try:
        data = json.loads(body.decode("utf8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        log.warn(f"parse failed: {e}")
        return None
    if not isinstance(data, list) or not all(isinstance(x, str) for x in data):
        log.warn(f"{url}: expected a JSON list of strings")
        return None
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(data, indent=2))
    return data


def _load_url(cfg: OrgConfig, url: str) -> list[str]:
    dest = _cache_path(cfg)
    fresh = _fetch_url(url, dest)
    if fresh is not None:
        return fresh
    if dest.is_file():
        log.warn(f"using stale cache: {dest}")
        return json.loads(dest.read_text("utf8"))
    return []


def load(cfg: OrgConfig) -> list[str]:
    """Return the configured repo list (inline or url-fetched), plus extras."""
    repos: list[str]
    if cfg.repos.inline:
        repos = list(cfg.repos.inline)
    elif cfg.repos.url:
        repos = _load_url(cfg, cfg.repos.url)
    else:
        repos = []
    repos.extend(cfg.repos.extra)
    # De-dup, preserving order.
    seen: set[str] = set()
    out: list[str] = []
    for r in repos:
        if r not in seen:
            seen.add(r)
            out.append(r)
    return out


def detect_current(cfg: OrgConfig, cwd: Path | None = None) -> str | None:
    """Return ``owner/name`` of the metarepo containing ``cwd``, or ``None``.

    Walks up from ``cwd`` looking for a dir that (a) sits two levels under
    ``cfg.root`` and (b) contains a ``.bare`` subdir.
    """
    try:
        cur = (cwd or Path.cwd()).resolve()
    except OSError:
        return None
    base = cfg.root.resolve()
    for candidate in [cur, *cur.parents]:
        try:
            rel = candidate.relative_to(base)
        except ValueError:
            continue
        parts = rel.parts
        if len(parts) >= 2 and (base / parts[0] / parts[1] / ".bare").is_dir():
            return f"{parts[0]}/{parts[1]}"
    return None
