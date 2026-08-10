"""Contrato das fontes de vídeo.

Webcam, arquivo e simulador entregam a mesma coisa: uma sequência de pares
(quadro, instante). O instante vem da fonte, e não de um contador de quadros,
porque webcam não entrega quadros em intervalo constante e essa irregularidade
precisa chegar ao processamento de sinais para ser corrigida.
"""

from __future__ import annotations

from typing import Iterator, Protocol, runtime_checkable

import numpy as np

Quadro = tuple[np.ndarray, float]


@runtime_checkable
class FonteVideo(Protocol):
    """Qualquer origem de quadros consumível pelo pipeline."""

    fps: float

    def quadros(self) -> Iterator[Quadro]:
        """Itera sobre `(imagem_bgr, instante_em_segundos)`."""
        ...

    def fechar(self) -> None:
        """Libera os recursos da fonte."""
        ...
