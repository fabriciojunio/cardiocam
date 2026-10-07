"""Ponto de entrada do aplicativo de desktop.

    python -m cardiocam.desktop

A ciência de DPI é declarada **antes** de qualquer coisa do Qt, e essa ordem não
é estilo: o Windows ignora o pedido depois que a primeira janela existe, e sem
ele, em tela com escala de 125% ou 150%, as coordenadas que a enumeração de
janelas devolve não batem com os pixels que a captura lê. A janela da reunião
sairia capturada deslocada e cortada, sem nada avisar.
"""

from __future__ import annotations

import sys

from cardiocam.desktop.janelas import declarar_ciencia_de_dpi


def principal() -> int:
    declarar_ciencia_de_dpi()

    from PySide6.QtWidgets import QApplication, QSystemTrayIcon

    from cardiocam.desktop.aplicativo import JanelaPrincipal

    aplicacao = QApplication(sys.argv)
    aplicacao.setApplicationName("Cardiocam")
    # Sem isto o programa encerra quando a janela é escondida para a bandeja,
    # que é exatamente o fluxo normal de uso.
    aplicacao.setQuitOnLastWindowClosed(False)

    if not QSystemTrayIcon.isSystemTrayAvailable():
        print("Este sistema não tem área de notificação; a bandeja não vai aparecer.")

    janela = JanelaPrincipal()
    janela.show()
    return aplicacao.exec()


if __name__ == "__main__":
    raise SystemExit(principal())
