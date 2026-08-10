"""Testes do filtro passa-faixa.

A propriedade que realmente importa é a de um filtro: deixar passar o que está
dentro da banda e atenuar o que está fora. Testamos isso medindo a amplitude que
sobra de senoides em dezenas de frequências, e não inspecionando coeficientes.
"""

from __future__ import annotations

import numpy as np
import pytest
from scipy import signal as scipy_signal

from cardiocam.dominio.erros import BandaInvalida, JanelaInsuficiente
from cardiocam.dominio.sinal import BandaCardiaca
from cardiocam.sinais.filtros import (
    amostras_minimas,
    aplicar_passa_faixa,
    media_movel,
    projetar_passa_faixa,
    resposta_em_frequencia,
)
from tests.conftest import ORDENS_FILTRO, TAXAS_QUADROS, senoide

FREQUENCIAS_NA_BANDA = tuple(np.round(np.arange(0.80, 3.81, 0.10), 2))
FREQUENCIAS_FORA_BAIXAS = (0.02, 0.05, 0.08, 0.10, 0.15, 0.20, 0.25, 0.30)
FREQUENCIAS_FORA_ALTAS = (5.5, 6.0, 6.5, 7.0)

# Um Butterworth de ordem 4 não corta a pique: entre 4,0 e 5,5 Hz existe a
# região de transição, onde a atenuação já é grande mas ainda não é total. A
# suíte trata as duas regiões separadamente para não cobrar do filtro um
# comportamento que nenhum filtro realizável tem.
FREQUENCIAS_DE_TRANSICAO = (4.3, 4.6, 5.0)


@pytest.mark.parametrize("fps", TAXAS_QUADROS)
@pytest.mark.parametrize("ordem", ORDENS_FILTRO)
def test_projeto_do_filtro_gera_secoes_validas(fps: float, ordem: int) -> None:
    sos = projetar_passa_faixa(BandaCardiaca(), fps, ordem)
    # Passa-faixa dobra a ordem: cada seção de segunda ordem cobre um par de polos.
    assert sos.shape == (ordem, 6)
    assert np.all(np.isfinite(sos))


@pytest.mark.parametrize("frequencia", FREQUENCIAS_NA_BANDA)
def test_ganho_dentro_da_banda_preserva_amplitude(frequencia: float) -> None:
    frequencias, ganho = resposta_em_frequencia(BandaCardiaca(), 30.0, 4)
    medido = float(np.interp(frequencia, frequencias, ganho))
    assert medido > 0.5, f"a banda deveria passar {frequencia} Hz, ganho {medido:.3f}"


@pytest.mark.parametrize("frequencia", FREQUENCIAS_FORA_BAIXAS)
def test_ganho_abaixo_da_banda_e_desprezivel(frequencia: float) -> None:
    frequencias, ganho = resposta_em_frequencia(BandaCardiaca(), 30.0, 4)
    assert float(np.interp(frequencia, frequencias, ganho)) < 0.05


@pytest.mark.parametrize("frequencia", FREQUENCIAS_FORA_ALTAS)
def test_ganho_acima_da_banda_e_desprezivel(frequencia: float) -> None:
    frequencias, ganho = resposta_em_frequencia(BandaCardiaca(), 30.0, 4)
    assert float(np.interp(frequencia, frequencias, ganho)) < 0.05


@pytest.mark.parametrize(
    "frequencia,limite", ((4.3, 0.40), (4.6, 0.25), (5.0, 0.10))
)
def test_regiao_de_transicao_atenua_progressivamente(
    frequencia: float, limite: float
) -> None:
    """Acima do corte a atenuação cresce de forma monotônica.

    Os limites vêm da própria resposta do Butterworth de ordem 4, e não de um
    valor arbitrário: a 4,3 Hz ainda passa cerca de 29% da energia, a 5,0 Hz
    sobram 6%.
    """
    frequencias, ganho = resposta_em_frequencia(BandaCardiaca(), 30.0, 4)
    assert float(np.interp(frequencia, frequencias, ganho)) < limite


