"""Perturbações reprodutíveis; não alteram os instantes nem a referência."""

from dataclasses import dataclass

import cv2
import numpy as np


@dataclass(frozen=True)
class Perturbacao:
    movimento_px: float = 0
    iluminacao: float = 0
    frequencia_hz: float = .2
    ruido: float = 0
    congelar_cada: int = 0
    semente: int = 0

    def __post_init__(self):
        if (not np.isfinite([self.movimento_px, self.iluminacao, self.frequencia_hz, self.ruido]).all()
                or self.movimento_px < 0 or not 0 <= self.iluminacao < 1
                or self.frequencia_hz <= 0 or self.ruido < 0 or self.congelar_cada < 0):
            raise ValueError("Perturbação inválida.")

    def criar(self):
        ultimo = None

        def aplicar(imagem, instante, indice):
            nonlocal ultimo
            if not np.isfinite(instante) or indice < 0:
                raise ValueError("Instante ou índice inválido.")
            if self.congelar_cada and indice % self.congelar_cada == 0 and ultimo is not None:
                return ultimo.copy()
            fase = 2*np.pi*self.frequencia_hz*instante
            matriz = np.float32([[1, 0, self.movimento_px*np.sin(fase)],
                                 [0, 1, self.movimento_px*np.cos(fase)]])
            h, w = imagem.shape[:2]
            y = cv2.warpAffine(imagem, matriz, (w, h), borderMode=cv2.BORDER_REFLECT_101).astype(float)
            y *= 1+self.iluminacao*np.sin(fase)
            if self.ruido:
                rng = np.random.default_rng(np.random.SeedSequence([self.semente, indice]))
                y += rng.normal(0, self.ruido, y.shape)
            ultimo = np.clip(np.round(y), 0, 255).astype(np.uint8)
            return ultimo.copy()
        return aplicar
