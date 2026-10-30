"""Varredura de lixo — somente leitura, nada é apagado aqui."""

from __future__ import annotations

import glob
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterator

from . import safety
from .targets import Target


@dataclass
class TargetResult:
    """Quanto lixo um alvo tem hoje."""

    target: Target
    files: int = 0
    size: int = 0
    errors: int = 0

    @property
    def usable(self) -> bool:
        return self.files > 0


def _cutoff(target: Target) -> float | None:
    if target.min_age_days <= 0:
        return None
    return time.time() - target.min_age_days * 86400


def _walk(root: Path, cutoff: float | None) -> Iterator[Path]:
    """Percorre ``root`` sem seguir junction/symlink de pasta.

    Pastas sem permissão e arquivos travados não derrubam a varredura.
    """
    stack = [root]
    while stack:
        current = stack.pop()
        try:
            with os.scandir(current) as entries:
                for entry in entries:
                    try:
                        if entry.is_dir(follow_symlinks=False):
                            if safety.is_link(entry.path):
                                continue  # não sai da pasta autorizada
                            stack.append(Path(entry.path))
                            continue
                        if cutoff is None:
                            yield Path(entry.path)
                        elif entry.stat(follow_symlinks=False).st_mtime < cutoff:
                            yield Path(entry.path)
                    except OSError:
                        continue
        except OSError:
            continue


def iter_target_files(target: Target) -> Iterator[Path]:
    """Todos os arquivos que este alvo autoriza a apagar."""
    cutoff = _cutoff(target)
    for raw in target.paths:
        pattern = safety.validate_pattern(raw)
        if pattern is None:
            continue
        if safety.has_wildcard(pattern):
            for match in sorted(glob.iglob(pattern)):
                if not safety.matches(pattern, match) or safety.is_prohibited(match):
                    continue
                path = Path(match)
                if path.is_dir() and not safety.is_link(path):
                    yield from _walk(path, cutoff)
                elif path.is_file():
                    if cutoff is None or _mtime(path) < cutoff:
                        yield path
        else:
            base = Path(pattern)
            if safety.is_prohibited(base) or safety.is_link(base):
                continue
            if base.is_file():
                if cutoff is None or _mtime(base) < cutoff:
                    yield base
            elif base.is_dir():
                yield from _walk(base, cutoff)


def _mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


def scan_target(target: Target) -> TargetResult:
    result = TargetResult(target=target)
    for path in iter_target_files(target):
        try:
            result.size += path.stat().st_size
            result.files += 1
        except OSError:
            result.errors += 1
    return result


def scan_all(
    targets: tuple[Target, ...] | list[Target] | None = None,
    only: list[str] | None = None,
    progress: Callable[[TargetResult], None] | None = None,
) -> list[TargetResult]:
    """Varre todos os alvos (ou só os ids em ``only``) e devolve o resumo."""
    from .targets import TARGETS

    chosen = [t for t in (targets or TARGETS) if only is None or t.id in only]
    results: list[TargetResult] = []
    for target in chosen:
        result = scan_target(target)
        results.append(result)
        if progress is not None:
            progress(result)
    return results


def total_size(results: list[TargetResult]) -> int:
    return sum(r.size for r in results)


def human_size(size: float) -> str:
    """8437123456 -> '7,9 GB' (separador decimal no padrão brasileiro)."""
    step = 1024.0
    value = float(size)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < step or unit == "TB":
            if unit == "B":
                return f"{int(value)} B"
            return f"{value:.1f}".replace(".", ",") + f" {unit}"
        value /= step
    return f"{value:.1f} TB"
