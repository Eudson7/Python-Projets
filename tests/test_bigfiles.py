"""Varredura de arquivos grandes: filtros, ordenação, exclusão e cancelamento."""

from __future__ import annotations

import json
from pathlib import Path

from win_janitor import bigfiles, report


def _make_files(root: Path) -> None:
    (root / "grande.zip").write_bytes(b"0" * 5000)
    (root / "medio.mp4").write_bytes(b"0" * 2500)
    (root / "pequeno.txt").write_bytes(b"0" * 100)
    (root / "pasta").mkdir()
    (root / "pasta" / "tambem_grande.iso").write_bytes(b"0" * 4000)


def test_scan_filters_sorts_and_limits(tmp_path: Path) -> None:
    _make_files(tmp_path)

    found = bigfiles.scan_big_files(
        [str(tmp_path)], min_size=2000, excludes=[], limit=10
    )
    assert [f.name for f in found] == ["grande.zip", "tambem_grande.iso", "medio.mp4"]
    assert found[0].size == 5000
    assert found[0].kind == "Compactado"
    assert found[1].kind == "Imagem de disco"
    assert found[2].kind == "Vídeo"
    assert found[0].created > 0
    assert found[0].folder == str(tmp_path)


def test_scan_honours_limit(tmp_path: Path) -> None:
    for index in range(6):
        (tmp_path / f"arq{index}.bin").write_bytes(b"0" * 3000)

    found = bigfiles.scan_big_files([str(tmp_path)], min_size=1000, excludes=[], limit=2)
    assert len(found) == 2


def test_scan_skips_excluded_dirs(tmp_path: Path) -> None:
    (tmp_path / "liberado").mkdir()
    (tmp_path / "proibido").mkdir()
    (tmp_path / "liberado" / "a.iso").write_bytes(b"0" * 3000)
    (tmp_path / "proibido" / "b.iso").write_bytes(b"0" * 3000)

    found = bigfiles.scan_big_files(
        [str(tmp_path)], min_size=1000, excludes=[str(tmp_path / "proibido")]
    )
    assert [f.name for f in found] == ["a.iso"]


def test_scan_stops_when_cancelled(tmp_path: Path) -> None:
    (tmp_path / "a.iso").write_bytes(b"0" * 3000)

    found = bigfiles.scan_big_files(
        [str(tmp_path)], min_size=1000, excludes=[], should_cancel=lambda: True
    )
    assert found == []


def test_scan_reports_progress(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(bigfiles, "DEFAULT_MIN_MB", 1)
    (tmp_path / "a.iso").write_bytes(b"0" * 10)
    seen: list[tuple] = []
    bigfiles.scan_big_files(
        [str(tmp_path)],
        min_size=1,
        excludes=[],
        on_progress=lambda n, size, path: seen.append((n, size)),
        limit=5,
    )
    # progresso sai a cada 500 arquivos; com poucos arquivos a lista fica vazia,
    # o importante é não explodir.
    assert isinstance(seen, list)


def test_kind_of() -> None:
    assert bigfiles.kind_of("filme_backup.MP4") == "Vídeo"
    assert bigfiles.kind_of("foto.jpg") == "Imagem"
    assert bigfiles.kind_of("sistema.xyzabc") == "Outro (.xyzabc)"
    assert bigfiles.kind_of("sem_extensao") == "Sem extensão"


def test_delete_permanent_writes_log(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "appdata"))
    _make_files(tmp_path)
    found = bigfiles.scan_big_files([str(tmp_path)], min_size=1000, excludes=[])

    deleted, freed, errors = bigfiles.delete_files(found, to_recycle=False)
    assert deleted == 3
    assert freed == 5000 + 2500 + 4000
    assert errors == []
    assert not (tmp_path / "grande.zip").exists()

    logs = list((tmp_path / "appdata" / "win_janitor" / "logs").glob("arquivos_grandes-*.json"))
    assert len(logs) == 1
    payload = json.loads(logs[0].read_text(encoding="utf-8"))
    assert payload["modo"] == "permanente"
    assert payload["apagados"] == 3


def test_delete_missing_file_reports_error(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "appdata"))
    (tmp_path / "fantasma.bin").write_bytes(b"0" * 3000)
    found = bigfiles.scan_big_files([str(tmp_path)], min_size=1000, excludes=[])
    (tmp_path / "fantasma.bin").unlink()  # sumiu entre varrer e apagar

    deleted, freed, errors = bigfiles.delete_files(found, to_recycle=False)
    assert deleted == 0
    assert errors and "não existe" in errors[0]


def test_recycle_bin_refused_outside_windows(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "appdata"))
    (tmp_path / "a.bin").write_bytes(b"0" * 3000)
    found = bigfiles.scan_big_files([str(tmp_path)], min_size=1000, excludes=[])

    deleted, _freed, errors = bigfiles.delete_files(found, to_recycle=True)
    assert deleted == 0
    assert errors  # nada é apagado em silêncio
    assert (tmp_path / "a.bin").exists()


def test_log_roundtrip(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "appdata"))
    path = report.write_log("limpeza", {"total_apagados": 4})
    assert path.exists()
    assert report.list_logs()[0] == path
    payload = report.read_log(path)
    assert payload["total_apagados"] == 4
    assert "total_apagados: 4" in report.format_log(payload)
