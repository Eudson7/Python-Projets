"""CLI de contingência — mesma coisa que a interface faz, só que no terminal."""

from __future__ import annotations

import argparse
import sys

from . import bigfiles, scan
from .clean import clean_targets
from .targets import TARGETS, default_selection, get_target


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="win_janitor",
        description="Limpa lixo do Windows e aponta arquivos grandes.",
    )
    sub = parser.add_subparsers(dest="comando")

    p_scan = sub.add_parser("scan", help="mostra quanto lixo existe (nada é apagado)")
    p_scan.add_argument("--all", action="store_true", help="inclui alvos que precisam de admin")

    p_clean = sub.add_parser("clean", help="limpa os alvos selecionados")
    p_clean.add_argument("--yes", action="store_true", help="não pede confirmação")
    p_clean.add_argument("--dry-run", action="store_true", help="só simula, não apaga")
    p_clean.add_argument("--all", action="store_true", help="inclui alvos que precisam de admin")

    p_big = sub.add_parser("bigfiles", help="lista arquivos grandes")
    p_big.add_argument("--root", action="append", help="pasta/drive para varrer (repetível)")
    p_big.add_argument("--min-mb", type=float, default=bigfiles.DEFAULT_MIN_MB)
    p_big.add_argument("--limit", type=int, default=50)
    return parser


def _selected(include_admin: bool) -> list[str]:
    if include_admin:
        return [t.id for t in TARGETS]
    return default_selection()


def cmd_scan(args: argparse.Namespace) -> int:
    results = scan.scan_all(only=_selected(args.all))
    print("\n  LIXO ENCONTRADO")
    print("  " + "-" * 56)
    for result in results:
        size = scan.human_size(result.size) if result.files else "-"
        print(f"  {result.target.label:<38} {size:>10}")
    total = scan.total_size(results)
    print("  " + "-" * 56)
    print(f"  {'TOTAL recuperável':<38} {scan.human_size(total):>10}\n")
    return 0


def cmd_clean(args: argparse.Namespace) -> int:
    chosen = [get_target(tid) for tid in _selected(args.all)]
    results = scan.scan_all(only=[t.id for t in chosen])
    total = scan.total_size(results)
    print(f"\n  Seria liberado: {scan.human_size(total)} em {len(chosen)} categorias.")

    if args.dry_run:
        print("  Modo simulação: nada foi apagado.\n")
        return 0
    if not args.yes:
        answer = input("  Confirma a limpeza? [s/N] ").strip().lower()
        if answer not in ("s", "sim", "y", "yes"):
            print("  Cancelado. Nada foi apagado.\n")
            return 0

    outcome = clean_targets(chosen, dry_run=False)
    print(
        f"\n  Apagados: {outcome.deleted} arquivos · "
        f"liberado {scan.human_size(outcome.freed)} · "
        f"pulados (em uso): {outcome.kept}"
    )
    if outcome.errors:
        print(f"  Avisos: {len(outcome.errors)}")
        for error in outcome.errors[:5]:
            print(f"    - {error}")
    print("  Log gravado na pasta de logs do programa.\n")
    return 0


def cmd_bigfiles(args: argparse.Namespace) -> int:
    roots = args.root or bigfiles.discover_roots()
    found = bigfiles.scan_big_files(
        roots,
        min_size=int(args.min_mb * 1024 * 1024),
        limit=args.limit,
    )
    if not found:
        print(f"\n  Nenhum arquivo acima de {args.min_mb:g} MB nessas pastas.\n")
        return 0
    print(f"\n  {len(found)} ARQUIVOS GRANDES ({args.min_mb} MB ou mais)\n")
    print(f"  {'TIPO':<16}{'TAMANHO':>10}  {'CRIADO':<12} NOME")
    print("  " + "-" * 72)
    for item in found:
        print(
            f"  {item.kind:<16}{scan.human_size(item.size):>10}  "
            f"{item.created_str():<12} {item.name}"
        )
        print(f"  {'':<16}{'':>10}  {'':<12} {item.folder}\n")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.comando == "clean":
        return cmd_clean(args)
    if args.comando == "bigfiles":
        return cmd_bigfiles(args)
    return cmd_scan(args)


if __name__ == "__main__":
    sys.exit(main())
