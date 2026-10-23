"""A duração e a cadência seguem o relógio, mesmo com FPS variável."""

import numpy as np
import pytest

from cardiocam.dominio.config import ConfiguracaoAnalise
from cardiocam.qualidade.coleta_de_video import ContextoDaJanela
from cardiocam.sinais.janela import JanelaDeslizante


@pytest.mark.parametrize("fps", [10, 20, 40])
def test_janela_de_dez_segundos_independe_do_fps_nominal(fps):
    janela = JanelaDeslizante(20, ConfiguracaoAnalise(janela_s=10, passo_s=1))
    emissoes = []
    for i in range(fps * 25):
        janela.adicionar(1, 2, 3, i / fps)
        if janela.deve_emitir():
            emissoes.append(i / fps)
            assert janela.duracao_s == pytest.approx(10, abs=1 / fps)
            janela.marcar_emissao()
    assert emissoes[0] == pytest.approx(10 - 1 / fps, abs=1e-8)
    assert np.diff(emissoes) == pytest.approx(np.ones(len(emissoes) - 1))
    assert len(janela) == 10 * fps


def test_janela_irregular_emite_e_alinha_contexto():
    janela = JanelaDeslizante(20, ConfiguracaoAnalise(janela_s=3, passo_s=.5))
    contexto = ContextoDaJanela(60)
    tempos = np.cumsum(np.random.default_rng(8).uniform(.04, .12, 300))
    emissoes = []
    for t in tempos:
        janela.adicionar(1, 2, 3, t)
        contexto.registrar(1, 0, .5, instante=t, inicio=janela.inicio)
        assert len(contexto.pele) == len(janela)
        assert list(contexto.instantes) == list(janela.serie(False).instantes)
        if janela.deve_emitir():
            emissoes.append(t)
            assert 3 <= janela.duracao_s < 3.2
            janela.marcar_emissao()
    assert len(emissoes) > 20
    assert np.min(np.diff(emissoes)) >= .5 - 1e-8


@pytest.mark.parametrize("t", [0, -1, float("nan"), float("inf")])
def test_janela_rejeita_tempo_invalido_sem_adicionar(t):
    janela = JanelaDeslizante(20)
    janela.adicionar(1, 2, 3, 0)
    with pytest.raises(ValueError):
        janela.adicionar(1, 2, 3, t)
    assert len(janela) == 1
