from __future__ import annotations

import json
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from pathlib import Path
from typing import Any

import pandas as pd
import requests

from .config import load_config, select_classes, stable_hash


def _payload(config: dict[str, Any], point: pd.Series) -> dict[str, Any]:
    return {
        "attributes": [*config["bands"], *config["qa_bands"]],
        "start_date": config["period"]["start"],
        "end_date": config["period"]["end"],
        "geom": {"type": "Point", "coordinates": [float(point["longitude"]), float(point["latitude"])]},
        "applyAttributeScale": bool(config["wtss"]["apply_attribute_scale"]),
        "pixelCollisionType": "center",
        "masked": bool(config["wtss"]["masked"]),
    }


def _request(config: dict[str, Any], point: pd.Series, cache: Path, force: bool) -> tuple[dict[str, Any], bool]:
    payload = _payload(config, point)
    query_hash = stable_hash(payload)
    cache_path = cache / f"{point['point_id']}_{query_hash[:16]}.json"
    if cache_path.exists() and not force:
        return json.loads(cache_path.read_text(encoding="utf-8")), True
    url = config["wtss_url"].rstrip("/") + f"/{config['collection_id']}/timeseries"
    error: Exception | None = None
    for attempt in range(1, int(config["wtss"]["retries"]) + 1):
        try:
            response = requests.post(url, json=payload, timeout=float(config["wtss"]["timeout_seconds"]))
            response.raise_for_status()
            result = response.json()
            if not result.get("results"):
                raise ValueError("O WTSS retornou uma resposta sem resultados.")
            temporary = cache_path.with_suffix(".tmp")
            temporary.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
            temporary.replace(cache_path)
            return result, False
        except Exception as exc:
            error = exc
            if attempt < int(config["wtss"]["retries"]):
                time.sleep(float(config["wtss"]["retry_delay_seconds"]) * (2 ** (attempt - 1)))
    raise RuntimeError(f"Falha WTSS após {config['wtss']['retries']} tentativas: {error}")


def _parse(result: dict[str, Any], point: pd.Series, config: dict[str, Any]) -> pd.DataFrame:
    payload = result["results"][0]
    series = payload.get("time_series") or payload.get("timeseries")
    dates = payload.get("timeline") or payload.get("dates")
    attributes = payload.get("attributes") or [*config["bands"], *config["qa_bands"]]
    rows: list[dict[str, Any]] = []
    if isinstance(series, dict):
        dates = series.get("timeline") or dates
        values = series.get("values")
        if not dates or not isinstance(values, dict):
            raise ValueError("Resposta WTSS sem timeline e valores.")
        for index, date in enumerate(dates):
            rows.append({"date": str(date)[:10], **{name: values.get(name, [None] * len(dates))[index] for name in attributes}})
    elif isinstance(series, list) and series and isinstance(series[0], dict):
        for item in series:
            values = item.get("values", item)
            date = item.get("date") or item.get("datetime")
            rows.append({"date": str(date)[:10], **{name: values.get(name) for name in attributes}})
    elif isinstance(series, list) and dates and len(series) == len(dates):
        for date, values in zip(dates, series):
            rows.append({"date": str(date)[:10], **dict(zip(attributes, values))})
    elif isinstance(series, list) and series and isinstance(series[0], list) and len(series[0]) == len(attributes) + 1:
        for values in series:
            rows.append({"date": str(values[0])[:10], **dict(zip(attributes, values[1:]))})
    else:
        raise ValueError("Estrutura de série temporal WTSS não reconhecida.")

    frame = pd.DataFrame(rows)
    frame = frame[
        frame["date"].between(config["period"]["start"], config["period"]["end"])
    ].copy()
    frame.insert(0, "point_id", point["point_id"])
    frame.insert(1, "class_code", str(point["class_code"]).zfill(2))
    frame.insert(2, "class_name", point["class_name"])
    frame["longitude"] = float(point["longitude"])
    frame["latitude"] = float(point["latitude"])
    frame["systematic_order"] = int(point["systematic_order"])
    for column in [*config["bands"], *config["qa_bands"], "longitude", "latitude"]:
        frame[column] = pd.to_numeric(frame[column], errors="coerce").astype("float64")
    return frame[
        [
            "point_id",
            "class_code",
            "class_name",
            "date",
            *config["bands"],
            *config["qa_bands"],
            "longitude",
            "latitude",
            "systematic_order",
        ]
    ]


def fetch_wtss(
    root: str | Path | None = None,
    *,
    classes: list[str] | None = None,
    output: str | Path = "outputs/wtss_refresh",
    force: bool = False,
) -> list[dict[str, Any]]:
    repository, config = load_config(root)
    selected = select_classes(config, classes)
    output_root = Path(output)
    if not output_root.is_absolute():
        output_root = repository / output_root
    output_root.mkdir(parents=True, exist_ok=True)
    cache = output_root / "cache"
    cache.mkdir(parents=True, exist_ok=True)
    points = pd.read_parquet(repository / "data" / "points" / "points.parquet")
    points["class_code"] = points["class_code"].astype(str).str.zfill(2)
    summaries: list[dict[str, Any]] = []

    for code in selected:
        class_points = points[points["class_code"].eq(code)].sort_values("systematic_order")
        rows: list[pd.DataFrame] = []
        failures: list[dict[str, str]] = []
        iterator = iter(class_points.iterrows())
        pending: dict[Any, pd.Series] = {}
        with ThreadPoolExecutor(max_workers=int(config["wtss"]["workers"])) as executor:
            for _ in range(int(config["wtss"]["workers"]) * 4):
                try:
                    _, point = next(iterator)
                except StopIteration:
                    break
                pending[executor.submit(_request, config, point, cache, force)] = point
            while pending:
                done, _ = wait(pending, return_when=FIRST_COMPLETED)
                for future in done:
                    point = pending.pop(future)
                    try:
                        result, _ = future.result()
                        parsed = _parse(result, point, config)
                        if len(parsed) != int(config["period"]["expected_dates"]):
                            raise ValueError(f"Foram recebidas {len(parsed)} datas.")
                        rows.append(parsed)
                    except Exception as exc:
                        failures.append({"point_id": str(point["point_id"]), "error": str(exc)})
                    try:
                        _, next_point = next(iterator)
                    except StopIteration:
                        continue
                    pending[executor.submit(_request, config, next_point, cache, force)] = next_point
        if failures:
            (output_root / f"failures_class_{code}.json").write_text(json.dumps(failures, ensure_ascii=False, indent=2), encoding="utf-8")
            raise RuntimeError(f"Classe {code}: {len(failures)} requisições falharam.")
        frame = pd.concat(rows, ignore_index=True).sort_values(["systematic_order", "date"])
        target = output_root / f"wtss_class_{code}.parquet"
        frame.to_parquet(target, index=False)
        summaries.append({"class_code": code, "points": len(class_points), "rows": len(frame), "output": str(target)})
    return summaries

