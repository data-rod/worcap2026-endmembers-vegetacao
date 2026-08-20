from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow
from scipy.interpolate import PchipInterpolator
from scipy.stats import spearmanr
from statsmodels.tsa.seasonal import STL


ANALYTIC_CLASSES = ("02", "09", "10", "11")
BANDS = ("B02", "B03", "B04", "B05", "B06", "B07", "B08", "B8A", "B11", "B12")
DOMAINS = {
    "VIS": ("B02", "B03", "B04"),
    "RED_EDGE": ("B05", "B06", "B07"),
    "NIR": ("B08", "B8A"),
    "SWIR": ("B11", "B12"),
}
BAND_DOMAIN = {band: domain for domain, bands in DOMAINS.items() for band in bands}

EXPECTED_COUNTS = {
    "class_dates": 736,
    "automatic_candidates": 2935,
    "class_dates_with_candidates": 734,
    "no_active_candidate": 76,
    "representative_spectra": 658,
    "single_active_candidate": 571,
    "multiple_active_candidates": 87,
}


def repository_root(start: str | Path | None = None) -> Path:
    current = Path(start or Path.cwd()).resolve()
    for candidate in (current, *current.parents):
        if (candidate / "config" / "study.yaml").is_file() and (candidate / "data" / "candidates").is_dir():
            return candidate
    raise FileNotFoundError("Repository root not found.")


def zfill_class(series: pd.Series) -> pd.Series:
    return series.astype(str).str.zfill(2)


def load_inputs(root: Path) -> dict[str, pd.DataFrame]:
    series = pd.read_parquet(root / "data" / "series" / "representative_spectra.parquet")
    reviews = pd.read_parquet(root / "reviews" / "validated" / "reviews_consolidadas.parquet")
    points = pd.read_parquet(root / "data" / "points" / "points.parquet")

    candidate_frames = []
    manifest_frames = []
    for class_code in ANALYTIC_CLASSES:
        candidate_frames.append(
            pd.read_parquet(root / "data" / "candidates" / f"candidates_class_{class_code}.parquet")
        )
        manifest_frames.append(
            pd.read_parquet(root / "data" / "candidates" / f"ppi_manifest_class_{class_code}.parquet")
        )

    candidates = pd.concat(candidate_frames, ignore_index=True)
    manifests = pd.concat(manifest_frames, ignore_index=True)
    tables = {
        "series": series,
        "reviews": reviews,
        "points": points,
        "candidates": candidates,
        "manifests": manifests,
    }
    for table in tables.values():
        if "class_code" in table.columns:
            table["class_code"] = zfill_class(table["class_code"])
        if "date" in table.columns:
            table["date"] = pd.to_datetime(table["date"]).dt.strftime("%Y-%m-%d")

    tables["series"] = series[series["class_code"].isin(ANALYTIC_CLASSES)].copy()
    tables["reviews"] = reviews[reviews["class_code"].isin(ANALYTIC_CLASSES)].copy()
    tables["points"] = points[points["class_code"].isin(ANALYTIC_CLASSES)].copy()
    return tables


def validate_counts(tables: dict[str, pd.DataFrame]) -> dict[str, int]:
    series = tables["series"]
    reviews = tables["reviews"]
    candidates = tables["candidates"]
    manifests = tables["manifests"]

    active_counts = reviews["active_vegetation_endmembers"].map(
        lambda value: 0 if value == "NENHUM" else len([item for item in str(value).split("|") if item])
    )
    counts = {
        "class_dates": int(len(series)),
        "automatic_candidates": int(len(candidates)),
        "class_dates_with_candidates": int(manifests["candidate_count"].gt(0).sum()),
        "no_active_candidate": int(active_counts.eq(0).sum()),
        "representative_spectra": int(series["valid_for_series"].sum()),
        "single_active_candidate": int(active_counts.eq(1).sum()),
        "multiple_active_candidates": int(active_counts.gt(1).sum()),
    }
    if counts != EXPECTED_COUNTS:
        raise ValueError(f"Unexpected four-class counts: {counts!r}")
    if series.duplicated(["class_code", "date"]).any():
        raise ValueError("Representative series contains duplicate class/date rows.")
    if candidates["candidate_id"].duplicated().any():
        raise ValueError("Candidate identifiers are not unique.")
    return counts


