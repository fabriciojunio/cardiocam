"""Regressões de validade temporal e alinhamento da qualidade."""

from dataclasses import replace

import numpy as np
import pytest

from cardiocam.desktop.qualidade_ao_vivo import JuizDeQualidade
from cardiocam.dominio.config import ConfiguracaoAnalise
from cardiocam.dominio.erros import SinalSemQualidade
from cardiocam.dominio.resultado import Falha, Ok
from cardiocam.pipeline.analisador import MonitorCardiaco, estimar_de_serie
from cardiocam.qualidade.extracao import caracteristicas_da_analise
from cardiocam.visao.detector_face import DetectorRegiaoFixa
from cardiocam.visao.extrator import AmostraQuadro, ExtratorRGB
from cardiocam.visao.geometria import Retangulo
from tests.conftest import serie_de


@pytest.fixture
def monitor(monkeypatch):
    analise = estimar_de_serie(serie_de(72.0), ConfiguracaoAnalise(algoritmo="pos")).desempacotar()
    monkeypatch.setattr("cardiocam.pipeline.analisador.estimar_de_serie", lambda *args: Ok(analise))
    extrator = ExtratorRGB(ancorar_nos_olhos=False)
    monkeypatch.setattr(extrator, "extrair", lambda *args: Ok(AmostraQuadro(150, 180, 100, 100, 1.0)))
    monitor = MonitorCardiaco(
        20.0, ConfiguracaoAnalise(janela_s=3.0, passo_s=0.5),
        detector=DetectorRegiaoFixa(Retangulo(0, 0, 10, 10)), extrator=extrator,
        detectar_congelamento=False,
    )
    quadro = np.full((20, 20, 3), 100, dtype=np.uint8)
    for i in range(60):
        estado = monitor.processar(quadro, i / 20)
    assert estado.bpm_exibido is not None
    return monitor, quadro, estado


def test_falha_da_proxima_janela_remove_bpm_e_analise(monitor, monkeypatch):
    medidor, quadro, anterior = monitor
    monkeypatch.setattr("cardiocam.pipeline.analisador.estimar_de_serie",
                        lambda *args: Falha(SinalSemQualidade(-5, 0)))
    for i in range(60, 70):
        estado = medidor.processar(quadro, i / 20)
    assert anterior.bpm_exibido == pytest.approx(72, abs=1)
    assert estado.bpm_exibido is None
    assert estado.analise is None
    assert medidor.bpm_atual is None
    assert medidor.ultima_analise is None
    assert estado.codigo_falha == "sinal_sem_qualidade"
    assert "iluminação" not in estado.mensagem


@pytest.mark.parametrize("instante,codigo", [(2.95, "tempo_nao_monotonico"),
                                              (2.0, "tempo_nao_monotonico"),
                                              (float("nan"), "tempo_invalido")])
def test_tempo_invalido_descarta_leitura(monitor, instante, codigo):
    medidor, quadro, _ = monitor
    estado = medidor.processar(quadro, instante)
    assert estado.bpm_exibido is None
    assert estado.codigo_falha == codigo
    assert len(medidor.janela) == 0
    assert estado.contexto_reiniciado


def test_pausa_inicia_nova_janela(monitor):
    medidor, quadro, _ = monitor
    estado = medidor.processar(quadro, 8.0)
    assert estado.bpm_exibido is None
    assert len(medidor.janela) == 1
    assert estado.contexto_reiniciado


def test_idade_da_leitura_e_nova_analise(monitor):
    medidor, quadro, anterior = monitor
    assert anterior.nova_analise
    assert anterior.idade_analise_s == 0
    estado = medidor.processar(quadro, 3.0)
    assert not estado.nova_analise
    assert estado.analise is anterior.analise
    assert estado.idade_analise_s == pytest.approx(0.05)


def test_qualidade_usa_canais_fundo_e_instantes_do_treino():
    serie = serie_de(72.0)
    t = serie.instantes
    fundo = np.vstack([120 + np.sin(t * 5), 140 + np.sin(t * 5), 100 + np.sin(t * 5)])
    serie = replace(serie, fundo=fundo)
    analise = estimar_de_serie(serie, ConfiguracaoAnalise(algoritmo="pos")).desempacotar()
    juiz = JuizDeQualidade(100)
    juiz.contexto.registrar(1.0, 0.0, 0.5)
    assert juiz.caracteristicas(analise) == caracteristicas_da_analise(analise, serie)


def test_veredito_nao_muda_quando_contexto_posterior_muda():
    analise = estimar_de_serie(serie_de(72.0)).desempacotar()
    juiz = JuizDeQualidade(100)
    assert juiz.disponivel
    primeiro = juiz.julgar(analise)
    for i in range(100):
        juiz.contexto.registrar(0, 1, i / 100)
    assert juiz.julgar(analise) is primeiro
    juiz.reiniciar()
    assert not juiz.contexto.pele
    assert juiz._analise_julgada is None


def test_historico_limitado_nao_perde_contagem_total(monitor):
    from collections import deque
    medidor, quadro, _ = monitor
    medidor._historico = deque(medidor.historico, maxlen=2)
    for i in range(60, 140):
        medidor.processar(quadro, i / 20)
    assert len(medidor.historico) == 2
    assert medidor.total_estimativas > 2


def test_ausencia_de_fundo_e_diferente_de_correlacao_zero():
    from cardiocam.qualidade.extracao import caracteristicas_ausentes
    analise = estimar_de_serie(serie_de(72)).desempacotar()
    assert "correlacao_com_fundo" in caracteristicas_ausentes(analise)
    assert "jitter_temporal" not in caracteristicas_ausentes(analise)


def test_modelo_sem_calibracao_viavel_recusa_na_interface():
    analise = estimar_de_serie(serie_de(72)).desempacotar()
    juiz = JuizDeQualidade(100)
    juiz.modelo = replace(juiz.modelo, calibracao_viavel=False)
    assert juiz.julgar(analise).recusa
