"""Testes da rectificação por referência de fundo."""

from __future__ import annotations

import numpy as np
import pytest

from cardiocam.sinais.rectificacao import (
    energia_removida,
    montar_atrasos,
    remover_referencia,
)
from tests.conftest import senoide


@pytest.mark.parametrize("atrasos", (1, 2, 3, 5, 8))
def test_matriz_de_atrasos_tem_o_formato_certo(atrasos: int) -> None:
    referencia = np.arange(50.0)
    matriz = montar_atrasos(referencia, atrasos)
    assert matriz.shape == (50, atrasos)


@pytest.mark.parametrize("atrasos", (1, 2, 4))
def test_primeira_coluna_e_a_propria_referencia(atrasos: int) -> None:
    referencia = np.arange(20.0)
    assert np.allclose(montar_atrasos(referencia, atrasos)[:, 0], referencia)


@pytest.mark.parametrize("k", (1, 2, 3))
def test_colunas_seguintes_sao_deslocadas_no_tempo(k: int) -> None:
    referencia = np.arange(20.0)
    coluna = montar_atrasos(referencia, k + 1)[:, k]
    assert np.allclose(coluna[:k], 0.0)
    assert np.allclose(coluna[k:], referencia[:-k])


@pytest.mark.parametrize("atrasos", (0, -1))
def test_atrasos_invalidos_sao_rejeitados(atrasos: int) -> None:
    with pytest.raises(ValueError):
        montar_atrasos(np.zeros(10), atrasos)


@pytest.mark.parametrize("ganho", (0.5, 1.0, 2.0, 4.0))
def test_interferencia_pura_e_removida(ganho: float) -> None:
    """O caso ideal: o sinal é só a interferência, escalada."""
    interferencia = senoide(120.0, duracao_s=20.0)
    limpo = remover_referencia(ganho * interferencia, interferencia)
    assert float(np.std(limpo)) < 0.2 * float(np.std(ganho * interferencia))


@pytest.mark.parametrize("bpm_pulso", (60.0, 78.0, 96.0))
@pytest.mark.parametrize("forca", (1.0, 2.0, 4.0))
def test_pulso_sobrevive_e_interferencia_some(bpm_pulso: float, forca: float) -> None:
    """O que importa na prática: tirar a interferência sem levar o pulso junto."""
    pulso = senoide(bpm_pulso, duracao_s=24.0)
    interferencia = senoide(bpm_pulso + 42.0, duracao_s=24.0)
    misturado = pulso + forca * interferencia

    limpo = remover_referencia(misturado, interferencia)

    correlacao_pulso = float(np.corrcoef(limpo, pulso)[0, 1])
    assert correlacao_pulso > 0.9, f"o pulso foi danificado, correlação {correlacao_pulso:.2f}"

    resto = abs(float(np.corrcoef(limpo, interferencia)[0, 1]))
    assert resto < 0.2, f"sobrou interferência, correlação {resto:.2f}"


@pytest.mark.parametrize("bpm", (66.0, 84.0, 108.0))
def test_referencia_sem_relacao_deixa_o_sinal_quase_intacto(bpm: float) -> None:
    """Se o fundo não explica nada, a rectificação não pode estragar o sinal."""
    pulso = senoide(bpm, duracao_s=24.0)
    ruido = np.random.default_rng(int(bpm)).standard_normal(pulso.size)
    limpo = remover_referencia(pulso, ruido)
    assert float(np.corrcoef(limpo, pulso)[0, 1]) > 0.9


@pytest.mark.parametrize("atrasos", (1, 2, 3, 6))
def test_interferencia_atrasada_tambem_e_removida(atrasos: int) -> None:
    """O ganho automático da câmera reage alguns quadros depois da mudança."""
    interferencia = senoide(140.0, duracao_s=24.0)
    deslocada = np.concatenate([np.zeros(3), interferencia[:-3]])
    pulso = senoide(72.0, duracao_s=24.0)
    limpo = remover_referencia(pulso + 3.0 * deslocada, interferencia, atrasos=max(4, atrasos))
    assert float(np.corrcoef(limpo, pulso)[0, 1]) > 0.75


def test_referencia_constante_nao_muda_nada() -> None:
    pulso = senoide(72.0, duracao_s=20.0)
    assert np.allclose(remover_referencia(pulso, np.ones(pulso.size)), pulso)


def test_sinal_constante_nao_muda_nada() -> None:
    constante = np.full(400, 7.0)
    assert np.allclose(remover_referencia(constante, senoide(90.0, duracao_s=400 / 30)), constante)


@pytest.mark.parametrize("tamanho", (0, 5, 50, 400))
def test_saida_preserva_o_comprimento(tamanho: int) -> None:
    sinal = np.random.default_rng(0).standard_normal(tamanho)
    referencia = np.random.default_rng(1).standard_normal(tamanho)
    assert remover_referencia(sinal, referencia).shape == sinal.shape


def test_tamanhos_incompativeis_devolvem_a_entrada() -> None:
    sinal = np.arange(100.0)
    assert np.allclose(remover_referencia(sinal, np.arange(50.0)), sinal)


def test_sinal_totalmente_explicado_pelo_fundo_e_zerado() -> None:
    """Se o fundo explica tudo, não havia pulso, apenas iluminação.

    Zerar é a resposta certa: a verificação de sinal degenerado mais adiante
    recusa a janela em vez de reportar a interferência como batimento.
    """
    pulso = senoide(72.0, duracao_s=20.0)
    limpo = remover_referencia(pulso, pulso)
    assert float(np.std(limpo)) < 0.05 * float(np.std(pulso))


@pytest.mark.parametrize("fracao", (0.2, 0.5, 0.8))
def test_energia_removida_reflete_a_reducao(fracao: float) -> None:
    original = senoide(72.0, duracao_s=20.0)
    reduzido = original * np.sqrt(1.0 - fracao)
    assert energia_removida(original, reduzido) == pytest.approx(fracao, abs=0.02)


def test_energia_removida_de_sinal_nulo_e_zero() -> None:
    assert energia_removida(np.zeros(100), np.zeros(100)) == 0.0
