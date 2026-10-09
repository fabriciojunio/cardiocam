"""Controle de exposição de pele com limites explícitos do dispositivo.

Inspiração Skin-AE, não reprodução do controlador da câmera industrial.
A calibração ocorre antes da janela fisiológica e confirma cada leitura.
"""

from dataclasses import dataclass

import cv2
import numpy as np


@dataclass(frozen=True)
class LimitesExposicao:
    minimo: float
    maximo: float
    passo: float
    sentido: int = 1

    def __post_init__(self):
        if (not np.isfinite([self.minimo, self.maximo, self.passo]).all()
                or self.minimo >= self.maximo or self.passo <= 0 or self.sentido not in (-1, 1)):
            raise ValueError("Limites de exposição inválidos.")


@dataclass(frozen=True)
class AjusteExposicao:
    valor: float
    alterado: bool
    confirmado: bool
    estavel: bool
    motivo: str


class ControleExposicaoPele:
    def __init__(self, limites: LimitesExposicao, alvo: tuple[float, float] = (90, 160)):
        if not 0 < alvo[0] < alvo[1] < 255:
            raise ValueError("Faixa de luminância inválida.")
        self.limites, self.alvo = limites, alvo
        self.confirmacoes = 0
        self.encerrado = False
        self.valor_estavel = None

    def ajustar(self, captura, pixels_bgr: np.ndarray) -> AjusteExposicao:
        atual = float(captura.get(cv2.CAP_PROP_EXPOSURE))
        if not np.isfinite(atual) or not self.limites.minimo <= atual <= self.limites.maximo:
            return AjusteExposicao(atual, False, False, False, "Exposição fora dos limites declarados.")
        if self.encerrado:
            if abs(atual-self.valor_estavel) > self.limites.passo*.1:
                self.encerrado = False
                self.confirmacoes = 0
                return AjusteExposicao(atual, False, False, False, "A exposição mudou após a calibração.")
            return AjusteExposicao(atual, False, True, True, "Exposição mantida durante a medição.")
        p = np.asarray(pixels_bgr)
        if p.ndim != 2 or p.shape[1] != 3 or len(p) < 50 or not np.isfinite(p).all() or np.any((p < 0) | (p > 255)):
            raise ValueError("Informe ao menos 50 pixels de pele BGR válidos.")
        mediana = float(np.median(p @ [.114, .587, .299]))
        saturada = float(np.mean(np.any(p >= 254, axis=1)))
        direcao = -1 if mediana > self.alvo[1] or saturada > .02 else (1 if mediana < self.alvo[0] else 0)
        if direcao == 0:
            self.confirmacoes += 1
            self.encerrado = self.confirmacoes >= 3
            if self.encerrado:
                self.valor_estavel = atual
            return AjusteExposicao(atual, False, True, self.encerrado, "Pele na faixa de calibração.")
        self.confirmacoes = 0
        pedido = float(np.clip(atual + direcao*self.limites.sentido*self.limites.passo,
                               self.limites.minimo, self.limites.maximo))
        if pedido == atual:
            return AjusteExposicao(atual, False, True, False, "Limite do dispositivo atingido.")
        aceitou = captura.set(cv2.CAP_PROP_EXPOSURE, pedido)
        lido = float(captura.get(cv2.CAP_PROP_EXPOSURE))
        confirmado = bool(aceitou and np.isfinite(lido) and abs(lido-pedido) <= self.limites.passo*.1)
        if not confirmado:
            captura.set(cv2.CAP_PROP_EXPOSURE, atual)
        return AjusteExposicao(lido, confirmado, confirmado, False,
                              "Ajuste confirmado." if confirmado else "O driver não confirmou o ajuste; restauração solicitada.")
