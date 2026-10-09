"""Detecta vídeo congelado sem guardar imagens da sessão."""

from hashlib import blake2b

import numpy as np


class VigilanteDeQuadros:
    def __init__(self, limite_s: float = 3.0) -> None:
        if not np.isfinite(limite_s) or limite_s <= 0:
            raise ValueError("O limite de congelamento precisa ser positivo e finito.")
        self.limite_s = limite_s
        self.reiniciar()

    def reiniciar(self) -> None:
        self._assinatura = None
        self._desde = None

    def congelado(self, quadro: np.ndarray, instante: float) -> bool:
        assinatura = (quadro.shape, quadro.dtype.str,
                      blake2b(np.ascontiguousarray(quadro).tobytes(), digest_size=16).digest())
        if assinatura != self._assinatura:
            self._assinatura = assinatura
            self._desde = instante
        return instante - self._desde >= self.limite_s
