"""Filtragem passa-faixa na banda cardíaca.

Usamos Butterworth em seções de segunda ordem (SOS) por estabilidade numérica, e
aplicamos com `sosfiltfilt` para filtragem de fase zero: o filtro roda para
frente e para trás, então o atraso de grupo se cancela e os picos do pulso não
saem deslocados no tempo. O preço é que a ordem efetiva dobra.
"""

from __future__ import annotations

import numpy as np
from scipy import signal

from cardiocam.dominio.erros import BandaInvalida, JanelaInsuficiente
from cardiocam.dominio.resultado import Falha, Ok, Resultado
from cardiocam.dominio.sinal import BandaCardiaca


def _validar_banda(banda: BandaCardiaca, fps: float) -> tuple[float, float]:
    """Converte a banda para frequência normalizada e checa Nyquist."""
    nyquist = fps / 2.0
    baixa = banda.minima_hz / nyquist
    alta = banda.maxima_hz / nyquist
    if not 0.0 < baixa < 1.0:
        raise BandaInvalida(
            f"A frequência de corte inferior ({banda.minima_hz} Hz) precisa ficar "
            f"entre 0 e Nyquist ({nyquist:.2f} Hz)."
        )
    if not 0.0 < alta < 1.0:
        raise BandaInvalida(
            f"A frequência de corte superior ({banda.maxima_hz} Hz) ultrapassa "
            f"Nyquist ({nyquist:.2f} Hz); aumente a taxa de quadros ou reduza a banda."
        )
    return baixa, alta


def projetar_passa_faixa(
    banda: BandaCardiaca, fps: float, ordem: int = 4
) -> np.ndarray:
    """Devolve as seções de segunda ordem do Butterworth passa-faixa."""
    if ordem < 1:
        raise BandaInvalida("A ordem do filtro precisa ser pelo menos 1.")
    baixa, alta = _validar_banda(banda, fps)
    return signal.butter(ordem, [baixa, alta], btype="bandpass", output="sos")


def amostras_minimas(sos: np.ndarray) -> int:
    """Quantidade mínima de amostras que `sosfiltfilt` exige para esse filtro.

    A filtragem bidirecional estende o sinal nas bordas; se a janela for menor
    que essa extensão, a SciPy levanta erro. Preferimos avisar antes.
    """
    n_secoes = sos.shape[0]
    padlen = 3 * (2 * n_secoes + 1 - min(
        int((sos[:, 2] == 0).sum()), int((sos[:, 5] == 0).sum())
    ))
    return padlen + 1


def aplicar_passa_faixa(
    amostras: np.ndarray,
    fps: float,
    banda: BandaCardiaca | None = None,
    ordem: int = 4,
) -> Resultado[np.ndarray]:
    """Filtra o sinal na banda cardíaca, sem deslocamento de fase.

    Aceita vetor 1-D ou matriz (canais nas linhas) e devolve o mesmo formato.
    """
    banda = banda or BandaCardiaca()
    entrada = np.asarray(amostras, dtype=float)
    if entrada.size == 0:
        return Falha(JanelaInsuficiente(0, 1))

    try:
        sos = projetar_passa_faixa(banda, fps, ordem)
    except BandaInvalida as erro:
        return Falha(erro)

    minimo = amostras_minimas(sos)
    n = entrada.shape[-1]
    if n < minimo:
        return Falha(JanelaInsuficiente(n, minimo))

    filtrado = signal.sosfiltfilt(sos, entrada, axis=-1)
    return Ok(np.asarray(filtrado, dtype=float))


def resposta_em_frequencia(
    banda: BandaCardiaca, fps: float, ordem: int = 4, pontos: int = 2048
) -> tuple[np.ndarray, np.ndarray]:
    """Módulo da resposta em frequência do filtro, já elevado ao quadrado para
    refletir a passagem dupla do `filtfilt`.

    Serve para a documentação e para os testes que verificam se a banda passante
    é mesmo onde prometemos.
    """
    sos = projetar_passa_faixa(banda, fps, ordem)
    frequencias, resposta = signal.sosfreqz(sos, worN=pontos, fs=fps)
    return frequencias, np.abs(resposta) ** 2


def media_movel(amostras: np.ndarray, tamanho: int) -> np.ndarray:
    """Média móvel centrada, com bordas replicadas.

    Alternativa barata ao detrend por regularização quando o custo importa mais
    que a qualidade, e base do detrend simples.
    """
    if tamanho < 1:
        raise ValueError("O tamanho da janela da média móvel precisa ser positivo.")
    entrada = np.asarray(amostras, dtype=float)
    if tamanho == 1 or entrada.size == 0:
        return entrada.copy()
    tamanho = min(tamanho, entrada.size)
    if tamanho % 2 == 0:
        tamanho += 1
    borda = tamanho // 2
    estendido = np.pad(entrada, borda, mode="edge")
    nucleo = np.ones(tamanho, dtype=float) / tamanho
    return np.convolve(estendido, nucleo, mode="valid")
