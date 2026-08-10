"""Entidades de sinal: a série RGB bruta e o sinal de pulso derivado dela."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from cardiocam.dominio.erros import BandaInvalida, FrequenciaAmostragemInvalida


@dataclass(frozen=True, slots=True)
class BandaCardiaca:
    """Banda de frequências fisiologicamente plausíveis para o pulso humano.

    O padrão de 0,7 a 4,0 Hz cobre de 42 a 240 bpm, ou seja, do repouso profundo
    de um atleta ao esforço máximo.
    """

    minima_hz: float = 0.7
    maxima_hz: float = 4.0

    def __post_init__(self) -> None:
        if self.minima_hz <= 0:
            raise BandaInvalida("A frequência mínima da banda precisa ser positiva.")
        if self.maxima_hz <= self.minima_hz:
            raise BandaInvalida(
                f"Banda inconsistente: máxima ({self.maxima_hz} Hz) não é maior "
                f"que a mínima ({self.minima_hz} Hz)."
            )

    @property
    def minima_bpm(self) -> float:
        return self.minima_hz * 60.0

    @property
    def maxima_bpm(self) -> float:
        return self.maxima_hz * 60.0

    def contem_hz(self, frequencia_hz: float) -> bool:
        return self.minima_hz <= frequencia_hz <= self.maxima_hz

    def contem_bpm(self, bpm: float) -> bool:
        return self.minima_bpm <= bpm <= self.maxima_bpm

    def fps_minimo(self) -> float:
        """Taxa mínima de quadros que evita rebatimento na banda (Nyquist)."""
        return 2.0 * self.maxima_hz

    def validar_fps(self, fps: float) -> None:
        minimo = self.fps_minimo()
        if fps < minimo:
            raise FrequenciaAmostragemInvalida(fps, minimo)


@dataclass(frozen=True, slots=True)
class SerieRGB:
    """Média espacial dos canais R, G e B da pele, um valor por quadro.

    É a ponte entre a parte de imagem e a parte de sinais: cada quadro de vídeo
    vira três números.
    """

    vermelho: np.ndarray
    verde: np.ndarray
    azul: np.ndarray
    fps: float
    instantes: np.ndarray = field(default=None)  # type: ignore[assignment]

    def __post_init__(self) -> None:
        tamanhos = {len(self.vermelho), len(self.verde), len(self.azul)}
        if len(tamanhos) != 1:
            raise ValueError("Os três canais precisam ter o mesmo número de amostras.")
        if self.fps <= 0:
            raise ValueError("A taxa de quadros precisa ser positiva.")
        if self.instantes is None:
            object.__setattr__(
                self, "instantes", np.arange(len(self.verde), dtype=float) / self.fps
            )
        elif len(self.instantes) != len(self.verde):
            raise ValueError("O vetor de instantes não casa com o número de amostras.")

    def __len__(self) -> int:
        return len(self.verde)

    @property
    def duracao_s(self) -> float:
        return len(self) / self.fps

    def como_matriz(self) -> np.ndarray:
        """Matriz 3xN na ordem R, G, B, que é a entrada dos algoritmos rPPG."""
        return np.vstack([self.vermelho, self.verde, self.azul])

    @classmethod
    def de_matriz(cls, matriz: np.ndarray, fps: float) -> "SerieRGB":
        if matriz.shape[0] != 3:
            raise ValueError("A matriz precisa ter três linhas, uma por canal.")
        return cls(matriz[0], matriz[1], matriz[2], fps)

    def ultimos(self, quantidade: int) -> "SerieRGB":
        """Recorta a cauda da série, que é o que a janela deslizante consome."""
        n = min(quantidade, len(self))
        return SerieRGB(
            self.vermelho[-n:], self.verde[-n:], self.azul[-n:], self.fps,
            self.instantes[-n:],
        )


@dataclass(frozen=True, slots=True)
class SinalPulso:
    """Sinal de pulso unidimensional já extraído pelo algoritmo rPPG."""

    amostras: np.ndarray
    fps: float
    origem: str = "desconhecida"

    def __post_init__(self) -> None:
        if self.fps <= 0:
            raise ValueError("A taxa de quadros precisa ser positiva.")
        if self.amostras.ndim != 1:
            raise ValueError("O sinal de pulso precisa ser unidimensional.")

    def __len__(self) -> int:
        return len(self.amostras)

    @property
    def duracao_s(self) -> float:
        return len(self) / self.fps

    def normalizado(self) -> np.ndarray:
        """Escore z; devolve zeros se o sinal for constante."""
        desvio = float(np.std(self.amostras))
        if desvio < 1e-12:
            return np.zeros_like(self.amostras)
        return (self.amostras - float(np.mean(self.amostras))) / desvio
