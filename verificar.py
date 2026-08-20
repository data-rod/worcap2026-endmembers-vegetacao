"""Confere, em um comando, se este repositório reproduz os números do artigo.

    python verificar.py

Não requer rede. Percorre a cadeia publicada, recalcula as métricas a partir dos
componentes STL brutos e compara cada resultado com o que o artigo afirma.
Termina com código de saída 0 se tudo confere e 1 caso contrário.
"""

from __future__ import annotations

import hashlib
import importlib.util
import sys
from pathlib import Path

import numpy as np
import pandas as pd

CLASSES = ("02", "09", "10", "11")
CLASS_NAMES = {
    "02": "Vegetação Secundária",
    "09": "Silvicultura",
    "10": "Pastagem Arbustiva/Arbórea",
    "11": "Pastagem Herbácea",
}
DOMAINS = {
    "VIS": ["B02", "B03", "B04"],
    "RED_EDGE": ["B05", "B06", "B07"],
    "NIR": ["B08", "B8A"],
    "SWIR": ["B11", "B12"],
}

# Valores exatamente como publicados no artigo.
DATAS_ARTIGO = {"02": 160, "09": 173, "10": 165, "11": 160}
FS_ARTIGO = {
    "02": [0.046, 0.435, 0.494, 0.143],
    "09": [0.175, 0.331, 0.350, 0.318],
    "10": [0.242, 0.481, 0.439, 0.343],
    "11": [0.295, 0.551, 0.583, 0.010],
}
TOTAL_COMBINACOES = 736
TOTAL_RETIDAS = 658
DISTANCIA_KM = (222, 774)

ROOT = Path(__file__).resolve().parent
ANALISE = ROOT / "data" / "analysis" / "spectrotemporal"
SAIDA = ROOT / "outputs" / "verificacao"

resultados: list[tuple[str, bool, str]] = []


def registrar(nome: str, ok: bool, detalhe: str = "") -> None:
    resultados.append((nome, ok, detalhe))
    print(f"  [{'OK   ' if ok else 'FALHA'}] {nome}" + (f" — {detalhe}" if detalhe else ""))


def sha256(caminho: Path) -> str:
    digest = hashlib.sha256()
    with open(caminho, "rb") as arquivo:
        for bloco in iter(lambda: arquivo.read(1 << 20), b""):
            digest.update(bloco)
    return digest.hexdigest()


def exigir_pyarrow() -> None:
    """Os Parquet foram escritos com pyarrow 22; versões anteriores não os leem."""
    import pyarrow

    if int(pyarrow.__version__.split(".")[0]) < 22:
        raise SystemExit(
            f"pyarrow {pyarrow.__version__} não lê os arquivos deste repositório.\n"
            "Eles foram escritos com pyarrow 22.0.0, versão fixada em requirements.txt.\n"
            "Instale as dependências declaradas antes de continuar:\n"
            "    python -m pip install -r requirements.txt"
        )


def ler(caminho: Path) -> pd.DataFrame:
    quadro = pd.read_parquet(caminho)
    if "class_code" in quadro.columns:
        quadro["class_code"] = quadro["class_code"].astype(str).str.zfill(2)
    return quadro


def forca_sazonal(sazonal: np.ndarray, residuo: np.ndarray) -> float:
    denominador = float(np.var(sazonal + residuo, ddof=1))
    if denominador <= 1e-15:
        return float("nan")
    return float(max(0.0, 1.0 - float(np.var(residuo, ddof=1)) / denominador))


