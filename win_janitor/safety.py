"""Validação de caminhos: allowlist + bloqueio de áreas protegidas.

Toda decisão de "posso apagar isto?" passa por aqui:

1. o caminho precisa vir de um padrão registrado em ``targets``;
2. o padrão não pode conter ``..`` nem apontar para área proibida;
3. os resultados têm que ficar dentro da parte fixa do padrão;
4. a varredura nunca entra em junction/symlink de pasta (evita fuga de escopo).
"""

from __future__ import annotations

import fnmatch
import os

WILDCARDS = "*?["

# Pastas que NUNCA podem ser alvo, seja qual for o alvo que as mencione.
_SYSTEM_DIRS = (
    "System32",
    "SysWOW64",
    "Boot",
    "Fonts",
    "LiveKernelReports",
    "WinSxS",
    "servicing",
)

# Pastas pessoais do usuário: conteúdo do usuário, jamais lixo automático.
_PERSONAL_DIRS = (
    "Desktop",
    "Documents",
    "Downloads",
    "Pictures",
    "Music",
    "Videos",
    "Contacts",
    "Favorites",
    "Links",
    "Searches",
    "Saved Games",
    "OneDrive",
)


def expand(raw: str) -> str:
    """Expande ``~`` e variáveis de ambiente (%VAR% no Windows, $VAR no POSIX)."""
    return os.path.normpath(os.path.expanduser(os.path.expandvars(raw)))


def has_wildcard(pattern: str) -> bool:
    return any(ch in pattern for ch in WILDCARDS)


def static_prefix(pattern: str) -> str:
    """Parte fixa do padrão, cortada no primeiro curinga.

    É a "raiz permitida": nenhum resultado pode sair dela.
    """
    parts = pattern.split(os.sep)
    keep: list[str] = []
    for part in parts:
        if any(ch in part for ch in WILDCARDS):
            break
        keep.append(part)
    prefix = os.sep.join(keep)
    return prefix if prefix else os.sep


def is_inside(path: str | os.PathLike[str], root: str | os.PathLike[str]) -> bool:
    """True se ``path`` está dentro (ou é) ``root``, ignorando maiúsculas."""
    p = os.path.normcase(os.path.abspath(str(path)))
    r = os.path.normcase(os.path.abspath(str(root)))
    return p == r or p.startswith(r.rstrip(os.sep) + os.sep)


def _prohibited_roots() -> list[str]:
    roots: list[str] = []

    windir = os.environ.get("WINDIR") or os.environ.get("SystemRoot") or r"C:\Windows"
    roots.extend(os.path.join(windir, name) for name in _SYSTEM_DIRS)
    roots.append(windir)

    for pf in filter(None, (os.environ.get("ProgramFiles"), os.environ.get("ProgramFiles(x86)"))):
        roots.append(pf)

    # Só as subpastas pessoais entram na lista: a raiz do perfil NÃO, porque
    # %LOCALAPPDATA% (onde mora o lixo legítimo) é filha dela.
    profile = os.environ.get("USERPROFILE") or os.path.expanduser("~")
    roots.extend(os.path.join(profile, name) for name in _PERSONAL_DIRS)

    public = os.environ.get("PUBLIC")
    if public:
        roots.append(public)

    roots.append(os.path.join(os.sep + "mnt"))  # nunca mexer em pontos de montagem (POSIX)
    return roots


def is_prohibited(path: str | os.PathLike[str]) -> bool:
    """True se o caminho cai em área protegida (sistema, Program Files, usuário)."""
    target = os.path.normcase(os.path.abspath(str(path)))
    for root in _prohibited_roots():
        r = os.path.normcase(root)
        if any(ch in root for ch in WILDCARDS):
            if fnmatch.fnmatch(target, r):
                return True
        elif target == r or target.startswith(r.rstrip(os.sep) + os.sep):
            return True
    return False


def is_link(path: str | os.PathLike[str]) -> bool:
    """True para symlink ou junction (3.12 tem ``os.path.isjunction``)."""
    try:
        if os.path.islink(path):
            return True
    except OSError:
        return True
    isjunction = getattr(os.path, "isjunction", None)
    if isjunction is not None:
        try:
            return bool(isjunction(str(path)))
        except OSError:
            return True
    return False


def validate_pattern(raw: str) -> str | None:
    """Normaliza um padrão da allowlist e o aceita, ou devolve ``None``.

    Motivos de recusa: ``..`` no original (o ``normpath`` o esconderia),
    variável de ambiente não resolvida, ou prefixo em área protegida.
    """
    if any(part == ".." for part in raw.replace("\\", "/").split("/")):
        return None
    expanded = expand(raw)
    if "%" in expanded or "$" in expanded.split(os.sep)[0]:
        return None  # variável de ambiente inexistente neste sistema
    if is_prohibited(static_prefix(expanded)):
        return None
    return expanded


def matches(pattern: str, path: str | os.PathLike[str]) -> bool:
    """True se ``path`` respeita o prefixo fixo de ``pattern``."""
    return is_inside(path, static_prefix(pattern))
