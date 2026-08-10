"""Aplicação interativa: mede e mostra em tempo real."""

from __future__ import annotations

import time
from dataclasses import dataclass

import cv2
import numpy as np

from cardiocam.dominio.config import ConfiguracaoAnalise
from cardiocam.pipeline.analisador import MonitorCardiaco, RelatorioSessao
from cardiocam.rppg import ALGORITMOS_DISPONIVEIS, criar_algoritmo
from cardiocam.ui.hud import compor
from cardiocam.ui.texto import PincelTexto

TITULO_JANELA = "Cardiocam"


@dataclass
class ResultadoSessao:
    """O que sobra depois de fechar a janela."""

    relatorio: RelatorioSessao
    duracao_s: float
    quadros_por_segundo: float


def executar(
    fonte,
    config: ConfiguracaoAnalise | None = None,
    mostrar_janela: bool = True,
    limite_quadros: int | None = None,
) -> ResultadoSessao:
    """Laço principal: lê quadros, processa e desenha.

    Aceita qualquer fonte que cumpra o contrato, então serve tanto para webcam
    quanto para arquivo ou simulação, sem mudar nada aqui.
    """
    config = config or ConfiguracaoAnalise()
    monitor = MonitorCardiaco(fps=getattr(fonte, "fps", 30.0) or 30.0, config=config)
    pincel = PincelTexto()

    relatorio = RelatorioSessao()
    inicio = time.perf_counter()
    quadros = 0

    if mostrar_janela:
        cv2.namedWindow(TITULO_JANELA, cv2.WINDOW_AUTOSIZE)

    try:
        for quadro, instante in fonte.quadros():
            if limite_quadros is not None and quadros >= limite_quadros:
                break

            estado = monitor.processar(quadro, instante)
            quadros += 1
            relatorio.quadros_processados += 1
            if estado.tem_rosto:
                relatorio.quadros_com_rosto += 1

            if not mostrar_janela:
                continue

            cv2.imshow(TITULO_JANELA, compor(quadro, estado, pincel))
            tecla = cv2.waitKey(1) & 0xFF
            if tecla in (ord("q"), 27):
                break
            if tecla == ord("r"):
                monitor.reiniciar()
            if ord("1") <= tecla <= ord("4"):
                escolhido = ALGORITMOS_DISPONIVEIS[tecla - ord("1")]
                monitor.algoritmo = criar_algoritmo(escolhido)
                monitor.reiniciar()
    finally:
        fonte.fechar()
        if mostrar_janela:
            cv2.destroyWindow(TITULO_JANELA)

    duracao = time.perf_counter() - inicio
    relatorio.estimativas = monitor.historico
    relatorio.ultima_analise = monitor.ultima_analise

    return ResultadoSessao(
        relatorio=relatorio,
        duracao_s=duracao,
        quadros_por_segundo=quadros / duracao if duracao > 0 else 0.0,
    )


def salvar_serie(caminho: str, relatorio: RelatorioSessao) -> None:
    """Grava as estimativas em CSV.

    Só números: instante, BPM, relação sinal-ruído, confiança e algoritmo.
    Nenhum quadro de vídeo é gravado em momento algum.
    """
    linhas = ["janela,bpm,frequencia_hz,snr_db,confianca,algoritmo"]
    for indice, estimativa in enumerate(relatorio.estimativas):
        linhas.append(
            f"{indice},{estimativa.bpm:.3f},{estimativa.frequencia_hz:.5f},"
            f"{estimativa.snr_db:.3f},{estimativa.confianca.value},{estimativa.algoritmo}"
        )
    with open(caminho, "w", encoding="utf-8") as arquivo:
        arquivo.write("\n".join(linhas) + "\n")
