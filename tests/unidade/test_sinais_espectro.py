"""Testes da análise espectral.

O critério central: dada uma senoide de frequência conhecida, o sistema precisa
devolver essa frequência. Varremos a banda inteira em passos finos, porque um
erro de interpolação do pico costuma aparecer só em algumas posições relativas
aos bins da FFT.
"""

from __future__ import annotations

import numpy as np
import pytest

from cardiocam.dominio.erros import JanelaInsuficiente
from cardiocam.dominio.sinal import BandaCardiaca, SinalPulso
from cardiocam.sinais.espectro import (
    analisar,
    periodograma,
    recortar_banda,
    refinar_pico,
    relacao_sinal_ruido,
    welch,
)
from tests.conftest import TAXAS_QUADROS, pulso_de, senoide

BPMS_FINOS = tuple(np.round(np.arange(45.0, 220.1, 2.5), 2))
BPMS_MEDIOS = tuple(range(48, 205, 6))


@pytest.mark.parametrize("bpm", BPMS_FINOS)
def test_frequencia_de_senoide_pura_e_recuperada(bpm: float) -> None:
    resultado = analisar(pulso_de(bpm, fps=30.0, duracao_s=12.0))
    assert resultado.ok
    estimado = resultado.desempacotar().bpm
    assert abs(estimado - bpm) < 1.0, f"esperado {bpm}, obtido {estimado:.2f}"


@pytest.mark.parametrize("bpm", BPMS_MEDIOS)
@pytest.mark.parametrize("fps", (20.0, 25.0, 30.0, 60.0))
def test_estimativa_independe_da_taxa_de_quadros(bpm: float, fps: float) -> None:
    resultado = analisar(pulso_de(bpm, fps=fps, duracao_s=14.0))
    assert resultado.ok
    assert abs(resultado.desempacotar().bpm - bpm) < 1.5


@pytest.mark.parametrize("bpm", BPMS_MEDIOS)
@pytest.mark.parametrize("ruido", (0.05, 0.2, 0.5))
def test_estimativa_resiste_a_ruido(bpm: float, ruido: float) -> None:
    pulso = pulso_de(bpm, fps=30.0, duracao_s=16.0, ruido=ruido, semente=int(bpm))
    resultado = analisar(pulso)
    assert resultado.ok
    assert abs(resultado.desempacotar().bpm - bpm) < 2.0


@pytest.mark.parametrize("bpm", (50.0, 65.0, 80.0, 95.0, 110.0, 140.0))
def test_harmonicos_nao_desviam_o_pico_para_o_dobro(bpm: float) -> None:
    """A onda de pulso real tem harmônicos fortes; o pico precisa ficar na
    fundamental, não em 2f."""
    pulso = SinalPulso(
        senoide(bpm, duracao_s=16.0, harmonicos=(1.0, 0.5, 0.2)), 30.0, "teste"
    )
    resultado = analisar(pulso)
    assert resultado.ok
    assert abs(resultado.desempacotar().bpm - bpm) < 1.5


@pytest.mark.parametrize("bpm", BPMS_MEDIOS)
def test_relacao_sinal_ruido_alta_para_senoide_limpa(bpm: float) -> None:
    resultado = analisar(pulso_de(bpm, duracao_s=14.0))
    assert resultado.ok
    assert resultado.desempacotar().snr_db > 5.0


@pytest.mark.parametrize("semente", tuple(range(25)))
def test_ruido_branco_produz_relacao_sinal_ruido_baixa(semente: int) -> None:
    """Sem pulso não deve haver confiança alta. É o teste que impede o sistema
    de inventar um número quando não há sinal."""
    gerador = np.random.default_rng(semente)
    pulso = SinalPulso(gerador.standard_normal(360), 30.0, "ruído")
    resultado = analisar(pulso)
    assert resultado.ok
    assert resultado.desempacotar().snr_db < 8.0


@pytest.mark.parametrize("bpm", BPMS_MEDIOS)
def test_metodo_de_welch_tambem_encontra_a_frequencia(bpm: float) -> None:
    resultado = analisar(pulso_de(bpm, duracao_s=20.0), metodo="welch")
    assert resultado.ok
    assert abs(resultado.desempacotar().bpm - bpm) < 4.0


@pytest.mark.parametrize("bpm", (60.0, 90.0, 120.0, 150.0))
def test_periodograma_tem_pico_na_frequencia_certa(bpm: float) -> None:
    frequencias, potencias = periodograma(senoide(bpm, duracao_s=14.0), 30.0)
    pico = frequencias[int(np.argmax(potencias))]
    assert abs(pico * 60.0 - bpm) < 1.5


@pytest.mark.parametrize("fps", TAXAS_QUADROS)
def test_periodograma_respeita_o_limite_de_nyquist(fps: float) -> None:
    frequencias, _ = periodograma(senoide(72.0, fps=fps, duracao_s=12.0), fps)
    assert frequencias[-1] <= fps / 2.0 + 1e-9


@pytest.mark.parametrize("amostras", (0, 1))
def test_periodograma_de_entrada_minuscula_devolve_vetores_vazios(amostras: int) -> None:
    frequencias, potencias = periodograma(np.zeros(amostras), 30.0)
    assert frequencias.size == 0 and potencias.size == 0


@pytest.mark.parametrize("amostras", (0, 1, 5, 7))
def test_janela_curta_devolve_falha(amostras: int) -> None:
    resultado = analisar(SinalPulso(np.zeros(amostras), 30.0, "curto"))
    assert resultado.falhou
    assert isinstance(resultado.erro, JanelaInsuficiente)


