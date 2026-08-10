"""Entidades de saída: a estimativa de batimentos e sua qualidade."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

import numpy as np


class Confianca(str, Enum):
    """Classificação legível da qualidade de uma estimativa."""

    ALTA = "alta"
    MEDIA = "média"
    BAIXA = "baixa"
    DESCARTADA = "descartada"

    @classmethod
    def de_snr(cls, snr_db: float) -> "Confianca":
        if snr_db >= 6.0:
            return cls.ALTA
        if snr_db >= 2.0:
            return cls.MEDIA
        if snr_db >= 0.0:
            return cls.BAIXA
        return cls.DESCARTADA


@dataclass(frozen=True, slots=True)
class EstimativaBPM:
    """Resultado de uma janela de análise."""

    bpm: float
    frequencia_hz: float
    snr_db: float
    confianca: Confianca
    algoritmo: str
    janela_s: float

    @classmethod
    def criar(
        cls,
        frequencia_hz: float,
        snr_db: float,
        algoritmo: str,
        janela_s: float,
    ) -> "EstimativaBPM":
        return cls(
            bpm=frequencia_hz * 60.0,
            frequencia_hz=frequencia_hz,
            snr_db=snr_db,
            confianca=Confianca.de_snr(snr_db),
            algoritmo=algoritmo,
            janela_s=janela_s,
        )

    @property
    def aproveitavel(self) -> bool:
        return self.confianca is not Confianca.DESCARTADA


@dataclass(frozen=True, slots=True)
class VariabilidadeCardiaca:
    """Índices de HRV no domínio do tempo, calculados a partir dos intervalos
    entre batimentos consecutivos.

    Só faz sentido com sinal limpo e janela longa; com webcam comum trate como
    indicativo, não como medida clínica.
    """

    intervalos_ms: np.ndarray
    media_ms: float
    sdnn_ms: float
    rmssd_ms: float
    pnn50: float

    @classmethod
    def de_intervalos(cls, intervalos_ms: np.ndarray) -> "VariabilidadeCardiaca":
        intervalos_ms = np.asarray(intervalos_ms, dtype=float)
        if len(intervalos_ms) < 2:
            return cls(intervalos_ms, float("nan"), float("nan"), float("nan"), float("nan"))
        diferencas = np.diff(intervalos_ms)
        return cls(
            intervalos_ms=intervalos_ms,
            media_ms=float(np.mean(intervalos_ms)),
            sdnn_ms=float(np.std(intervalos_ms, ddof=1)),
            rmssd_ms=float(np.sqrt(np.mean(diferencas**2))),
            pnn50=float(np.mean(np.abs(diferencas) > 50.0)),
        )

    @property
    def bpm_medio(self) -> float:
        if not np.isfinite(self.media_ms) or self.media_ms <= 0:
            return float("nan")
        return 60000.0 / self.media_ms


@dataclass(frozen=True, slots=True)
class Espectro:
    """Densidade espectral de potência restrita à banda cardíaca."""

    frequencias_hz: np.ndarray
    potencias: np.ndarray

    @property
    def bpm(self) -> np.ndarray:
        return self.frequencias_hz * 60.0

    def normalizado(self) -> np.ndarray:
        maximo = float(np.max(self.potencias)) if len(self.potencias) else 0.0
        if maximo <= 0:
            return np.zeros_like(self.potencias)
        return self.potencias / maximo
