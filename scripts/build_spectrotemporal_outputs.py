from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
import numpy as np
import pandas as pd


CLASSES = ("02", "09", "10", "11")
PANEL_LABELS = dict(zip(CLASSES, "ABCD"))
CLASS_NAMES = {
    "02": "Floresta secundária",
    "09": "Silvicultura",
    "10": "Pastagem arbustiva/arbórea",
    "11": "Pastagem herbácea",
}
BANDS = ("B02", "B03", "B04", "B05", "B06", "B07", "B08", "B8A", "B11", "B12")
COMPONENTS = (
    ("low_frequency", "Baixa freq.", "#3B7D54"),
    ("seasonal", "Sazonal", "#2F68B0"),
    ("residual", "Resíduo", "#8E5A43"),
)
DOMAIN_SPANS = (
    ("VIS", 0, 2, "#59636B"),
    ("Red edge", 3, 5, "#B85042"),
    ("NIR", 6, 7, "#347C55"),
    ("SWIR", 8, 9, "#7A5C99"),
)


def repository_root(start: str | Path | None = None) -> Path:
    current = Path(start or Path.cwd()).resolve()
    for candidate in (current, *current.parents):
        if (candidate / "config" / "study.yaml").is_file() and (candidate / "data" / "analysis").is_dir():
            return candidate
    raise FileNotFoundError("Repository root not found.")


def configure_style() -> None:
    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 6.0,
            "axes.titlesize": 6.2,
            "axes.labelsize": 6.0,
            "xtick.labelsize": 6.0,
            "ytick.labelsize": 6.0,
            "legend.fontsize": 6.0,
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
            "axes.linewidth": 0.35,
        }
    )


def full_limits(values: np.ndarray, *, symmetric: bool) -> tuple[float, float]:
    finite = values[np.isfinite(values)]
    if finite.size == 0:
        return (-1.0, 1.0)
    if symmetric:
        ceiling = max(float(np.max(np.abs(finite))) * 1.035, 1e-4)
        return (-ceiling, ceiling)
    low = float(np.min(finite))
    high = float(np.max(finite))
    pad = max((high - low) * 0.055, 1e-4)
    return (low - pad, high + pad)


