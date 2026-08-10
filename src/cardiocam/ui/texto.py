"""Desenho de texto acentuado sobre os quadros.

As fontes Hershey que o `cv2.putText` usa são vetoriais e cobrem apenas ASCII:
qualquer acento vira um retângulo vazio. Como a interface é em português,
desenhamos o texto com Pillow, que usa fontes TrueType do sistema.

A conversão entre o array do OpenCV e a imagem do Pillow custa alguns
milissegundos, então todas as legendas de um quadro são desenhadas numa única
passagem, em vez de uma conversão por texto.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

try:
    from PIL import Image, ImageDraw, ImageFont

    PILLOW_DISPONIVEL = True
except ImportError:  # pragma: sem cobertura
    PILLOW_DISPONIVEL = False

FONTES_CANDIDATAS = (
    "C:/Windows/Fonts/segoeui.ttf",
    "C:/Windows/Fonts/arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/Library/Fonts/Arial.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
)


@dataclass(frozen=True, slots=True)
class ItemTexto:
    """Uma legenda a ser desenhada."""

    texto: str
    posicao: tuple[int, int]
    tamanho: int = 18
    cor: tuple[int, int, int] = (255, 255, 255)
    """Cor em BGR, para ficar consistente com o resto do OpenCV."""
    negrito: bool = False


def _sem_acentos(texto: str) -> str:
    """Versão ASCII do texto, para o caso de não haver fonte disponível."""
    normalizado = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in normalizado if not unicodedata.combining(c))


class PincelTexto:
    """Desenha texto com acentuação correta, com degradação elegante."""

    def __init__(self, caminho_fonte: str | Path | None = None) -> None:
        self._cache_fontes: dict[int, object] = {}
        self.caminho_fonte = self._descobrir_fonte(caminho_fonte)

    @staticmethod
    def _descobrir_fonte(preferida: str | Path | None) -> str | None:
        if preferida and Path(preferida).exists():
            return str(preferida)
        for candidata in FONTES_CANDIDATAS:
            if Path(candidata).exists():
                return candidata
        return None

    @property
    def usa_truetype(self) -> bool:
        return PILLOW_DISPONIVEL and self.caminho_fonte is not None

    def _fonte(self, tamanho: int):
        if tamanho not in self._cache_fontes:
            if self.caminho_fonte:
                self._cache_fontes[tamanho] = ImageFont.truetype(
                    self.caminho_fonte, tamanho
                )
            else:
                self._cache_fontes[tamanho] = ImageFont.load_default(size=tamanho)
        return self._cache_fontes[tamanho]

    def _desenhar_com_opencv(
        self, imagem: np.ndarray, itens: list[ItemTexto]
    ) -> np.ndarray:
        """Reserva para quando o Pillow não estiver instalado."""
        for item in itens:
            escala = item.tamanho / 30.0
            cv2.putText(
                imagem,
                _sem_acentos(item.texto),
                item.posicao,
                cv2.FONT_HERSHEY_SIMPLEX,
                escala,
                item.cor,
                2 if item.negrito else 1,
                cv2.LINE_AA,
            )
        return imagem

    def escrever(self, imagem: np.ndarray, itens: list[ItemTexto]) -> np.ndarray:
        """Desenha todas as legendas de uma vez e devolve a imagem alterada."""
        if not itens:
            return imagem
        if not PILLOW_DISPONIVEL:
            return self._desenhar_com_opencv(imagem, itens)

        tela = Image.fromarray(cv2.cvtColor(imagem, cv2.COLOR_BGR2RGB))
        lapis = ImageDraw.Draw(tela)
        for item in itens:
            azul, verde, vermelho = item.cor
            lapis.text(
                item.posicao,
                item.texto,
                font=self._fonte(item.tamanho),
                fill=(vermelho, verde, azul),
            )
        return cv2.cvtColor(np.array(tela), cv2.COLOR_RGB2BGR)

    def medir(self, texto: str, tamanho: int) -> tuple[int, int]:
        """Largura e altura aproximadas do texto, para alinhar elementos."""
        if not PILLOW_DISPONIVEL:
            (largura, altura), _ = cv2.getTextSize(
                _sem_acentos(texto), cv2.FONT_HERSHEY_SIMPLEX, tamanho / 30.0, 1
            )
            return largura, altura
        fonte = self._fonte(tamanho)
        caixa = fonte.getbbox(texto)
        return int(caixa[2] - caixa[0]), int(caixa[3] - caixa[1])
