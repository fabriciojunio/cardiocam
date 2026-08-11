"""Testes da localização dos olhos e das regiões ancoradas neles."""

from __future__ import annotations

import numpy as np
import pytest

from cardiocam.fontes.sintetica import RenderizadorRosto
from cardiocam.visao.detector_face import DetectorHaar
from cardiocam.visao.extrator import ExtratorRGB
from cardiocam.visao.geometria import Retangulo
from cardiocam.visao.olhos import DetectorOlhos, Olhos, regioes_ancoradas
from cardiocam.visao.roi import RegiaoInteresse

RESOLUCOES = ((320, 240), (400, 300), (640, 480))
TONS = ((175, 200, 230), (150, 175, 205), (105, 130, 160), (70, 90, 118))


@pytest.mark.parametrize("largura,altura", RESOLUCOES)
def test_encontra_os_dois_olhos(largura: int, altura: int) -> None:
    renderizador = RenderizadorRosto(largura=largura, altura=altura)
    quadro = renderizador.desenhar(ruido=1.0, semente=2)
    caixa = DetectorHaar().detectar(quadro).desempacotar()
    olhos = DetectorOlhos().detectar(quadro, caixa)
    assert olhos is not None


@pytest.mark.parametrize("tom", TONS)
def test_funciona_em_diferentes_tons_de_pele(tom: tuple) -> None:
    renderizador = RenderizadorRosto(tom_pele=tom)
    quadro = renderizador.desenhar(ruido=1.0, semente=3)
    caixa = DetectorHaar().detectar(quadro).desempacotar()
    assert DetectorOlhos().detectar(quadro, caixa) is not None


@pytest.mark.parametrize("largura,altura", RESOLUCOES)
def test_separacao_e_coerente_com_o_tamanho_do_rosto(largura: int, altura: int) -> None:
    renderizador = RenderizadorRosto(largura=largura, altura=altura)
    quadro = renderizador.desenhar(ruido=1.0, semente=4)
    caixa = DetectorHaar().detectar(quadro).desempacotar()
    olhos = DetectorOlhos().detectar(quadro, caixa)
    assert olhos is not None
    assert 0.22 * caixa.largura <= olhos.separacao <= 0.75 * caixa.largura


def test_quadro_sem_rosto_nao_devolve_olhos() -> None:
    vazio = np.full((240, 320, 3), 90, dtype=np.uint8)
    assert DetectorOlhos().detectar(vazio, Retangulo(50, 50, 150, 150)) is None


@pytest.mark.parametrize("quadro", (None, np.zeros((0, 0, 3), dtype=np.uint8)))
def test_quadro_invalido_nao_devolve_olhos(quadro) -> None:
    assert DetectorOlhos().detectar(quadro, Retangulo(0, 0, 10, 10)) is None


# --------------------------------------------------------------------------
# Geometria das regiões ancoradas
# --------------------------------------------------------------------------
def olhos_em(separacao: float, linha: float = 200.0, centro: float = 320.0) -> Olhos:
    return Olhos((centro - separacao / 2, linha), (centro + separacao / 2, linha))


@pytest.mark.parametrize("separacao", (40.0, 60.0, 90.0, 130.0, 180.0))
def test_a_testa_fica_acima_dos_olhos(separacao: float) -> None:
    """O defeito que motivou este módulo: a região da testa caía sobre os olhos.

    Piscar produz variação de intensidade muito maior que a do pulso, e dentro
    da banda cardíaca. Medir a região dos olhos arruína a medição.
    """
    olhos = olhos_em(separacao)
    testa = regioes_ancoradas(olhos, 640, 480)[0]
    assert testa.base < olhos.linha, "a testa invadiu a linha dos olhos"
    # E com folga: a sobrancelha fica cerca de 0,3 separações acima do olho.
    assert olhos.linha - testa.base >= 0.4 * separacao


@pytest.mark.parametrize("separacao", (40.0, 60.0, 90.0, 130.0))
def test_as_bochechas_ficam_abaixo_dos_olhos(separacao: float) -> None:
    olhos = olhos_em(separacao)
    _, esquerda, direita = regioes_ancoradas(olhos, 640, 480)
    assert esquerda.y > olhos.linha
    assert direita.y > olhos.linha


