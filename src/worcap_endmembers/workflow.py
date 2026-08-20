from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .config import load_config, select_classes, sha256
from .ppi import extract_ppi


def qa_valid(frame: pd.DataFrame, config: dict[str, Any]) -> pd.Series:
    valid = pd.to_numeric(frame["CLEAROB"], errors="coerce").gt(0)
    scl = pd.to_numeric(frame["SCL"], errors="coerce")
    valid &= ~scl.isin(config["scl_invalid"])
    finite = np.isfinite(frame[config["bands"]].apply(pd.to_numeric, errors="coerce").to_numpy(float)).all(axis=1)
    return valid & finite


def run_ppi(
    root: str | Path | None = None,
    *,
    classes: list[str] | None = None,
    output: str | Path = "outputs/reproduced",
) -> list[dict[str, Any]]:
    repository, config = load_config(root)
    selected = select_classes(config, classes)
    output_root = Path(output)
    if not output_root.is_absolute():
        output_root = repository / output_root
    candidates_dir = output_root / "candidates"
    candidates_dir.mkdir(parents=True, exist_ok=True)
    results: list[dict[str, Any]] = []
    ppi = config["ppi"]
    production_hash = config["provenance"]["production_config_hash"]

    for code in selected:
        source = repository / "data" / "wtss" / f"wtss_class_{code}.parquet"
        data = pd.read_parquet(source)
        data["date"] = pd.to_datetime(data["date"]).dt.strftime("%Y-%m-%d")
        if data["date"].nunique() != int(config["period"]["expected_dates"]):
            raise AssertionError(f"Classe {code}: número inesperado de datas.")

        candidate_rows: list[dict[str, Any]] = []
        manifest_rows: list[dict[str, Any]] = []
        for date, group in data.groupby("date", sort=True):
            group = group.sort_values("systematic_order")
            valid = group[qa_valid(group, config)].head(int(ppi["max_sampled_pixels"])).reset_index(drop=True)
            n_valid = len(valid)
            base = {
                "class_code": code,
                "class_name": config["classes"][code],
                "date": date,
                "total_sampled_pixels": int(len(group)),
                "valid_pixels": n_valid,
                "endmembers_max": int(ppi["endmembers_max"]),
                "max_sampled_pixels": int(ppi["max_sampled_pixels"]),
                "ppi_seed": int(ppi["seed"]),
                "ppi_projections": int(ppi["projections"]),
                "candidate_pool_method": ppi["candidate_pool_method"],
                "duplicate_sam_threshold_deg": float(ppi["duplicate_sam_threshold_deg"]),
                "stability_assessed": False,
                "stability_status": "STABILITY_NOT_ASSESSED",
                "config_hash": production_hash,
            }
            if n_valid < int(ppi["endmembers_max"]):
                manifest_rows.append({**base, "status": "INSUFFICIENT_VALID_PIXELS", "candidate_count": 0})
                continue

            spectra = valid[config["bands"]].to_numpy(float)
            result = extract_ppi(
                spectra,
                count=int(ppi["endmembers_max"]),
                projections=int(ppi["projections"]),
                seed=int(ppi["seed"]),
                projection_batch=int(ppi["projection_batch"]),
                duplicate_sam_deg=float(ppi["duplicate_sam_threshold_deg"]),
                master_order=valid["systematic_order"].to_numpy(np.int64),
                memory_limit_mb=int(ppi["memory_limit_mb"]),
            )
            qa_status = "LOW_VALID_N" if n_valid < int(ppi["low_valid_n_threshold"]) else "OK"
            warnings = [value for value in [qa_status if qa_status != "OK" else "", result.status if result.status != "OK" else ""] if value]
            manifest_rows.append(
                {
                    **base,
                    "status": qa_status if result.status == "OK" else result.status,
                    "warnings": "|".join(warnings),
                    "candidate_count": len(result.indices),
                    "candidate_pool_size": result.candidate_pool_size,
                    "effective_projection_batch": result.projection_batch,
                }
            )
            compact_date = date.replace("-", "")
            for rank, (index, score) in enumerate(zip(result.indices, result.scores), start=1):
                source_row = valid.iloc[int(index)]
                record = {
                    **base,
                    "endmember_label": f"EM{rank:02d}",
                    "candidate_id": f"TCAMZ_C{code}_D{compact_date}_PPI_EM{rank:02d}",
                    "point_id": source_row["point_id"],
                    "systematic_order": int(source_row["systematic_order"]),
                    "ppi_score": int(score),
                    "candidate_pool_size": result.candidate_pool_size,
                    "effective_projection_batch": result.projection_batch,
                    "qa_status": qa_status,
                    "ppi_status": result.status,
                }
                record.update({band: float(source_row[band]) for band in config["bands"]})
                candidate_rows.append(record)

        candidates = pd.DataFrame(candidate_rows)
        manifest = pd.DataFrame(manifest_rows)
        candidate_csv = candidates_dir / f"candidates_class_{code}.csv"
        candidate_parquet = candidates_dir / f"candidates_class_{code}.parquet"
        manifest_csv = candidates_dir / f"ppi_manifest_class_{code}.csv"
        manifest_parquet = candidates_dir / f"ppi_manifest_class_{code}.parquet"
        candidates.to_csv(candidate_csv, index=False, encoding="utf-8")
        candidates.to_parquet(candidate_parquet, index=False)
        manifest.to_csv(manifest_csv, index=False, encoding="utf-8")
        manifest.to_parquet(manifest_parquet, index=False)
        results.append(
            {
                "class_code": code,
                "dates": int(len(manifest)),
                "candidates": int(len(candidates)),
                "candidate_sha256": sha256(candidate_parquet),
                "manifest_sha256": sha256(manifest_parquet),
            }
        )
    return results