def test_atenuacao_cresce_ao_longo_da_transicao() -> None:
    frequencias, ganho = resposta_em_frequencia(BandaCardiaca(), 30.0, 4)
    valores = [
        float(np.interp(f, frequencias, ganho)) for f in FREQUENCIAS_DE_TRANSICAO
    ]
    assert all(a > b for a, b in zip(valores, valores[1:])), valores


@pytest.mark.parametrize("bpm", tuple(range(52, 212, 4)))
def test_senoide_na_banda_sobrevive_a_filtragem(bpm: float) -> None:
    entrada = senoide(bpm, fps=30.0, duracao_s=12.0)
    resultado = aplicar_passa_faixa(entrada, 30.0)
    assert resultado.ok
    saida = resultado.desempacotar()
    # Descarta as bordas, onde o transiente do prolongamento ainda aparece.
    miolo = slice(60, -60)
    razao = float(np.std(saida[miolo]) / np.std(entrada[miolo]))
    assert 0.7 < razao < 1.3, f"{bpm} bpm foi alterado demais (razão {razao:.2f})"


@pytest.mark.parametrize("frequencia_hz", (0.05, 0.10, 0.20, 0.30, 6.0, 7.0, 8.0))
def test_senoide_fora_da_banda_e_atenuada(frequencia_hz: float) -> None:
    tempos = np.arange(360) / 30.0
    entrada = np.sin(2.0 * np.pi * frequencia_hz * tempos)
    resultado = aplicar_passa_faixa(entrada, 30.0)
    assert resultado.ok
    saida = resultado.desempacotar()[60:-60]
    assert float(np.std(saida)) < 0.2 * float(np.std(entrada[60:-60]))


@pytest.mark.parametrize("fps", TAXAS_QUADROS)
def test_filtragem_preserva_o_formato_do_vetor(fps: float) -> None:
    entrada = senoide(72.0, fps=fps, duracao_s=14.0)
    resultado = aplicar_passa_faixa(entrada, fps)
    assert resultado.ok
    assert resultado.desempacotar().shape == entrada.shape


@pytest.mark.parametrize("canais", (2, 3, 5))
def test_filtragem_aceita_matriz_de_canais(canais: int) -> None:
    entrada = np.vstack([senoide(60.0 + 10 * i, duracao_s=12.0) for i in range(canais)])
    resultado = aplicar_passa_faixa(entrada, 30.0)
    assert resultado.ok
    assert resultado.desempacotar().shape == entrada.shape


@pytest.mark.parametrize("amostras", (0, 1, 5, 10, 20, 26))
def test_janela_curta_devolve_falha_em_vez_de_explodir(amostras: int) -> None:
    resultado = aplicar_passa_faixa(np.ones(amostras), 30.0)
    assert resultado.falhou
    assert isinstance(resultado.erro, JanelaInsuficiente)


@pytest.mark.parametrize("fps", (1.0, 2.0, 4.0, 6.0, 7.9))
def test_taxa_abaixo_de_nyquist_devolve_falha(fps: float) -> None:
    resultado = aplicar_passa_faixa(np.zeros(300), fps)
    assert resultado.falhou
    assert isinstance(resultado.erro, (BandaInvalida, JanelaInsuficiente))


@pytest.mark.parametrize("ordem", (0, -1, -5))
def test_ordem_invalida_e_rejeitada(ordem: int) -> None:
    with pytest.raises(BandaInvalida):
        projetar_passa_faixa(BandaCardiaca(), 30.0, ordem)


@pytest.mark.parametrize("ordem", ORDENS_FILTRO)
def test_amostras_minimas_bate_com_a_exigencia_da_scipy(ordem: int) -> None:
    sos = projetar_passa_faixa(BandaCardiaca(), 30.0, ordem)
    minimo = amostras_minimas(sos)
    # Com o mínimo declarado a SciPy aceita; com um a menos, recusa.
    scipy_signal.sosfiltfilt(sos, np.zeros(minimo))
    with pytest.raises(ValueError):
        scipy_signal.sosfiltfilt(sos, np.zeros(minimo - 1))


