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
from cardiocam.visao.fundo import media_do_fundo
from cardiocam.visao.geometria import Retangulo
from cardiocam.visao.olhos import DetectorOlhos, Olhos, regioes_ancoradas
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
    fundo: tuple[float, float, float] | None = None
    """Média RGB do fundo neste quadro, quando houve fundo utilizável."""

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
        medir_fundo: bool = True,
        intervalo_mascara: int = 30,
        ancorar_nos_olhos: bool = True,
    ) -> None:
        """
        `percentil_descarte` corta os pixels mais claros e mais escuros de cada
        região. Reflexo especular e sombra dura entram nessas caudas e não
        acompanham o pulso.

        `intervalo_mascara` é de quantos em quantos quadros a seleção de pixels
        é recalculada. Reaproveitar a seleção é o que garante que a média seja
        sempre sobre o mesmo conjunto de pixels, e isso importa muito mais do
        que parece: com o rosto real, os pixels de borda entram e saem da
        máscara a cada quadro por causa do ruído do sensor, e essa troca de
        conjunto vira ruído no sinal. Medido sobre um recorte de pele com
        textura, pelos e sombra, congelar a seleção rendeu 3,7 dB.

        Num rosto sintético de cor uniforme o efeito é invisível, que é
        exatamente por que ele passou despercebido por muito tempo.
        """
        if not 0.0 <= percentil_descarte < 50.0:
            raise ValueError("O percentil de descarte precisa estar entre 0 e 50.")
        self.regiao = RegiaoInteresse(regiao)
        self.usar_mascara_pele = usar_mascara_pele
        self.percentil_descarte = percentil_descarte
        self.pixels_minimos = pixels_minimos
        self.medir_fundo = medir_fundo
        self.intervalo_mascara = max(1, intervalo_mascara)
        self._selecoes: dict[int, tuple[tuple[int, int], np.ndarray]] = {}
        self._contador = 0

        self.ancorar_nos_olhos = ancorar_nos_olhos
        self._detector_olhos: DetectorOlhos | None = None
        if ancorar_nos_olhos:
            try:
                self._detector_olhos = DetectorOlhos()
            except RuntimeError:  # pragma: sem cobertura
                self._detector_olhos = None
        self._olhos: Olhos | None = None
        self.usou_olhos = False

    def reiniciar(self) -> None:
        """Esquece as seleções memorizadas. Chamado quando o rosto se perde."""
        self._selecoes.clear()
        self._olhos = None
        self._contador = 0

    def _regioes_para(
        self, quadro: np.ndarray, caixa_rosto: Retangulo
    ) -> list[Retangulo]:
        """Regiões a medir, ancoradas nos olhos quando possível.

        A posição dos olhos é redetectada de tempos em tempos, e não a cada
        quadro, por dois motivos: custa caro e oscila. Entre uma detecção e
        outra, as regiões ficam paradas, o que também ajuda a média a ser sempre
        sobre os mesmos pixels.
        """
        altura, largura = quadro.shape[:2]

        # A âncora nos olhos entrega testa e bochechas. Quando alguém pediu
        # explicitamente outro conjunto de regiões, essa escolha manda.
        pode_ancorar = self.regiao is RegiaoInteresse.TESTA_E_BOCHECHAS

        if pode_ancorar and self._detector_olhos is not None:
            if self._olhos is None or self._contador % (self.intervalo_mascara * 2) == 0:
                encontrados = self._detector_olhos.detectar(quadro, caixa_rosto)
                if encontrados is not None:
                    self._olhos = encontrados
            if self._olhos is not None:
                regioes = regioes_ancoradas(self._olhos, largura, altura)
                if len(regioes) == 3:
                    self.usou_olhos = True
                    return regioes

        # Sem olhos confiáveis, cai nas proporções da caixa do rosto.
        self.usou_olhos = False
        return [
            regiao.limitar(largura, altura)
            for regiao in regioes_de(caixa_rosto, self.regiao)
        ]

    def _selecao_estavel(self, recorte: np.ndarray, indice: int) -> np.ndarray | None:
        """Índice booleano dos pixels a promediar, reaproveitado entre quadros.

        Recalcula quando o recorte muda de tamanho, o que acontece quando o
        rosto se aproxima ou se afasta, e periodicamente, para acompanhar
        mudanças lentas de postura e de iluminação.
        """
        forma = (recorte.shape[0], recorte.shape[1])
        memorizado = self._selecoes.get(indice)
        precisa_recalcular = (
            memorizado is None
            or memorizado[0] != forma
            or self._contador % self.intervalo_mascara == 0
        )

        if not precisa_recalcular:
            return memorizado[1]

        planos = recorte.reshape(-1, 3).astype(float)
        selecao = np.ones(planos.shape[0], dtype=bool)

        if self.usar_mascara_pele:
            pele = mascara_pele(recorte).reshape(-1)
            if int(np.count_nonzero(pele)) >= self.pixels_minimos:
                selecao = pele

        if self.percentil_descarte > 0 and int(np.count_nonzero(selecao)) > self.pixels_minimos:
            referencia = planos[:, 1]
            valores = referencia[selecao]
            inferior = np.percentile(valores, self.percentil_descarte)
            superior = np.percentile(valores, 100.0 - self.percentil_descarte)
            candidata = selecao & (referencia >= inferior) & (referencia <= superior)
            if int(np.count_nonzero(candidata)) >= self.pixels_minimos:
                selecao = candidata

        if int(np.count_nonzero(selecao)) < self.pixels_minimos:
            return None

        self._selecoes[indice] = (forma, selecao)
        return selecao

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

        regioes = [r for r in self._regioes_para(quadro, caixa_rosto) if not r.vazio]
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
        for indice, regiao in enumerate(regioes):
            recorte = regiao.recortar(quadro)
            if recorte.size == 0:
                continue
            area_total += recorte.shape[0] * recorte.shape[1]
            selecao = self._selecao_estavel(recorte, indice)
            if selecao is None:
                continue
            selecionados = recorte.reshape(-1, 3).astype(float)[selecao]
            if selecionados.shape[0] > 0:
                acumulado.append(selecionados)
                pixels_pele += selecionados.shape[0]
        self._contador += 1

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
        fundo = media_do_fundo(quadro, caixa_rosto) if self.medir_fundo else None
        return Ok(
            AmostraQuadro(
                vermelho=float(vermelho),
                verde=float(verde),
                azul=float(azul),
                pixels_usados=int(pixels.shape[0]),
                proporcao_pele=float(pixels_pele / area_total) if area_total else 0.0,
                regioes=tuple(regioes),
                fundo=fundo,
            )
        )
