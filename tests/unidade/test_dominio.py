"""Testes das entidades e do tipo Result."""

from __future__ import annotations

import numpy as np
import pytest

from cardiocam.dominio.config import ConfiguracaoAnalise
from cardiocam.dominio.erros import (
    BandaInvalida,
    ErroCardiocam,
    FrequenciaAmostragemInvalida,
    JanelaInsuficiente,
    RostoNaoEncontrado,
    SinalSemQualidade,
)
from cardiocam.dominio.estimativa import Confianca, Espectro, EstimativaBPM
from cardiocam.dominio.resultado import Falha, Ok, tentar
from cardiocam.dominio.sinal import BandaCardiaca, SerieRGB, SinalPulso
from tests.conftest import TAXAS_QUADROS


# --------------------------------------------------------------------------
# Resultado
# --------------------------------------------------------------------------
@pytest.mark.parametrize("valor", (0, 1, -3, 3.14, "texto", [1, 2], {"a": 1}, None))
def test_ok_carrega_o_valor(valor: object) -> None:
    resultado = Ok(valor)
    assert resultado.ok and not resultado.falhou
    assert resultado.desempacotar() == valor or valor is None


@pytest.mark.parametrize(
    "erro",
    (
        JanelaInsuficiente(5, 10),
        RostoNaoEncontrado(),
        BandaInvalida("banda ruim"),
        FrequenciaAmostragemInvalida(5.0, 8.0),
        SinalSemQualidade(-2.0, 0.0),
    ),
)
def test_falha_carrega_o_erro(erro: ErroCardiocam) -> None:
    resultado: Falha = Falha(erro)
    assert resultado.falhou and not resultado.ok
    assert resultado.erro is erro
    with pytest.raises(ErroCardiocam):
        resultado.desempacotar()


@pytest.mark.parametrize("entrada,esperado", ((1, 2), (10, 20), (-4, -8)))
def test_mapear_transforma_apenas_o_sucesso(entrada: int, esperado: int) -> None:
    assert Ok(entrada).mapear(lambda x: x * 2).desempacotar() == esperado
    falha = Falha(RostoNaoEncontrado())
    assert falha.mapear(lambda x: x * 2).falhou


@pytest.mark.parametrize("entrada", (1, 5, 9))
def test_encadear_propaga_a_falha(entrada: int) -> None:
    assert Ok(entrada).encadear(lambda x: Ok(x + 1)).desempacotar() == entrada + 1
    assert Ok(entrada).encadear(lambda x: Falha(RostoNaoEncontrado())).falhou
    assert Falha(RostoNaoEncontrado()).encadear(lambda x: Ok(x)).falhou


@pytest.mark.parametrize("padrao", (0, -1, "reserva"))
def test_ou_entao_usa_o_padrao_somente_na_falha(padrao: object) -> None:
    assert Ok(42).ou_entao(padrao) == 42
    assert Falha(RostoNaoEncontrado()).ou_entao(padrao) == padrao


def test_tentar_captura_excecao_como_falha() -> None:
    def explode() -> int:
        raise ValueError("problema na biblioteca")

    resultado = tentar(explode, RostoNaoEncontrado())
    assert resultado.falhou
    assert isinstance(resultado.erro.__cause__, ValueError)


def test_tentar_devolve_ok_quando_nao_ha_excecao() -> None:
    assert tentar(lambda: 7, RostoNaoEncontrado()).desempacotar() == 7


# --------------------------------------------------------------------------
# Banda cardíaca
# --------------------------------------------------------------------------
@pytest.mark.parametrize(
    "minima,maxima", ((0.7, 4.0), (0.5, 3.0), (1.0, 2.0), (0.8, 3.5))
)
def test_banda_valida_converte_para_bpm(minima: float, maxima: float) -> None:
    banda = BandaCardiaca(minima, maxima)
    assert banda.minima_bpm == pytest.approx(minima * 60)
    assert banda.maxima_bpm == pytest.approx(maxima * 60)


@pytest.mark.parametrize(
    "minima,maxima", ((0.0, 4.0), (-1.0, 4.0), (4.0, 4.0), (4.0, 1.0))
)
def test_banda_invalida_e_rejeitada(minima: float, maxima: float) -> None:
    with pytest.raises(BandaInvalida):
        BandaCardiaca(minima, maxima)


@pytest.mark.parametrize("bpm", (42.0, 60.0, 100.0, 180.0, 240.0))
def test_bpm_dentro_da_banda_padrao(bpm: float) -> None:
    assert BandaCardiaca().contem_bpm(bpm)


