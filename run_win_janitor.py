"""Ponto de entrada usado pelo PyInstaller para gerar o WinJanitor.exe."""

from win_janitor.__main__ import main

if __name__ == "__main__":
    raise SystemExit(main())
