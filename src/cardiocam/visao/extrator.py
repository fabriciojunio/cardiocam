"""A ponte entre imagem e sinal: cada quadro vira três números.

Milhões de pixels são reduzidos à média de cada canal sobre a pele visível. Essa
média espacial é, ela própria, um filtro poderoso: o ruído de leitura do sensor
é aproximadamente independente entre pixels, então promediar N pixels reduz o
desvio do ruído por um fator de raiz de N. É por isso que uma variação de
intensidade da ordem de 0,1% consegue emergir do ruído de uma webcam comum.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from cardiocam.dominio.erros import RegiaoInvalida
from cardiocam.dominio.resultado import Falha, Ok, Resultado
from cardiocam.visao.geometria import Retangulo
from cardiocam.visao.pele import mascara_pele
from cardiocam.visao.roi import RegiaoInteresse, regioes_de

PIXELS_MINIMOS = 50


@dataclass(frozen=True, slots=True)
class AmostraQuadro:
    """O que um único quadro contribui para a série temporal."""

    vermelho: float
    verde: float
    azul: float
    pixels_usados: int
    proporcao_pele: float
    regioes: tuple[Retangulo, ...] = ()

    def como_vetor(self) -> np.ndarray:
        return np.array([self.vermelho, self.verde, self.azul], dtype=float)


class ExtratorRGB:
    """Calcula a média RGB da pele nas regiões de interesse."""

    def __init__(
        self,
        regiao: RegiaoInteresse = RegiaoInteresse.TESTA_E_BOCHECHAS,
        usar_mascara_pele: bool = True,
        percentil_descarte: float = 5.0,
        pixels_minimos: int = PIXELS_MINIMOS,
    ) -> None:
        """
        `percentil_descarte` corta os pixels mais claros e mais escuros de cada
        região. Reflexo especular e sombra dura entram nessas caudas e não
        acompanham o pulso.
        """
        if not 0.0 <= percentil_descarte < 50.0:
            raise ValueError("O percentil de descarte precisa estar entre 0 e 50.")
        self.regiao = RegiaoInteresse(regiao)
        self.usar_mascara_pele = usar_mascara_pele
        self.percentil_descarte = percentil_descarte
        self.pixels_minimos = pixels_minimos

    def _selecionar_pixels(self, recorte: np.ndarray) -> np.ndarray:
        """Devolve os pixels válidos do recorte, no formato Nx3 (B, G, R).

        O corte por percentil usa o canal verde como referência de luminância e
        aplica a mesma seleção aos três canais. Cortar cada canal separadamente
        quebraria a correspondência entre eles, e CHROM e POS dependem
        justamente da relação entre canais no mesmo pixel.
        """
        if recorte.size == 0:
            return np.zeros((0, 3), dtype=float)

        planos = recorte.reshape(-1, 3).astype(float)

        if self.usar_mascara_pele:
            mascara = mascara_pele(recorte)
            selecionados = planos[mascara.reshape(-1)]
            # Se a segmentação foi severa demais, é melhor usar tudo do que
            # descartar a região inteira.
            if selecionados.shape[0] >= self.pixels_minimos:
                planos = selecionados

        if self.percentil_descarte > 0 and planos.shape[0] > self.pixels_minimos:
            referencia = planos[:, 1]
            inferior = np.percentile(referencia, self.percentil_descarte)
            superior = np.percentile(referencia, 100.0 - self.percentil_descarte)
            dentro = (referencia >= inferior) & (referencia <= superior)
            if np.count_nonzero(dentro) >= self.pixels_minimos:
                planos = planos[dentro]

        return planos

    def extrair(
        self, quadro: np.ndarray, caixa_rosto: Retangulo
    ) -> Resultado[AmostraQuadro]:
        """Média RGB da pele do rosto neste quadro."""
        if quadro is None or quadro.size == 0:
            return Falha(RegiaoInvalida("Quadro vazio."))
        if quadro.ndim != 3 or quadro.shape[2] != 3:
            return Falha(RegiaoInvalida("O quadro precisa ser uma imagem BGR."))

        altura, largura = quadro.shape[:2]
        regioes = [
            regiao.limitar(largura, altura)
            for regiao in regioes_de(caixa_rosto, self.regiao)
        ]
        regioes = [regiao for regiao in regioes if not regiao.vazio]
        if not regioes:
            return Falha(
                RegiaoInvalida(
                    "As regiões de interesse ficaram fora do quadro. O rosto "
                    "provavelmente está muito perto da borda da imagem."
                )
            )

        acumulado: list[np.ndarray] = []
        area_total = 0
        pixels_pele = 0
        for regiao in regioes:
            recorte = regiao.recortar(quadro)
            if recorte.size == 0:
                continue
            area_total += recorte.shape[0] * recorte.shape[1]
            selecionados = self._selecionar_pixels(recorte)
            if selecionados.shape[0] > 0:
                acumulado.append(selecionados)
                pixels_pele += selecionados.shape[0]

        if not acumulado:
            return Falha(
                RegiaoInvalida("Nenhum pixel válido nas regiões de interesse.")
            )

        pixels = np.vstack(acumulado)
        if pixels.shape[0] < self.pixels_minimos:
            return Falha(
                RegiaoInvalida(
                    f"Apenas {pixels.shape[0]} pixels válidos, abaixo do mínimo "
                    f"de {self.pixels_minimos}. Aproxime-se da câmera."
                )
            )

        azul, verde, vermelho = pixels.mean(axis=0)
        return Ok(
            AmostraQuadro(
                vermelho=float(vermelho),
                verde=float(verde),
                azul=float(azul),
                pixels_usados=int(pixels.shape[0]),
                proporcao_pele=float(pixels_pele / area_total) if area_total else 0.0,
                regioes=tuple(regioes),
            )
        )
