"""Análise espectral: de um sinal de pulso para uma frequência em batimentos.

A resolução bruta de uma FFT é fs/N. Numa janela de 10 s isso dá 0,1 Hz, ou seja
6 bpm, o que é grosseiro demais para exibir. Resolvemos em duas etapas:

1. Preenchimento com zeros, que não cria informação nova mas interpola o
   espectro numa grade bem mais fina, revelando o formato real do lóbulo.
2. Interpolação parabólica em torno do bin de pico. Como a janela de Hann tem
   lóbulo principal simétrico, o vértice da parábola ajustada aos três pontos
   centrais cai praticamente sobre a frequência verdadeira.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy import signal as scipy_signal

from cardiocam.dominio.erros import JanelaInsuficiente
from cardiocam.dominio.estimativa import Espectro
from cardiocam.dominio.resultado import Falha, Ok, Resultado
from cardiocam.dominio.sinal import BandaCardiaca, SinalPulso

FATOR_ZERO_PADDING = 8
LARGURA_SNR_HZ = 0.1

SNR_MAXIMO_DB = 60.0
"""Teto da relação sinal-ruído reportada.

Um valor infinito é matematicamente correto quando não sobra energia fora do
pico, mas contamina qualquer média ou mediana calculada depois e transmite uma
certeza que nenhuma medição óptica sustenta. Sessenta decibéis já significam um
milhão de vezes mais sinal que ruído."""


@dataclass(frozen=True, slots=True)
class AnaliseEspectral:
    """Saída completa da análise: onde está o pico e o quanto ele se destaca."""

    frequencia_hz: float
    snr_db: float
    espectro: Espectro

    @property
    def bpm(self) -> float:
        return self.frequencia_hz * 60.0


def _proxima_potencia_de_dois(valor: int) -> int:
    return 1 << max(0, int(valor - 1)).bit_length()


def periodograma(
    amostras: np.ndarray, fps: float, zero_padding: int = FATOR_ZERO_PADDING
) -> tuple[np.ndarray, np.ndarray]:
    """Densidade espectral por FFT de janela única com apodização de Hann."""
    entrada = np.asarray(amostras, dtype=float)
    n = entrada.size
    if n < 2:
        return np.zeros(0), np.zeros(0)

    entrada = entrada - np.mean(entrada)
    janela = np.hanning(n)
    apodizado = entrada * janela

    n_fft = _proxima_potencia_de_dois(n * max(1, zero_padding))
    espectro = np.fft.rfft(apodizado, n=n_fft)
    frequencias = np.fft.rfftfreq(n_fft, d=1.0 / fps)

    # Normalização coerente com a perda de energia da janela.
    ganho = np.sum(janela**2)
    potencias = (np.abs(espectro) ** 2) / (ganho * fps)
    return frequencias, potencias


def welch(
    amostras: np.ndarray, fps: float, segmentos: int = 3
) -> tuple[np.ndarray, np.ndarray]:
    """Densidade espectral por média de periodogramas (Welch).

    Troca resolução em frequência por variância menor. Útil quando o sinal está
    ruidoso e o pico do periodograma simples fica instável entre janelas.
    """
    entrada = np.asarray(amostras, dtype=float)
    n = entrada.size
    if n < 8:
        return np.zeros(0), np.zeros(0)
    por_segmento = max(8, n // max(1, segmentos))
    frequencias, potencias = scipy_signal.welch(
        entrada,
        fs=fps,
        window="hann",
        nperseg=min(por_segmento, n),
        noverlap=min(por_segmento, n) // 2,
        nfft=_proxima_potencia_de_dois(min(por_segmento, n) * FATOR_ZERO_PADDING),
        detrend="constant",
    )
    return frequencias, potencias


def refinar_pico(
    frequencias: np.ndarray, potencias: np.ndarray, indice: int
) -> float:
    """Interpolação parabólica em escala logarítmica em torno do bin de pico.

    Ajusta uma parábola aos três pontos centrais e devolve a abscissa do vértice.
    Nas bordas do vetor não há vizinho dos dois lados, então devolvemos o próprio
    bin.
    """
    if indice <= 0 or indice >= len(potencias) - 1:
        return float(frequencias[indice])

    anterior, central, posterior = potencias[indice - 1 : indice + 2]
    if anterior <= 0 or central <= 0 or posterior <= 0:
        return float(frequencias[indice])

    esquerda = np.log(anterior)
    meio = np.log(central)
    direita = np.log(posterior)
    denominador = esquerda - 2.0 * meio + direita
    if abs(denominador) < 1e-18:
        return float(frequencias[indice])

    deslocamento = 0.5 * (esquerda - direita) / denominador
    deslocamento = float(np.clip(deslocamento, -0.5, 0.5))
    passo = float(frequencias[indice + 1] - frequencias[indice])
    return float(frequencias[indice] + deslocamento * passo)


def relacao_sinal_ruido(
    frequencias: np.ndarray,
    potencias: np.ndarray,
    frequencia_hz: float,
    banda: BandaCardiaca,
    largura_hz: float = LARGURA_SNR_HZ,
) -> float:
    """Relação sinal-ruído no espectro, em decibéis.

    Segue a definição usada na literatura de rPPG: considera sinal a energia
    próxima da fundamental e do primeiro harmônico, e ruído todo o resto da
    banda cardíaca. O harmônico entra porque o pulso não é senoidal — a onda tem
    subida rápida e descida lenta, o que sempre deposita energia em 2f.
    """
    na_banda = (frequencias >= banda.minima_hz) & (frequencias <= banda.maxima_hz)
    if not np.any(na_banda):
        return float("-inf")

    fundamental = np.abs(frequencias - frequencia_hz) <= largura_hz
    harmonico = np.abs(frequencias - 2.0 * frequencia_hz) <= 2.0 * largura_hz
    e_sinal = (fundamental | harmonico) & na_banda
    e_ruido = na_banda & ~e_sinal

    potencia_sinal = float(np.sum(potencias[e_sinal]))
    potencia_ruido = float(np.sum(potencias[e_ruido]))

    if potencia_sinal <= 1e-20:
        return float("-inf")
    if potencia_ruido <= 1e-20:
        return SNR_MAXIMO_DB
    return float(
        min(SNR_MAXIMO_DB, 10.0 * np.log10(potencia_sinal / potencia_ruido))
    )


def recortar_banda(
    frequencias: np.ndarray, potencias: np.ndarray, banda: BandaCardiaca
) -> Espectro:
    """Espectro restrito à banda cardíaca, que é o que a interface desenha."""
    mascara = (frequencias >= banda.minima_hz) & (frequencias <= banda.maxima_hz)
    return Espectro(frequencias[mascara], potencias[mascara])


def analisar(
    pulso: SinalPulso,
    banda: BandaCardiaca | None = None,
    metodo: str = "periodograma",
    zero_padding: int = FATOR_ZERO_PADDING,
) -> Resultado[AnaliseEspectral]:
    """Encontra a frequência dominante do pulso dentro da banda fisiológica.

    Uma variante deste seletor foi testada e descartada: pontuar cada candidata
    somando a energia encontrada no dobro da frequência, na expectativa de que o
    pulso, por ter harmônico, vencesse artefatos senoidais. A medição mostrou
    que a ideia premia subharmônicos, porque uma interferência a 48 bpm recebe o
    bônus do próprio pulso a 96 bpm. Na faixa em que o sistema já acertava tudo,
    a taxa caiu de 100% para 75%. O maior pico simples continua sendo o melhor
    critério.
    """
    banda = banda or BandaCardiaca()
    if len(pulso) < 8:
        return Falha(JanelaInsuficiente(len(pulso), 8))

    if metodo == "welch":
        frequencias, potencias = welch(pulso.amostras, pulso.fps)
    elif metodo == "periodograma":
        frequencias, potencias = periodograma(pulso.amostras, pulso.fps, zero_padding)
    else:
        raise ValueError(
            f"Método espectral desconhecido: {metodo!r}. "
            "Use 'periodograma' ou 'welch'."
        )

    if frequencias.size == 0:
        return Falha(JanelaInsuficiente(len(pulso), 8))

    na_banda = (frequencias >= banda.minima_hz) & (frequencias <= banda.maxima_hz)
    if not np.any(na_banda):
        return Falha(JanelaInsuficiente(len(pulso), 8))

    indices_banda = np.flatnonzero(na_banda)
    indice_pico = int(indices_banda[np.argmax(potencias[indices_banda])])

    frequencia = refinar_pico(frequencias, potencias, indice_pico)
    frequencia = float(np.clip(frequencia, banda.minima_hz, banda.maxima_hz))
    snr_db = relacao_sinal_ruido(frequencias, potencias, frequencia, banda)

    return Ok(
        AnaliseEspectral(
            frequencia_hz=frequencia,
            snr_db=snr_db,
            espectro=recortar_banda(frequencias, potencias, banda),
        )
    )