@pytest.mark.parametrize("separacao", (50.0, 80.0, 120.0))
def test_as_bochechas_nao_se_encostam_no_meio(separacao: float) -> None:
    """Entre as bochechas fica o nariz, que não deve entrar na medição."""
    olhos = olhos_em(separacao)
    _, esquerda, direita = regioes_ancoradas(olhos, 640, 480)
    assert esquerda.direita < direita.x


@pytest.mark.parametrize("separacao", (50.0, 80.0, 120.0))
def test_as_regioes_nao_se_sobrepoem(separacao: float) -> None:
    regioes = regioes_ancoradas(olhos_em(separacao), 640, 480)
    for i, primeira in enumerate(regioes):
        for segunda in regioes[i + 1 :]:
            assert primeira.sobreposicao(segunda) == 0.0


@pytest.mark.parametrize("separacao", (40.0, 70.0, 110.0, 160.0))
def test_as_regioes_escalam_com_o_rosto(separacao: float) -> None:
    testa = regioes_ancoradas(olhos_em(separacao), 900, 900)[0]
    assert testa.largura == pytest.approx(1.10 * separacao, rel=0.05)
    assert testa.altura == pytest.approx(0.50 * separacao, rel=0.05)


def test_regioes_sao_limitadas_ao_quadro() -> None:
    """Rosto encostado na borda não pode gerar região fora da imagem."""
    olhos = Olhos((20.0, 15.0), (70.0, 15.0))
    for regiao in regioes_ancoradas(olhos, 320, 240):
        assert regiao.x >= 0 and regiao.y >= 0
        assert regiao.direita <= 320 and regiao.base <= 240


# --------------------------------------------------------------------------
# Integração com o extrator
# --------------------------------------------------------------------------
@pytest.mark.parametrize("largura,altura", RESOLUCOES)
def test_extrator_usa_a_ancora_quando_encontra_os_olhos(
    largura: int, altura: int
) -> None:
    renderizador = RenderizadorRosto(largura=largura, altura=altura)
    quadro = renderizador.desenhar(ruido=1.0, semente=5)
    caixa = DetectorHaar().detectar(quadro).desempacotar()
    extrator = ExtratorRGB()
    resultado = extrator.extrair(quadro, caixa)
    assert resultado.ok
    assert extrator.usou_olhos
    assert len(resultado.desempacotar().regioes) == 3


def test_extrator_cai_nas_proporcoes_sem_olhos() -> None:
    """Sem olhos detectáveis, a medição continua, usando a caixa do rosto."""
    quadro = np.full((240, 320, 3), (150, 175, 205), dtype=np.uint8)
    extrator = ExtratorRGB()
    resultado = extrator.extrair(quadro, Retangulo(60, 40, 180, 180))
    assert resultado.ok
    assert not extrator.usou_olhos


@pytest.mark.parametrize(
    "regiao", (RegiaoInteresse.TESTA, RegiaoInteresse.BOCHECHAS, RegiaoInteresse.ROSTO_CENTRAL)
)
def test_escolha_explicita_de_regiao_desliga_a_ancora(regiao: RegiaoInteresse) -> None:
    """Quem pediu um conjunto específico de regiões deve recebê-lo."""
    renderizador = RenderizadorRosto()
    quadro = renderizador.desenhar(ruido=1.0, semente=6)
    caixa = DetectorHaar().detectar(quadro).desempacotar()
    extrator = ExtratorRGB(regiao=regiao)
    assert extrator.extrair(quadro, caixa).ok
    assert not extrator.usou_olhos


def test_ancoragem_pode_ser_desligada() -> None:
    renderizador = RenderizadorRosto()
    quadro = renderizador.desenhar(ruido=1.0, semente=7)
    caixa = DetectorHaar().detectar(quadro).desempacotar()
    extrator = ExtratorRGB(ancorar_nos_olhos=False)
    assert extrator.extrair(quadro, caixa).ok
    assert not extrator.usou_olhos


def test_reiniciar_esquece_os_olhos() -> None:
    renderizador = RenderizadorRosto()
    quadro = renderizador.desenhar(ruido=1.0, semente=8)
    caixa = DetectorHaar().detectar(quadro).desempacotar()
    extrator = ExtratorRGB()
    extrator.extrair(quadro, caixa)
    assert extrator._olhos is not None
    extrator.reiniciar()
    assert extrator._olhos is None
