from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class PPIResult:
    indices: np.ndarray
    spectra: np.ndarray
    scores: np.ndarray
    projections: int
    seed: int
    projection_batch: int
    candidate_pool_size: int
    status: str


def spectral_angle_degrees(a: np.ndarray, b: np.ndarray) -> float:
    a = np.asarray(a, dtype=np.float64)
    b = np.asarray(b, dtype=np.float64)
    denominator = float(np.linalg.norm(a) * np.linalg.norm(b))
    if denominator <= 0:
        return float("nan")
    cosine = float(np.clip(np.dot(a, b) / denominator, -1.0, 1.0))
    return float(np.degrees(np.arccos(cosine)))


def select_distinct_candidates(
    pixels: np.ndarray,
    scores: np.ndarray,
    count: int,
    master_order: np.ndarray,
    minimum_sam_deg: float,
) -> tuple[np.ndarray, int]:
    pixels = np.asarray(pixels, dtype=np.float64)
    scores = np.asarray(scores)
    master_order = np.asarray(master_order, dtype=np.int64)
    pool = np.flatnonzero(scores > 0)
    pool = pool[np.lexsort((master_order[pool], -scores[pool]))]
    selected: list[int] = []
    for index in pool:
        candidate = int(index)
        angles = [spectral_angle_degrees(pixels[candidate], pixels[other]) for other in selected]
        if any(np.isfinite(angle) and angle < minimum_sam_deg for angle in angles):
            continue
        selected.append(candidate)
        if len(selected) == int(count):
            break
    return np.asarray(selected, dtype=np.int64), int(len(pool))


def extract_ppi(
    pixels: np.ndarray,
    count: int,
    projections: int,
    seed: int,
    *,
    projection_batch: int = 32,
    duplicate_sam_deg: float = 2.0,
    master_order: np.ndarray | None = None,
    memory_limit_mb: int = 6144,
) -> PPIResult:
    values = np.asarray(pixels, dtype=np.float64)
    if values.ndim != 2 or values.shape[0] < int(count) or values.shape[1] < 2:
        raise ValueError("O PPI requer uma matriz pixels × bandas com linhas suficientes.")
    finite = np.all(np.isfinite(values), axis=1)
    values = values[finite]
    if master_order is None:
        master_order = np.arange(1, len(values) + 1, dtype=np.int64)
    else:
        master_order = np.asarray(master_order, dtype=np.int64)[finite]

    centered = values - np.mean(values, axis=0, keepdims=True)
    scores = np.zeros(len(values), dtype=np.int32)
    generator = np.random.default_rng(int(seed))

    limit = int(memory_limit_mb) * 1024 * 1024
    fixed = values.nbytes + centered.nbytes + scores.nbytes + master_order.nbytes
    batches = list(dict.fromkeys([int(projection_batch), 16, 8, 4, 1]))
    effective_batch = next(
        (
            batch
            for batch in batches
            if batch <= int(projection_batch)
            and fixed + len(values) * batch * 8 + batch * values.shape[1] * 8 <= limit
        ),
        None,
    )
    if effective_batch is None:
        raise MemoryError("O limite de memória é insuficiente mesmo para um lote de uma projeção.")

    remaining = int(projections)
    while remaining:
        batch = min(effective_batch, remaining)
        directions = generator.normal(size=(batch, values.shape[1]))
        norms = np.linalg.norm(directions, axis=1, keepdims=True)
        directions = np.divide(directions, norms, out=np.zeros_like(directions), where=norms > 0)
        projected = centered @ directions.T
        np.add.at(scores, np.argmax(projected, axis=0), 1)
        np.add.at(scores, np.argmin(projected, axis=0), 1)
        remaining -= batch

    indices, pool_size = select_distinct_candidates(
        values,
        scores,
        count,
        master_order,
        duplicate_sam_deg,
    )
    status = "OK" if len(indices) == int(count) else "FEWER_THAN_FOUR_DISTINCT_CANDIDATES"
    return PPIResult(
        indices=indices,
        spectra=values[indices],
        scores=scores[indices],
        projections=int(projections),
        seed=int(seed),
        projection_batch=int(effective_batch),
        candidate_pool_size=pool_size,
        status=status,
    )

