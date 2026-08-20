from worcap_endmembers.workflow import verify_release


def test_release_structure():
    result = verify_release()
    assert result["points"] == 5000
    assert set(result["classes"]) == {"01", "02", "09", "10", "11"}

