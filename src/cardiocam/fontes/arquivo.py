"""Leitura de vídeo gravado."""

from __future__ import annotations

from pathlib import Path
from typing import Iterator

import cv2

from cardiocam.dominio.erros import FonteIndisponivel
from cardiocam.dominio.resultado import Falha, Ok, Resultado
from cardiocam.fontes.base import Quadro


class FonteArquivo:
    """Quadros de um arquivo de vídeo.

    O instante de cada quadro vem da própria posição no arquivo, o que permite
    analisar corretamente vídeos com taxa de quadros variável.
    """

    def __init__(self, caminho: str | Path) -> None:
        self.caminho = Path(caminho)
        self.fps = 0.0
        self.total_quadros = 0
        self._captura: cv2.VideoCapture | None = None

    def abrir(self) -> Resultado["FonteArquivo"]:
        if not self.caminho.exists():
            return Falha(
                FonteIndisponivel(f"O arquivo {self.caminho} não foi encontrado.")
            )

        captura = cv2.VideoCapture(str(self.caminho))
        if not captura.isOpened():
            captura.release()
            return Falha(
                FonteIndisponivel(
                    f"Não foi possível decodificar {self.caminho}. O formato pode "
                    "não ser suportado pela instalação do OpenCV."
                )
            )

        fps = captura.get(cv2.CAP_PROP_FPS)
        self.fps = float(fps) if fps and fps > 0 else 30.0
        self.total_quadros = int(captura.get(cv2.CAP_PROP_FRAME_COUNT))
        self._captura = captura
        return Ok(self)

    def quadros(self) -> Iterator[Quadro]:
        if self._captura is None:
            raise RuntimeError("O arquivo precisa ser aberto antes de ler quadros.")

        indice = 0
        while True:
            posicao_ms = self._captura.get(cv2.CAP_PROP_POS_MSEC)
            capturou, quadro = self._captura.read()
            if not capturou or quadro is None:
                break
            # Alguns contêineres não preenchem a posição em milissegundos;
            # nesse caso caímos no tempo nominal.
            if posicao_ms and posicao_ms > 0:
                instante = float(posicao_ms) / 1000.0
            else:
                instante = indice / self.fps
            indice += 1
            yield quadro, instante

    def fechar(self) -> None:
        if self._captura is not None:
            self._captura.release()
            self._captura = None

    def __enter__(self) -> "FonteArquivo":
        resultado = self.abrir()
        if resultado.falhou:
            raise resultado.erro
        return self

    def __exit__(self, *_: object) -> None:
        self.fechar()


def abrir_arquivo(caminho: str | Path) -> Resultado[FonteArquivo]:
    """Cria e abre uma fonte de arquivo, devolvendo falha em vez de exceção."""
    return FonteArquivo(caminho).abrir()
