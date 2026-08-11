"""Ponto de entrada para `python -m cardiocam` e para o executável empacotado."""

from __future__ import annotations

import multiprocessing
import sys


def _preparar_console() -> None:
    """Faz o console do Windows aceitar acentuação.

    O executável empacotado herda a página de código antiga do console, que não
    cobre os acentos do português: sem este ajuste, "Frequência" aparece
    corrompido. São duas coisas separadas e ambas necessárias: dizer ao console
    para interpretar UTF-8 e dizer ao Python para escrever em UTF-8.
    """
    if sys.platform.startswith("win"):
        try:
            import ctypes

            ctypes.windll.kernel32.SetConsoleOutputCP(65001)
            ctypes.windll.kernel32.SetConsoleCP(65001)
        except Exception:  # noqa: BLE001 - console indisponível não é erro fatal
            pass

    for fluxo in (sys.stdout, sys.stderr):
        try:
            fluxo.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):  # pragma: sem cobertura
            pass


if __name__ == "__main__":
    # Necessário no executável do Windows: sem isso, qualquer processo filho
    # criado por bibliotecas reexecutaria o programa inteiro em vez de rodar a
    # função pedida, e o programa abriria cópias de si mesmo sem parar.
    multiprocessing.freeze_support()
    _preparar_console()

    from cardiocam.cli import main

    sys.exit(main())
