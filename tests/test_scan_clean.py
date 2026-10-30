"""Varredura e limpeza dos alvos, incluindo arquivos travados e modo simulação."""

from __future__ import annotations

import os
import time
from pathlib import Path

from win_janitor import scan
from win_janitor.clean import clean_target, clean_targets, remove_file
from win_janitor.targets import Target


def _target(root: Path, **kwargs) -> Target:
    return Target(id="teste", label="Alvo de teste", paths=(str(root),), **kwargs)


def _make_tree(root: Path) -> None:
    (root / "sub").mkdir(parents=True)
    (root / "a.tmp").write_bytes(b"0" * 100)
    (root / "sub" / "b.tmp").write_bytes(b"0" * 250)
    (root / "sub" / "c.log").write_bytes(b"0" * 50)


def test_scan_counts_files_and_size(tmp_path: Path) -> None:
    root = tmp_path / "temp"
    _make_tree(root)

    result = scan.scan_target(_target(root))
    assert result.files == 3
    assert result.size == 400
    assert result.usable


def test_scan_empty_when_missing(tmp_path: Path) -> None:
    result = scan.scan_target(_target(tmp_path / "nao_existe"))
    assert result.files == 0
    assert not result.usable


def test_scan_respects_min_age(tmp_path: Path) -> None:
    root = tmp_path / "temp"
    root.mkdir()
    old = root / "antigo.tmp"
    fresh = root / "novo.tmp"
    old.write_bytes(b"0" * 10)
    fresh.write_bytes(b"0" * 10)
    decade_ago = time.time() - 40 * 86400
    os.utime(old, (decade_ago, decade_ago))

    result = scan.scan_target(_target(root, min_age_days=30))
    assert result.files == 1
    assert result.size == 10


def test_glob_target_only_touches_matching(tmp_path: Path) -> None:
    root = tmp_path / "logs"
    root.mkdir()
    (root / "um.log").write_bytes(b"0" * 10)
    (root / "dois.tmp").write_bytes(b"0" * 10)
    pattern = str(root / "*.log")

    target = Target(id="logs", label="Logs", paths=(pattern,))
    assert [p.name for p in scan.iter_target_files(target)] == ["um.log"]


def test_clean_deletes_and_keeps_root(tmp_path: Path) -> None:
    root = tmp_path / "temp"
    _make_tree(root)

    outcome = clean_target(_target(root))
    assert outcome.deleted == 3
    assert outcome.freed == 400
    assert outcome.kept == 0
    assert root.is_dir()  # a raiz permanece
    assert not (root / "a.tmp").exists()
    assert not (root / "sub").exists()  # subpasta vazia é removida


def test_clean_dry_run_deletes_nothing(tmp_path: Path) -> None:
    root = tmp_path / "temp"
    _make_tree(root)

    outcome = clean_target(_target(root), dry_run=True)
    assert outcome.deleted == 3
    assert outcome.freed == 400
    assert (root / "a.tmp").exists()


def test_locked_file_is_kept_not_fatal(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "temp"
    _make_tree(root)
    original = Path.unlink

    def locked(self: Path, missing_ok: bool = False):
        if self.name == "b.tmp":
            raise PermissionError("arquivo em uso")
        return original(self, missing_ok)

    monkeypatch.setattr(Path, "unlink", locked)

    outcome = clean_target(_target(root))
    assert outcome.deleted == 2
    assert outcome.kept == 1
    assert (root / "sub" / "b.tmp").exists()


def test_remove_file_reports_reasons(tmp_path: Path) -> None:
    assert remove_file(tmp_path / "nao_existe.tmp") == "já não existe"


def test_clean_targets_writes_log(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "appdata"))
    root = tmp_path / "temp"
    _make_tree(root)

    outcome = clean_targets([_target(root)], dry_run=False)
    assert outcome.deleted == 3
    logs = sorted((tmp_path / "appdata" / "win_janitor" / "logs").glob("limpeza-*.json"))
    assert len(logs) == 1


def test_prohibited_path_yields_nothing(tmp_path: Path, monkeypatch) -> None:
    profile = tmp_path / "perfil"
    downloads = profile / "Downloads"
    downloads.mkdir(parents=True)
    (downloads / "filme.iso").write_bytes(b"0")

    monkeypatch.setenv("USERPROFILE", str(profile))
    target = Target(id="perigo", label="Downloads", paths=(str(downloads),))
    assert list(scan.iter_target_files(target)) == []


def test_human_size_format() -> None:
    assert scan.human_size(512) == "512 B"
    assert scan.human_size(1024 * 1024 * 1536) == "1,5 GB"
