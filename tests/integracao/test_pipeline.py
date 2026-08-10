"""Testes do pipeline: janela deslizante, monitor e relatório de sessão."""

from __future__ import annotations

import numpy as np
import pytest

from cardiocam.dominio.config import ConfiguracaoAnalise
from cardiocam.dominio.estimativa import Confianca
from cardiocam.fontes.sintetica import FonteSintetica, RenderizadorRosto
from cardiocam.pipeline.analisador import (
    MonitorCardiaco,
    RelatorioSessao,
    analisar_fonte,
    estimar_de_serie,
)
from cardiocam.rppg import ALGORITMOS_DISPONIVEIS, criar_algoritmo
from cardiocam.sinais.janela import JanelaDeslizante
from cardiocam.visao.detector_face import DetectorRegiaoFixa
from cardiocam.visao.rastreador import RastreadorRosto
from tests.conftest import TAXAS_QUADROS, parametros, serie_de


def rastreador_fixo(fonte: FonteSintetica) -> RastreadorRosto:
    """Rastreador ancorado no rosto conhecido, para isolar o resto do pipeline."""
    return RastreadorRosto(DetectorRegiaoFixa(fonte.caixa_esperada()), suavizacao=1.0)


# --------------------------------------------------------------------------
# Janela deslizante
# --------------------------------------------------------------------------
@pytest.mark.parametrize("fps", TAXAS_QUADROS)
@pytest.mark.parametrize("janela_s", (5.0, 10.0, 15.0))
def test_capacidade_da_janela(fps: float, janela_s: float) -> None:
    janela = JanelaDeslizante(fps, ConfiguracaoAnalise(janela_s=janela_s))
    assert janela.capacidade == max(2, round(janela_s * fps))


@pytest.mark.parametrize("fps", (0.0, -1.0))
def test_janela_rejeita_fps_invalido(fps: float) -> None:
    with pytest.raises(ValueError):
        JanelaDeslizante(fps)


@pytest.mark.parametrize("fps", (20.0, 30.0, 60.0))
def test_janela_enche_e_para_de_crescer(fps: float) -> None:
    janela = JanelaDeslizante(fps, ConfiguracaoAnalise(janela_s=4.0))
    for indice in range(int(fps * 10)):
        janela.adicionar(1.0, 2.0, 3.0, indice / fps)
    assert len(janela) == janela.capacidade
    assert janela.total_recebido == int(fps * 10)


@pytest.mark.parametrize("passo_s", (0.5, 1.0, 2.0))
def test_emissao_respeita_o_passo(passo_s: float) -> None:
    fps = 30.0
    config = ConfiguracaoAnalise(janela_s=4.0, passo_s=passo_s)
    janela = JanelaDeslizante(fps, config)

    emissoes = 0
    for indice in range(int(fps * 20)):
        janela.adicionar(1.0, 2.0, 3.0, indice / fps)
        if janela.deve_emitir():
            janela.marcar_emissao()
            emissoes += 1

    esperado = (20 - 4) / passo_s
    assert abs(emissoes - esperado) <= 2


def test_janela_vazia_nao_emite() -> None:
    janela = JanelaDeslizante(30.0)
    assert not janela.deve_emitir()


def test_limpar_zera_a_janela() -> None:
    janela = JanelaDeslizante(30.0, ConfiguracaoAnalise(janela_s=2.0))
    for indice in range(100):
        janela.adicionar(1.0, 2.0, 3.0, indice / 30.0)
    janela.limpar()
    assert len(janela) == 0
    assert not janela.deve_emitir()


@pytest.mark.parametrize("fps_real", (18.0, 24.0, 29.0, 41.0))
def test_fps_efetivo_reflete_a_captura_real(fps_real: float) -> None:
    """A janela precisa medir a taxa real, não acreditar na nominal."""
    janela = JanelaDeslizante(30.0, ConfiguracaoAnalise(janela_s=5.0))
    for indice in range(150):
        janela.adicionar(1.0, 2.0, 3.0, indice / fps_real)
    assert abs(janela.fps_efetivo() - fps_real) < 1.0


@pytest.mark.parametrize("uniformizar", (True, False))
def test_serie_da_janela_tem_o_tamanho_certo(uniformizar: bool) -> None:
    janela = JanelaDeslizante(30.0, ConfiguracaoAnalise(janela_s=5.0))
    for indice in range(150):
        janela.adicionar(1.0, 2.0, 3.0, indice / 30.0)
    serie = janela.serie(uniformizar=uniformizar)
    assert abs(len(serie) - 150) <= 2


