import json
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
ANALYSIS = ROOT / "data" / "analysis" / "spectrotemporal"


def test_spectrotemporal_counts_and_scope():
    report = json.loads((ANALYSIS / "spectrotemporal_report.json").read_text(encoding="utf-8"))
    assert report["analytic_classes"] == ["02", "09", "10", "11"]
    assert report["class_dates"] == 736
    assert report["automatic_candidates"] == 2935
    assert report["class_dates_with_candidates"] == 734
    assert report["no_active_candidate"] == 76
    assert report["representative_spectra"] == 658
    assert report["single_active_candidate"] == 571
    assert report["multiple_active_candidates"] == 87
    assert report["excluded_class"]["class_code"] == "01"
    assert report["excluded_class"]["valid_fraction"] == 0.75


def test_components_metrics_and_robustness():
    components = pd.read_parquet(ANALYSIS / "spectrotemporal_components.parquet")
    metrics = pd.read_parquet(ANALYSIS / "spectrotemporal_band_metrics.parquet")
    domains = pd.read_parquet(ANALYSIS / "spectrotemporal_domain_metrics.parquet")
    comparison = pd.read_parquet(ANALYSIS / "robustness_comparison.parquet")
    amplitude_claims = pd.read_parquet(ANALYSIS / "robustness_amplitude_claims.parquet")

    assert len(components) == 4 * 184 * 10
    assert set(components["class_code"]) == {"02", "09", "10", "11"}
    assert set(components["band"]) == {"B02", "B03", "B04", "B05", "B06", "B07", "B08", "B8A", "B11", "B12"}
    assert len(metrics) == 8 * 4 * 10
    assert len(domains) == 8 * 4 * 4
    assert len(comparison) == 8
    assert set(metrics["interpolation_method"]) == {"linear", "pchip"}
    assert len(amplitude_claims) == 4
    assert set(amplitude_claims["primary_top_amplitude_domain"]) == {"NIR"}
    assert amplitude_claims.set_index("class_code").loc["09", "variants_preserving_primary_top"] == 7
    assert amplitude_claims.set_index("class_code").loc["09", "differing_variants"] == "lowest_active_ppi"
    assert amplitude_claims.loc[
        amplitude_claims["class_code"].ne("09"), "preserved_in_all_variants"
    ].all()
    assert comparison["mean_absolute_amplitude_difference"].ge(0).all()
    assert comparison["maximum_absolute_amplitude_difference"].ge(0).all()
    assert metrics["maximum_reconstruction_error"].max() < 1e-10
    assert metrics["seasonal_strength"].between(0, 1).all()
    assert metrics["low_frequency_strength"].between(0, 1).all()
    assert metrics["seasonal_amplitude_q95_q05"].ge(0).all()
    assert np.isfinite(metrics["seasonal_strength"]).all()


def test_turnover_and_diagnostics():
    turnover = pd.read_parquet(ANALYSIS / "representative_turnover.parquet")
    transitions = pd.read_parquet(ANALYSIS / "representative_transitions.parquet")
    correlations = pd.read_parquet(ANALYSIS / "valid_pixel_correlations.parquet")
    integrity = pd.read_csv(ANALYSIS / "integrity_sha256.csv")

    expected_valid = {"02": 160, "09": 173, "10": 165, "11": 160}
    assert turnover.set_index("class_code")["valid_dates"].to_dict() == expected_valid
    assert turnover["unique_representative_pixels"].le(turnover["valid_dates"]).all()
    assert turnover["same_pixel_adjacent_fraction"].between(0, 1).all()
    assert transitions["distance_m"].ge(0).all()
    assert len(correlations) == 40
    assert correlations["spearman_rho_valid_pixels_reflectance"].between(-1, 1).all()
    assert integrity["sha256"].str.fullmatch(r"[0-9a-f]{64}").all()


def test_amplitude_scale_availability_and_parquet_runtime():
    amplitude = pd.read_parquet(ANALYSIS / "amplitude_scale_diagnostics.parquet")
    availability = pd.read_parquet(ANALYSIS / "active_candidate_availability_by_phase.parquet")
    report = json.loads((ANALYSIS / "spectrotemporal_report.json").read_text(encoding="utf-8"))

    assert len(amplitude) == 40
    assert amplitude["seasonal_amplitude_absolute"].ge(0).all()
    assert np.isfinite(amplitude["seasonal_amplitude_relative_to_median"]).all()
    assert report["amplitude_scale"]["spearman_absolute_amplitude_vs_median_reflectance"] > 0.85
    assert len(availability) == 4 * 23
    assert availability["active_fraction"].between(0, 1).all()
    assert availability.groupby("class_code")["dates"].sum().eq(184).all()
    assert report["parquet_runtime"] == {"pyarrow": "22.0.0", "read_back_validated": True}
    assert "pchip_interpolation" in report["sensitivity_variants"]
