from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import yaml
from statsmodels.tsa.seasonal import STL


PRIMARY_REVIEWS = {
    "01": "reviews/incoming/class_01/wtss1000_active_vegetation_class_01.csv",
    "02": "reviews/incoming/class_02/wtss1000_active_vegetation_class_02.csv",
    "09": "reviews/incoming/class_09/wtss1000_active_vegetation_class_09.csv",
    "10": "reviews/incoming/class_10/wtss1000_active_vegetation_class_10.csv",
    "11": "reviews/incoming/class_11/wtss1000_active_vegetation_class_11.csv",
}

SECONDARY_REVIEWS: dict[str, str] = {}

REVIEW_COLUMNS = [
    "class_code",
    "date",
    "active_vegetation_endmembers",
    "candidate_ids",
    "reviewed_at",
]


def repository_root(start: str | Path | None = None) -> Path:
    current = Path(start or Path.cwd()).resolve()
    for candidate in (current, *current.parents):
        if (candidate / "config" / "study.yaml").is_file() and (candidate / "data" / "candidates").is_dir():
            return candidate
    raise FileNotFoundError("Repository root not found.")


def load_config(root: Path) -> dict:
    with (root / "config" / "study.yaml").open(encoding="utf-8") as stream:
        return yaml.safe_load(stream)


def load_review(root: Path, relative: str, class_code: str) -> pd.DataFrame:
    path = root / relative
    table = pd.read_csv(path, dtype=str).fillna("")
    if list(table.columns) != REVIEW_COLUMNS:
        raise ValueError(f"Unexpected columns in {relative}.")
    table["class_code"] = table["class_code"].astype(str).str.zfill(2)
    table["date"] = pd.to_datetime(table["date"]).dt.strftime("%Y-%m-%d")
    if not table["class_code"].eq(class_code).all():
        raise ValueError(f"Unexpected class code in {relative}.")
    if table.duplicated(["class_code", "date"]).any():
        raise ValueError(f"Duplicate class/date rows in {relative}.")
    table["review_source"] = relative
    return table


def load_candidates(root: Path, class_codes: list[str]) -> pd.DataFrame:
    frames = []
    for class_code in class_codes:
        frame = pd.read_parquet(root / "data" / "candidates" / f"candidates_class_{class_code}.parquet")
        frame["class_code"] = frame["class_code"].astype(str).str.zfill(2)
        frame["date"] = pd.to_datetime(frame["date"]).dt.strftime("%Y-%m-%d")
        frames.append(frame)
    result = pd.concat(frames, ignore_index=True)
    if result["candidate_id"].duplicated().any():
        raise ValueError("Candidate identifiers are not unique.")
    return result


def validate_review_candidates(reviews: pd.DataFrame, candidates: pd.DataFrame) -> None:
    by_id = candidates.set_index("candidate_id", drop=False).to_dict("index")
    errors: list[str] = []
    for row in reviews.itertuples(index=False):
        if row.active_vegetation_endmembers == "NENHUM":
            if row.candidate_ids:
                errors.append(f"NENHUM with candidate IDs: {row.class_code}/{row.date}")
            continue
        labels = [value for value in row.active_vegetation_endmembers.split("|") if value]
        identifiers = [value for value in row.candidate_ids.split("|") if value]
        if not labels or len(labels) != len(identifiers):
            errors.append(f"Incompatible labels and identifiers: {row.class_code}/{row.date}")
            continue
        for label, identifier in zip(labels, identifiers):
            candidate = by_id.get(identifier)
            if candidate is None:
                errors.append(f"Unknown candidate: {identifier}")
                continue
            if (
                candidate["class_code"] != row.class_code
                or candidate["date"] != row.date
                or candidate["endmember_label"] != label
            ):
                errors.append(f"Candidate mismatch: {row.class_code}/{row.date}/{label}")
    if errors:
        raise ValueError("; ".join(errors[:20]))


def spectral_indices(record: dict, bands: list[str]) -> dict[str, float]:
    values = {band: float(record[band]) for band in bands}
    blue, red, nir, swir = values["B02"], values["B04"], values["B08"], values["B11"]
    ndvi_denominator = nir + red
    evi_denominator = nir + 6 * red - 7.5 * blue + 1
    bsi_denominator = swir + red + nir + blue
    return {
        "NDVI": (nir - red) / ndvi_denominator if abs(ndvi_denominator) > 1e-12 else np.nan,
        "EVI": 2.5 * (nir - red) / evi_denominator if abs(evi_denominator) > 1e-12 else np.nan,
        "BSI": ((swir + red) - (nir + blue)) / bsi_denominator
        if abs(bsi_denominator) > 1e-12
        else np.nan,
    }