def test_serie_com_uma_amostra_nao_quebra() -> None:
    janela = JanelaDeslizante(30.0)
    janela.adicionar(1.0, 2.0, 3.0, 0.0)
    assert len(janela.serie()) == 1


# --------------------------------------------------------------------------
# Estimativa a partir de série
# --------------------------------------------------------------------------
@pytest.mark.parametrize("algoritmo", ALGORITMOS_DISPONIVEIS)
@pytest.mark.parametrize("bpm", (55.0, 72.0, 96.0, 130.0))
def test_analise_completa_traz_todos_os_campos(algoritmo: str, bpm: float) -> None:
    serie = serie_de(bpm, duracao_s=18.0)
    resultado = estimar_de_serie(
        serie, ConfiguracaoAnalise(algoritmo=algoritmo), criar_algoritmo(algoritmo)
    )
    assert resultado.ok
    analise = resultado.desempacotar()
    assert abs(analise.estimativa.bpm - bpm) < 2.5
    assert len(analise.pulso) == len(serie)
    assert analise.espectro.potencias.size > 0
    assert analise.estimativa.algoritmo == algoritmo


@pytest.mark.parametrize("bpm", (60.0, 75.0, 90.0, 110.0))
def test_concordancia_entre_espectro_e_contagem_de_picos(bpm: float) -> None:
    """Duas vias independentes chegando ao mesmo número é o melhor indício de
    que a medição é real e não um artefato periódico."""
    serie = serie_de(bpm, fps=60.0, duracao_s=20.0, amplitude_pulso=0.03)
    resultado = estimar_de_serie(serie, ConfiguracaoAnalise(algoritmo="pos"))
    assert resultado.ok
    analise = resultado.desempacotar()
    assert np.isfinite(analise.bpm_por_picos)
    assert analise.concordancia_bpm < 6.0


@pytest.mark.parametrize("snr_minimo", (5.0, 10.0, 20.0, 40.0))
def test_limiar_de_qualidade_descarta_janelas_fracas(snr_minimo: float) -> None:
    serie = serie_de(72.0, amplitude_pulso=0.002, ruido_sensor=25.0, duracao_s=12.0)
    config = ConfiguracaoAnalise(algoritmo="pos", snr_minimo_db=snr_minimo)
    resultado = estimar_de_serie(serie, config)
    if resultado.ok:
        assert resultado.desempacotar().estimativa.snr_db >= snr_minimo


# --------------------------------------------------------------------------
# Monitor
# --------------------------------------------------------------------------
@pytest.mark.parametrize("bpm", (60.0, 78.0, 96.0))
def test_monitor_acumula_e_emite(bpm: float) -> None:
    fonte = FonteSintetica(parametros(bpm, duracao_s=16.0, largura=240, altura=180))
    config = ConfiguracaoAnalise(janela_s=10.0, passo_s=1.0, algoritmo="pos")
    monitor = MonitorCardiaco(
        fps=fonte.fps, config=config, rastreador=rastreador_fixo(fonte)
    )

    for quadro, instante in fonte.quadros():
        estado = monitor.processar(quadro, instante)

    assert monitor.bpm_atual is not None
    assert abs(monitor.bpm_atual - bpm) < 3.0
    assert len(monitor.historico) > 0
    assert monitor.quadros_processados == fonte.total_quadros


def test_monitor_informa_progresso_enquanto_enche() -> None:
    fonte = FonteSintetica(parametros(72.0, duracao_s=4.0, largura=240, altura=180))
    monitor = MonitorCardiaco(
        fps=fonte.fps,
        config=ConfiguracaoAnalise(janela_s=10.0),
        rastreador=rastreador_fixo(fonte),
    )
    progressos = []
    for quadro, instante in fonte.quadros():
        progressos.append(monitor.processar(quadro, instante).progresso)

    assert progressos[0] < progressos[-1] < 1.0
    assert monitor.bpm_atual is None


def test_monitor_avisa_quando_nao_ha_rosto() -> None:
    from cardiocam.visao.detector_face import DetectorHaar

    monitor = MonitorCardiaco(
        fps=30.0, rastreador=RastreadorRosto(DetectorHaar(), tolerancia_quadros=1)
    )
    vazio = np.full((180, 240, 3), 90, dtype=np.uint8)
    estado = monitor.processar(vazio, 0.0)
    assert not estado.tem_rosto
    assert "rosto" in estado.mensagem.lower()


