"""``python -m win_janitor`` abre a interface; com argumentos, usa o terminal."""

from __future__ import annotations

import sys


def main() -> int:
    if len(sys.argv) > 1:
        from . import cli

        return cli.main(sys.argv[1:])
    from .ui.app import run

    run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