def compare_candidates(
    reproduced: str | Path,
    reference: str | Path,
    root: str | Path | None = None,
) -> dict[str, Any]:
    repository, config = load_config(root)
    reproduced = Path(reproduced)
    reference = Path(reference)
    if not reproduced.is_absolute():
        reproduced = repository / reproduced
    if not reference.is_absolute():
        reference = repository / reference
    compared = []
    for code in config["classes"]:
        left = pd.read_parquet(reproduced / f"candidates_class_{code}.parquet")
        right = pd.read_parquet(reference / f"candidates_class_{code}.parquet")
        keys = ["candidate_id", "point_id", "ppi_score", *config["bands"]]
        left = left[keys].sort_values("candidate_id").reset_index(drop=True)
        right = right[keys].sort_values("candidate_id").reset_index(drop=True)
        if list(left["candidate_id"]) != list(right["candidate_id"]):
            raise AssertionError(f"Classe {code}: identificadores divergentes.")
        if list(left["point_id"]) != list(right["point_id"]):
            raise AssertionError(f"Classe {code}: pixels candidatos divergentes.")
        if not np.array_equal(left["ppi_score"].to_numpy(), right["ppi_score"].to_numpy()):
            raise AssertionError(f"Classe {code}: escores PPI divergentes.")
        if not np.allclose(left[config["bands"]].to_numpy(float), right[config["bands"]].to_numpy(float), rtol=0, atol=0):
            raise AssertionError(f"Classe {code}: espectros divergentes.")
        compared.append({"class_code": code, "candidates": len(left), "identical": True})
    return {"classes": compared, "identical": True}


def verify_release(root: str | Path | None = None) -> dict[str, Any]:
    repository, config = load_config(root)
    points = pd.read_parquet(repository / "data" / "points" / "points.parquet")
    counts = points.assign(class_code=points["class_code"].astype(str).str.zfill(2)).groupby("class_code").size().to_dict()
    expected = int(config["sampling"]["points_per_class"])
    if counts != {code: expected for code in config["classes"]}:
        raise AssertionError(f"Contagem de pontos inesperada: {counts}")
    if points.duplicated(["class_code", "source_row", "source_col"]).any():
        raise AssertionError("Foram encontrados pixels duplicados dentro de uma classe.")
    summary: dict[str, Any] = {"points": len(points), "classes": {}}
    for code in config["classes"]:
        wtss = pd.read_parquet(repository / "data" / "wtss" / f"wtss_class_{code}.parquet", columns=["point_id", "date"])
        candidates = pd.read_parquet(repository / "data" / "candidates" / f"candidates_class_{code}.parquet")
        manifest = pd.read_parquet(repository / "data" / "candidates" / f"ppi_manifest_class_{code}.parquet")
        if len(wtss) != expected * int(config["period"]["expected_dates"]):
            raise AssertionError(f"Classe {code}: número inesperado de linhas WTSS.")
        if len(manifest) != int(config["period"]["expected_dates"]):
            raise AssertionError(f"Classe {code}: manifesto incompleto.")
        summary["classes"][code] = {
            "wtss_rows": int(len(wtss)),
            "dates": int(manifest["date"].nunique()),
            "candidates": int(len(candidates)),
        }
    checksum_file = repository / "metadata" / "checksums.sha256"
    checked = 0
    if checksum_file.exists():
        for line in checksum_file.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            expected_hash, relative = line.split("  ", 1)
            target = repository / relative
            if sha256(target) != expected_hash:
                raise AssertionError(f"Hash divergente: {relative}")
            checked += 1
    summary["checksums_verified"] = checked
    return summary


def write_json(path: str | Path, value: Any) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")

