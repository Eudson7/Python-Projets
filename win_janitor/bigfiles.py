"""Passo 2 — localizar arquivos grandes para você escolher o que apagar.

A varredura roda em thread (a interface não trava), reporta progresso,
respeita cancelamento e nunca entra em pasta de sistema.
"""

from __future__ import annotations

import mimetypes
import os
import string
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Sequence

from . import report
from .clean import remove_file, send_to_recycle_bin

DEFAULT_MIN_MB = 500
DEFAULT_LIMIT = 500

# Extensão -> rótulo de tipo amigável, agrupado por família.
_KIND_BY_EXT: dict[str, str] = {
    **{e: "Vídeo" for e in ("mp4", "mkv", "avi", "mov", "wmv", "flv", "webm", "m4v", "mpg", "mpeg", "ts", "3gp")},
    **{e: "Áudio" for e in ("mp3", "wav", "flac", "aac", "ogg", "m4a", "wma", "opus")},
    **{e: "Imagem" for e in ("jpg", "jpeg", "png", "gif", "bmp", "tiff", "tif", "webp", "psd", "raw", "cr2", "nef", "heic", "svg")},
    **{e: "Compactado" for e in ("zip", "rar", "7z", "tar", "gz", "bz2", "xz", "zst", "tgz")},
    **{e: "Imagem de disco" for e in ("iso", "img", "vhd", "vhdx", "wim", "esd", "dmg")},
    **{e: "Instalador" for e in ("exe", "msi", "msix", "appx", "apk")},
    **{e: "Documento" for e in ("pdf", "doc", "docx", "xls", "xlsx", "ppt", "pptx", "rtf", "odt", "odp", "ods", "epub")},
    **{e: "Backup/dados" for e in ("bak", "db", "sqlite", "sqlite3", "sql", "dump", "sqlitedb", "pst", "ost", "vhdx.bak")},
    **{e: "Fonte/programa" for e in ("ttf", "otf", "woff", "woff2", "jar", "pyc", "dll")},
}


def kind_of(name: str) -> str:
    """'filme_backup.mp4' -> 'Vídeo'; extensão desconhecida -> 'Outro'."""
    ext = Path(name).suffix.lstrip(".").lower()
    if not ext:
        return "Sem extensão"
    kind = _KIND_BY_EXT.get(ext)
    if kind:
        return kind
    guessed, _ = mimetypes.guess_type(name)
    if guessed:
        return guessed.split("/")[0].capitalize()
    return f"Outro (.{ext})"


@dataclass
class BigFile:
    path: Path
    name: str
    kind: str
    size: int
    created: float  # epoch; no Windows é a data de criação real

    @property
    def ext(self) -> str:
        return self.path.suffix.lower()

    @property
    def folder(self) -> str:
        return str(self.path.parent)

    def created_str(self) -> str:
        import time

        return time.strftime("%d/%m/%Y", time.localtime(self.created))


def creation_time(path: str, st: os.stat_result) -> float:
    """No Windows ``st_ctime`` é a data de criação; em outros sistemas, nasce/hora."""
    if os.name == "nt":
        return st.st_ctime
    return getattr(st, "st_birthtime", st.st_mtime)


def discover_roots() -> list[str]:
    """Drives fixos no Windows; o diretório pessoal em outros sistemas."""
    if os.name == "nt":
        drives = [f"{letter}:\\" for letter in string.ascii_uppercase if os.path.exists(f"{letter}:\\")]
        return drives or [os.environ.get("SystemRoot", "C:\\")]
    return [str(Path.home())]


