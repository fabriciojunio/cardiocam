"""Amostragem do fundo, usado como referência de iluminação.

A parede atrás da pessoa não tem pulso. Tudo que oscila nela é luz do ambiente
ou o próprio ganho da câmera se ajustando. Medir o fundo dá uma leitura direta
da perturbação, que depois é subtraída do sinal do rosto.

A amostragem usa faixas nas laterais do quadro, longe do rosto, e descarta
qualquer pixel que pareça pele: se um braço ou outra pessoa entrar na faixa,
esses pixels teriam pulso e contaminariam a referência.
"""

from __future__ import annotations

import numpy as np

from cardiocam.visao.geometria import Retangulo
from cardiocam.visao.pele import mascara_pele

LARGURA_FAIXA = 0.14
"""Fração da largura do quadro usada em cada faixa lateral."""

PIXELS_MINIMOS_FUNDO = 200


def regioes_de_fundo(
    largura: int, altura: int, caixa_rosto: Retangulo | None = None
) -> list[Retangulo]:
    """Faixas laterais que não encostam na caixa do rosto."""
    faixa = max(8, int(largura * LARGURA_FAIXA))
    candidatas = [
        Retangulo(0, 0, faixa, altura),
        Retangulo(largura - faixa, 0, faixa, altura),
    ]
    if caixa_rosto is None:
        return candidatas
    # Uma margem em torno do rosto evita pegar cabelo, ombro ou orelha.
    zona = caixa_rosto.escalar(1.35).limitar(largura, altura)
    return [r for r in candidatas if r.sobreposicao(zona) == 0.0]


def media_do_fundo(
    quadro: np.ndarray, caixa_rosto: Retangulo | None = None
) -> tuple[float, float, float] | None:
    """Média RGB dos pixels de fundo. Devolve None se não houver fundo utilizável."""
    if quadro is None or quadro.size == 0 or quadro.ndim != 3:
        return None

    altura, largura = quadro.shape[:2]
    acumulado: list[np.ndarray] = []

    for regiao in regioes_de_fundo(largura, altura, caixa_rosto):
        recorte = regiao.recortar(quadro)
        if recorte.size == 0:
            continue
        planos = recorte.reshape(-1, 3).astype(float)
        try:
            pele = mascara_pele(recorte, suavizar=False).reshape(-1)
        except ValueError:  # pragma: sem cobertura
            continue
        sem_pele = planos[~pele]
        if sem_pele.shape[0] > 0:
            acumulado.append(sem_pele)

    if not acumulado:
        return None
    pixels = np.vstack(acumulado)
    if pixels.shape[0] < PIXELS_MINIMOS_FUNDO:
        return None

    azul, verde, vermelho = pixels.mean(axis=0)
    return float(vermelho), float(verde), float(azul)
