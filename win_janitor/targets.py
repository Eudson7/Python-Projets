"""Allowlist de alvos de limpeza.

Regra de ouro do programa: só é apagado o que estiver listado AQUI.
Não existe "denylist" — qualquer caminho fora desta tabela é ignorado.

Cada entrada pode conter:
  * variáveis de ambiente (%LOCALAPPDATA%, %TEMP%, %WINDIR%...)
  * curingas (ex.: thumbcache_*.db) — aí o alvo são arquivos, não pastas
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Risk(str, Enum):
    """Nível de aviso mostrado na interface antes da limpeza."""

    SAFE = "safe"  # lixo de verdade: cache/temporário, apagar não muda nada
    CAUTION = "caution"  # pede confirmação destacada (ex.: cache de navegador aberto)


@dataclass(frozen=True)
class Target:
    id: str
    label: str
    paths: tuple[str, ...]
    description: str = ""
    risk: Risk = Risk.SAFE
    requires_admin: bool = False
    min_age_days: int = 0  # ignora arquivos modificados nos últimos N dias


TARGETS: tuple[Target, ...] = (
    Target(
        id="temp_user",
        label="Temporários do usuário",
        paths=("%LOCALAPPDATA%\\Temp", "%TEMP%"),
        description="Arquivos que programas deixaram para trás.",
        min_age_days=1,
    ),
    Target(
        id="temp_system",
        label="Temporários do Windows",
        paths=("%WINDIR%\\Temp",),
        description="Temporários do sistema. Precisa de administrador.",
        requires_admin=True,
        min_age_days=1,
    ),
    Target(
        id="windows_update",
        label="Cache do Windows Update",
        paths=("%WINDIR%\\SoftwareDistribution\\Download",),
        description="Instalações já aplicadas que continuam ocupando espaço.",
        requires_admin=True,
    ),
    Target(
        id="error_reports",
        label="Relatórios de erro e crashes",
        paths=(
            "%LOCALAPPDATA%\\CrashDumps",
            "%LOCALAPPDATA%\\Microsoft\\Windows\\WER",
            "%PROGRAMDATA%\\Microsoft\\Windows\\WER",
        ),
        description="Dumps de programas que pararam de responder.",
    ),
    Target(
        id="minidump",
        label="Minidumps do sistema",
        paths=("%WINDIR%\\Minidump",),
        description="Pequenos registros de tela azul (BSOD).",
        requires_admin=True,
    ),
    Target(
        id="explorer_cache",
        label="Miniaturas e ícones do Explorador",
        paths=(
            "%LOCALAPPDATA%\\Microsoft\\Windows\\Explorer\\thumbcache_*.db",
            "%LOCALAPPDATA%\\Microsoft\\Windows\\Explorer\\iconcache_*.db",
        ),
        description="São reconstruídos automaticamente quando necessário.",
    ),
    Target(
        id="browser_cache",
        label="Cache de navegadores",
        paths=(
            "%LOCALAPPDATA%\\Google\\Chrome\\User Data\\Default\\Cache",
            "%LOCALAPPDATA%\\Google\\Chrome\\User Data\\Default\\Code Cache",
            "%LOCALAPPDATA%\\Google\\Chrome\\User Data\\Default\\GPUCache",
            "%LOCALAPPDATA%\\Microsoft\\Edge\\User Data\\Default\\Cache",
            "%LOCALAPPDATA%\\Microsoft\\Edge\\User Data\\Default\\Code Cache",
            "%LOCALAPPDATA%\\Mozilla\\Firefox\\Profiles\\*\\cache2",
        ),
        description="Páginas guardadas. Com o navegador aberto, arquivos são pulados.",
        risk=Risk.CAUTION,
        min_age_days=1,
    ),
    Target(
        id="logs",
        label="Logs antigos de aplicativos",
        paths=(
            "%LOCALAPPDATA%\\Temp\\*.log",
            "%LOCALAPPDATA%\\Temp\\*.tmp",
        ),
        description="Registros e arquivos .tmp com mais de 30 dias.",
        min_age_days=30,
    ),
)

_BY_ID = {t.id: t for t in TARGETS}


def get_target(target_id: str) -> Target:
    """Devolve um alvo pelo id (KeyError se não existir)."""
    return _BY_ID[target_id]


def default_selection() -> list[str]:
    """Alvos marcados por padrão: todos os seguros, sem admin."""
    return [t.id for t in TARGETS if t.risk is Risk.SAFE and not t.requires_admin]
