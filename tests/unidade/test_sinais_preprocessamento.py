"""Testes do preparo do sinal: detrend, normalização e reamostragem."""

from __future__ import annotations

import numpy as np
import pytest

from cardiocam.sinais.preprocessamento import (
    estimar_fps,
    normalizar,
    normalizar_pela_media,
    reamostrar_uniforme,
    remover_tendencia,
    remover_tendencia_movel,
)
from tests.conftest import TAXAS_QUADROS, senoide

LAMBDAS = (10.0, 50.0, 100.0, 300.0, 1000.0)
INCLINACOES = (-5.0, -1.0, -0.2, 0.2, 1.0, 5.0, 20.0)


@pytest.mark.parametrize("inclinacao", INCLINACOES)
@pytest.mark.parametrize("lambda_", LAMBDAS)
def test_rampa_pura_e_removida(inclinacao: float, lambda_: float) -> None:
    tempos = np.linspace(0.0, 10.0, 300)
    rampa = inclinacao * tempos + 7.0
    residuo = remover_tendencia(rampa, lambda_)
    # Uma reta é exatamente o que o operador de segunda diferença anula.
    assert float(np.max(np.abs(residuo))) < 0.05 * abs(inclinacao) + 0.05


@pytest.mark.parametrize("bpm", (50.0, 72.0, 96.0, 120.0, 160.0))
@pytest.mark.parametrize("lambda_", (50.0, 100.0, 300.0))
def test_oscilacao_na_banda_sobrevive_ao_detrend(bpm: float, lambda_: float) -> None:
    tempos = np.arange(360) / 30.0
    oscilacao = senoide(bpm, duracao_s=12.0)
    com_tendencia = oscilacao + 3.0 * tempos + 0.5 * tempos**2
    residuo = remover_tendencia(com_tendencia, lambda_)
    correlacao = float(np.corrcoef(residuo[30:-30], oscilacao[30:-30])[0, 1])
    assert correlacao > 0.95, f"correlação {correlacao:.3f}"


@pytest.mark.parametrize("grau", (0, 1, 2))
@pytest.mark.parametrize("lambda_", (100.0, 500.0))
def test_polinomios_lentos_sao_atenuados(grau: int, lambda_: float) -> None:
    tempos = np.linspace(0.0, 1.0, 300)
    tendencia = tempos**grau if grau else np.ones_like(tempos)
    residuo = remover_tendencia(tendencia * 10.0, lambda_)
    assert float(np.std(residuo)) < float(np.std(tendencia * 10.0)) + 1e-9


@pytest.mark.parametrize("amostras", (0, 1, 2, 3))
def test_detrend_de_sinal_minusculo_nao_quebra(amostras: int) -> None:
    entrada = np.ones(amostras)
    saida = remover_tendencia(entrada)
    assert saida.shape == entrada.shape


@pytest.mark.parametrize("lambda_", (0.0, -1.0))
def test_lambda_nao_positivo_cai_na_remocao_de_media(lambda_: float) -> None:
    entrada = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    assert np.allclose(remover_tendencia(entrada, lambda_), entrada - 3.0)


@pytest.mark.parametrize("tamanho", (300, 450, 600))
def test_detrend_preserva_o_comprimento(tamanho: int) -> None:
    entrada = np.random.default_rng(1).standard_normal(tamanho)
    assert remover_tendencia(entrada).shape == entrada.shape


@pytest.mark.parametrize("janela", (5, 11, 31, 61, 121))
def test_detrend_movel_remove_o_nivel(janela: int) -> None:
    entrada = senoide(72.0, duracao_s=12.0) + 50.0
    residuo = remover_tendencia_movel(entrada, janela)
    assert abs(float(np.mean(residuo))) < 1.0


def test_detrend_movel_de_vetor_vazio() -> None:
    assert remover_tendencia_movel(np.zeros(0), 5).size == 0


@pytest.mark.parametrize("media", (-10.0, 0.0, 5.0, 128.0))
@pytest.mark.parametrize("desvio", (0.5, 1.0, 10.0, 40.0))
def test_normalizacao_produz_media_nula_e_desvio_unitario(
    media: float, desvio: float
) -> None:
    entrada = np.random.default_rng(7).standard_normal(500) * desvio + media
    saida = normalizar(entrada)
    assert abs(float(np.mean(saida))) < 1e-9
    assert abs(float(np.std(saida)) - 1.0) < 1e-9


@pytest.mark.parametrize("constante", (-3.0, 0.0, 1.0, 255.0))
def test_normalizacao_de_sinal_constante_devolve_zeros(constante: float) -> None:
    assert np.all(normalizar(np.full(50, constante)) == 0.0)


@pytest.mark.parametrize("canais", (1, 2, 3, 4))
def test_normalizacao_age_por_linha(canais: int) -> None:
    gerador = np.random.default_rng(3)
    matriz = np.vstack(
        [gerador.standard_normal(200) * (i + 1) + i * 10 for i in range(canais)]
    )
    saida = normalizar(matriz)
    assert saida.shape == matriz.shape
    assert np.allclose(np.mean(saida, axis=1), 0.0, atol=1e-9)
    assert np.allclose(np.std(saida, axis=1), 1.0, atol=1e-9)


def test_normalizacao_de_vetor_vazio() -> None:
    assert normalizar(np.zeros(0)).size == 0


