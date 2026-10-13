"""Comparação de estimadores, concordância e acompanhamento temporal."""

from dataclasses import dataclass

import numpy as np
from scipy import signal

from cardiocam.dominio.sinal import BandaCardiaca, SinalPulso
from cardiocam.sinais.espectro import analisar


def autocorrelacao(pulso: SinalPulso, banda: BandaCardiaca = BandaCardiaca()) -> float:
    banda.validar_fps(pulso.fps)
    x = np.asarray(pulso.amostras, dtype=float)
    if len(x) < pulso.fps * 4 or not np.isfinite(x).all() or np.std(x) < 1e-10:
        raise ValueError("Autocorrelação exige quatro segundos de sinal variável e finito.")
    x = signal.detrend(x)
    ac = signal.correlate(x, x, mode="full", method="fft")[len(x)-1:]
    ac /= np.arange(len(x), 0, -1)
    minimo = max(1, int(np.ceil(pulso.fps / banda.maxima_hz)))
    maximo = min(len(x)-2, int(np.floor(pulso.fps / banda.minima_hz)))
    picos, _ = signal.find_peaks(ac[minimo-1:maximo+2])
    picos = picos + minimo - 1
    picos = picos[(picos >= minimo) & (picos <= maximo)]
    if not len(picos):
        raise ValueError("Não há período identificável na banda cardíaca.")
    melhores = picos[ac[picos] >= 0.9 * ac[picos].max()]
    i = int(melhores[0])  # primeiro período; evita escolher múltiplos do período
    a, b, c = ac[i-1:i+2]
    denominador = a - 2*b + c
    delta = 0.0 if abs(denominador) < 1e-14 else float(np.clip(.5*(a-c)/denominador, -.5, .5))
    return float(np.clip(60 * pulso.fps / (i + delta), banda.minima_hz*60, banda.maxima_hz*60))


def comparar_estimadores(pulso: SinalPulso, banda: BandaCardiaca = BandaCardiaca()) -> dict[str, float]:
    if not np.isfinite(pulso.amostras).all() or np.std(pulso.amostras) < 1e-10:
        raise ValueError("Sinal constante ou não finito não produz BPM.")
    banda.validar_fps(pulso.fps)
    return {**{m: analisar(pulso, banda, m).desempacotar().bpm
               for m in ("periodograma", "welch")}, "autocorrelacao": autocorrelacao(pulso, banda)}


@dataclass(frozen=True)
class Candidato:
    regiao: str
    algoritmo: str
    bpm: float
    snr_db: float
    fracao_pele: float = 1.0
    fracao_saturada: float = 0.0
    correlacao_fundo: float | None = 0.0


@dataclass(frozen=True)
class Consenso:
    bpm: float | None
    participantes: tuple[Candidato, ...]
    motivo: str


def fundir(candidatos: list[Candidato], tolerancia_bpm: float = 5.0) -> Consenso:
    """Pede concordância entre regiões E algoritmos; SNR sozinho não decide."""
    if not np.isfinite(tolerancia_bpm) or tolerancia_bpm <= 0:
        raise ValueError("A tolerância precisa ser positiva e finita.")
    validos = [c for c in candidatos if c.correlacao_fundo is not None and np.isfinite([
        c.bpm, c.snr_db, c.fracao_pele, c.fracao_saturada, c.correlacao_fundo]).all()
        and 0 < c.bpm and c.snr_db >= 0 and .5 <= c.fracao_pele <= 1
        and 0 <= c.fracao_saturada < .05 and abs(c.correlacao_fundo) < .8]
    validos.sort(key=lambda c: (c.bpm, c.regiao, c.algoritmo))
    grupos = [validos[i:j+1] for i in range(len(validos)) for j in range(i, len(validos))
              if validos[j].bpm-validos[i].bpm <= tolerancia_bpm]
    grupos = [g for g in grupos if len({c.regiao for c in g}) >= 2
              and len({c.algoritmo for c in g}) >= 2]
    if not grupos:
        return Consenso(None, (), "Sem concordância entre regiões e métodos.")
    grupos.sort(key=lambda g: (len({c.regiao for c in g}), len({c.algoritmo for c in g}), len(g)), reverse=True)
    melhor = grupos[0]
    # Dois agrupamentos independentes igualmente sustentados pedem abstenção.
    for outro in grupos[1:]:
        if len(outro) == len(melhor) and abs(np.median([c.bpm for c in outro]) - np.median([c.bpm for c in melhor])) > tolerancia_bpm:
            return Consenso(None, (), "Há dois consensos incompatíveis.")
    # Cada região recebe um voto, independentemente do número de métodos nela.
    por_regiao = [np.median([c.bpm for c in melhor if c.regiao == r]) for r in sorted({c.regiao for c in melhor})]
    return Consenso(float(np.median(por_regiao)), tuple(melhor), "Concordância experimental; não constitui validação clínica.")


class RastreadorTemporal:
    """Filtro com limite de inovação; recusa saltos e apaga estado após lacuna."""

    def __init__(self, lacuna_s: float = 3, variacao_bpm_s: float = 8):
        if not np.isfinite([lacuna_s, variacao_bpm_s]).all() or min(lacuna_s, variacao_bpm_s) <= 0:
            raise ValueError("Limites temporais precisam ser positivos e finitos.")
        self.lacuna_s, self.variacao_bpm_s = lacuna_s, variacao_bpm_s
        self.reiniciar()

    def reiniciar(self) -> None:
        self.bpm = self.instante = None

    def atualizar(self, instante: float, consenso: Consenso) -> float | None:
        if not np.isfinite(instante):
            raise ValueError("Instante inválido.")
        if self.instante is not None and instante <= self.instante:
            raise ValueError("Os instantes precisam avançar.")
        if self.instante is not None and instante-self.instante > self.lacuna_s:
            self.reiniciar()
        if consenso.bpm is None:
            return None
        if not np.isfinite(consenso.bpm) or consenso.bpm <= 0:
            raise ValueError("BPM inválido.")
        if self.bpm is not None:
            dt = instante-self.instante
            if abs(consenso.bpm-self.bpm) > 3+self.variacao_bpm_s*dt:
                return None
            self.bpm += (1-np.exp(-dt/2)) * (consenso.bpm-self.bpm)
        else:
            self.bpm = consenso.bpm
        self.instante = instante
        return float(self.bpm)
