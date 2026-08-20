from __future__ import annotations

import argparse
import json
from pathlib import Path

from .panel import build_panels
from .review import merge_reviews, validate_all, validate_reviews
from .workflow import compare_candidates, run_ppi, verify_release
from .wtss import fetch_wtss


def _classes(value: str | None) -> list[str] | None:
    return [part.strip().zfill(2) for part in value.split(",") if part.strip()] if value else None


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description="Fluxo reproduzível de endmembers de vegetação.")
    root.add_argument("--root", type=Path, help="Raiz do repositório; detectada automaticamente por padrão.")
    commands = root.add_subparsers(dest="command", required=True)

    commands.add_parser("verify", help="Verificar estrutura, contagens e checksums.")

    ppi = commands.add_parser("run-ppi", help="Reproduzir candidatos PPI a partir dos Parquets WTSS publicados.")
    ppi.add_argument("--classes", help="Códigos separados por vírgula.")
    ppi.add_argument("--output", default="outputs/reproduced")

    compare = commands.add_parser("compare-candidates", help="Comparar candidatos reproduzidos com a versão publicada.")
    compare.add_argument("reproduced")
    compare.add_argument("reference")

    panels = commands.add_parser("build-panels", help="Gerar painéis HTML offline.")
    panels.add_argument("--classes", help="Códigos separados por vírgula.")
    panels.add_argument("--candidates", default="data/candidates")
    panels.add_argument("--output", default="outputs/reproduced/panels")

    wtss = commands.add_parser("fetch-wtss", help="Consultar novamente as séries WTSS.")
    wtss.add_argument("--classes", help="Códigos separados por vírgula.")
    wtss.add_argument("--output", default="outputs/wtss_refresh")
    wtss.add_argument("--force", action="store_true")

    validate = commands.add_parser("validate-reviews", help="Validar um CSV exportado pelo painel.")
    validate.add_argument("review_csv")
    commands.add_parser("validate-all-reviews", help="Validar todos os CSVs em reviews/incoming.")

    merge = commands.add_parser("merge-reviews", help="Fundir avaliações válidas sem duplicar classe × data.")
    merge.add_argument("review_csv", nargs="*")
    merge.add_argument("--output", default="reviews/validated/reviews_consolidadas.parquet")
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if args.command == "verify":
        result = verify_release(args.root)
    elif args.command == "run-ppi":
        result = run_ppi(args.root, classes=_classes(args.classes), output=args.output)
    elif args.command == "compare-candidates":
        result = compare_candidates(args.reproduced, args.reference, args.root)
    elif args.command == "build-panels":
        result = build_panels(args.root, classes=_classes(args.classes), candidates=args.candidates, output=args.output)
    elif args.command == "fetch-wtss":
        result = fetch_wtss(args.root, classes=_classes(args.classes), output=args.output, force=args.force)
    elif args.command == "validate-reviews":
        result = validate_reviews(args.review_csv, args.root)
    elif args.command == "validate-all-reviews":
        result = validate_all(args.root)
    elif args.command == "merge-reviews":
        result = merge_reviews(args.review_csv or None, output=args.output, root=args.root)
    else:
        raise AssertionError(args.command)
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0

