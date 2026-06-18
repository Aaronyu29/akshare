"""Filesystem cache helpers for research data."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from .config import CacheSettings, get_default_settings


@dataclass(frozen=True)
class CacheMetadata:
    provider: str
    dataset: str
    params: dict[str, Any]
    fetched_at: str
    ttl_seconds: int
    row_count: int
    schema_version: str


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def params_hash(params: dict[str, Any] | None) -> str:
    payload = json.dumps(params or {}, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def safe_cache_component(value: str) -> str:
    """Return a filesystem-safe cache path component."""
    safe = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", value.strip())
    safe = safe.strip(" .")
    return safe or "_"


def cache_path(
    namespace: str,
    provider: str,
    dataset: str,
    params: dict[str, Any] | None = None,
    extension: str = "json",
    settings: CacheSettings | None = None,
) -> Path:
    settings = settings or get_default_settings().cache
    root_map = {
        "raw": settings.raw_dir,
        "normalized": settings.normalized_dir,
        "evidence": settings.evidence_dir,
    }
    root = root_map.get(namespace, settings.cache_dir / namespace)
    filename = f"{params_hash(params)}.{extension.lstrip('.')}"
    return root / safe_cache_component(provider) / safe_cache_component(dataset) / filename


def metadata_path(data_path: Path) -> Path:
    return data_path.with_suffix(data_path.suffix + ".meta.json")


def ensure_cache_dirs(settings: CacheSettings | None = None) -> None:
    settings = settings or get_default_settings().cache
    for path in [
        settings.cache_dir,
        settings.raw_dir,
        settings.normalized_dir,
        settings.evidence_dir,
    ]:
        path.mkdir(parents=True, exist_ok=True)


def is_fresh(meta_path: Path) -> bool:
    if not meta_path.exists():
        return False
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        fetched_at = datetime.fromisoformat(meta["fetched_at"])
        ttl_seconds = int(meta["ttl_seconds"])
    except (KeyError, ValueError, json.JSONDecodeError, OSError):
        return False
    return (_now() - fetched_at).total_seconds() <= ttl_seconds


def write_metadata(path: Path, metadata: CacheMetadata) -> None:
    metadata_path(path).write_text(
        json.dumps(asdict(metadata), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def build_metadata(
    provider: str,
    dataset: str,
    params: dict[str, Any] | None,
    ttl_seconds: int,
    row_count: int,
    settings: CacheSettings | None = None,
) -> CacheMetadata:
    settings = settings or get_default_settings().cache
    return CacheMetadata(
        provider=provider,
        dataset=dataset,
        params=params or {},
        fetched_at=_now().isoformat(),
        ttl_seconds=ttl_seconds,
        row_count=row_count,
        schema_version=settings.schema_version,
    )


def save_json(
    path: Path,
    data: Any,
    metadata: CacheMetadata | None = None,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    if metadata is not None:
        write_metadata(path, metadata)


def load_json(path: Path, require_fresh: bool = False) -> Any | None:
    if not path.exists():
        return None
    if require_fresh and not is_fresh(metadata_path(path)):
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def save_dataframe_csv(
    path: Path,
    frame: pd.DataFrame,
    metadata: CacheMetadata | None = None,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False, encoding="utf-8-sig")
    if metadata is not None:
        write_metadata(path, metadata)


def load_dataframe_csv(path: Path, require_fresh: bool = False) -> pd.DataFrame | None:
    if not path.exists():
        return None
    if require_fresh and not is_fresh(metadata_path(path)):
        return None
    return pd.read_csv(path)
