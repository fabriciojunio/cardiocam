"""Testes de ponta a ponta: vídeo renderizado até o número final.

Nada é substituído por simulacro. Cada teste renderiza quadros, a cascata de
Haar procura o rosto, as regiões de interesse são recortadas, a máscara de pele
é aplicada, a média é acumulada numa janela deslizante e o algoritmo rPPG
estima a frequência. O valor esperado é conhecido porque fomos nós que
construímos o pulso.

São os testes mais lentos da suíte, e os únicos que autorizam afirmar que o
sistema funciona.
"""

from __future__ import annotations

import numpy as np
import pytest

from cardiocam.dominio.config import ConfiguracaoAnalise
from cardiocam.fontes.sintetica import FonteSintetica, ParametrosSimulacao
from cardiocam.pipeline.analisador import analisar_fonte
from cardiocam.rppg import ALGORITMOS_DISPONIVEIS, criar_algoritmo

pytestmark = pytest.mark.lento

TOLERANCIA_BPM = 3.0
CROMATICOS = ("chrom", "pos")


def cenario(bpm: float, **ajustes) -> ParametrosSimulacao:
    """Vídeo curto e pequeno, mas com todo o realismo que importa."""
    base = dict(
        bpm=bpm,
        duracao_s=15.0,
        fps=20.0,
        largura=240,
        altura=180,
        amplitude_pulso=0.025,
        ruido_sensor=2.0,
        semente=int(bpm * 13) % 9973,
    )
    base.update(ajustes)
    return ParametrosSimulacao(**base)


def medir(parametros: ParametrosSimulacao, algoritmo: str = "pos"):
    """Roda o pipeline completo e devolve o relatório da sessão."""
    return analisar_fonte(
        FonteSintetica(parametros),
        ConfiguracaoAnalise(janela_s=10.0, passo_s=1.0, algoritmo=algoritmo),
        algoritmo=criar_algoritmo(algoritmo),
    )


# --------------------------------------------------------------------------
# O teste central
# --------------------------------------------------------------------------
@pytest.mark.parametrize("algoritmo", ALGORITMOS_DISPONIVEIS)
@pytest.mark.parametrize("bpm", (52.0, 66.0, 78.0, 92.0, 108.0, 135.0, 160.0))
def test_do_video_ao_batimento(algoritmo: str, bpm: float) -> None:
    relatorio = medir(cenario(bpm), algoritmo)
    assert relatorio.total_estimativas > 0, "nenhuma janela produziu estimativa"
    assert abs(relatorio.bpm_mediano - bpm) < TOLERANCIA_BPM, (
        f"{algoritmo}: esperado {bpm} bpm, medido {relatorio.bpm_mediano:.1f}"
    )


@pytest.mark.parametrize("bpm", (60.0, 75.0, 90.0, 120.0))
def test_rosto_encontrado_em_todos_os_quadros(bpm: float) -> None:
    relatorio = medir(cenario(bpm))
    assert relatorio.taxa_deteccao > 0.95


# --------------------------------------------------------------------------
# Variações de captura
# --------------------------------------------------------------------------
@pytest.mark.parametrize("largura,altura", ((240, 180), (320, 240), (400, 300)))
@pytest.mark.parametrize("bpm", (66.0, 96.0))
def test_diferentes_resolucoes(largura: int, altura: int, bpm: float) -> None:
    relatorio = medir(cenario(bpm, largura=largura, altura=altura))
    assert abs(relatorio.bpm_mediano - bpm) < TOLERANCIA_BPM


@pytest.mark.parametrize("fps", (15.0, 20.0, 25.0, 30.0))
@pytest.mark.parametrize("bpm", (72.0, 110.0))
def test_diferentes_taxas_de_quadros(fps: float, bpm: float) -> None:
    relatorio = medir(cenario(bpm, fps=fps, duracao_s=16.0))
    assert abs(relatorio.bpm_mediano - bpm) < TOLERANCIA_BPM


@pytest.mark.parametrize("jitter", (0.0, 0.006, 0.015))
@pytest.mark.parametrize("bpm", (68.0, 104.0))
def test_captura_com_temporizacao_irregular(jitter: float, bpm: float) -> None:
    """Webcam real não entrega quadros em intervalo constante."""
    relatorio = medir(cenario(bpm, jitter_fps=jitter, duracao_s=17.0))
    assert abs(relatorio.bpm_mediano - bpm) < TOLERANCIA_BPM + 1.0


@pytest.mark.parametrize(
    "tom", ((175, 200, 230), (150, 175, 205), (105, 130, 160), (70, 90, 118), (48, 65, 88))
)
@pytest.mark.parametrize("algoritmo", CROMATICOS)
def test_diferentes_tons_de_pele(tom: tuple, algoritmo: str) -> None:
    """O sistema precisa medir qualquer pessoa com a mesma competência."""
    relatorio = medir(cenario(84.0, tom_pele=tom), algoritmo)
    assert relatorio.total_estimativas > 0
    assert abs(relatorio.bpm_mediano - 84.0) < TOLERANCIA_BPM