def default_excludes() -> list[str]:
    """Áreas que a varredura de arquivos grandes jamais deve abrir."""
    out: list[str] = []
    if os.name == "nt":
        out.append(os.environ.get("WINDIR") or r"C:\Windows")
        out.append(os.environ.get("ProgramFiles") or r"C:\Program Files")
        out.append(os.environ.get("ProgramFiles(x86)") or r"C:\Program Files (x86)")
        out.append(os.environ.get("PROGRAMDATA") or r"C:\ProgramData")
        for letter in string.ascii_uppercase:
            drive = f"{letter}:\\"
            if os.path.exists(drive):
                out.append(drive + "$Recycle.Bin")
                out.append(drive + "System Volume Information")
    else:
        out.extend(["/proc", "/sys", "/dev"])
    return out


def scan_big_files(
    roots: Sequence[str],
    min_size: int = DEFAULT_MIN_MB * 1024 * 1024,
    excludes: Sequence[str] | None = None,
    limit: int = DEFAULT_LIMIT,
    on_progress: Callable[[int, int, str], None] | None = None,
    should_cancel: Callable[[], bool] | None = None,
) -> list[BigFile]:
    """Procura arquivos de pelo menos ``min_size`` dentro de ``roots``.

    ``on_progress(arquivos_vistos, bytes_vistos, caminho_atual)`` é chamado a
    cada 500 arquivos; ``should_cancel`` encerra a varredura no próximo laco.
    """
    exclude_list = [
        os.path.normcase(os.path.abspath(e)) for e in (excludes if excludes is not None else default_excludes())
    ]

    found: list[BigFile] = []
    seen = 0
    seen_bytes = 0
    stack = [str(r) for r in roots]

    while stack:
        if should_cancel is not None and should_cancel():
            break
        current = stack.pop()
        try:
            with os.scandir(current) as entries:
                for entry in entries:
                    if should_cancel is not None and should_cancel():
                        stack.clear()
                        break
                    try:
                        if entry.is_dir(follow_symlinks=False):
                            if os.path.islink(entry.path):
                                continue
                            normalized = os.path.normcase(os.path.abspath(entry.path))
                            if any(
                                normalized == e or normalized.startswith(e + os.sep)
                                for e in exclude_list
                            ):
                                continue
                            stack.append(entry.path)
                            continue
                        st = entry.stat(follow_symlinks=False)
                        seen += 1
                        seen_bytes += st.st_size
                        if seen % 500 == 0 and on_progress is not None:
                            on_progress(seen, seen_bytes, entry.path)
                        if st.st_size < min_size:
                            continue
                        found.append(
                            BigFile(
                                path=Path(entry.path),
                                name=entry.name,
                                kind=kind_of(entry.name),
                                size=st.st_size,
                                created=creation_time(entry.path, st),
                            )
                        )
                    except OSError:
                        continue
        except OSError:
            continue

    found.sort(key=lambda f: f.size, reverse=True)
    return found[:limit]


def delete_files(files: Sequence[BigFile], to_recycle: bool = False) -> tuple[int, int, list[str]]:
    """Apaga os arquivos selecionados. Retorna (apagados, liberado, erros)."""
    if not files:
        return 0, 0, []

    deleted = 0
    freed = 0
    errors: list[str] = []
    mode = "lixeira" if to_recycle else "permanente"

    if to_recycle:
        failure = send_to_recycle_bin([f.path for f in files])
        if failure:
            # Nada foi movido: melhor não afirmar que apagou.
            report.write_log(
                "arquivos_grandes",
                {"modo": mode, "erro": failure, "selecionados": len(files)},
            )
            return 0, 0, [failure]
        deleted = len(files)
        freed = sum(f.size for f in files)
    else:
        for item in files:
            error = remove_file(item.path)
            if error is None:
                deleted += 1
                freed += item.size
            else:
                errors.append(f"{item.name}: {error}")

    report.write_log(
        "arquivos_grandes",
        {
            "modo": mode,
            "apagados": deleted,
            "liberado": freed,
            "pulados": len(files) - deleted,
            "erros": errors,
            "detalhes": [
                {"nome": f.name, "pasta": f.folder, "tamanho": f.size, "tipo": f.kind}
                for f in files
            ],
        },
    )
    return deleted, freed, errors
