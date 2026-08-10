"""Análise no domínio do tempo: onde estão os batimentos.

O espectro responde "qual a frequência média na janela". Contar picos responde
"quando bateu", que é o que permite calcular variabilidade. As duas estimativas
concordando é um bom indício de que o sinal é real e não um artefato periódico
de iluminação.
"""

from __future__ import annotations

import numpy as np
from scipy import signal as scipy_signal

from cardiocam.dominio.estimativa import VariabilidadeCardiaca
from cardiocam.dominio.sinal import BandaCardiaca, SinalPulso


def detectar_picos(
    pulso: SinalPulso,
    banda: BandaCardiaca | None = None,
    proeminencia_relativa: float = 0.3,
    frequencia_esperada_hz: float | None = None,
) -> np.ndarray:
    """Índices dos picos sistólicos do sinal de pulso.

    A distância mínima entre picos vem do limite superior da banda: acima de
    240 bpm não é batimento, é ruído. A proeminência é relativa ao desvio padrão
    da janela, então o critério acompanha a amplitude do sinal em vez de depender
    de um limiar absoluto.

    Quando o espectro já indicou uma frequência dominante, passe-a em
    `frequencia_esperada_hz`: a distância mínima passa a ser 70% do período
    esperado, o que impede que o entalhe dicrótico (o segundo bico da onda de
    pulso, em 2f) seja contado como batimento. Sem essa dica, sinais com
    harmônico forte tendem a ser contados em dobro.
    """
    banda = banda or BandaCardiaca()
    if len(pulso) < 3:
        return np.zeros(0, dtype=int)

    amostras = pulso.normalizado()
    if frequencia_esperada_hz and frequencia_esperada_hz > 0:
        distancia_minima = max(1, int(0.7 * pulso.fps / frequencia_esperada_hz))
    else:
        distancia_minima = max(1, int(pulso.fps / banda.maxima_hz))
    proeminencia = proeminencia_relativa * float(np.std(amostras))
    if proeminencia <= 0:
        return np.zeros(0, dtype=int)

    indices, _ = scipy_signal.find_peaks(
        amostras, distance=distancia_minima, prominence=proeminencia
    )
    return np.asarray(indices, dtype=int)


def intervalos_entre_batimentos(indices: np.ndarray, fps: float) -> np.ndarray:
    """Intervalos consecutivos entre picos, em milissegundos."""
    if fps <= 0:
        raise ValueError("A taxa de quadros precisa ser positiva.")
    indices = np.asarray(indices, dtype=float)
    if indices.size < 2:
        return np.zeros(0)
    return np.diff(indices) * (1000.0 / fps)


def filtrar_intervalos(
    intervalos_ms: np.ndarray, tolerancia: float = 0.3
) -> np.ndarray:
    """Descarta intervalos implausíveis (batimento perdido ou pico espúrio).

    Um pico não detectado dobra o intervalo; um pico falso corta pela metade.
    Removemos o que se afasta demais da mediana, que resiste bem a esse tipo de
    contaminação.
    """
    intervalos = np.asarray(intervalos_ms, dtype=float)
    if intervalos.size < 3:
        return intervalos
    mediana = float(np.median(intervalos))
    if mediana <= 0:
        return intervalos
    desvio_relativo = np.abs(intervalos - mediana) / mediana
    return intervalos[desvio_relativo <= tolerancia]


def bpm_por_picos(
    pulso: SinalPulso,
    banda: BandaCardiaca | None = None,
    frequencia_esperada_hz: float | None = None,
) -> float:
    """Frequência cardíaca estimada pela mediana dos intervalos.

    Devolve NaN quando não há batimentos suficientes para uma mediana confiável.

    Atenção à quantização: com 30 quadros por segundo, um batimento a 200 bpm
    dura 9 quadros e a 210 bpm dura 8,6. Como o pico cai sempre num quadro
    inteiro, a resolução desta via degrada em frequências altas, e a estimativa
    espectral passa a ser a mais confiável.
    """
    banda = banda or BandaCardiaca()
    indices = detectar_picos(
        pulso, banda, frequencia_esperada_hz=frequencia_esperada_hz
    )
    intervalos = filtrar_intervalos(intervalos_entre_batimentos(indices, pulso.fps))
    if intervalos.size < 2:
        return float("nan")
    mediana_ms = float(np.median(intervalos))
    if mediana_ms <= 0:
        return float("nan")
    bpm = 60000.0 / mediana_ms
    if not banda.contem_bpm(bpm):
        return float("nan")
    return bpm


def variabilidade(
    pulso: SinalPulso,
    banda: BandaCardiaca | None = None,
    frequencia_esperada_hz: float | None = None,
) -> VariabilidadeCardiaca:
    """Índices de HRV no domínio do tempo para a janela analisada."""
    banda = banda or BandaCardiaca()
    indices = detectar_picos(
        pulso, banda, frequencia_esperada_hz=frequencia_esperada_hz
    )
    intervalos = filtrar_intervalos(intervalos_entre_batimentos(indices, pulso.fps))
    return VariabilidadeCardiaca.de_intervalos(intervalos)
