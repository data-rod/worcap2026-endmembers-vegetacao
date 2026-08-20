from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

import pandas as pd

from .config import load_config


REVIEW_COLUMNS = [
    "class_code",
    "date",
    "active_vegetation_endmembers",
    "candidate_ids",
    "reviewed_at",
]


def _candidate_table(repository: Path) -> pd.DataFrame:
    frames = [pd.read_parquet(path) for path in sorted((repository / "data" / "candidates").glob("candidates_class_*.parquet"))]
    result = pd.concat(frames, ignore_index=True)
    result["class_code"] = result["class_code"].astype(str).str.zfill(2)
    result["date"] = pd.to_datetime(result["date"]).dt.strftime("%Y-%m-%d")
    return result


def validate_reviews(path: str | Path, root: str | Path | None = None) -> dict[str, Any]:
    repository, _ = load_config(root)
    review_path = Path(path)
    if not review_path.is_absolute():
        review_path = repository / review_path
    reviews = pd.read_csv(review_path, dtype=str).fillna("")
    if list(reviews.columns) != REVIEW_COLUMNS:
        raise ValueError(f"Colunas inválidas. Esperado: {REVIEW_COLUMNS}")
    reviews["class_code"] = reviews["class_code"].astype(str).str.zfill(2)
    reviews["date"] = pd.to_datetime(reviews["date"]).dt.strftime("%Y-%m-%d")
    if reviews.duplicated(["class_code", "date"]).any():
        raise ValueError("O CSV contém combinações classe × data duplicadas.")

    candidates = _candidate_table(repository)
    by_id = candidates.set_index("candidate_id", drop=False).to_dict("index")
    errors: list[str] = []
    for row in reviews.itertuples(index=False):
        key = f"{row.class_code}/{row.date}"
        if row.active_vegetation_endmembers == "NENHUM":
            if row.candidate_ids:
                errors.append(f"NENHUM deve ter candidate_ids vazio: {key}")
            continue
        labels = [value for value in row.active_vegetation_endmembers.split("|") if value]
        ids = [value for value in row.candidate_ids.split("|") if value]
        if not labels or len(labels) != len(ids):
            errors.append(f"Seleção incompatível com os identificadores: {key}")
            continue
        if len(labels) != len(set(labels)) or len(ids) != len(set(ids)):
            errors.append(f"Candidatos repetidos: {key}")
        for label, candidate_id in zip(labels, ids):
            candidate = by_id.get(candidate_id)
            if candidate is None:
                errors.append(f"Identificador inexistente: {candidate_id}")
                continue
            expected_label = candidate["endmember_label"]
            if candidate["class_code"] != row.class_code or candidate["date"] != row.date or expected_label != label:
                errors.append(f"Identificador não corresponde a {label}: {key}")

    for code in sorted(reviews["class_code"].unique()):
        expected_dates = set(candidates.loc[candidates["class_code"].eq(code), "date"])
        received_dates = set(reviews.loc[reviews["class_code"].eq(code), "date"])
        missing = expected_dates - received_dates
        extra = received_dates - expected_dates
        if missing:
            errors.append(f"Classe {code}: faltam {len(missing)} datas disponíveis no painel.")
        if extra:
            errors.append(f"Classe {code}: existem {len(extra)} datas sem candidatos publicados.")
    if errors:
        raise ValueError("; ".join(errors[:20]))
    return {"file": str(review_path), "rows": len(reviews), "classes": sorted(reviews["class_code"].unique()), "valid": True}


def incoming_files(root: str | Path | None = None) -> list[Path]:
    repository, _ = load_config(root)
    return sorted((repository / "reviews" / "incoming").glob("class_*/*.csv"))


def validate_all(root: str | Path | None = None) -> list[dict[str, Any]]:
    files = incoming_files(root)
    return [validate_reviews(path, root=root) for path in files]


def merge_reviews(
    paths: Iterable[str | Path] | None = None,
    *,
    output: str | Path = "reviews/validated/reviews_consolidadas.parquet",
    root: str | Path | None = None,
) -> dict[str, Any]:
    repository, _ = load_config(root)
    selected = [Path(path) for path in paths] if paths else incoming_files(root)
    if not selected:
        raise FileNotFoundError("Nenhum CSV de revisão foi encontrado.")
    tables: list[pd.DataFrame] = []
    for path in selected:
        if not path.is_absolute():
            path = repository / path
        validate_reviews(path, root=repository)
        table = pd.read_csv(path, dtype=str).fillna("")
        table["class_code"] = table["class_code"].astype(str).str.zfill(2)
        table["date"] = pd.to_datetime(table["date"]).dt.strftime("%Y-%m-%d")
        table["review_source"] = path.relative_to(repository).as_posix()
        tables.append(table)
    combined = pd.concat(tables, ignore_index=True)
    if combined.duplicated(["class_code", "date"]).any():
        duplicates = combined.loc[combined.duplicated(["class_code", "date"], keep=False), ["class_code", "date"]].drop_duplicates()
        raise ValueError(f"Existem {len(duplicates)} decisões duplicadas de classe × data.")
    target = Path(output)
    if not target.is_absolute():
        target = repository / target
    target.parent.mkdir(parents=True, exist_ok=True)
    combined.sort_values(["class_code", "date"]).to_parquet(target, index=False)
    return {"files": len(selected), "rows": len(combined), "output": str(target)}

