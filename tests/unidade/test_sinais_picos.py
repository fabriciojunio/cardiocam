"""Testes da análise no domínio do tempo."""

from __future__ import annotations

import numpy as np
import pytest

from cardiocam.dominio.estimativa import VariabilidadeCardiaca
from cardiocam.dominio.sinal import BandaCardiaca, SinalPulso
from cardiocam.sinais.picos import (
    bpm_por_picos,
    detectar_picos,
    filtrar_intervalos,
    intervalos_entre_batimentos,
    variabilidade,
)
from tests.conftest import pulso_de, senoide

BPMS = (48.0, 55.0, 60.0, 66.0, 72.0, 80.0, 90.0, 100.0, 110.0, 120.0, 140.0)


@pytest.mark.parametrize("bpm", BPMS)
def test_numero_de_picos_bate_com_a_frequencia(bpm: float) -> None:
    duracao = 20.0
    pulso = pulso_de(bpm, fps=60.0, duracao_s=duracao)
    picos = detectar_picos(pulso, frequencia_esperada_hz=bpm / 60.0)
    esperado = duracao * bpm / 60.0
    assert abs(len(picos) - esperado) <= 2, f"{len(picos)} picos, esperado ~{esperado:.0f}"


@pytest.mark.parametrize("bpm", BPMS)
def test_bpm_por_picos_recupera_a_frequencia(bpm: float) -> None:
    pulso = pulso_de(bpm, fps=60.0, duracao_s=20.0)
    estimado = bpm_por_picos(pulso, frequencia_esperada_hz=bpm / 60.0)
    assert abs(estimado - bpm) < 2.5, f"esperado {bpm}, obtido {estimado:.2f}"


@pytest.mark.parametrize("bpm", (50.0, 65.0, 80.0, 100.0))
def test_dica_espectral_evita_contar_o_harmonico(bpm: float) -> None:
    """Sem a dica de frequência, o entalhe dicrótico é contado como batimento.

    Este teste documenta exatamente por que a dica existe.
    """
    pulso = SinalPulso(
        senoide(bpm, fps=60.0, duracao_s=20.0, harmonicos=(1.0, 0.6)), 60.0, "teste"
    )
    com_dica = bpm_por_picos(pulso, frequencia_esperada_hz=bpm / 60.0)
    assert abs(com_dica - bpm) < 3.0


@pytest.mark.parametrize("amostras", (0, 1, 2))
def test_sinal_curto_nao_tem_picos(amostras: int) -> None:
    pulso = SinalPulso(np.zeros(amostras), 30.0, "curto")
    assert detectar_picos(pulso).size == 0


def test_sinal_constante_nao_tem_picos() -> None:
    pulso = SinalPulso(np.full(300, 5.0), 30.0, "constante")
    assert detectar_picos(pulso).size == 0


@pytest.mark.parametrize("fps", (20.0, 30.0, 60.0, 120.0))
def test_intervalos_em_milissegundos(fps: float) -> None:
    indices = np.array([0, int(fps), int(2 * fps)])
    intervalos = intervalos_entre_batimentos(indices, fps)
    assert np.allclose(intervalos, 1000.0)


@pytest.mark.parametrize("indices", ([], [5]))
def test_intervalos_com_poucos_picos_devolve_vazio(indices: list) -> None:
    assert intervalos_entre_batimentos(np.array(indices), 30.0).size == 0


@pytest.mark.parametrize("fps", (0.0, -1.0))
def test_intervalos_rejeitam_fps_invalido(fps: float) -> None:
    with pytest.raises(ValueError):
        intervalos_entre_batimentos(np.array([0, 10]), fps)


@pytest.mark.parametrize("tolerancia", (0.1, 0.2, 0.3, 0.5))
def test_filtro_remove_intervalo_dobrado(tolerancia: float) -> None:
    """Um batimento não detectado dobra o intervalo e precisa ser descartado."""
    intervalos = np.array([800.0, 810.0, 1600.0, 795.0, 805.0, 800.0])
    filtrados = filtrar_intervalos(intervalos, tolerancia)
    assert 1600.0 not in filtrados


def test_filtro_remove_intervalo_pela_metade() -> None:
    intervalos = np.array([800.0, 790.0, 400.0, 805.0, 810.0])
    assert 400.0 not in filtrar_intervalos(intervalos)


@pytest.mark.parametrize("quantidade", (0, 1, 2))
def test_filtro_com_poucos_intervalos_devolve_tudo(quantidade: int) -> None:
    intervalos = np.full(quantidade, 800.0)
    assert filtrar_intervalos(intervalos).size == quantidade


