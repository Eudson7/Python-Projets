"""Remoção de lixo com registro de tudo que aconteceu.

Política: falhar nunca pode ser pior que não limpar. Arquivo em uso,
sem permissão ou já sumido são contados e pulados — a limpeza continua.
"""

from __future__ import annotations

import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from . import report
from .scan import iter_target_files
from .targets import Target


@dataclass
class CleanResult:
    deleted: int = 0
    freed: int = 0
    kept: int = 0  # travados, sem permissão ou já ausentes
    errors: list[str] = field(default_factory=list)
    by_target: dict[str, tuple[int, int]] = field(default_factory=dict)
    dry_run: bool = False

    @property
    def per_target(self) -> dict[str, tuple[int, int]]:
        return self.by_target


def remove_file(path: Path) -> str | None:
    """Apaga um arquivo. Devolve ``None`` no sucesso ou o motivo da recusa."""
    try:
        path.unlink()
        return None
    except PermissionError:
        return "em uso"
    except FileNotFoundError:
        return "já não existe"
    except OSError as exc:
        return exc.strerror or str(exc)


def send_to_recycle_bin(paths: list[Path]) -> str | None:
    """Envia arquivos para a lixeira do Windows (só Windows).

    Devolve ``None`` em sucesso ou o motivo da falha. Nunca apaga por conta
    própria: se a lixeira recusar, o arquivo fica onde está.
    """
    if sys.platform != "win32" or not paths:
        return "lixeira disponível apenas no Windows"
    import ctypes
    from ctypes import wintypes

    class SHFILEOPSTRUCTW(ctypes.Structure):
        _fields_ = [
            ("hwnd", wintypes.HWND),
            ("wFunc", ctypes.c_uint),
            ("pFrom", wintypes.LPCWSTR),
            ("pTo", wintypes.LPCWSTR),
            ("fFlags", ctypes.c_ushort),
            ("fAnyOperationsAborted", wintypes.BOOL),
            ("hNameMappings", ctypes.c_void_p),
            ("lpszProgressTitle", wintypes.LPCWSTR),
        ]

    FO_DELETE = 3
    FOF_ALLOWUNDO = 0x40  # leva para a lixeira
    FOF_NOCONFIRMATION = 0x10
    FOF_SILENT = 0x4

    info = SHFILEOPSTRUCTW()
    info.wFunc = FO_DELETE
    info.pFrom = "\0".join(str(p) for p in paths) + "\0\0"
    info.fFlags = FOF_ALLOWUNDO | FOF_NOCONFIRMATION | FOF_SILENT
    result = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(info))
    if result:
        return f"lixeira recusou a operação (código {result})"
    if info.fAnyOperationsAborted:
        return "operação cancelada"
    return None


def prune_empty_dirs(target: Target, removed: int = 0) -> int:
    """Remove subpastas que ficaram vazias (a raiz do alvo permanece)."""
    from . import safety

    for raw in target.paths:
        pattern = safety.validate_pattern(raw)
        if pattern is None or safety.has_wildcard(pattern):
            continue
        root = Path(pattern)
        if not root.is_dir():
            continue
        for current, _dirs, files in os.walk(root, topdown=False):
            if os.path.normcase(os.path.abspath(current)) == os.path.normcase(
                os.path.abspath(str(root))
            ):
                continue
            if files:
                continue
            try:
                os.rmdir(current)
                removed += 1
            except OSError:
                continue
    return removed


def clean_target(
    target: Target,
    dry_run: bool = False,
    on_progress: Callable[[int, int], None] | None = None,
) -> CleanResult:
    """Limpa um alvo. Com ``dry_run`` só contabiliza o que seria apagado."""
    result = CleanResult(dry_run=dry_run)
    deleted = freed = kept = 0
    scanned = 0

    for path in iter_target_files(target):
        scanned += 1
        if on_progress and scanned % 100 == 0:
            on_progress(scanned, deleted)
        if dry_run:
            try:
                freed += path.stat().st_size
            except OSError:
                pass
            deleted += 1
            continue
        try:
            size = path.stat().st_size
        except OSError:
            size = 0
        error = remove_file(path)
        if error is None:
            deleted += 1
            freed += size
        elif error in ("em uso", "já não existe"):
            kept += 1
        else:
            kept += 1
            result.errors.append(f"{path}: {error}")

    if not dry_run and deleted:
        prune_empty_dirs(target)

    result.deleted, result.freed, result.kept = deleted, freed, kept
    result.by_target[target.id] = (deleted, freed)
    return result


def clean_targets(
    targets: list[Target],
    dry_run: bool = False,
    on_progress: Callable[[Target, int, int], None] | None = None,
) -> CleanResult:
    """Limpa vários alvos e consolida o resultado em um único objeto."""
    total = CleanResult(dry_run=dry_run)
    for target in targets:
        partial = clean_target(
            target,
            dry_run=dry_run,
            on_progress=(
                (lambda c, d: on_progress(target, c, d)) if on_progress else None
            ),
        )
        total.deleted += partial.deleted
        total.freed += partial.freed
        total.kept += partial.kept
        total.errors.extend(partial.errors)
        total.by_target.update(partial.by_target)

    entry = {
        "quando": time.strftime("%Y-%m-%d %H:%M:%S"),
        "modo": "simulacao" if dry_run else "limpeza",
        "alvos": [
            {
                "id": t.id,
                "nome": t.label,
                "apagados": partial_count(t, total)[0],
                "liberado": partial_count(t, total)[1],
            }
            for t in targets
        ],
        "total_apagados": total.deleted,
        "total_liberado": total.freed,
        "pulados": total.kept,
        "erros": total.errors,
    }
    report.write_log("limpeza", entry)
    return total


def partial_count(target: Target, result: CleanResult) -> tuple[int, int]:
    return result.by_target.get(target.id, (0, 0))