def build_figure(components: pd.DataFrame, output_dir: Path) -> None:
    components = components.copy()
    components["class_code"] = components["class_code"].astype(str).str.zfill(2)
    components["date"] = pd.to_datetime(components["date"])
    components = components[components["class_code"].isin(CLASSES)].copy()

    limits: dict[tuple[str, str], tuple[float, float]] = {}
    for band in BANDS:
        subset = components[components["band"].eq(band)]
        for component, _, _ in COMPONENTS:
            limits[(band, component)] = full_limits(
                subset[component].to_numpy(float),
                symmetric=component in {"seasonal", "residual"},
            )

    rows = len(CLASSES) * len(COMPONENTS)
    figure, axes = plt.subplots(
        rows,
        len(BANDS),
        figsize=(5.93, 8.15),
        squeeze=False,
        sharex=True,
        gridspec_kw={"hspace": 0.20, "wspace": 0.10},
    )
    first_date = components["date"].min()
    last_date = components["date"].max()
    first_edge_end = components[components["time_order"].eq(21)]["date"].min()
    last_edge_start = components[components["time_order"].eq(162)]["date"].min()

    for class_index, class_code in enumerate(CLASSES):
        for component_index, (component, label, color) in enumerate(COMPONENTS):
            row = class_index * len(COMPONENTS) + component_index
            for band_index, band in enumerate(BANDS):
                axis = axes[row, band_index]
                subset = components[
                    components["class_code"].eq(class_code) & components["band"].eq(band)
                ].sort_values("date")
                if component == "low_frequency":
                    axis.axvspan(first_date, first_edge_end, color="#E8E8E8", alpha=0.72, linewidth=0)
                    axis.axvspan(last_edge_start, last_date, color="#E8E8E8", alpha=0.72, linewidth=0)
                if component == "seasonal":
                    axis.set_facecolor("#F5F8FC")
                axis.plot(
                    subset["date"],
                    subset[component],
                    color=color,
                    linewidth=0.52 if component == "seasonal" else 0.43,
                    zorder=2,
                )
                imputed = subset[subset["imputed_for_stl"].astype(bool)]
                if component == "low_frequency" and band_index == 0 and not imputed.empty:
                    for missing_date in imputed["date"]:
                        axis.plot(
                            [missing_date, missing_date],
                            [0.93, 1.0],
                            transform=axis.get_xaxis_transform(),
                            color="#707070",
                            linewidth=0.34,
                            alpha=0.55,
                            zorder=3,
                        )
                if component in {"seasonal", "residual"}:
                    axis.axhline(0.0, color="#B8B8B8", linewidth=0.28, zorder=0)
                axis.set_ylim(*limits[(band, component)])
                axis.set_xlim(first_date, last_date)
                axis.set_yticks([])
                axis.tick_params(axis="x", length=1.5, width=0.35, pad=1.0)
                for spine in axis.spines.values():
                    spine.set_linewidth(0.32)
                    spine.set_color("#A0A0A0")

                if component_index == 0:
                    axis.set_title(band, pad=1.6, fontweight="bold")
                if band_index == 0:
                    axis.set_ylabel(label, color=color, fontweight="bold", labelpad=3.0)
                axis.set_xticks([])

    figure.subplots_adjust(left=0.105, right=0.995, bottom=0.035, top=0.945)

    for class_index, class_code in enumerate(CLASSES):
        top_row = class_index * len(COMPONENTS)
        bottom_row = top_row + len(COMPONENTS) - 1
        top_box = axes[top_row, 0].get_position()
        bottom_box = axes[bottom_row, 0].get_position()
        center_y = (top_box.y1 + bottom_box.y0) / 2.0
        figure.text(
            0.020,
            center_y,
            f"{PANEL_LABELS[class_code]}  |  Classe {class_code}\n{CLASS_NAMES[class_code]}",
            rotation=90,
            ha="center",
            va="center",
            fontsize=6.4,
            fontweight="bold",
        )
        if class_index < len(CLASSES) - 1:
            next_box = axes[bottom_row + 1, 0].get_position()
            # Keep the class divider above the following row's band titles.
            # The midpoint crossed those titles because Matplotlib draws them
            # into the inter-row gap.
            separator_y = next_box.y1 + 0.82 * (bottom_box.y0 - next_box.y1)
            figure.add_artist(
                Line2D(
                    [0.055, 0.995],
                    [separator_y, separator_y],
                    transform=figure.transFigure,
                    color="#8F8F8F",
                    linewidth=0.45,
                )
            )

    top_axes = [axes[0, index].get_position() for index in range(len(BANDS))]
    for label, first, last, color in DOMAIN_SPANS:
        x0 = top_axes[first].x0
        x1 = top_axes[last].x1
        center = (x0 + x1) / 2.0
        figure.text(center, 0.985, label, ha="center", va="center", color=color, fontweight="bold", fontsize=6.2)
        figure.add_artist(
            Line2D([x0, x1], [0.974, 0.974], transform=figure.transFigure, color=color, linewidth=1.0)
        )

    bottom_left = axes[-1, 0].get_position().x0
    bottom_right = axes[-1, -1].get_position().x1
    figure.text(bottom_left, 0.023, "2017", ha="left", va="center", fontsize=6.0)
    figure.text((bottom_left + bottom_right) / 2.0, 0.023, "2021", ha="center", va="center", fontsize=6.0)
    figure.text(bottom_right, 0.023, "2024", ha="right", va="center", fontsize=6.0)
    figure.text(0.55, 0.009, "Tempo", ha="center", va="center", fontsize=6.2)
    output_dir.mkdir(parents=True, exist_ok=True)
    figure.savefig(output_dir / "figura_01_decomposicao_espectrotemporal.pdf", bbox_inches="tight", pad_inches=0.015)
    figure.savefig(output_dir / "figura_01_decomposicao_espectrotemporal.png", dpi=400, bbox_inches="tight", pad_inches=0.015)
    plt.close(figure)


def format_strength(value: float) -> str:
    return f"{value:.3f}".replace(".", ",")


def build_reported_metrics(domains: pd.DataFrame, output_dir: Path) -> pd.DataFrame:
    """Escreve as forças sazonais relatadas no texto do artigo, no mesmo arredondamento."""
    primary = domains[domains["variant"].eq("primary")].copy()
    strength = primary.pivot(index="class_code", columns="domain", values="seasonal_strength_median")
    records = []
    for class_code in CLASSES:
        class_rows = primary.loc[primary["class_code"].eq(class_code)]
        record = {
            "class_code": class_code,
            "class_name": CLASS_NAMES[class_code],
            "observed_dates": int(class_rows["observed_dates"].iloc[0]),
            "total_dates": 184,
        }
        for domain, label in (("VIS", "VIS"), ("RED_EDGE", "red_edge"), ("NIR", "NIR"), ("SWIR", "SWIR")):
            value = float(strength.loc[class_code, domain])
            record[f"F_S_{label}"] = round(value, 3)
            record[f"F_S_{label}_texto"] = format_strength(value)
        records.append(record)

    frame = pd.DataFrame(records)
    output_dir.mkdir(parents=True, exist_ok=True)
    frame.to_csv(output_dir / "metricas_reportadas_no_texto.csv", index=False, encoding="utf-8")
    return frame


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build the WORCAP spectrotemporal figure and the metrics stated in the article."
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    configure_style()
    root = repository_root()
    analysis = root / "data" / "analysis" / "spectrotemporal"
    components = pd.read_parquet(analysis / "spectrotemporal_components.parquet")
    domains = pd.read_parquet(analysis / "spectrotemporal_domain_metrics.parquet")
    build_figure(components, args.output_dir)
    build_reported_metrics(domains, args.output_dir)
    print(f"Figure and reported metrics written to {args.output_dir.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
