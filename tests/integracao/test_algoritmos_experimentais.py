"""Contrato e limites dos métodos de pesquisa."""

import numpy as np
import pytest

from cardiocam.avaliacao.benchmark import cenarios_padrao
from cardiocam.avaliacao.experimentos import avaliar_experimentais
from cardiocam.dominio.config import ConfiguracaoAnalise
from cardiocam.dominio.sinal import SerieRGB
from cardiocam.pipeline.analisador import estimar_de_serie
from cardiocam.rppg.experimentais import ALGORITMOS_EXPERIMENTAIS
from tests.conftest import serie_de


@pytest.mark.parametrize("classe", ALGORITMOS_EXPERIMENTAIS)
@pytest.mark.parametrize("bpm", [48, 60, 72, 96, 120, 180])
def test_pulso_ideal_e_recuperado(classe, bpm):
    serie = serie_de(bpm, amplitude_pulso=.02, ruido_sensor=1)
    resultado = estimar_de_serie(serie, ConfiguracaoAnalise(), classe())
    assert resultado.ok
    assert abs(resultado.desempacotar().estimativa.bpm - bpm) < 2.5


@pytest.mark.parametrize("classe", ALGORITMOS_EXPERIMENTAIS)
@pytest.mark.parametrize("valor", [0.0, 100.0])
def test_sinal_constante_nao_vira_bpm(classe, valor):
    serie = SerieRGB.de_matriz(np.full((3, 300), valor), 30)
    assert estimar_de_serie(serie, ConfiguracaoAnalise(), classe()).falhou


def test_avaliacao_conta_todos_os_cenarios_e_nao_muda_o_padrao():
    resultados = avaliar_experimentais(cenarios_padrao(bpms=(72,)))
    assert len(resultados) == 3
    assert all(r.total == 7 for r in resultados.values())
    assert ConfiguracaoAnalise().algoritmo == "pos"


def test_comando_imprime_tabela_completa(capsys):
    from cardiocam.avaliacao.experimentos import principal
    principal(cenarios_padrao(bpms=(72,)))
    texto = capsys.readouterr().out
    for classe in ALGORITMOS_EXPERIMENTAIS:
        assert classe.nome.upper() in texto
    assert "sem validação em pessoas reais" in texto
