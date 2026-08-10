"""POS: projeção no plano ortogonal à pele.

Wang, den Brinker, Stuijk e de Haan (2017) refinam a ideia do CHROM. Em vez de
escolher coeficientes fixos calibrados para um tom de pele médio, eles definem
um plano no espaço RGB que é ortogonal à direção do tom de pele. Qualquer
variação puramente de intensidade (a pessoa se move para uma região mais clara,
a lâmpada oscila) desloca a cor ao longo dessa direção, e ao projetar no plano
ortogonal ela simplesmente desaparece.

A projeção é fixa e não depende de calibração:

    S1 =        G - B
    S2 = -2R +  G + B

O sinal final é S1 + (σ(S1)/σ(S2))·S2, com o peso escolhido para cancelar o que
sobrou de distorção.

Dois detalhes de implementação importam. O primeiro é que a normalização é feita
em sub-janelas curtas de cerca de 1,6 s deslizando sobre o sinal, não sobre a
janela inteira: assim a suposição de tom de pele constante só precisa valer por
um instante. O segundo é a soma com sobreposição das sub-janelas, que faz as
bordas de uma compensarem as da outra.

Na prática é o método mais confiável dos quatro aqui, e por isso é o padrão.
"""

from __future__ import annotations

import numpy as np

from cardiocam.dominio.config import ConfiguracaoAnalise
from cardiocam.dominio.resultado import Resultado
from cardiocam.dominio.sinal import SerieRGB, SinalPulso
from cardiocam.rppg.base import finalizar

JANELA_POS_S = 1.6

# Linhas da matriz de projeção no plano ortogonal ao tom de pele.
PROJECAO = np.array([[0.0, 1.0, -1.0], [-2.0, 1.0, 1.0]], dtype=float)


def _combinar(bloco: np.ndarray) -> np.ndarray:
    """Aplica a projeção e a combinação ponderada a um bloco 3xL."""
    media = bloco.mean(axis=1, keepdims=True)
    media = np.where(np.abs(media) < 1e-12, 1.0, media)
    normalizado = bloco / media

    projetado = PROJECAO @ normalizado
    desvio_segundo = float(np.std(projetado[1]))
    if desvio_segundo > 1e-12:
        alfa = float(np.std(projetado[0])) / desvio_segundo
    else:
        alfa = 0.0

    combinado = projetado[0] + alfa * projetado[1]
    combinado = combinado - float(np.mean(combinado))
    desvio = float(np.std(combinado))
    return combinado / desvio if desvio > 1e-12 else combinado


class Pos:
    """Extração de pulso por projeção ortogonal ao plano da pele."""

    nome = "pos"

    def __init__(self, janela_s: float = JANELA_POS_S) -> None:
        if janela_s <= 0:
            raise ValueError("A sub-janela do POS precisa ser positiva.")
        self.janela_s = janela_s

    def extrair(
        self, serie: SerieRGB, config: ConfiguracaoAnalise
    ) -> Resultado[SinalPulso]:
        matriz = serie.como_matriz()
        total = matriz.shape[1]
        comprimento = max(2, int(round(self.janela_s * serie.fps)))

        if total <= comprimento:
            # Janela curta demais para deslizar: aplica a projeção uma única vez.
            return finalizar(_combinar(matriz), serie, config, self.nome)

        acumulado = np.zeros(total, dtype=float)
        for fim in range(comprimento, total + 1):
            inicio = fim - comprimento
            acumulado[inicio:fim] += _combinar(matriz[:, inicio:fim])

        return finalizar(acumulado, serie, config, self.nome)