@pytest.mark.parametrize("base", (10.0, 50.0, 128.0, 200.0))
def test_normalizacao_pela_media_centra_em_um(base: float) -> None:
    entrada = base + senoide(72.0, duracao_s=10.0)
    saida = normalizar_pela_media(entrada)
    assert abs(float(np.mean(saida)) - 1.0) < 1e-9


@pytest.mark.parametrize("canais", (2, 3))
def test_normalizacao_pela_media_age_por_linha(canais: int) -> None:
    matriz = np.vstack([np.full(100, 50.0 * (i + 1)) for i in range(canais)])
    saida = normalizar_pela_media(matriz)
    assert np.allclose(saida, 1.0)


def test_normalizacao_pela_media_com_media_nula_nao_divide_por_zero() -> None:
    entrada = np.array([-1.0, 1.0, -1.0, 1.0])
    saida = normalizar_pela_media(entrada)
    assert np.all(np.isfinite(saida))


def test_normalizacao_pela_media_de_vetor_vazio() -> None:
    assert normalizar_pela_media(np.zeros(0)).size == 0


@pytest.mark.parametrize("fps_alvo", (10.0, 15.0, 25.0, 30.0, 60.0))
def test_reamostragem_gera_grade_uniforme(fps_alvo: float) -> None:
    tempos = np.array([0.0, 0.11, 0.19, 0.33, 0.40, 0.55, 0.70])
    valores = np.sin(2.0 * np.pi * tempos)
    saida, grade = reamostrar_uniforme(valores, tempos, fps_alvo)
    intervalos = np.diff(grade)
    assert np.allclose(intervalos, intervalos[0])
    assert saida.size == grade.size


@pytest.mark.parametrize("bpm", (60.0, 90.0, 120.0))
def test_reamostragem_preserva_a_frequencia(bpm: float) -> None:
    gerador = np.random.default_rng(11)
    tempos = np.sort(np.cumsum(gerador.uniform(0.02, 0.05, 400)))
    valores = np.sin(2.0 * np.pi * (bpm / 60.0) * tempos)
    saida, grade = reamostrar_uniforme(valores, tempos, 30.0)
    espectro = np.abs(np.fft.rfft(saida - saida.mean()))
    frequencias = np.fft.rfftfreq(saida.size, d=float(grade[1] - grade[0]))
    pico = frequencias[int(np.argmax(espectro))] * 60.0
    assert abs(pico - bpm) < 5.0


@pytest.mark.parametrize("canais", (2, 3, 4))
def test_reamostragem_de_matriz_mantem_as_linhas(canais: int) -> None:
    tempos = np.linspace(0.0, 2.0, 60)
    matriz = np.vstack([np.sin(2 * np.pi * (i + 1) * tempos) for i in range(canais)])
    saida, grade = reamostrar_uniforme(matriz, tempos, 30.0)
    assert saida.shape == (canais, grade.size)


def test_reamostragem_com_uma_amostra_devolve_a_entrada() -> None:
    saida, grade = reamostrar_uniforme(np.array([1.0]), np.array([0.0]), 30.0)
    assert saida.size == 1 and grade.size == 1


@pytest.mark.parametrize("fps_alvo", (0.0, -1.0, -30.0))
def test_reamostragem_rejeita_taxa_nao_positiva(fps_alvo: float) -> None:
    with pytest.raises(ValueError):
        reamostrar_uniforme(np.zeros(10), np.arange(10.0), fps_alvo)


def test_reamostragem_rejeita_tamanhos_incompativeis() -> None:
    with pytest.raises(ValueError):
        reamostrar_uniforme(np.zeros(10), np.arange(5.0), 30.0)


def test_reamostragem_ordena_instantes_embaralhados() -> None:
    tempos = np.array([0.3, 0.0, 0.2, 0.1])
    valores = np.array([3.0, 0.0, 2.0, 1.0])
    saida, grade = reamostrar_uniforme(valores, tempos, 20.0)
    assert grade[0] == 0.0 and np.isclose(grade[-1], 0.3)
    assert saida[0] < saida[-1]


@pytest.mark.parametrize("fps", TAXAS_QUADROS)
def test_estimativa_de_fps_em_grade_perfeita(fps: float) -> None:
    tempos = np.arange(200) / fps
    assert abs(estimar_fps(tempos) - fps) < 1e-6


@pytest.mark.parametrize("fps", (20.0, 30.0, 60.0))
@pytest.mark.parametrize("jitter", (0.001, 0.003, 0.008))
def test_estimativa_de_fps_resiste_a_jitter(fps: float, jitter: float) -> None:
    gerador = np.random.default_rng(5)
    tempos = np.sort(np.arange(300) / fps + gerador.normal(0, jitter, 300))
    assert abs(estimar_fps(tempos) - fps) < fps * 0.25


def test_estimativa_de_fps_ignora_travada_pontual() -> None:
    """A mediana não deve ser puxada por um único quadro atrasado."""
    tempos = list(np.arange(100) / 30.0)
    tempos.append(tempos[-1] + 2.0)
    assert abs(estimar_fps(np.array(tempos)) - 30.0) < 1.0


@pytest.mark.parametrize("amostras", (0, 1))
def test_estimativa_de_fps_sem_dados_devolve_zero(amostras: int) -> None:
    assert estimar_fps(np.zeros(amostras)) == 0.0


def test_estimativa_de_fps_com_instantes_repetidos() -> None:
    assert estimar_fps(np.zeros(10)) == 0.0
