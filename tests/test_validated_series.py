from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]


def test_validated_reviews_and_representative_series():
    reviews = pd.read_parquet(ROOT / "reviews" / "validated" / "reviews_consolidadas.parquet")
    provenance = pd.read_parquet(ROOT / "reviews" / "validated" / "review_provenance.parquet")
    series = pd.read_parquet(ROOT / "data" / "series" / "representative_spectra.parquet")

    assert len(reviews) == 918
    assert not reviews.duplicated(["class_code", "date"]).any()
    assert len(provenance) == 918
    assert provenance["decision_rule"].eq("PRIMARY_REVIEW").all()
    assert len(series) == 920
    assert not series.duplicated(["class_code", "date"]).any()
    assert series["valid_for_series"].sum() == 796

    bands = ["B02", "B03", "B04", "B05", "B06", "B07", "B08", "B8A", "B11", "B12"]
    valid = series[series["valid_for_series"]]
    assert np.isfinite(valid[[*bands, "NDVI", "EVI", "BSI"]].to_numpy(float)).all()


def test_stl_outputs_and_threshold():
    completeness = pd.read_parquet(ROOT / "data" / "series" / "series_completeness.parquet")
    components = pd.read_parquet(ROOT / "data" / "analysis" / "stl_components.parquet")
    summary = pd.read_parquet(ROOT / "data" / "analysis" / "stl_summary.parquet")

    eligibility = completeness.set_index("class_code")["stl_eligible"].to_dict()
    assert eligibility == {"01": False, "02": True, "09": True, "10": True, "11": True}
    assert len(components) == 9_200
    assert len(summary) == 50
    assert summary["status"].eq("OK").sum() == 40
    assert summary["status"].eq("INSUFFICIENT_VALID_FRACTION").sum() == 10
    assert summary.loc[summary["status"].eq("OK"), "maximum_reconstruction_error"].max() < 1e-10