def attach_candidate_metadata(
    series: pd.DataFrame,
    candidates: pd.DataFrame,
    manifests: pd.DataFrame,
) -> pd.DataFrame:
    candidate_metadata = candidates[
        ["candidate_id", "point_id", "ppi_score", "systematic_order", *BANDS]
    ].rename(
        columns={
            "candidate_id": "representative_candidate_id",
            "ppi_score": "candidate_ppi_score",
            "systematic_order": "candidate_systematic_order",
        }
    )
    result = series.merge(candidate_metadata, on="representative_candidate_id", how="left", suffixes=("", "_candidate"))
    manifest_columns = manifests[["class_code", "date", "valid_pixels", "candidate_count", "status", "warnings"]].rename(
        columns={"status": "ppi_status", "warnings": "ppi_warnings"}
    )
    result = result.merge(manifest_columns, on=["class_code", "date"], how="left")
    for band in BANDS:
        candidate_band = f"{band}_candidate"
        mismatch = result["valid_for_series"] & ~np.isclose(
            result[band].to_numpy(float), result[candidate_band].to_numpy(float), equal_nan=True
        )
        if mismatch.any():
            raise ValueError(f"Representative spectrum differs from candidate table for {band}.")
        result = result.drop(columns=candidate_band)
    valid = result["valid_for_series"]
    if result.loc[valid, "point_id"].isna().any():
        raise ValueError("A valid representative lacks point metadata.")
    return result.sort_values(["class_code", "date"]).reset_index(drop=True)


def build_lowest_score_series(
    primary: pd.DataFrame,
    reviews: pd.DataFrame,
    candidates: pd.DataFrame,
) -> pd.DataFrame:
    result = primary.copy()
    result["valid_for_series"] = False
    result["representative_candidate_id"] = ""
    result["point_id"] = pd.NA
    result["candidate_ppi_score"] = np.nan
    result["candidate_systematic_order"] = np.nan
    for band in BANDS:
        result[band] = np.nan

    candidate_index = candidates.set_index("candidate_id", drop=False)
    result_index = result.set_index(["class_code", "date"]).index
    row_lookup = {key: index for index, key in enumerate(result_index)}

    for review in reviews.itertuples(index=False):
        if review.active_vegetation_endmembers == "NENHUM":
            continue
        identifiers = [item for item in str(review.candidate_ids).split("|") if item]
        selected = candidate_index.loc[identifiers].copy()
        if isinstance(selected, pd.Series):
            selected = selected.to_frame().T
        selected = selected.reset_index(drop=True)
        selected = selected.sort_values(
            ["ppi_score", "systematic_order", "candidate_id"],
            ascending=[True, False, False],
        )
        representative = selected.iloc[0]
        row_index = row_lookup[(review.class_code, review.date)]
        result.loc[row_index, "valid_for_series"] = True
        result.loc[row_index, "representative_candidate_id"] = representative["candidate_id"]
        result.loc[row_index, "point_id"] = representative["point_id"]
        result.loc[row_index, "candidate_ppi_score"] = int(representative["ppi_score"])
        result.loc[row_index, "candidate_systematic_order"] = int(representative["systematic_order"])
        for band in BANDS:
            result.loc[row_index, band] = float(representative[band])

    if int(result["valid_for_series"].sum()) != EXPECTED_COUNTS["representative_spectra"]:
        raise ValueError("Lowest-score sensitivity series has an unexpected valid count.")
    return result


def attach_coordinates(series: pd.DataFrame, points: pd.DataFrame) -> pd.DataFrame:
    coordinates = points[["point_id", "x_5880", "y_5880", "longitude", "latitude"]].drop_duplicates("point_id")
    result = series.merge(coordinates, on="point_id", how="left")
    if result.loc[result["valid_for_series"], ["x_5880", "y_5880"]].isna().any().any():
        raise ValueError("Coordinates are missing for valid representatives.")
    return result