@pytest.mark.parametrize("deslocamento", np.round(np.arange(-0.45, 0.46, 0.05), 3))
def test_refino_parabolico_recupera_o_vertice(deslocamento: float) -> None:
    """Monta uma parábola com vértice conhecido e confere se é encontrado."""
    frequencias = np.array([1.0, 2.0, 3.0])
    # log(p) = -(x - deslocamento)^2 em torno do bin central
    posicoes = np.array([-1.0, 0.0, 1.0])
    potencias = np.exp(-((posicoes - deslocamento) ** 2))
    estimado = refinar_pico(frequencias, potencias, 1)
    assert abs(estimado - (2.0 + deslocamento)) < 0.02


@pytest.mark.parametrize("indice", (0, 2))
def test_refino_nas_bordas_devolve_o_proprio_bin(indice: int) -> None:
    frequencias = np.array([1.0, 2.0, 3.0])
    potencias = np.array([1.0, 2.0, 1.0])
    assert refinar_pico(frequencias, potencias, indice) == frequencias[indice]


def test_refino_com_potencia_nula_nao_quebra() -> None:
    frequencias = np.array([1.0, 2.0, 3.0])
    potencias = np.array([0.0, 1.0, 0.0])
    assert refinar_pico(frequencias, potencias, 1) == 2.0


@pytest.mark.parametrize("bpm", (55.0, 72.0, 96.0, 130.0, 170.0))
def test_recorte_devolve_apenas_a_banda_pedida(bpm: float) -> None:
    frequencias, potencias = periodograma(senoide(bpm, duracao_s=12.0), 30.0)
    banda = BandaCardiaca()
    espectro = recortar_banda(frequencias, potencias, banda)
    assert espectro.frequencias_hz.min() >= banda.minima_hz
    assert espectro.frequencias_hz.max() <= banda.maxima_hz
    assert espectro.potencias.size == espectro.frequencias_hz.size


@pytest.mark.parametrize("bpm", (60.0, 90.0, 120.0))
def test_espectro_normalizado_tem_maximo_unitario(bpm: float) -> None:
    resultado = analisar(pulso_de(bpm, duracao_s=14.0))
    assert resultado.ok
    normalizado = resultado.desempacotar().espectro.normalizado()
    assert np.isclose(float(np.max(normalizado)), 1.0)
    assert np.all(normalizado >= 0.0)


def test_espectro_de_potencia_nula_normaliza_para_zeros() -> None:
    from cardiocam.dominio.estimativa import Espectro

    espectro = Espectro(np.linspace(0.7, 4.0, 10), np.zeros(10))
    assert np.all(espectro.normalizado() == 0.0)


@pytest.mark.parametrize("bpm", (60.0, 100.0, 150.0))
def test_conversao_para_bpm_do_espectro(bpm: float) -> None:
    resultado = analisar(pulso_de(bpm, duracao_s=12.0))
    assert resultado.ok
    espectro = resultado.desempacotar().espectro
    assert np.allclose(espectro.bpm, espectro.frequencias_hz * 60.0)


def test_metodo_espectral_desconhecido_e_rejeitado() -> None:
    with pytest.raises(ValueError, match="Método espectral"):
        analisar(pulso_de(72.0), metodo="transformada_magica")


@pytest.mark.parametrize("bpm", (60.0, 90.0, 130.0))
def test_relacao_sinal_ruido_cai_quando_o_ruido_cresce(bpm: float) -> None:
    limpo = analisar(pulso_de(bpm, duracao_s=16.0, ruido=0.0))
    sujo = analisar(pulso_de(bpm, duracao_s=16.0, ruido=1.5, semente=3))
    assert limpo.ok and sujo.ok
    assert limpo.desempacotar().snr_db > sujo.desempacotar().snr_db


def test_relacao_sinal_ruido_sem_banda_valida_devolve_menos_infinito() -> None:
    frequencias = np.array([10.0, 11.0, 12.0])
    potencias = np.ones(3)
    valor = relacao_sinal_ruido(frequencias, potencias, 11.0, BandaCardiaca())
    assert valor == float("-inf")


@pytest.mark.parametrize("bpm", (72.0, 108.0))
def test_welch_devolve_vetores_coerentes(bpm: float) -> None:
    frequencias, potencias = welch(senoide(bpm, duracao_s=20.0), 30.0)
    assert frequencias.size == potencias.size > 0
    assert np.all(potencias >= 0.0)


@pytest.mark.parametrize("amostras", (0, 4, 7))
def test_welch_com_entrada_curta_devolve_vazio(amostras: int) -> None:
    frequencias, potencias = welch(np.zeros(amostras), 30.0)
    assert frequencias.size == 0 and potencias.size == 0


@pytest.mark.parametrize("bpm", (45.0, 50.0, 200.0, 220.0, 235.0))
def test_pico_fica_dentro_dos_limites_da_banda(bpm: float) -> None:
    """Mesmo com pulso perto da borda, a estimativa não escapa da banda."""
    resultado = analisar(pulso_de(bpm, duracao_s=16.0))
    assert resultado.ok
    banda = BandaCardiaca()
    assert banda.contem_bpm(resultado.desempacotar().bpm)


@pytest.mark.parametrize("duracao", (6.0, 8.0, 10.0, 12.0, 16.0, 20.0, 30.0))
def test_janelas_mais_longas_nao_pioram_a_estimativa(duracao: float) -> None:
    resultado = analisar(pulso_de(88.0, duracao_s=duracao))
    assert resultado.ok
    assert abs(resultado.desempacotar().bpm - 88.0) < 2.0