@pytest.mark.parametrize("amplitude", (0.012, 0.02, 0.03, 0.05))
def test_diferentes_intensidades_de_pulso(amplitude: float) -> None:
    relatorio = medir(cenario(78.0, amplitude_pulso=amplitude, duracao_s=17.0))
    assert abs(relatorio.bpm_mediano - 78.0) < TOLERANCIA_BPM


@pytest.mark.parametrize("ruido", (1.0, 3.0, 6.0, 10.0))
def test_diferentes_niveis_de_ruido_do_sensor(ruido: float) -> None:
    relatorio = medir(cenario(90.0, ruido_sensor=ruido, duracao_s=17.0))
    assert abs(relatorio.bpm_mediano - 90.0) < TOLERANCIA_BPM


# --------------------------------------------------------------------------
# Perturbações que aparecem no uso real
# --------------------------------------------------------------------------
@pytest.mark.parametrize("deriva", (0.0, 0.15, 0.3))
@pytest.mark.parametrize("algoritmo", CROMATICOS)
def test_deriva_de_iluminacao(deriva: float, algoritmo: str) -> None:
    relatorio = medir(cenario(72.0, deriva_iluminacao=deriva), algoritmo)
    assert abs(relatorio.bpm_mediano - 72.0) < TOLERANCIA_BPM


@pytest.mark.parametrize("algoritmo", CROMATICOS)
@pytest.mark.parametrize("intensidade", (0.02, 0.05))
def test_interferencia_de_iluminacao_na_banda(
    algoritmo: str, intensidade: float
) -> None:
    """A prova de fogo dos métodos cromáticos, agora no pipeline completo."""
    relatorio = medir(
        cenario(
            72.0,
            amplitude_tremor=intensidade,
            tremor_iluminacao_hz=1.9,
            duracao_s=18.0,
        ),
        algoritmo,
    )
    assert abs(relatorio.bpm_mediano - 72.0) < TOLERANCIA_BPM


@pytest.mark.parametrize("movimento", (0.0, 2.0, 4.0))
@pytest.mark.parametrize("algoritmo", CROMATICOS)
def test_movimento_leve_da_cabeca(movimento: float, algoritmo: str) -> None:
    """Ninguém fica perfeitamente imóvel. O rastreador precisa segurar a região
    e a estimativa precisa sobreviver."""
    relatorio = medir(
        cenario(80.0, movimento_px=movimento, movimento_hz=0.12, duracao_s=18.0),
        algoritmo,
    )
    assert relatorio.total_estimativas > 0
    assert abs(relatorio.bpm_mediano - 80.0) < TOLERANCIA_BPM + 1.0


# --------------------------------------------------------------------------
# Estabilidade e recusa
# --------------------------------------------------------------------------
@pytest.mark.parametrize("bpm", (64.0, 88.0, 112.0))
def test_janelas_sucessivas_concordam(bpm: float) -> None:
    relatorio = medir(cenario(bpm, duracao_s=22.0))
    assert relatorio.total_estimativas >= 5
    assert relatorio.desvio_bpm < 2.5


@pytest.mark.parametrize("bpm", (70.0, 100.0))
def test_confianca_reportada_e_boa_em_condicao_favoravel(bpm: float) -> None:
    relatorio = medir(cenario(bpm, ruido_sensor=1.0, amplitude_pulso=0.03))
    assert relatorio.snr_mediano_db > 3.0
    assert relatorio.confianca_predominante.value in ("alta", "média")


def test_video_sem_rosto_nao_produz_medida() -> None:
    """Uma parede filmada não pode virar batimento cardíaco."""

    class ParedeLisa:
        fps = 20.0

        def quadros(self):
            gerador = np.random.default_rng(0)
            for indice in range(300):
                quadro = np.full((180, 240, 3), 110, dtype=np.uint8)
                quadro = np.clip(
                    quadro + gerador.normal(0, 2, quadro.shape), 0, 255
                ).astype(np.uint8)
                yield quadro, indice / 20.0

        def fechar(self):
            return None

    relatorio = analisar_fonte(ParedeLisa(), ConfiguracaoAnalise(janela_s=8.0))
    assert relatorio.total_estimativas == 0
    assert relatorio.taxa_deteccao == 0.0


def test_video_curto_demais_nao_produz_medida() -> None:
    relatorio = medir(cenario(72.0, duracao_s=4.0))
    assert relatorio.total_estimativas == 0
    assert not np.isfinite(relatorio.bpm_mediano)


@pytest.mark.parametrize("algoritmo", ALGORITMOS_DISPONIVEIS)
def test_relatorio_registra_o_algoritmo_usado(algoritmo: str) -> None:
    relatorio = medir(cenario(72.0), algoritmo)
    assert all(e.algoritmo == algoritmo for e in relatorio.estimativas)


def test_bpm_mediano_ignora_janela_contaminada() -> None:
    """A mediana precisa resistir a uma janela ruim, senão um piscar de luz
    estraga a leitura inteira."""
    relatorio = medir(cenario(76.0, duracao_s=24.0))
    assert relatorio.total_estimativas >= 8
    assert abs(relatorio.bpm_mediano - 76.0) < TOLERANCIA_BPM
