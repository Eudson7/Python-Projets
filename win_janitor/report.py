"""Registro em JSON de tudo que o programa faz — sua trilha de auditoria."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any


def log_dir() -> Path:
    """Pasta dos logs: %LOCALAPPDATA%\\win_janitor\\logs (ou ~/.win_janitor/logs)."""
    base = os.environ.get("LOCALAPPDATA") or str(Path.home())
    folder = Path(base) / "win_janitor" / "logs"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def write_log(kind: str, data: dict[str, Any]) -> Path:
    """Grava ``{kind}-AAAAmmdd-HHMMSS.json`` e devolve o caminho."""
    stamp = time.strftime("%Y%m%d-%H%M%S")
    path = log_dir() / f"{kind}-{stamp}.json"
    payload = {"tipo": kind, "gerado_em": time.strftime("%Y-%m-%d %H:%M:%S"), **data}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def list_logs(limit: int = 20) -> list[Path]:
    """Logs mais recentes primeiro."""
    files = [p for p in log_dir().iterdir() if p.suffix == ".json"]
    files.sort(key=lambda p: p.name, reverse=True)
    return files[:limit]


def read_log(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def format_log(data: dict[str, Any]) -> str:
    """Log JSON -> texto legível para a tela de Relatório."""
    if not data:
        return "(log ilegível)"
    lines = [
        f"{data.get('gerado_em', '?')}  ·  {data.get('tipo', '?')}",
        "=" * 58,
    ]
    for key, value in data.items():
        if key in ("tipo", "gerado_em"):
            continue
        if key == "alvos" and isinstance(value, list):
            lines.append("alvos:")
            for item in value:
                lines.append(
                    f"  · {item.get('nome', '?')}: {item.get('apagados', 0)} arquivos, "
                    f"{item.get('liberado', 0) // (1024 * 1024)} MB liberados"
                )
        elif isinstance(value, list):
            lines.append(f"{key}: {len(value)} registro(s)")
            lines.extend(f"  - {v}" for v in value[:15])
        else:
            lines.append(f"{key}: {value}")
    return "\n".join(lines)
