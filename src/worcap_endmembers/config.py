from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import yaml


def find_repository(start: str | Path | None = None) -> Path:
    path = Path(start or Path.cwd()).resolve()
    if path.is_file():
        path = path.parent
    for candidate in [path, *path.parents]:
        if (candidate / "config" / "study.yaml").exists() and (candidate / "pyproject.toml").exists():
            return candidate
    raise FileNotFoundError("Não foi possível localizar config/study.yaml.")


def load_config(root: str | Path | None = None) -> tuple[Path, dict[str, Any]]:
    repository = find_repository(root)
    config_path = repository / "config" / "study.yaml"
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    config["_path"] = str(config_path)
    return repository, config


def sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def stable_hash(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def select_classes(config: dict[str, Any], values: list[str] | None = None) -> list[str]:
    selected = [str(value).zfill(2) for value in (values or config["classes"].keys())]
    unknown = sorted(set(selected) - set(config["classes"]))
    if unknown:
        raise ValueError(f"Classes não configuradas: {', '.join(unknown)}")
    return selected

