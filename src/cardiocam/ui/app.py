"""Aplicação interativa: mede e mostra em tempo real."""

from __future__ import annotations

import time
import csv
from collections import deque
from dataclasses import dataclass

import cv2
import numpy as np

from cardiocam.dominio.config import ConfiguracaoAnalise
from cardiocam.pipeline.analisador import MonitorCardiaco, RelatorioSessao
from cardiocam.rppg import ALGORITMOS_DISPONIVEIS, criar_algoritmo
from cardiocam.ui.hud import compor
from cardiocam.ui.texto import PincelTexto
from cardiocam.pipeline.registros import RegistroMedicao
from cardiocam.desktop.qualidade_ao_vivo import JuizDeQualidade, aplicar_qualidade

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
    juiz = JuizDeQualidade(monitor.janela.capacidade)
    registros = deque(maxlen=3600)

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
            aplicar_qualidade(juiz, quadro, estado)
            if (estado.janela_emitida or (estado.codigo_falha is not None
                    and (not registros or registros[-1].codigo_falha != estado.codigo_falha))):
                registros.append(RegistroMedicao.do_estado(estado))
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
    relatorio.registros = list(registros)
    relatorio.historico_limitado = monitor.total_estimativas > len(monitor.historico)

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
    registros = relatorio.registros or [
        RegistroMedicao(None, e, e.aproveitavel, None, None, "", None)
        for e in relatorio.estimativas
    ]
    with open(caminho, "w", encoding="utf-8", newline="") as arquivo:
        escritor = csv.writer(arquivo)
        escritor.writerow(["janela", "bpm", "frequencia_hz", "snr_db", "confianca", "algoritmo",
                           "instante_s", "aceita", "qualidade", "codigo_falha", "mensagem",
                           "idade_analise_s", "caracteristicas_ausentes", "historico_limitado"])
        for indice, registro in enumerate(registros):
            e = registro.estimativa
            escritor.writerow([
                indice, "" if e is None else f"{e.bpm:.3f}",
                "" if e is None else f"{e.frequencia_hz:.5f}",
                "" if e is None else f"{e.snr_db:.3f}",
                "" if e is None else e.confianca.value, "" if e is None else e.algoritmo,
                registro.instante, registro.aceita, registro.qualidade, registro.codigo_falha,
                registro.mensagem, registro.idade_analise_s,
                ";".join(registro.caracteristicas_ausentes), relatorio.historico_limitado,
            ])