def test_monitor_descarta_o_sinal_quando_o_rosto_some_por_muito_tempo() -> None:
    """O sinal de antes e o de depois de uma ausência longa não formam uma série
    contínua, e juntá-los produziria uma frequência sem sentido."""
    from cardiocam.visao.detector_face import DetectorHaar

    fonte = FonteSintetica(parametros(72.0, duracao_s=12.0, largura=240, altura=180))
    monitor = MonitorCardiaco(
        fps=fonte.fps,
        config=ConfiguracaoAnalise(janela_s=6.0),
        rastreador=RastreadorRosto(DetectorHaar(), tolerancia_quadros=3),
    )
    for indice, (quadro, instante) in enumerate(fonte.quadros()):
        monitor.processar(quadro, instante)
        if indice > 200:
            break

    assert len(monitor.janela) > 0
    vazio = np.full((180, 240, 3), 90, dtype=np.uint8)
    for passo in range(20):
        monitor.processar(vazio, 10.0 + passo / 30.0)
    assert len(monitor.janela) == 0


@pytest.mark.parametrize("suavizacao", (0.1, 0.3, 0.5, 1.0))
def test_suavizacao_do_bpm_exibido(suavizacao: float) -> None:
    monitor = MonitorCardiaco(
        fps=30.0, config=ConfiguracaoAnalise(suavizacao_bpm=suavizacao)
    )
    primeiro = monitor._suavizar(60.0)
    segundo = monitor._suavizar(90.0)
    assert primeiro == 60.0
    if suavizacao >= 1.0:
        assert segundo == 90.0
    else:
        assert 60.0 < segundo < 90.0
        assert segundo == pytest.approx(60.0 + suavizacao * 30.0)


def test_reiniciar_o_monitor_zera_tudo() -> None:
    fonte = FonteSintetica(parametros(72.0, duracao_s=13.0, largura=240, altura=180))
    monitor = MonitorCardiaco(
        fps=fonte.fps,
        config=ConfiguracaoAnalise(janela_s=8.0),
        rastreador=rastreador_fixo(fonte),
    )
    for quadro, instante in fonte.quadros():
        monitor.processar(quadro, instante)
    assert monitor.bpm_atual is not None

    monitor.reiniciar()
    assert monitor.bpm_atual is None
    assert monitor.ultima_analise is None
    assert len(monitor.janela) == 0


# --------------------------------------------------------------------------
# Relatório de sessão
# --------------------------------------------------------------------------
def test_relatorio_vazio_devolve_valores_neutros() -> None:
    relatorio = RelatorioSessao()
    assert relatorio.total_estimativas == 0
    assert relatorio.taxa_deteccao == 0.0
    assert not np.isfinite(relatorio.bpm_mediano)
    assert not np.isfinite(relatorio.desvio_bpm)
    assert relatorio.confianca_predominante is Confianca.DESCARTADA


@pytest.mark.parametrize("bpm", (58.0, 72.0, 88.0, 115.0))
def test_relatorio_de_sessao_completa(bpm: float) -> None:
    fonte = FonteSintetica(parametros(bpm, duracao_s=16.0, largura=240, altura=180))
    relatorio = analisar_fonte(
        fonte,
        ConfiguracaoAnalise(janela_s=10.0, algoritmo="pos"),
        rastreador=rastreador_fixo(fonte),
    )
    assert relatorio.total_estimativas > 0
    assert abs(relatorio.bpm_mediano - bpm) < 3.0
    assert relatorio.taxa_deteccao == pytest.approx(1.0)
    assert np.isfinite(relatorio.snr_mediano_db)
    assert relatorio.confianca_predominante in tuple(Confianca)


@pytest.mark.parametrize("limite", (30, 60, 120))
def test_limite_de_quadros_e_respeitado(limite: int) -> None:
    fonte = FonteSintetica(parametros(72.0, duracao_s=20.0, largura=240, altura=180))
    relatorio = analisar_fonte(
        fonte, rastreador=rastreador_fixo(fonte), limite_quadros=limite
    )
    assert relatorio.quadros_processados == limite


def test_desvio_entre_janelas_e_pequeno_com_pulso_estavel() -> None:
    """Um pulso constante deve produzir janelas concordantes; dispersão grande
    seria sinal de instabilidade do estimador."""
    fonte = FonteSintetica(parametros(80.0, duracao_s=22.0, largura=240, altura=180))
    relatorio = analisar_fonte(
        fonte,
        ConfiguracaoAnalise(janela_s=10.0, passo_s=1.0, algoritmo="pos"),
        rastreador=rastreador_fixo(fonte),
    )
    assert relatorio.total_estimativas >= 5
    assert relatorio.desvio_bpm < 2.0