@pytest.mark.parametrize("bpm", (10.0, 30.0, 41.0, 241.0, 400.0))
def test_bpm_fora_da_banda_padrao(bpm: float) -> None:
    assert not BandaCardiaca().contem_bpm(bpm)


@pytest.mark.parametrize("hz", (0.7, 1.0, 2.5, 4.0))
def test_frequencia_dentro_da_banda(hz: float) -> None:
    assert BandaCardiaca().contem_hz(hz)


@pytest.mark.parametrize("fps", (8.0, 10.0, 15.0, 30.0, 60.0))
def test_fps_suficiente_e_aceito(fps: float) -> None:
    BandaCardiaca().validar_fps(fps)


@pytest.mark.parametrize("fps", (1.0, 4.0, 7.0, 7.99))
def test_fps_insuficiente_e_rejeitado(fps: float) -> None:
    with pytest.raises(FrequenciaAmostragemInvalida):
        BandaCardiaca().validar_fps(fps)


def test_fps_minimo_e_o_dobro_da_frequencia_maxima() -> None:
    assert BandaCardiaca(0.7, 4.0).fps_minimo() == pytest.approx(8.0)


# --------------------------------------------------------------------------
# SerieRGB
# --------------------------------------------------------------------------
@pytest.mark.parametrize("tamanho", (2, 10, 100, 500))
@pytest.mark.parametrize("fps", (15.0, 30.0, 60.0))
def test_serie_calcula_duracao(tamanho: int, fps: float) -> None:
    serie = SerieRGB(np.zeros(tamanho), np.zeros(tamanho), np.zeros(tamanho), fps)
    assert len(serie) == tamanho
    assert serie.duracao_s == pytest.approx(tamanho / fps)


@pytest.mark.parametrize("tamanho", (5, 50, 200))
def test_serie_gera_instantes_uniformes_quando_omitidos(tamanho: int) -> None:
    serie = SerieRGB(np.zeros(tamanho), np.zeros(tamanho), np.zeros(tamanho), 30.0)
    assert np.allclose(np.diff(serie.instantes), 1 / 30.0)


def test_serie_rejeita_canais_de_tamanhos_diferentes() -> None:
    with pytest.raises(ValueError):
        SerieRGB(np.zeros(10), np.zeros(9), np.zeros(10), 30.0)


@pytest.mark.parametrize("fps", (0.0, -1.0, -30.0))
def test_serie_rejeita_fps_nao_positivo(fps: float) -> None:
    with pytest.raises(ValueError):
        SerieRGB(np.zeros(10), np.zeros(10), np.zeros(10), fps)


def test_serie_rejeita_instantes_incompativeis() -> None:
    with pytest.raises(ValueError):
        SerieRGB(np.zeros(10), np.zeros(10), np.zeros(10), 30.0, np.zeros(5))


@pytest.mark.parametrize("tamanho", (10, 60, 300))
def test_matriz_tem_tres_linhas_na_ordem_rgb(tamanho: int) -> None:
    vermelho = np.full(tamanho, 1.0)
    verde = np.full(tamanho, 2.0)
    azul = np.full(tamanho, 3.0)
    matriz = SerieRGB(vermelho, verde, azul, 30.0).como_matriz()
    assert matriz.shape == (3, tamanho)
    assert np.all(matriz[0] == 1.0) and np.all(matriz[1] == 2.0) and np.all(matriz[2] == 3.0)


@pytest.mark.parametrize("tamanho", (10, 100))
def test_ida_e_volta_pela_matriz(tamanho: int) -> None:
    gerador = np.random.default_rng(0)
    original = SerieRGB(
        gerador.standard_normal(tamanho),
        gerador.standard_normal(tamanho),
        gerador.standard_normal(tamanho),
        30.0,
    )
    recuperada = SerieRGB.de_matriz(original.como_matriz(), 30.0)
    assert np.allclose(recuperada.verde, original.verde)


def test_de_matriz_rejeita_numero_errado_de_linhas() -> None:
    with pytest.raises(ValueError):
        SerieRGB.de_matriz(np.zeros((2, 10)), 30.0)


@pytest.mark.parametrize("pedido,esperado", ((5, 5), (50, 50), (500, 100)))
def test_ultimos_recorta_a_cauda(pedido: int, esperado: int) -> None:
    serie = SerieRGB(np.arange(100.0), np.arange(100.0), np.arange(100.0), 30.0)
    recorte = serie.ultimos(pedido)
    assert len(recorte) == esperado
    assert recorte.verde[-1] == 99.0


