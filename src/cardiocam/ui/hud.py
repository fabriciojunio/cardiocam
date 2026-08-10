"""Painel sobreposto ao vídeo.

Mostra três coisas ao mesmo tempo, e é essa simultaneidade que torna o sistema
convincente para quem assiste: a região do rosto que está sendo medida, a onda
de pulso recuperada e o espectro com o pico marcado. Ver a onda pulsar em
sincronia com o próprio coração é o que transforma um número abstrato em algo
que a pessoa reconhece como real.
"""

from __future__ import annotations

import cv2
import numpy as np

from cardiocam.dominio.estimativa import Confianca
from cardiocam.pipeline.analisador import EstadoQuadro
from cardiocam.ui.texto import ItemTexto, PincelTexto

COR_FUNDO = (28, 26, 24)
COR_TEXTO = (240, 240, 240)
COR_APAGADA = (150, 150, 150)
COR_ONDA = (120, 220, 120)
COR_ESPECTRO = (200, 170, 90)
COR_PICO = (90, 140, 250)
COR_CAIXA = (200, 200, 200)
COR_REGIAO = (110, 220, 110)

CORES_CONFIANCA = {
    Confianca.ALTA: (110, 220, 110),
    Confianca.MEDIA: (90, 200, 240),
    Confianca.BAIXA: (90, 140, 250),
    Confianca.DESCARTADA: (110, 110, 240),
}

ALTURA_PAINEL = 200
LARGURA_PAINEL = 380


def desenhar_regioes(quadro: np.ndarray, estado: EstadoQuadro) -> np.ndarray:
    """Marca a caixa do rosto e as regiões efetivamente medidas."""
    if estado.caixa is not None:
        x, y, largura, altura = estado.caixa.como_tupla()
        cv2.rectangle(quadro, (x, y), (x + largura, y + altura), COR_CAIXA, 1)
    if estado.amostra is not None:
        for regiao in estado.amostra.regioes:
            rx, ry, rl, ra = regiao.como_tupla()
            cv2.rectangle(quadro, (rx, ry), (rx + rl, ry + ra), COR_REGIAO, 2)
    return quadro


def _traçar_serie(
    painel: np.ndarray,
    valores: np.ndarray,
    area: tuple[int, int, int, int],
    cor: tuple[int, int, int],
    preencher: bool = False,
) -> None:
    """Desenha uma série normalizada dentro de um retângulo do painel."""
    x0, y0, largura, altura = area
    if valores.size < 2 or largura < 2 or altura < 2:
        return

    minimo = float(np.min(valores))
    maximo = float(np.max(valores))
    amplitude = maximo - minimo
    if amplitude < 1e-12:
        amplitude = 1.0

    indices = np.linspace(0, valores.size - 1, min(valores.size, largura)).astype(int)
    amostrado = valores[indices]
    xs = np.linspace(x0, x0 + largura - 1, amostrado.size).astype(np.int32)
    ys = (y0 + altura - 1 - (amostrado - minimo) / amplitude * (altura - 1)).astype(np.int32)

    pontos = np.stack([xs, ys], axis=1)
    if preencher:
        base = np.array([[x0 + largura - 1, y0 + altura - 1], [x0, y0 + altura - 1]])
        poligono = np.vstack([pontos, base]).astype(np.int32)
        sombra = painel.copy()
        cv2.fillPoly(sombra, [poligono], tuple(int(c * 0.35) for c in cor))
        cv2.addWeighted(sombra, 0.6, painel, 0.4, 0, painel)
    cv2.polylines(painel, [pontos], False, cor, 2, cv2.LINE_AA)


