"""Segmentação de pele.

Dentro da caixa do rosto entra muita coisa que não é pele: cabelo, óculos,
sobrancelha, barba, fundo nos cantos. Esses pixels não pulsam, então só diluem o
sinal. Filtrar por cor de pele aumenta bastante a relação sinal-ruído sem custo
relevante.

Trabalhamos em YCrCb porque esse espaço separa luminância (Y) de crominância
(Cr, Cb). A cor da pele humana ocupa uma faixa estreita e surpreendentemente
estável em Cr e Cb, independentemente do tom: o que muda entre pessoas de pele
clara e escura é principalmente o Y. Aplicar o limiar só na crominância torna a
segmentação bem mais justa entre tons de pele do que limiarizar em RGB.
"""

from __future__ import annotations

import cv2
import numpy as np

# Faixa clássica de crominância da pele (Chai e Ngan, 1999).
CR_MINIMO, CR_MAXIMO = 133, 173
CB_MINIMO, CB_MAXIMO = 77, 127

# Descarta pixels queimados ou totalmente escuros, onde a informação de cor
# perde o sentido.
Y_MINIMO, Y_MAXIMO = 40, 250


def mascara_pele(
    imagem_bgr: np.ndarray,
    suavizar: bool = True,
    usar_luminancia: bool = True,
) -> np.ndarray:
    """Máscara booleana dos pixels classificados como pele.

    `suavizar` aplica abertura e fechamento morfológicos, que removem pixels
    isolados e fecham buracos pequenos, deixando regiões conexas.
    """
    if imagem_bgr is None or imagem_bgr.size == 0:
        return np.zeros((0, 0), dtype=bool)
    if imagem_bgr.ndim != 3 or imagem_bgr.shape[2] != 3:
        raise ValueError("A segmentação de pele espera uma imagem BGR de três canais.")

    ycrcb = cv2.cvtColor(imagem_bgr, cv2.COLOR_BGR2YCrCb)
    luminancia, cr, cb = cv2.split(ycrcb)

    dentro = (
        (cr >= CR_MINIMO) & (cr <= CR_MAXIMO) & (cb >= CB_MINIMO) & (cb <= CB_MAXIMO)
    )
    if usar_luminancia:
        dentro &= (luminancia >= Y_MINIMO) & (luminancia <= Y_MAXIMO)

    if not suavizar:
        return dentro

    binaria = dentro.astype(np.uint8)
    nucleo = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    binaria = cv2.morphologyEx(binaria, cv2.MORPH_OPEN, nucleo)
    binaria = cv2.morphologyEx(binaria, cv2.MORPH_CLOSE, nucleo)
    return binaria.astype(bool)


def proporcao_de_pele(imagem_bgr: np.ndarray) -> float:
    """Fração de pixels de pele na imagem, de 0 a 1.

    Serve de indicador de qualidade: uma região de interesse com pouca pele
    provavelmente está desalinhada.
    """
    if imagem_bgr is None or imagem_bgr.size == 0:
        return 0.0
    mascara = mascara_pele(imagem_bgr)
    if mascara.size == 0:
        return 0.0
    return float(np.count_nonzero(mascara) / mascara.size)


def descartar_extremos(
    valores: np.ndarray, percentil: float = 5.0
) -> np.ndarray:
    """Remove as caudas da distribuição de intensidade.

    Reflexo especular (o brilho da tela na testa) e sombra dura são pixels que
    variam muito e não acompanham o pulso. Cortar os percentis extremos é uma
    forma barata de tirá-los da média.
    """
    if valores.size == 0:
        return valores
    if not 0.0 <= percentil < 50.0:
        raise ValueError("O percentil precisa estar entre 0 e 50.")
    if percentil == 0.0:
        return valores
    inferior = np.percentile(valores, percentil)
    superior = np.percentile(valores, 100.0 - percentil)
    dentro = (valores >= inferior) & (valores <= superior)
    return valores[dentro] if np.any(dentro) else valores