# --------------------------------------------------------------------------
# SinalPulso
# --------------------------------------------------------------------------
@pytest.mark.parametrize("fps", TAXAS_QUADROS)
def test_pulso_calcula_duracao(fps: float) -> None:
    pulso = SinalPulso(np.zeros(300), fps, "teste")
    assert pulso.duracao_s == pytest.approx(300 / fps)


def test_pulso_rejeita_matriz() -> None:
    with pytest.raises(ValueError):
        SinalPulso(np.zeros((2, 10)), 30.0)


@pytest.mark.parametrize("fps", (0.0, -5.0))
def test_pulso_rejeita_fps_nao_positivo(fps: float) -> None:
    with pytest.raises(ValueError):
        SinalPulso(np.zeros(10), fps)


@pytest.mark.parametrize("media,desvio", ((0.0, 1.0), (10.0, 3.0), (-5.0, 0.5)))
def test_pulso_normalizado(media: float, desvio: float) -> None:
    amostras = np.random.default_rng(1).standard_normal(400) * desvio + media
    normalizado = SinalPulso(amostras, 30.0).normalizado()
    assert abs(float(np.mean(normalizado))) < 1e-9
    assert abs(float(np.std(normalizado)) - 1.0) < 1e-9


def test_pulso_constante_normaliza_para_zeros() -> None:
    assert np.all(SinalPulso(np.full(50, 3.0), 30.0).normalizado() == 0.0)


# --------------------------------------------------------------------------
# Estimativa e confiança
# --------------------------------------------------------------------------
@pytest.mark.parametrize(
    "snr,esperado",
    (
        (20.0, Confianca.ALTA),
        (6.0, Confianca.ALTA),
        (5.9, Confianca.MEDIA),
        (2.0, Confianca.MEDIA),
        (1.9, Confianca.BAIXA),
        (0.0, Confianca.BAIXA),
        (-0.1, Confianca.DESCARTADA),
        (-30.0, Confianca.DESCARTADA),
    ),
)
def test_classificacao_de_confianca(snr: float, esperado: Confianca) -> None:
    assert Confianca.de_snr(snr) is esperado


@pytest.mark.parametrize("hz", (0.7, 1.0, 1.2, 2.0, 3.0, 4.0))
def test_estimativa_converte_hertz_para_bpm(hz: float) -> None:
    estimativa = EstimativaBPM.criar(hz, 10.0, "pos", 10.0)
    assert estimativa.bpm == pytest.approx(hz * 60.0)
    assert estimativa.frequencia_hz == pytest.approx(hz)


@pytest.mark.parametrize("snr,aproveitavel", ((10.0, True), (0.5, True), (-1.0, False)))
def test_estimativa_aproveitavel(snr: float, aproveitavel: bool) -> None:
    assert EstimativaBPM.criar(1.2, snr, "pos", 10.0).aproveitavel is aproveitavel


@pytest.mark.parametrize("tamanho", (0, 1, 10, 100))
def test_espectro_converte_para_bpm(tamanho: int) -> None:
    frequencias = np.linspace(0.7, 4.0, tamanho) if tamanho else np.zeros(0)
    espectro = Espectro(frequencias, np.ones(tamanho))
    assert np.allclose(espectro.bpm, frequencias * 60.0)


# --------------------------------------------------------------------------
# Configuração
# --------------------------------------------------------------------------
@pytest.mark.parametrize("fps", TAXAS_QUADROS)
@pytest.mark.parametrize("janela", (5.0, 8.0, 10.0, 15.0, 20.0))
def test_amostras_por_janela(fps: float, janela: float) -> None:
    config = ConfiguracaoAnalise(janela_s=janela)
    assert config.amostras_por_janela(fps) == max(2, round(janela * fps))


@pytest.mark.parametrize("fps", TAXAS_QUADROS)
@pytest.mark.parametrize("passo", (0.5, 1.0, 2.0))
def test_amostras_por_passo(fps: float, passo: float) -> None:
    config = ConfiguracaoAnalise(passo_s=passo)
    assert config.amostras_por_passo(fps) == max(1, round(passo * fps))


def test_amostras_por_janela_nunca_e_menor_que_dois() -> None:
    assert ConfiguracaoAnalise(janela_s=0.001).amostras_por_janela(1.0) == 2


@pytest.mark.parametrize("algoritmo", ("verde", "chrom", "pos", "ica"))
def test_configuracao_com_cria_copia(algoritmo: str) -> None:
    original = ConfiguracaoAnalise()
    alterada = original.com(algoritmo=algoritmo)
    assert alterada.algoritmo == algoritmo
    assert original.algoritmo == "pos"
    assert alterada is not original
