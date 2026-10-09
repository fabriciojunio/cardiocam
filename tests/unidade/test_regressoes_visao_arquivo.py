"""Regressões de movimento, segmentação e tempo de vídeos."""

import cv2
import numpy as np
import pytest

from cardiocam.fontes.arquivo import FonteArquivo
from cardiocam.visao.extrator import ExtratorRGB
from cardiocam.visao.geometria import Retangulo
from cardiocam.visao.olhos import Olhos


class DetectorDeOlhosControlado:
    def __init__(self):
        self.chamadas = 0

    def detectar(self, quadro, caixa):
        self.chamadas += 1
        return Olhos((70, 70), (110, 70)) if self.chamadas == 1 else None


def test_regioes_acompanham_translacao_do_rosto():
    quadro = np.full((300, 400, 3), (150, 175, 205), dtype=np.uint8)
    extrator = ExtratorRGB(intervalo_mascara=30)
    extrator._detector_olhos = DetectorDeOlhosControlado()
    inicial = extrator.extrair(quadro, Retangulo(30, 20, 120, 160)).desempacotar()
    atual = extrator.extrair(quadro, Retangulo(130, 50, 120, 160)).desempacotar()
    for a, b in zip(inicial.regioes, atual.regioes):
        assert b.x - a.x == 100
        assert b.y - a.y == 30
        assert b.largura == a.largura


def test_regioes_acompanham_escala_do_rosto():
    quadro = np.full((600, 600, 3), (150, 175, 205), dtype=np.uint8)
    extrator = ExtratorRGB()
    extrator._detector_olhos = DetectorDeOlhosControlado()
    inicial = extrator.extrair(quadro, Retangulo(30, 20, 120, 160)).desempacotar()
    atual = extrator.extrair(quadro, Retangulo(60, 40, 240, 320)).desempacotar()
    assert atual.regioes[0].largura == pytest.approx(2 * inicial.regioes[0].largura, abs=1)


def test_redeteccao_falha_descarta_olhos_antigos():
    quadro = np.full((300, 400, 3), (150, 175, 205), dtype=np.uint8)
    extrator = ExtratorRGB(intervalo_mascara=1)
    extrator._detector_olhos = DetectorDeOlhosControlado()
    for _ in range(3):
        extrator.extrair(quadro, Retangulo(30, 20, 120, 160))
    assert extrator._olhos is None
    assert not extrator.usou_olhos


@pytest.mark.parametrize("mascara", [True, False])
def test_alternativa_sem_pele_nao_declara_pele(mascara):
    quadro = np.full((200, 200, 3), (255, 0, 0), dtype=np.uint8)
    extrator = ExtratorRGB(usar_mascara_pele=mascara, ancorar_nos_olhos=False)
    amostra = extrator.extrair(quadro, Retangulo(0, 0, 200, 200)).desempacotar()
    assert amostra.pixels_usados > 50
    assert amostra.proporcao_pele == 0


class CapturaControlada:
    def __init__(self, tempos):
        self.tempos = tempos
        self.indice = -1

    def read(self):
        self.indice += 1
        return (True, np.zeros((10, 10, 3), np.uint8)) if self.indice < len(self.tempos) else (False, None)

    def get(self, propriedade):
        assert propriedade == cv2.CAP_PROP_POS_MSEC
        assert self.indice >= 0, "A posição deve ser lida após o quadro."
        return self.tempos[self.indice]


@pytest.mark.parametrize("tempos,esperados", [
    ([0, 100, 250, 450], [0, .1, .25, .45]),
    ([0, 0, 0, 0], [0, .1, .2, .3]),
    ([0, 100, 100, 50], [0, .1, .2, .3]),
    ([float("nan")] * 4, [0, .1, .2, .3]),
])
def test_timestamps_da_captura_sao_atuais_e_monotonicos(tempos, esperados):
    fonte = FonteArquivo("nao_usado.avi")
    fonte.fps = 10
    fonte._captura = CapturaControlada(tempos)
    assert [t for _, t in fonte.quadros()] == pytest.approx(esperados)