def main() -> int:
    print(__doc__.splitlines()[0])
    print("=" * 72)
    exigir_pyarrow()

    print("\n1. Integridade dos arquivos publicados")
    manifesto = pd.read_csv(ANALISE / "integrity_sha256.csv")
    ruins = [
        registro.file
        for registro in manifesto.itertuples(index=False)
        if not (ANALISE / registro.file).is_file() or sha256(ANALISE / registro.file) != registro.sha256
    ]
    registrar(
        f"{len(manifesto)} arquivos de análise conferem com o manifesto SHA-256",
        not ruins,
        "" if not ruins else f"divergentes: {ruins}",
    )

    print("\n2. Completude — o artigo afirma 658 de 736 combinações classe–data")
    metricas = ler(ANALISE / "spectrotemporal_domain_metrics.parquet")
    primaria = metricas[metricas["variant"].eq("primary")]
    datas = {
        codigo: int(primaria.loc[primaria["class_code"].eq(codigo), "observed_dates"].iloc[0])
        for codigo in CLASSES
    }
    registrar(f"combinações classe–data = {len(CLASSES) * 184}", len(CLASSES) * 184 == TOTAL_COMBINACOES)
    registrar(f"combinações com extremo retido = {sum(datas.values())}", sum(datas.values()) == TOTAL_RETIDAS)
    for codigo in CLASSES:
        registrar(
            f"classe {codigo} ({CLASS_NAMES[codigo]}): {datas[codigo]} datas",
            datas[codigo] == DATAS_ARTIGO[codigo],
            "" if datas[codigo] == DATAS_ARTIGO[codigo] else f"artigo: {DATAS_ARTIGO[codigo]}",
        )

    print("\n3. Força sazonal — rederivada dos componentes STL, não relida das métricas")
    componentes = ler(ANALISE / "spectrotemporal_components.parquet")
    observados = componentes[~componentes["imputed_for_stl"].astype(bool)]
    por_banda = [
        {
            "class_code": codigo,
            "band": banda,
            "F_S": forca_sazonal(
                grupo["seasonal"].to_numpy(dtype=float), grupo["residual"].to_numpy(dtype=float)
            ),
        }
        for (codigo, banda), grupo in observados.groupby(["class_code", "band"])
    ]
    por_banda = pd.DataFrame(por_banda)

    for codigo in CLASSES:
        obtidos, esperados = [], FS_ARTIGO[codigo]
        for dominio, bandas in DOMAINS.items():
            recorte = por_banda[por_banda["class_code"].eq(codigo) & por_banda["band"].isin(bandas)]
            obtidos.append(round(float(recorte["F_S"].median()), 3))
        registrar(
            f"classe {codigo}: F_S = {', '.join(f'{v:.3f}' for v in obtidos)}",
            obtidos == esperados,
            "" if obtidos == esperados else f"artigo: {esperados}",
        )

    print("\n4. Rotatividade espacial — o artigo afirma distâncias medianas de 222 a 774 km")
    rotatividade = ler(ANALISE / "representative_turnover.parquet")
    rotatividade = rotatividade[rotatividade["class_code"].isin(CLASSES)]
    faixa = (
        round(float(rotatividade["median_adjacent_distance_km"].min())),
        round(float(rotatividade["median_adjacent_distance_km"].max())),
    )
    registrar(f"faixa observada = {faixa[0]} a {faixa[1]} km", faixa == DISTANCIA_KM)

    print("\n5. Figura 1 — regerada pelo mesmo código que produziu o artigo")
    try:
        especificacao = importlib.util.spec_from_file_location(
            "build_spectrotemporal_outputs", ROOT / "scripts" / "build_spectrotemporal_outputs.py"
        )
        construtor = importlib.util.module_from_spec(especificacao)
        especificacao.loader.exec_module(construtor)
        SAIDA.mkdir(parents=True, exist_ok=True)
        construtor.configure_style()
        construtor.build_figure(componentes, SAIDA)
        construtor.build_reported_metrics(metricas, SAIDA)
        gerados = sorted(p.name for p in SAIDA.iterdir())
        registrar(f"gerada em outputs/verificacao/ ({len(gerados)} arquivos)", True)
    except Exception as erro:  # pragma: no cover - depende do ambiente gráfico
        registrar("geração da Figura 1", False, f"{type(erro).__name__}: {erro}")

    print("\n" + "=" * 72)
    falhas = [nome for nome, ok, _ in resultados if not ok]
    if falhas:
        print(f"RESULTADO: {len(falhas)} de {len(resultados)} verificações falharam")
        for nome in falhas:
            print(f"  - {nome}")
        return 1
    print(f"RESULTADO: as {len(resultados)} verificações conferem com o artigo")
    print("A Figura 1 regerada está em outputs/verificacao/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
