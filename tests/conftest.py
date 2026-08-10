"""Fixtures e utilidades comuns aos testes.

Princípio adotado na suíte: nada de simulacro. Os testes executam o código real
sobre sinais e imagens gerados por um modelo físico do fenômeno, com a
frequência verdadeira conhecida. Quando um teste afirma que o sistema mede
72 bpm, é porque o pipeline inteiro rodou sobre um vídeo em que o pulso foi
construído a 72 bpm.
"""

from __future__ import annotations

import cv2
import numpy as np
import pytest

# O OpenCV paraleliza a detecção internamente. Rodando a suíte com pytest-xdist,
# cada processo abriria o próprio conjunto de threads e a máquina ficaria com
# mais threads do que núcleos. Sob essa disputa a detecção chega a falhar em
# quadros que normalmente resolve, e testes determinísticos passam a falhar de
# forma intermitente. O paralelismo aqui vem do xdist, um processo por núcleo;
# dentro de cada processo, uma thread só.
cv2.setNumThreads(1)

from cardiocam.dominio.config import ConfiguracaoAnalise
from cardiocam.dominio.sinal import BandaCardiaca, SinalPulso
from cardiocam.fontes.sintetica import (
    FonteSintetica,
    ParametrosSimulacao,
    gerar_serie_rgb,
)

# Grades usadas para parametrizar em massa. Cobrem de bradicardia a taquicardia
# intensa, que é a faixa em que o sistema promete funcionar.
BPMS_AMPLOS = (42.0, 48.0, 55.0, 60.0, 66.0, 72.0, 78.0, 84.0, 90.0, 96.0,
               104.0, 112.0, 120.0, 132.0, 144.0, 156.0, 168.0, 180.0, 200.0, 220.0)
BPMS_COMUNS = (50.0, 60.0, 72.0, 85.0, 100.0, 120.0, 150.0, 180.0)
BPMS_CURTOS = (55.0, 72.0, 95.0, 130.0)

TAXAS_QUADROS = (15.0, 20.0, 24.0, 25.0, 30.0, 50.0, 60.0)
ORDENS_FILTRO = (2, 3, 4, 5, 6)


@pytest.fixture
def banda() -> BandaCardiaca:
    return BandaCardiaca()


@pytest.fixture
def config() -> ConfiguracaoAnalise:
    return ConfiguracaoAnalise()


def parametros(bpm: float, **ajustes) -> ParametrosSimulacao:
    """Cenário sintético com padrões convenientes para teste."""
    base = dict(
        bpm=bpm,
        duracao_s=14.0,
        fps=30.0,
        amplitude_pulso=0.02,
        ruido_sensor=2.0,
        semente=int(bpm * 7) % 10_000,
    )
    base.update(ajustes)
    return ParametrosSimulacao(**base)


def serie_de(bpm: float, **ajustes):
    """Série RGB analítica com pulso na frequência pedida."""
    return gerar_serie_rgb(parametros(bpm, **ajustes))


def fonte_de(bpm: float, **ajustes) -> FonteSintetica:
    """Fonte de vídeo sintético com pulso na frequência pedida."""
    return FonteSintetica(parametros(bpm, **ajustes))


def senoide(
    bpm: float,
    fps: float = 30.0,
    duracao_s: float = 12.0,
    ruido: float = 0.0,
    semente: int = 0,
    harmonicos: tuple[float, ...] = (1.0,),
) -> np.ndarray:
    """Sinal sintético direto, sem passar pelo modelo de pele.

    Usado nos testes das rotinas de processamento de sinais, onde o que
    interessa é a matemática e não a fotometria.
    """
    tempos = np.arange(int(duracao_s * fps)) / fps
    frequencia = bpm / 60.0
    onda = np.zeros_like(tempos)
    for ordem, amplitude in enumerate(harmonicos, start=1):
        onda += amplitude * np.sin(2.0 * np.pi * ordem * frequencia * tempos)
    if ruido > 0:
        onda = onda + np.random.default_rng(semente).normal(0.0, ruido, onda.size)
    return onda


def pulso_de(bpm: float, fps: float = 30.0, duracao_s: float = 12.0, **kw) -> SinalPulso:
    """Sinal de pulso pronto para a análise espectral."""
    return SinalPulso(senoide(bpm, fps, duracao_s, **kw), fps, "teste")