def turnover_metrics(series: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    summaries: list[dict] = []
    transitions: list[dict] = []
    for class_code, group in series.groupby("class_code", sort=True):
        group = group.sort_values("date").reset_index(drop=True)
        valid = group[group["valid_for_series"]].copy()
        for index in range(1, len(group)):
            previous = group.iloc[index - 1]
            current = group.iloc[index]
            if not bool(previous["valid_for_series"]) or not bool(current["valid_for_series"]):
                continue
            distance = float(
                np.hypot(
                    float(current["x_5880"]) - float(previous["x_5880"]),
                    float(current["y_5880"]) - float(previous["y_5880"]),
                )
            )
            transitions.append(
                {
                    "class_code": class_code,
                    "previous_date": previous["date"],
                    "date": current["date"],
                    "previous_point_id": previous["point_id"],
                    "point_id": current["point_id"],
                    "same_point": bool(previous["point_id"] == current["point_id"]),
                    "distance_m": distance,
                }
            )
        class_transitions = [row for row in transitions if row["class_code"] == class_code]
        distances = np.array([row["distance_m"] for row in class_transitions], dtype=float)
        same = np.array([row["same_point"] for row in class_transitions], dtype=bool)
        summaries.append(
            {
                "class_code": class_code,
                "valid_dates": int(len(valid)),
                "unique_representative_pixels": int(valid["point_id"].nunique()),
                "unique_pixel_fraction": float(valid["point_id"].nunique() / len(valid)),
                "adjacent_valid_pairs": int(len(class_transitions)),
                "same_pixel_adjacent_pairs": int(same.sum()) if same.size else 0,
                "same_pixel_adjacent_fraction": float(same.mean()) if same.size else np.nan,
                "median_adjacent_distance_km": float(np.median(distances) / 1000.0) if distances.size else np.nan,
                "mean_adjacent_distance_km": float(np.mean(distances) / 1000.0) if distances.size else np.nan,
            }
        )
    return pd.DataFrame(summaries), pd.DataFrame(transitions)


def strength(component: np.ndarray, residual: np.ndarray) -> float:
    denominator = float(np.var(component + residual, ddof=1))
    if denominator <= 1e-15:
        return np.nan
    value = 1.0 - float(np.var(residual, ddof=1)) / denominator
    return float(max(0.0, value))


def interpolate_for_stl(observed: pd.Series, method: str) -> pd.Series:
    if method == "linear":
        return observed.interpolate(method="time", limit_direction="both")
    if method != "pchip":
        raise ValueError(f"Unsupported interpolation method: {method!r}.")

    values = observed.to_numpy(float)
    observed_positions = np.flatnonzero(np.isfinite(values))
    if len(observed_positions) < 2:
        raise ValueError("PCHIP interpolation requires at least two observed values.")

    first = int(observed_positions[0])
    last = int(observed_positions[-1])
    filled = values.copy()
    internal_positions = np.arange(first, last + 1, dtype=float)
    interpolator = PchipInterpolator(
        observed_positions.astype(float),
        values[observed_positions],
        extrapolate=False,
    )
    filled[first : last + 1] = interpolator(internal_positions)
    filled[:first] = values[first]
    filled[last + 1 :] = values[last]
    return pd.Series(filled, index=observed.index)


def fit_variant(
    series: pd.DataFrame,
    *,
    variant: str,
    seasonal_window: int = 7,
    trend_window: int = 45,
    low_pass_window: int = 25,
    robust: bool = True,
    exclude_valid_pixels_below: int | None = None,
    trim_initial_imputed: bool = False,
    interpolation_method: str = "linear",
    keep_components: bool = False,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    metric_rows: list[dict] = []
    component_rows: list[dict] = []

    for class_code, class_group in series.groupby("class_code", sort=True):
        class_group = class_group.sort_values("date").reset_index(drop=True).copy()
        class_group["time_order"] = np.arange(len(class_group), dtype=int)
        class_group["seasonal_phase"] = class_group["time_order"] % 23 + 1
        if trim_initial_imputed and class_code == "11" and not bool(class_group.iloc[0]["valid_for_series"]):
            class_group = class_group.iloc[1:].reset_index(drop=True)

        dates = pd.to_datetime(class_group["date"])
        for band in BANDS:
            values = class_group[band].astype(float).copy()
            values[~class_group["valid_for_series"].astype(bool)] = np.nan
            if exclude_valid_pixels_below is not None:
                values[class_group["valid_pixels"].astype(float) < exclude_valid_pixels_below] = np.nan
            observed = pd.Series(values.to_numpy(float), index=dates)
            stl_input = interpolate_for_stl(observed, interpolation_method)
            if stl_input.isna().any():
                raise ValueError(f"Interpolation failed for {variant}/{class_code}/{band}.")

            fit = STL(
                stl_input.to_numpy(float),
                period=23,
                seasonal=seasonal_window,
                trend=trend_window,
                low_pass=low_pass_window,
                robust=robust,
            ).fit()
            observed_mask = observed.notna().to_numpy(bool)
            seasonal_values = np.asarray(fit.seasonal, dtype=float)
            trend_values = np.asarray(fit.trend, dtype=float)
            residual_values = np.asarray(fit.resid, dtype=float)
            seasonal_observed = seasonal_values[observed_mask]
            trend_observed = trend_values[observed_mask]
            residual_observed = residual_values[observed_mask]

            phase_table = pd.DataFrame(
                {
                    "phase": class_group.loc[observed_mask, "seasonal_phase"].to_numpy(int),
                    "seasonal": seasonal_observed,
                }
            )
            phase_profile = phase_table.groupby("phase", sort=True)["seasonal"].median()
            reconstruction = trend_values + seasonal_values + residual_values
            metric_rows.append(
                {
                    "variant": variant,
                    "class_code": class_code,
                    "band": band,
                    "domain": BAND_DOMAIN[band],
                    "observed_dates": int(observed_mask.sum()),
                    "imputed_dates": int((~observed_mask).sum()),
                    "seasonal_window": seasonal_window,
                    "trend_window": trend_window,
                    "low_pass_window": low_pass_window,
                    "robust": bool(robust),
                    "exclude_valid_pixels_below": exclude_valid_pixels_below,
                    "trim_initial_imputed": bool(trim_initial_imputed),
                    "interpolation_method": interpolation_method,
                    "seasonal_strength": strength(seasonal_observed, residual_observed),
                    "low_frequency_strength": strength(trend_observed, residual_observed),
                    "seasonal_amplitude_q95_q05": float(
                        np.quantile(seasonal_observed, 0.95) - np.quantile(seasonal_observed, 0.05)
                    ),
                    "seasonal_phase_max_composite": int(phase_profile.idxmax()),
                    "seasonal_phase_min_composite": int(phase_profile.idxmin()),
                    "maximum_reconstruction_error": float(
                        np.max(np.abs(stl_input.to_numpy(float) - reconstruction))
                    ),
                }
            )

            if keep_components:
                for index, date in enumerate(dates):
                    component_rows.append(
                        {
                            "class_code": class_code,
                            "date": date.strftime("%Y-%m-%d"),
                            "time_order": int(class_group.iloc[index]["time_order"]),
                            "seasonal_phase": int(class_group.iloc[index]["seasonal_phase"]),
                            "band": band,
                            "observed_reflectance": observed.iloc[index],
                            "stl_input": float(stl_input.iloc[index]),
                            "imputed_for_stl": bool(pd.isna(observed.iloc[index])),
                            "edge_low_frequency": bool(index < 22 or index >= len(dates) - 22),
                            "low_frequency": float(trend_values[index]),
                            "seasonal": float(seasonal_values[index]),
                            "residual": float(residual_values[index]),
                        }
                    )

    return pd.DataFrame(metric_rows), pd.DataFrame(component_rows)


def domain_metrics(band_metrics: pd.DataFrame, turnover: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict] = []
    for (variant, class_code, domain), group in band_metrics.groupby(
        ["variant", "class_code", "domain"], sort=True
    ):
        rows.append(
            {
                "variant": variant,
                "class_code": class_code,
                "domain": domain,
                "bands": "|".join(group["band"].tolist()),
                "band_count": int(len(group)),
                "observed_dates": int(group["observed_dates"].min()),
                "seasonal_strength_median": float(group["seasonal_strength"].median()),
                "seasonal_strength_min": float(group["seasonal_strength"].min()),
                "seasonal_strength_max": float(group["seasonal_strength"].max()),
                "seasonal_amplitude_median": float(group["seasonal_amplitude_q95_q05"].median()),
                "low_frequency_strength_median": float(group["low_frequency_strength"].median()),
            }
        )
    result = pd.DataFrame(rows)
    return result.merge(
        turnover[["class_code", "unique_representative_pixels"]], on="class_code", how="left"
    )


def robustness_comparison(domain: pd.DataFrame) -> pd.DataFrame:
    primary = domain[domain["variant"].eq("primary")].set_index(["class_code", "domain"])
    rows: list[dict] = []
    primary_top = (
        domain[domain["variant"].eq("primary")]
        .sort_values(["class_code", "seasonal_strength_median"], ascending=[True, False])
        .groupby("class_code", sort=True)
        .first()["domain"]
        .to_dict()
    )
    primary_amplitude_top = (
        domain[domain["variant"].eq("primary")]
        .sort_values(["class_code", "seasonal_amplitude_median"], ascending=[True, False])
        .groupby("class_code", sort=True)
        .first()["domain"]
        .to_dict()
    )
    for variant, group in domain.groupby("variant", sort=True):
        aligned = group.set_index(["class_code", "domain"]).loc[primary.index]
        rho = spearmanr(
            primary["seasonal_strength_median"].to_numpy(float),
            aligned["seasonal_strength_median"].to_numpy(float),
        ).statistic
        difference = (
            aligned["seasonal_strength_median"].to_numpy(float)
            - primary["seasonal_strength_median"].to_numpy(float)
        )
        variant_top = (
            group.sort_values(["class_code", "seasonal_strength_median"], ascending=[True, False])
            .groupby("class_code", sort=True)
            .first()["domain"]
            .to_dict()
        )
        amplitude_difference = (
            aligned["seasonal_amplitude_median"].to_numpy(float)
            - primary["seasonal_amplitude_median"].to_numpy(float)
        )
        amplitude_rho = spearmanr(
            primary["seasonal_amplitude_median"].to_numpy(float),
            aligned["seasonal_amplitude_median"].to_numpy(float),
        ).statistic
        variant_amplitude_top = (
            group.sort_values(["class_code", "seasonal_amplitude_median"], ascending=[True, False])
            .groupby("class_code", sort=True)
            .first()["domain"]
            .to_dict()
        )
        rows.append(
            {
                "variant": variant,
                "spearman_with_primary": float(rho),
                "mean_absolute_strength_difference": float(np.mean(np.abs(difference))),
                "maximum_absolute_strength_difference": float(np.max(np.abs(difference))),
                "top_domain_matches": int(
                    sum(primary_top[class_code] == variant_top[class_code] for class_code in ANALYTIC_CLASSES)
                ),
                "amplitude_spearman_with_primary": float(amplitude_rho),
                "mean_absolute_amplitude_difference": float(np.mean(np.abs(amplitude_difference))),
                "maximum_absolute_amplitude_difference": float(np.max(np.abs(amplitude_difference))),
                "top_amplitude_domain_matches": int(
                    sum(
                        primary_amplitude_top[class_code] == variant_amplitude_top[class_code]
                        for class_code in ANALYTIC_CLASSES
                    )
                ),
                "classes_compared": len(ANALYTIC_CLASSES),
            }
        )
    return pd.DataFrame(rows)


def amplitude_rank_claims(domain: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict] = []
    for class_code in ANALYTIC_CLASSES:
        class_table = domain[domain["class_code"].eq(class_code)].copy()
        top_by_variant = (
            class_table.sort_values(["variant", "seasonal_amplitude_median"], ascending=[True, False])
            .groupby("variant", sort=True)
            .first()["domain"]
        )
        primary_domain = str(top_by_variant.loc["primary"])
        matches = top_by_variant.eq(primary_domain)
        rows.append(
            {
                "class_code": class_code,
                "primary_top_amplitude_domain": primary_domain,
                "variants_preserving_primary_top": int(matches.sum()),
                "variants_tested": int(len(matches)),
                "preserved_in_all_variants": bool(matches.all()),
                "differing_variants": "|".join(top_by_variant.index[~matches].tolist()),
            }
        )
    return pd.DataFrame(rows)


def robustness_claims(domain: pd.DataFrame) -> pd.DataFrame:
    comparisons = (
        ("RED_EDGE", "VIS"),
        ("NIR", "VIS"),
        ("NIR", "SWIR"),
        ("RED_EDGE", "SWIR"),
    )
    rows: list[dict] = []
    for class_code in ANALYTIC_CLASSES:
        class_table = domain[domain["class_code"].eq(class_code)].pivot(
            index="variant", columns="domain", values="seasonal_strength_median"
        )
        for left, right in comparisons:
            outcomes = class_table[left] > class_table[right]
            rows.append(
                {
                    "class_code": class_code,
                    "claim": f"{left}_GT_{right}",
                    "variants_supporting": int(outcomes.sum()),
                    "variants_tested": int(len(outcomes)),
                    "supported_in_all_variants": bool(outcomes.all()),
                }
            )
    return pd.DataFrame(rows)


def valid_pixel_correlations(series: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict] = []
    for class_code, group in series.groupby("class_code", sort=True):
        group = group[group["valid_for_series"]].copy()
        for band in BANDS:
            subset = group[["valid_pixels", band]].dropna()
            rho = spearmanr(subset["valid_pixels"].to_numpy(float), subset[band].to_numpy(float)).statistic
            rows.append(
                {
                    "class_code": class_code,
                    "band": band,
                    "observations": int(len(subset)),
                    "spearman_rho_valid_pixels_reflectance": float(rho),
                }
            )
    return pd.DataFrame(rows)


def amplitude_scale_diagnostics(
    series: pd.DataFrame,
    band_metrics: pd.DataFrame,
) -> tuple[pd.DataFrame, float]:
    primary_metrics = band_metrics[band_metrics["variant"].eq("primary")].set_index(
        ["class_code", "band"]
    )
    rows: list[dict] = []
    for class_code, group in series.groupby("class_code", sort=True):
        observed_group = group[group["valid_for_series"].astype(bool)]
        for band in BANDS:
            observed = observed_group[band].dropna().to_numpy(float)
            median_reflectance = float(np.median(observed))
            amplitude = float(
                primary_metrics.loc[(class_code, band), "seasonal_amplitude_q95_q05"]
            )
            rows.append(
                {
                    "class_code": class_code,
                    "band": band,
                    "domain": BAND_DOMAIN[band],
                    "observed_dates": int(len(observed)),
                    "median_observed_reflectance": median_reflectance,
                    "seasonal_amplitude_absolute": amplitude,
                    "seasonal_amplitude_relative_to_median": (
                        amplitude / median_reflectance if abs(median_reflectance) > 1e-15 else np.nan
                    ),
                }
            )
    result = pd.DataFrame(rows)
    rho = spearmanr(
        result["seasonal_amplitude_absolute"].to_numpy(float),
        result["median_observed_reflectance"].to_numpy(float),
    ).statistic
    return result, float(rho)


def availability_by_phase(series: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict] = []
    for class_code, group in series.groupby("class_code", sort=True):
        group = group.sort_values("date").reset_index(drop=True).copy()
        group["seasonal_phase"] = np.arange(len(group), dtype=int) % 23 + 1
        for phase, phase_group in group.groupby("seasonal_phase", sort=True):
            active = phase_group["valid_for_series"].astype(bool)
            rows.append(
                {
                    "class_code": class_code,
                    "seasonal_phase": int(phase),
                    "dates": int(len(phase_group)),
                    "active_dates": int(active.sum()),
                    "no_active_dates": int((~active).sum()),
                    "active_fraction": float(active.mean()),
                    "median_valid_pixels": float(phase_group["valid_pixels"].median()),
                    "minimum_valid_pixels": int(phase_group["valid_pixels"].min()),
                    "maximum_valid_pixels": int(phase_group["valid_pixels"].max()),
                }
            )
    return pd.DataFrame(rows)


def write_table(frame: pd.DataFrame, path: Path) -> None:
    csv_path = path.with_suffix(".csv")
    parquet_path = path.with_suffix(".parquet")
    frame.to_csv(csv_path, index=False, encoding="utf-8")
    frame.to_parquet(parquet_path, index=False)
    reopened = pd.read_parquet(parquet_path)
    if len(reopened) != len(frame) or list(reopened.columns) != list(frame.columns):
        raise ValueError(f"Parquet read-back validation failed for {parquet_path.name}.")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> int:
    root = repository_root()
    output = root / "data" / "analysis" / "spectrotemporal"
    output.mkdir(parents=True, exist_ok=True)

    tables = load_inputs(root)
    counts = validate_counts(tables)
    primary = attach_candidate_metadata(tables["series"], tables["candidates"], tables["manifests"])
    primary = attach_coordinates(primary, tables["points"])
    lowest = build_lowest_score_series(primary, tables["reviews"], tables["candidates"])
    lowest = attach_coordinates(lowest.drop(columns=["x_5880", "y_5880", "longitude", "latitude"]), tables["points"])

    turnover, transitions = turnover_metrics(primary)
    variant_specs = (
        ("primary", primary, {}),
        ("lowest_active_ppi", lowest, {}),
        ("exclude_valid_pixels_below_100", primary, {"exclude_valid_pixels_below": 100}),
        ("seasonal_13", primary, {"seasonal_window": 13}),
        ("seasonal_23_trend_69", primary, {"seasonal_window": 23, "trend_window": 69}),
        ("nonrobust", primary, {"robust": False}),
        ("trim_initial_imputed", primary, {"trim_initial_imputed": True}),
        ("pchip_interpolation", primary, {"interpolation_method": "pchip"}),
    )

    all_metrics: list[pd.DataFrame] = []
    primary_components = pd.DataFrame()
    for variant, variant_series, options in variant_specs:
        metrics, components = fit_variant(
            variant_series,
            variant=variant,
            keep_components=variant == "primary",
            **options,
        )
        all_metrics.append(metrics)
        if variant == "primary":
            primary_components = components

    metrics = pd.concat(all_metrics, ignore_index=True)
    domains = domain_metrics(metrics, turnover)
    comparison = robustness_comparison(domains)
    claims = robustness_claims(domains)
    amplitude_claims = amplitude_rank_claims(domains)
    valid_correlations = valid_pixel_correlations(primary)
    amplitude_scale, amplitude_scale_rho = amplitude_scale_diagnostics(primary, metrics)
    availability = availability_by_phase(primary)

    write_table(primary_components, output / "spectrotemporal_components")
    write_table(metrics, output / "spectrotemporal_band_metrics")
    write_table(domains, output / "spectrotemporal_domain_metrics")
    write_table(turnover, output / "representative_turnover")
    write_table(transitions, output / "representative_transitions")
    write_table(comparison, output / "robustness_comparison")
    write_table(claims, output / "robustness_claims")
    write_table(amplitude_claims, output / "robustness_amplitude_claims")
    write_table(valid_correlations, output / "valid_pixel_correlations")
    write_table(amplitude_scale, output / "amplitude_scale_diagnostics")
    write_table(availability, output / "active_candidate_availability_by_phase")

    primary_domains = domains[domains["variant"].eq("primary")].copy()
    maximum_abs_valid_rho = float(
        valid_correlations["spearman_rho_valid_pixels_reflectance"].abs().max()
    )
    report = {
        **counts,
        "analytic_classes": list(ANALYTIC_CLASSES),
        "excluded_class": {"class_code": "01", "valid_dates": 138, "expected_dates": 184, "valid_fraction": 0.75},
        "stl_primary": {
            "period": 23,
            "seasonal": 7,
            "trend": 45,
            "low_pass": 25,
            "robust": True,
            "metrics_use_observed_dates_only": True,
        },
        "sensitivity_variants": [item[0] for item in variant_specs if item[0] != "primary"],
        "amplitude_rank_robustness": amplitude_claims.to_dict(orient="records"),
        "amplitude_scale": {
            "spearman_absolute_amplitude_vs_median_reflectance": amplitude_scale_rho,
            "combinations": int(len(amplitude_scale)),
            "relative_amplitude_is_supplementary": True,
        },
        "active_candidate_availability": {
            "minimum_phase_fraction": float(availability["active_fraction"].min()),
            "maximum_phase_fraction": float(availability["active_fraction"].max()),
            "phase_rows": int(len(availability)),
        },
        "valid_pixel_phase_ranges": [
            {
                "class_code": class_code,
                "minimum_phase_median": int(group["median_valid_pixels"].min()),
                "maximum_phase_median": int(group["median_valid_pixels"].max()),
                "maximum_to_minimum_ratio": float(
                    group["median_valid_pixels"].max() / group["median_valid_pixels"].min()
                ),
            }
            for class_code, group in availability.groupby("class_code", sort=True)
        ],
        "maximum_absolute_valid_pixel_correlation": maximum_abs_valid_rho,
        "parquet_runtime": {"pyarrow": pyarrow.__version__, "read_back_validated": True},
        "all_reconstruction_errors_below_1e_10": bool(
            metrics["maximum_reconstruction_error"].max() < 1e-10
        ),
        "primary_domain_metrics": primary_domains.to_dict(orient="records"),
    }
    report_path = output / "spectrotemporal_report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    integrity_rows = []
    for path in sorted(output.glob("*")):
        if path.is_file() and path.name != "integrity_sha256.csv":
            integrity_rows.append({"file": path.name, "bytes": path.stat().st_size, "sha256": sha256(path)})
    pd.DataFrame(integrity_rows).to_csv(output / "integrity_sha256.csv", index=False, encoding="utf-8")

    print(json.dumps({key: report[key] for key in EXPECTED_COUNTS}, ensure_ascii=False))
    print(f"Spectrotemporal analysis written to {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