@pytest.mark.parametrize("bpm", (50.0, 72.0, 100.0, 150.0))
@pytest.mark.parametrize("ordem", ORDENS_FILTRO)
def test_filtro_nao_desloca_a_fase(bpm: float, ordem: int) -> None:
    """A filtragem bidirecional precisa manter os picos onde estavam.

    É o que garante que a contagem de batimentos e a variabilidade não fiquem
    enviesadas por atraso de grupo.
    """
    entrada = senoide(bpm, fps=30.0, duracao_s=16.0)
    resultado = aplicar_passa_faixa(entrada, 30.0, ordem=ordem)
    assert resultado.ok
    saida = resultado.desempacotar()

    miolo = slice(90, -90)
    correlacao = float(
        np.corrcoef(entrada[miolo], saida[miolo])[0, 1]
    )
    assert correlacao > 0.99, f"correlação {correlacao:.4f} indica deslocamento"


@pytest.mark.parametrize("ordem", ORDENS_FILTRO)
def test_ordem_maior_atenua_mais_fora_da_banda(ordem: int) -> None:
    frequencias, ganho = resposta_em_frequencia(BandaCardiaca(), 30.0, ordem)
    fora = float(np.interp(6.0, frequencias, ganho))
    assert fora < 0.1


def test_ordem_crescente_estreita_a_transicao() -> None:
    ganhos = []
    for ordem in ORDENS_FILTRO:
        frequencias, ganho = resposta_em_frequencia(BandaCardiaca(), 30.0, ordem)
        ganhos.append(float(np.interp(5.0, frequencias, ganho)))
    assert all(a >= b for a, b in zip(ganhos, ganhos[1:])), ganhos


@pytest.mark.parametrize("tamanho", (1, 3, 5, 9, 15, 31, 61))
def test_media_movel_preserva_o_comprimento(tamanho: int) -> None:
    entrada = senoide(72.0, duracao_s=10.0)
    assert media_movel(entrada, tamanho).shape == entrada.shape


@pytest.mark.parametrize("tamanho", (3, 5, 11, 21, 41))
def test_media_movel_atenua_oscilacao_rapida(tamanho: int) -> None:
    entrada = senoide(200.0, duracao_s=10.0)
    suavizado = media_movel(entrada, tamanho)
    assert float(np.std(suavizado)) < float(np.std(entrada))


@pytest.mark.parametrize("constante", (-5.0, 0.0, 1.0, 100.0))
def test_media_movel_de_sinal_constante_e_o_proprio(constante: float) -> None:
    entrada = np.full(200, constante)
    assert np.allclose(media_movel(entrada, 11), entrada)


@pytest.mark.parametrize("tamanho", (0, -1, -10))
def test_media_movel_rejeita_tamanho_nao_positivo(tamanho: int) -> None:
    with pytest.raises(ValueError):
        media_movel(np.zeros(10), tamanho)


def test_media_movel_de_vetor_vazio_nao_quebra() -> None:
    assert media_movel(np.zeros(0), 5).size == 0


@pytest.mark.parametrize("fps", TAXAS_QUADROS)
def test_resposta_em_frequencia_cobre_ate_nyquist(fps: float) -> None:
    frequencias, ganho = resposta_em_frequencia(BandaCardiaca(), fps, 4)
    assert frequencias[0] >= 0.0
    assert np.isclose(frequencias[-1], fps / 2.0, rtol=0.01)
    assert np.all(ganho >= 0.0)


@pytest.mark.parametrize(
    "minima,maxima", ((0.7, 4.0), (0.8, 3.0), (1.0, 2.5), (0.75, 3.5))
)
def test_banda_personalizada_e_respeitada(minima: float, maxima: float) -> None:
    banda = BandaCardiaca(minima, maxima)
    frequencias, ganho = resposta_em_frequencia(banda, 30.0, 4)
    centro = (minima + maxima) / 2.0
    assert float(np.interp(centro, frequencias, ganho)) > 0.7
    assert float(np.interp(minima / 3.0, frequencias, ganho)) < 0.2


def test_entrada_vazia_devolve_falha() -> None:
    assert aplicar_passa_faixa(np.zeros(0), 30.0).falhou