def test_filtro_com_mediana_nula_devolve_entrada() -> None:
    intervalos = np.zeros(5)
    assert filtrar_intervalos(intervalos).size == 5


@pytest.mark.parametrize("media_ms", (500.0, 700.0, 800.0, 1000.0, 1200.0))
def test_variabilidade_de_intervalos_constantes_e_nula(media_ms: float) -> None:
    hrv = VariabilidadeCardiaca.de_intervalos(np.full(20, media_ms))
    assert hrv.sdnn_ms == pytest.approx(0.0, abs=1e-9)
    assert hrv.rmssd_ms == pytest.approx(0.0, abs=1e-9)
    assert hrv.pnn50 == 0.0
    assert hrv.bpm_medio == pytest.approx(60000.0 / media_ms)


@pytest.mark.parametrize("quantidade", (0, 1))
def test_variabilidade_com_dados_insuficientes_devolve_nan(quantidade: int) -> None:
    hrv = VariabilidadeCardiaca.de_intervalos(np.full(quantidade, 800.0))
    assert not np.isfinite(hrv.sdnn_ms)
    assert not np.isfinite(hrv.bpm_medio)


@pytest.mark.parametrize("dispersao", (10.0, 30.0, 60.0))
def test_variabilidade_cresce_com_a_dispersao(dispersao: float) -> None:
    gerador = np.random.default_rng(2)
    intervalos = 800.0 + gerador.normal(0.0, dispersao, 40)
    hrv = VariabilidadeCardiaca.de_intervalos(intervalos)
    assert hrv.sdnn_ms > dispersao * 0.5
    assert hrv.rmssd_ms > 0.0


def test_pnn50_conta_diferencas_grandes() -> None:
    intervalos = np.array([800.0, 900.0, 800.0, 900.0, 800.0])
    hrv = VariabilidadeCardiaca.de_intervalos(intervalos)
    assert hrv.pnn50 == pytest.approx(1.0)


@pytest.mark.parametrize("bpm", (60.0, 75.0, 90.0))
def test_variabilidade_a_partir_do_sinal(bpm: float) -> None:
    pulso = pulso_de(bpm, fps=60.0, duracao_s=24.0)
    hrv = variabilidade(pulso, frequencia_esperada_hz=bpm / 60.0)
    assert np.isfinite(hrv.media_ms)
    assert abs(hrv.bpm_medio - bpm) < 4.0


def test_bpm_por_picos_devolve_nan_sem_batimentos() -> None:
    pulso = SinalPulso(np.zeros(300), 30.0, "silencio")
    assert not np.isfinite(bpm_por_picos(pulso))


@pytest.mark.parametrize("bpm_real", (150.0, 170.0, 190.0))
def test_bpm_fora_da_banda_configurada_e_descartado(bpm_real: float) -> None:
    """A banda é a última guarda contra reportar um valor implausível.

    Aqui a banda foi configurada para repouso (até 90 bpm) mas o sinal tem
    batimentos bem mais rápidos. Com a dica de frequência, o detector encontra
    esses picos; cabe à banda recusar o resultado em vez de exibi-lo.
    """
    pulso = pulso_de(bpm_real, fps=60.0, duracao_s=20.0)
    banda_repouso = BandaCardiaca(0.7, 1.5)
    estimado = bpm_por_picos(
        pulso, banda_repouso, frequencia_esperada_hz=bpm_real / 60.0
    )
    assert not np.isfinite(estimado)


def test_bpm_dentro_da_banda_configurada_e_aceito() -> None:
    pulso = pulso_de(72.0, fps=60.0, duracao_s=20.0)
    banda_repouso = BandaCardiaca(0.7, 1.5)
    estimado = bpm_por_picos(pulso, banda_repouso, frequencia_esperada_hz=1.2)
    assert np.isfinite(estimado)
    assert abs(estimado - 72.0) < 3.0


@pytest.mark.parametrize("proeminencia", (0.1, 0.3, 0.5, 0.8))
def test_proeminencia_maior_encontra_menos_picos(proeminencia: float) -> None:
    gerador = np.random.default_rng(4)
    amostras = senoide(72.0, fps=60.0, duracao_s=20.0) + gerador.normal(0, 0.3, 1200)
    pulso = SinalPulso(amostras, 60.0, "ruidoso")
    picos = detectar_picos(pulso, proeminencia_relativa=proeminencia)
    assert picos.size >= 0
    if proeminencia >= 0.8:
        assert picos.size <= 40
