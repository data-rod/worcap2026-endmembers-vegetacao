import pandas as pd
import pytest

from worcap_endmembers.review import REVIEW_COLUMNS, validate_reviews


def test_review_columns_are_strict(tmp_path):
    path = tmp_path / "invalid.csv"
    pd.DataFrame([{"class_code": "01"}]).to_csv(path, index=False)
    with pytest.raises(ValueError, match="Colunas inválidas"):
        validate_reviews(path)


def test_review_schema_constant():
    assert REVIEW_COLUMNS == [
        "class_code",
        "date",
        "active_vegetation_endmembers",
        "candidate_ids",
        "reviewed_at",
    ]

