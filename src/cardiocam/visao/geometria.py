"""Retângulo com as operações que o pipeline precisa."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from cardiocam.dominio.erros import RegiaoInvalida


@dataclass(frozen=True, slots=True)
class Retangulo:
    """Região retangular em coordenadas de pixel, origem no canto superior esquerdo."""

    x: int
    y: int
    largura: int
    altura: int

    def __post_init__(self) -> None:
        if self.largura < 0 or self.altura < 0:
            raise RegiaoInvalida(
                f"Retângulo com dimensão negativa: {self.largura}x{self.altura}."
            )

    @property
    def area(self) -> int:
        return self.largura * self.altura

    @property
    def vazio(self) -> bool:
        return self.area == 0

    @property
    def centro(self) -> tuple[float, float]:
        return (self.x + self.largura / 2.0, self.y + self.altura / 2.0)

    @property
    def direita(self) -> int:
        return self.x + self.largura

    @property
    def base(self) -> int:
        return self.y + self.altura

    def como_tupla(self) -> tuple[int, int, int, int]:
        return (self.x, self.y, self.largura, self.altura)

    def limitar(self, largura_imagem: int, altura_imagem: int) -> "Retangulo":
        """Recorta o retângulo para caber dentro da imagem."""
        x0 = max(0, min(int(self.x), largura_imagem))
        y0 = max(0, min(int(self.y), altura_imagem))
        x1 = max(x0, min(int(self.direita), largura_imagem))
        y1 = max(y0, min(int(self.base), altura_imagem))
        return Retangulo(x0, y0, x1 - x0, y1 - y0)

    def escalar(self, fator: float) -> "Retangulo":
        """Amplia ou reduz mantendo o centro."""
        cx, cy = self.centro
        nova_largura = self.largura * fator
        nova_altura = self.altura * fator
        return Retangulo(
            int(round(cx - nova_largura / 2.0)),
            int(round(cy - nova_altura / 2.0)),
            int(round(nova_largura)),
            int(round(nova_altura)),
        )

    def fracao(
        self, x_inicio: float, y_inicio: float, x_fim: float, y_fim: float
    ) -> "Retangulo":
        """Sub-retângulo em coordenadas relativas (0 a 1) ao próprio retângulo.

        É assim que a testa e as bochechas são definidas a partir da caixa do
        rosto, sem depender da resolução da câmera.
        """
        if not (0.0 <= x_inicio < x_fim <= 1.0 and 0.0 <= y_inicio < y_fim <= 1.0):
            raise RegiaoInvalida(
                "As frações precisam estar entre 0 e 1 e o início vir antes do fim."
            )
        return Retangulo(
            int(round(self.x + x_inicio * self.largura)),
            int(round(self.y + y_inicio * self.altura)),
            int(round((x_fim - x_inicio) * self.largura)),
            int(round((y_fim - y_inicio) * self.altura)),
        )

    def recortar(self, imagem: np.ndarray) -> np.ndarray:
        """Fatia da imagem correspondente ao retângulo, já limitada às bordas."""
        altura, largura = imagem.shape[:2]
        seguro = self.limitar(largura, altura)
        return imagem[seguro.y : seguro.base, seguro.x : seguro.direita]

    def interpolar(self, outro: "Retangulo", peso: float) -> "Retangulo":
        """Mistura dois retângulos; `peso` é quanto o outro contribui."""
        peso = float(np.clip(peso, 0.0, 1.0))
        return Retangulo(
            int(round(self.x + peso * (outro.x - self.x))),
            int(round(self.y + peso * (outro.y - self.y))),
            int(round(self.largura + peso * (outro.largura - self.largura))),
            int(round(self.altura + peso * (outro.altura - self.altura))),
        )

    def sobreposicao(self, outro: "Retangulo") -> float:
        """Índice de Jaccard entre os dois retângulos, de 0 a 1."""
        x0 = max(self.x, outro.x)
        y0 = max(self.y, outro.y)
        x1 = min(self.direita, outro.direita)
        y1 = min(self.base, outro.base)
        if x1 <= x0 or y1 <= y0:
            return 0.0
        intersecao = (x1 - x0) * (y1 - y0)
        uniao = self.area + outro.area - intersecao
        return intersecao / uniao if uniao > 0 else 0.0
