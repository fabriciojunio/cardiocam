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

# Faixa de crominância da pele, partindo da clássica (Chai e Ngan, 1999) e
# alargada por medição em 05/10/2026.
#
# O limite inferior de Cr era 133, o valor do artigo original. Medido num rosto
# real de tom médio sob iluminação fraca de ambiente interno, a mediana de Cr
# ficou em **130**, isto é, três unidades abaixo do corte, e apenas 9,8% dos
# pixels do rosto passavam na classificação.
#
# Isso não é defeito de um caso: a faixa clássica foi derivada de imagens bem
# iluminadas e de uma amostra pouco diversa, e é justamente o tipo de limiar que
# funciona melhor para pele clara e bem iluminada do que para o resto. Baixar o
# piso para 128 levou o acerto nesse rosto de 9,8% para 45,2%, mantendo a
# rejeição do fundo em 94,8% e sem perder nenhum dos oito tons de referência nem
# aceitar nenhuma das seis cores que a suíte exige recusar.
CR_MINIMO, CR_MAXIMO = 128, 173
CB_MINIMO, CB_MAXIMO = 77, 127

# Piso de luminância, que depende do uso da máscara. São dois, e separá-los é
# o ponto.
#
# **Para medir**, 40. Abaixo disso o pixel não carrega sinal aproveitável: a
# variação do pulso é de 0,1% a 1% da intensidade, então em luminância 20 ela
# vale entre 0,02 e 0,2 nível, e o sensor quantiza em inteiros. Incluir esses
# pixels na média só adiciona ruído. Este era o único valor que existia, e ele
# está certo para este uso.
#
# **Para localizar o rosto**, 10. Aqui o que importa é a extensão da mancha de
# pele, não a qualidade do sinal de cada pixel, e o corte em 40 era alto demais:
# medido num rosto real sob luz fraca de ambiente interno, a mediana de
# luminância ficou em 20 e a testa em 10, de modo que o corte descartava três
# quartos do rosto **antes mesmo de olhar a cor** e o localizador não achava
# rosto nenhum.
#
# A alternativa seria baixar o piso único para 10, e ela foi descartada: um
# teste existente já cobrava que pixel em sombra fechada fosse recusado, e esse
# teste está certo no que cobra. Afrouxar o piso único satisfaria a localização
# estragando a medição.
Y_MINIMO, Y_MAXIMO = 40, 250
Y_MINIMO_LOCALIZACAO = 10


def mascara_pele(
    imagem_bgr: np.ndarray,
    suavizar: bool = True,
    usar_luminancia: bool = True,
    y_minimo: int = Y_MINIMO,
) -> np.ndarray:
    """Máscara booleana dos pixels classificados como pele.

    `suavizar` aplica abertura e fechamento morfológicos, que removem pixels
    isolados e fecham buracos pequenos, deixando regiões conexas.

    `y_minimo` existe porque a máscara tem dois usos com exigências opostas. O
    padrão é o da medição, mais exigente. Para localizar o rosto, passe
    `Y_MINIMO_LOCALIZACAO`: ali interessa a extensão da mancha, e perder a parte
    escura do rosto desloca a caixa inteira.
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
        dentro &= (luminancia >= y_minimo) & (luminancia <= Y_MAXIMO)

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