def consolidate_reviews(
    root: Path,
    config: dict,
    primary: dict[str, pd.DataFrame],
    secondary: dict[str, pd.DataFrame],
    candidates: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    class_codes = list(config["classes"])
    primary_table = pd.concat(primary.values(), ignore_index=True)
    validate_review_candidates(primary_table, candidates)
    for table in secondary.values():
        validate_review_candidates(table, candidates)

    decision_rows: list[dict] = []
    provenance_rows: list[dict] = []
    for class_code in class_codes:
        primary_class = primary[class_code].sort_values("date")
        secondary_class = secondary.get(class_code)
        secondary_by_date = secondary_class.set_index("date") if secondary_class is not None else None
        for row in primary_class.itertuples(index=False):
            final = {
                "class_code": class_code,
                "date": row.date,
                "active_vegetation_endmembers": row.active_vegetation_endmembers,
                "candidate_ids": row.candidate_ids,
                "reviewed_at": row.reviewed_at,
                "reviewer_id": "rodrigo",
                "decision_rule": "PRIMARY_REVIEW",
                "review_source": row.review_source,
            }
            secondary_labels = ""
            secondary_ids = ""
            secondary_exact = pd.NA
            secondary_source = ""
            if secondary_by_date is not None:
                other = secondary_by_date.loc[row.date]
                secondary_labels = other["active_vegetation_endmembers"]
                secondary_ids = other["candidate_ids"]
                secondary_source = other["review_source"]
                secondary_exact = bool(
                    row.active_vegetation_endmembers == secondary_labels and row.candidate_ids == secondary_ids
                )
                final["decision_rule"] = (
                    "PRIMARY_REVIEW_WITH_EXACT_SECONDARY_AGREEMENT"
                    if secondary_exact
                    else "PRIMARY_REVIEW_PRECEDENCE_ON_DISAGREEMENT"
                )
            decision_rows.append(final)
            provenance_rows.append(
                {
                    **final,
                    "secondary_reviewer_id": "secundario" if secondary_by_date is not None else "",
                    "secondary_active_vegetation_endmembers": secondary_labels,
                    "secondary_candidate_ids": secondary_ids,
                    "secondary_exact_match": secondary_exact,
                    "secondary_review_source": secondary_source,
                }
            )

    decisions = pd.DataFrame(decision_rows).sort_values(["class_code", "date"]).reset_index(drop=True)
    provenance = pd.DataFrame(provenance_rows).sort_values(["class_code", "date"]).reset_index(drop=True)
    if decisions.duplicated(["class_code", "date"]).any():
        raise ValueError("Consolidated reviews contain duplicate class/date rows.")
    return decisions, provenance


def full_timeline(root: Path, class_codes: list[str]) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for class_code in class_codes:
        dates = pd.read_parquet(
            root / "data" / "wtss" / f"wtss_class_{class_code}.parquet", columns=["date"]
        )["date"]
        result[class_code] = sorted(pd.to_datetime(dates).dt.strftime("%Y-%m-%d").unique().tolist())
    return result


def representative_series(
    root: Path,
    config: dict,
    decisions: pd.DataFrame,
    provenance: pd.DataFrame,
    candidates: pd.DataFrame,
) -> pd.DataFrame:
    bands = list(config["bands"])
    class_codes = list(config["classes"])
    timeline = full_timeline(root, class_codes)
    decisions_by_key = decisions.set_index(["class_code", "date"], drop=False)
    provenance_by_key = provenance.set_index(["class_code", "date"], drop=False)
    candidates_by_id = candidates.set_index("candidate_id", drop=False)
    rows: list[dict] = []

    for class_code in class_codes:
        for date in timeline[class_code]:
            key = (class_code, date)
            base = {
                "class_code": class_code,
                "class_name": config["classes"][class_code],
                "date": date,
                "reviewer_id": "rodrigo",
                "decision_rule": "NO_PPI_CANDIDATES",
                "validated_active_vegetation_endmembers": "",
                "validated_candidate_ids": "",
                "validated_candidate_count": 0,
                "representative_candidate_id": "",
                "representative_endmember_label": "",
                "representative_ppi_score": pd.NA,
                "representative_systematic_order": pd.NA,
                "representative_rule": "MAX_PPI_SCORE_THEN_SYSTEMATIC_ORDER",
                "secondary_review_available": class_code in SECONDARY_REVIEWS,
                "secondary_exact_match": pd.NA,
                "series_status": "NO_PPI_CANDIDATES",
                "valid_for_series": False,
            }
            base.update({band: np.nan for band in bands})
            base.update({"NDVI": np.nan, "EVI": np.nan, "BSI": np.nan})

            if key not in decisions_by_key.index:
                rows.append(base)
                continue

            decision = decisions_by_key.loc[key]
            evidence = provenance_by_key.loc[key]
            base["decision_rule"] = decision["decision_rule"]
            base["secondary_exact_match"] = evidence["secondary_exact_match"]
            base["validated_active_vegetation_endmembers"] = decision[
                "active_vegetation_endmembers"
            ]
            base["validated_candidate_ids"] = decision["candidate_ids"]

            if decision["active_vegetation_endmembers"] == "NENHUM":
                base["series_status"] = "NO_VALIDATED_ACTIVE_VEGETATION"
                rows.append(base)
                continue

            identifiers = [value for value in decision["candidate_ids"].split("|") if value]
            selected = candidates_by_id.loc[identifiers].copy()
            if isinstance(selected, pd.Series):
                selected = selected.to_frame().T
            selected = selected.reset_index(drop=True)
            selected = selected.sort_values(
                ["ppi_score", "systematic_order", "candidate_id"], ascending=[False, True, True]
            )
            representative = selected.iloc[0].to_dict()
            base["validated_candidate_count"] = len(identifiers)
            base["representative_candidate_id"] = representative["candidate_id"]
            base["representative_endmember_label"] = representative["endmember_label"]
            base["representative_ppi_score"] = int(representative["ppi_score"])
            base["representative_systematic_order"] = int(representative["systematic_order"])
            base["series_status"] = "VALIDATED_ACTIVE_VEGETATION"
            base["valid_for_series"] = True
            base.update({band: float(representative[band]) for band in bands})
            base.update(spectral_indices(representative, bands))
            rows.append(base)

    result = pd.DataFrame(rows).sort_values(["class_code", "date"]).reset_index(drop=True)
    expected_rows = len(class_codes) * int(config["period"]["expected_dates"])
    if len(result) != expected_rows:
        raise ValueError(f"Expected {expected_rows} full-series rows, found {len(result)}.")
    return result


def summarize_series(series: pd.DataFrame, config: dict) -> pd.DataFrame:
    expected = int(config["period"]["expected_dates"])
    threshold = float(config["analysis"]["minimum_valid_fraction"])
    rows = []
    for class_code, group in series.groupby("class_code", sort=True):
        valid = int(group["valid_for_series"].sum())
        fraction = valid / expected
        rows.append(
            {
                "class_code": class_code,
                "class_name": config["classes"][class_code],
                "expected_dates": expected,
                "validated_active_dates": valid,
                "no_validated_active_vegetation": int(
                    group["series_status"].eq("NO_VALIDATED_ACTIVE_VEGETATION").sum()
                ),
                "no_ppi_candidates": int(group["series_status"].eq("NO_PPI_CANDIDATES").sum()),
                "valid_fraction": fraction,
                "minimum_valid_fraction": threshold,
                "stl_eligible": bool(fraction >= threshold),
            }
        )
    return pd.DataFrame(rows)


def decompose_bands(
    series: pd.DataFrame, summary: pd.DataFrame, config: dict
) -> tuple[pd.DataFrame, pd.DataFrame]:
    bands = list(config["bands"])
    period = int(config["analysis"]["stl_period"])
    eligible = summary.set_index("class_code")["stl_eligible"].to_dict()
    rows: list[dict] = []
    decomposition_summary: list[dict] = []

    for class_code, group in series.groupby("class_code", sort=True):
        group = group.sort_values("date").reset_index(drop=True)
        dates = pd.to_datetime(group["date"])
        for band in bands:
            observed = pd.Series(group[band].to_numpy(float), index=dates)
            valid_count = int(observed.notna().sum())
            base_summary = {
                "class_code": class_code,
                "band": band,
                "period": period,
                "valid_observations": valid_count,
                "missing_observations": int(observed.isna().sum()),
                "valid_fraction": valid_count / len(observed),
            }
            if not eligible[class_code]:
                decomposition_summary.append(
                    {
                        **base_summary,
                        "status": "INSUFFICIENT_VALID_FRACTION",
                        "maximum_reconstruction_error": np.nan,
                    }
                )
                for date, value in observed.items():
                    rows.append(
                        {
                            "class_code": class_code,
                            "date": date.strftime("%Y-%m-%d"),
                            "band": band,
                            "observed": value,
                            "stl_input": np.nan,
                            "imputed_for_stl": bool(pd.isna(value)),
                            "trend": np.nan,
                            "seasonal": np.nan,
                            "residual": np.nan,
                            "status": "INSUFFICIENT_VALID_FRACTION",
                        }
                    )
                continue

            stl_input = observed.interpolate(method="time", limit_direction="both")
            if stl_input.isna().any():
                raise ValueError(f"Interpolation failed for class {class_code}, band {band}.")
            fit = STL(stl_input.to_numpy(float), period=period, robust=True).fit()
            reconstructed = fit.trend + fit.seasonal + fit.resid
            error = float(np.max(np.abs(stl_input.to_numpy(float) - reconstructed)))
            decomposition_summary.append(
                {**base_summary, "status": "OK", "maximum_reconstruction_error": error}
            )
            for index, date in enumerate(dates):
                rows.append(
                    {
                        "class_code": class_code,
                        "date": date.strftime("%Y-%m-%d"),
                        "band": band,
                        "observed": observed.iloc[index],
                        "stl_input": float(stl_input.iloc[index]),
                        "imputed_for_stl": bool(pd.isna(observed.iloc[index])),
                        "trend": float(fit.trend[index]),
                        "seasonal": float(fit.seasonal[index]),
                        "residual": float(fit.resid[index]),
                        "status": "OK",
                    }
                )

    return pd.DataFrame(rows), pd.DataFrame(decomposition_summary)


def main() -> int:
    root = repository_root()
    config = load_config(root)
    class_codes = list(config["classes"])
    candidates = load_candidates(root, class_codes)
    primary = {
        class_code: load_review(root, relative, class_code)
        for class_code, relative in PRIMARY_REVIEWS.items()
    }
    secondary = {
        class_code: load_review(root, relative, class_code)
        for class_code, relative in SECONDARY_REVIEWS.items()
    }

    decisions, provenance = consolidate_reviews(
        root, config, primary, secondary, candidates
    )
    validated_dir = root / "reviews" / "validated"
    validated_dir.mkdir(parents=True, exist_ok=True)
    decisions.to_csv(validated_dir / "reviews_consolidadas.csv", index=False, encoding="utf-8")
    decisions.to_parquet(validated_dir / "reviews_consolidadas.parquet", index=False)
    provenance.to_csv(validated_dir / "review_provenance.csv", index=False, encoding="utf-8")
    provenance.to_parquet(validated_dir / "review_provenance.parquet", index=False)

    series = representative_series(root, config, decisions, provenance, candidates)
    summary = summarize_series(series, config)
    series_dir = root / "data" / "series"
    series_dir.mkdir(parents=True, exist_ok=True)
    series.to_csv(series_dir / "representative_spectra.csv", index=False, encoding="utf-8")
    series.to_parquet(series_dir / "representative_spectra.parquet", index=False)
    summary.to_csv(series_dir / "series_completeness.csv", index=False, encoding="utf-8")
    summary.to_parquet(series_dir / "series_completeness.parquet", index=False)

    components, stl_summary = decompose_bands(series, summary, config)
    analysis_dir = root / "data" / "analysis"
    analysis_dir.mkdir(parents=True, exist_ok=True)
    components.to_csv(analysis_dir / "stl_components.csv", index=False, encoding="utf-8")
    components.to_parquet(analysis_dir / "stl_components.parquet", index=False)
    stl_summary.to_csv(analysis_dir / "stl_summary.csv", index=False, encoding="utf-8")
    stl_summary.to_parquet(analysis_dir / "stl_summary.parquet", index=False)

    report = {
        "review_decisions": int(len(decisions)),
        "full_class_dates": int(len(series)),
        "representative_spectra": int(series["valid_for_series"].sum()),
        "classes_stl_eligible": summary.loc[summary["stl_eligible"], "class_code"].tolist(),
        "classes_stl_ineligible": summary.loc[~summary["stl_eligible"], "class_code"].tolist(),
        "bands_decomposed": int(stl_summary["status"].eq("OK").sum()),
        "primary_reviewer": "rodrigo",
        
        "disagreement_rule": ("PRIMARY_REVIEW_PRECEDENCE" if SECONDARY_REVIEWS else "NOT_APPLICABLE_SINGLE_REVIEWER"),
        "representative_rule": "MAX_PPI_SCORE_THEN_SYSTEMATIC_ORDER",
        "stl_period": int(config["analysis"]["stl_period"]),
        "minimum_valid_fraction": float(config["analysis"]["minimum_valid_fraction"]),
    }
    (analysis_dir / "validated_series_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(summary.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