def construir_painel(
    estado: EstadoQuadro, largura: int = LARGURA_PAINEL, altura: int = ALTURA_PAINEL
) -> tuple[np.ndarray, list[ItemTexto]]:
    """Monta o painel lateral com a onda de pulso e o espectro."""
    painel = np.full((altura, largura, 3), COR_FUNDO, dtype=np.uint8)
    textos: list[ItemTexto] = []

    margem = 12
    altura_grafico = (altura - 3 * margem) // 2
    area_onda = (margem, margem + 16, largura - 2 * margem, altura_grafico - 16)
    area_espectro = (
        margem,
        2 * margem + altura_grafico + 16,
        largura - 2 * margem,
        altura_grafico - 16,
    )

    textos.append(ItemTexto("Onda de pulso", (margem, margem - 2), 14, COR_APAGADA))
    textos.append(
        ItemTexto(
            "Espectro na banda cardíaca",
            (margem, 2 * margem + altura_grafico - 2),
            14,
            COR_APAGADA,
        )
    )

    analise = estado.analise
    if analise is not None:
        _traçar_serie(painel, analise.pulso.normalizado(), area_onda, COR_ONDA)

        espectro = analise.espectro
        if espectro.potencias.size >= 2:
            _traçar_serie(
                painel, espectro.normalizado(), area_espectro, COR_ESPECTRO, preencher=True
            )
            # Marca a posição do pico estimado sobre o eixo de frequência.
            x0, y0, largura_g, altura_g = area_espectro
            faixa = espectro.bpm
            if faixa.size >= 2:
                posicao = (analise.estimativa.bpm - faixa[0]) / max(
                    1e-9, faixa[-1] - faixa[0]
                )
                px = int(x0 + np.clip(posicao, 0.0, 1.0) * (largura_g - 1))
                cv2.line(painel, (px, y0), (px, y0 + altura_g - 1), COR_PICO, 1, cv2.LINE_AA)
    else:
        textos.append(
            ItemTexto(
                "Aguardando sinal…",
                (margem, margem + altura_grafico // 2),
                16,
                COR_APAGADA,
            )
        )

    return painel, textos


def compor(quadro: np.ndarray, estado: EstadoQuadro, pincel: PincelTexto) -> np.ndarray:
    """Junta vídeo, marcações, painel e legendas num único quadro exibível."""
    quadro = desenhar_regioes(quadro.copy(), estado)
    altura_video, largura_video = quadro.shape[:2]

    painel, textos_painel = construir_painel(
        estado, altura=max(ALTURA_PAINEL, altura_video)
    )
    if painel.shape[0] != altura_video:
        painel = cv2.resize(painel, (painel.shape[1], altura_video))

    composicao = np.hstack([quadro, painel])
    deslocamento_painel = largura_video

    itens: list[ItemTexto] = []

    # Bloco principal: o número grande.
    if estado.bpm_exibido is not None:
        confianca = (
            estado.analise.estimativa.confianca if estado.analise else Confianca.BAIXA
        )
        cor = CORES_CONFIANCA.get(confianca, COR_TEXTO)
        itens.append(ItemTexto(f"{estado.bpm_exibido:.0f}", (16, 10), 64, cor))
        largura_numero, _ = pincel.medir(f"{estado.bpm_exibido:.0f}", 64)
        itens.append(ItemTexto("bpm", (16 + largura_numero + 8, 48), 22, cor))
    else:
        itens.append(ItemTexto("--", (16, 10), 64, COR_APAGADA))
        itens.append(ItemTexto("bpm", (16 + 70, 48), 22, COR_APAGADA))

    linha = 90
    if estado.analise is not None:
        estimativa = estado.analise.estimativa
        itens.append(
            ItemTexto(
                f"Algoritmo: {estimativa.algoritmo.upper()}", (16, linha), 16, COR_TEXTO
            )
        )
        linha += 22
        itens.append(
            ItemTexto(
                f"Relação sinal-ruído: {estimativa.snr_db:.1f} dB",
                (16, linha),
                16,
                COR_TEXTO,
            )
        )
        linha += 22
        itens.append(
            ItemTexto(
                f"Confiança: {estimativa.confianca.value}", (16, linha), 16, COR_TEXTO
            )
        )
        linha += 22
        hrv = estado.analise.hrv
        if np.isfinite(hrv.sdnn_ms):
            itens.append(
                ItemTexto(
                    f"Variabilidade: {hrv.sdnn_ms:.0f} ms", (16, linha), 16, COR_APAGADA
                )
            )
            linha += 22

    if estado.mensagem:
        itens.append(
            ItemTexto(estado.mensagem, (16, altura_video - 30), 16, COR_APAGADA)
        )

    # Barra de progresso do preenchimento da janela.
    if estado.progresso < 1.0:
        largura_barra = largura_video - 32
        y_barra = altura_video - 52
        cv2.rectangle(
            composicao, (16, y_barra), (16 + largura_barra, y_barra + 4), (70, 70, 70), -1
        )
        cv2.rectangle(
            composicao,
            (16, y_barra),
            (16 + int(largura_barra * estado.progresso), y_barra + 4),
            COR_REGIAO,
            -1,
        )

    for item in textos_painel:
        itens.append(
            ItemTexto(
                item.texto,
                (item.posicao[0] + deslocamento_painel, item.posicao[1]),
                item.tamanho,
                item.cor,
            )
        )

    itens.append(
        ItemTexto(
            "q sair   r reiniciar   1-4 trocar algoritmo",
            (deslocamento_painel + 12, composicao.shape[0] - 24),
            13,
            COR_APAGADA,
        )
    )

    return pincel.escrever(composicao, itens)
