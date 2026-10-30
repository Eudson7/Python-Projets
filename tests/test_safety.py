"""Regras de segurança: allowlist, curingas e áreas protegidas."""

from __future__ import annotations

from pathlib import Path

from win_janitor import safety


def test_expand_and_wildcards() -> None:
    assert safety.has_wildcard("thumbcache_*.db")
    assert safety.has_wildcard("dump?.tmp")
    assert not safety.has_wildcard("/tmp/pasta")


def test_static_prefix_corta_no_curinga(tmp_path: Path) -> None:
    pattern = str(tmp_path / "cache" / "*.log")
    assert safety.static_prefix(pattern) == str(tmp_path / "cache")


def test_is_inside(tmp_path: Path) -> None:
    root = tmp_path / "raiz"
    (root / "sub").mkdir(parents=True)
    assert safety.is_inside(root / "sub" / "a.txt", root)
    assert safety.is_inside(root, root)
    assert not safety.is_inside(tmp_path / "fora", root)
    # caminho que só parece dentro (raiz2 vs raiz22)
    (tmp_path / "raiz22").mkdir()
    assert not safety.is_inside(tmp_path / "raiz22", root)


def test_prohibited_covers_system_and_personal_dirs(tmp_path: Path, monkeypatch) -> None:
    profile = tmp_path / "perfil"
    (profile / "Documents").mkdir(parents=True)
    (profile / "AppData" / "Local" / "Temp").mkdir(parents=True)
    monkeypatch.setenv("USERPROFILE", str(profile))
    monkeypatch.setenv("WINDIR", str(tmp_path / "Windows"))
    (tmp_path / "Windows" / "System32").mkdir(parents=True)

    assert safety.is_prohibited(profile / "Documents" / "nota.txt")
    assert safety.is_prohibited(tmp_path / "Windows" / "System32" / "kernel32.dll")
    assert not safety.is_prohibited(profile / "AppData" / "Local" / "Temp" / "lixo.tmp")


def test_validate_pattern_rejects_escape(tmp_path: Path) -> None:
    assert safety.validate_pattern(str(tmp_path / "ok" / ".." / ".." / "fora")) is None


def test_validate_pattern_rejects_unknown_env_var() -> None:
    # variável inexistente: o caminho fica literal com % e não pode ser alvo
    assert safety.validate_pattern("%VAR_QUE_NAO_EXISTE_XYZ%/temp") is None


def test_validate_pattern_rejects_personal_dir(tmp_path: Path, monkeypatch) -> None:
    profile = tmp_path / "perfil"
    (profile / "Downloads").mkdir(parents=True)
    monkeypatch.setenv("USERPROFILE", str(profile))
    pattern = str(profile / "Downloads" / "qualquer.iso")
    assert safety.validate_pattern(pattern) is None


def test_validate_pattern_accepts_temp(tmp_path: Path, monkeypatch) -> None:
    profile = tmp_path / "perfil"
    temp = profile / "AppData" / "Local" / "Temp"
    temp.mkdir(parents=True)
    monkeypatch.setenv("USERPROFILE", str(profile))
    accepted = safety.validate_pattern(str(temp))
    assert accepted == str(temp)
    assert safety.matches(accepted, temp / "arquivo.tmp")
