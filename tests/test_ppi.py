import numpy as np

from worcap_endmembers.ppi import extract_ppi, spectral_angle_degrees


def test_spectral_angle_identity():
    assert spectral_angle_degrees(np.array([1.0, 2.0]), np.array([1.0, 2.0])) < 1e-5


def test_ppi_is_reproducible():
    pixels = np.random.default_rng(7).uniform(size=(100, 10))
    first = extract_ppi(pixels, 4, 500, 13, master_order=np.arange(100))
    second = extract_ppi(pixels, 4, 500, 13, master_order=np.arange(100))
    assert np.array_equal(first.indices, second.indices)
    assert np.array_equal(first.scores, second.scores)
