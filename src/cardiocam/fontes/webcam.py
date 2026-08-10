"""Captura ao vivo pela webcam."""

from __future__ import annotations

import time
from typing import Iterator

import cv2

from cardiocam.dominio.erros import FonteIndisponivel
from cardiocam.dominio.resultado import Falha, Ok, Resultado
from cardiocam.fontes.base import Quadro


class FonteWebcam:
    """Quadros de uma câmera, com carimbo de tempo medido na chegada.

    O tempo vem do relógio monotônico do sistema no instante em que o quadro
    chega, e não de um contador dividido pelo fps nominal. A diferença importa:
    a taxa anunciada pela câmera raramente é a taxa entregue, e usar a nominal
    desloca sistematicamente a frequência estimada.
    """

    def __init__(
        self,
        indice: int = 0,
        largura: int = 640,
        altura: int = 480,
        fps_desejado: float = 30.0,
        espelhar: bool = True,
    ) -> None:
        self.indice = indice
        self.largura = largura
        self.altura = altura
        self.fps = fps_desejado
        self.espelhar = espelhar
        self._captura: cv2.VideoCapture | None = None
        self._inicio: float | None = None

    def abrir(self) -> Resultado["FonteWebcam"]:
        """Tenta abrir a câmera e configurar a resolução."""
        captura = cv2.VideoCapture(self.indice, cv2.CAP_ANY)
        if not captura.isOpened():
            captura.release()
            return Falha(
                FonteIndisponivel(
                    f"Não foi possível abrir a câmera {self.indice}. Verifique se "
                    "ela está conectada e se nenhum outro programa está usando."
                )
            )

        captura.set(cv2.CAP_PROP_FRAME_WIDTH, self.largura)
        captura.set(cv2.CAP_PROP_FRAME_HEIGHT, self.altura)
        captura.set(cv2.CAP_PROP_FPS, self.fps)
        # Buffer pequeno reduz o atraso entre o que acontece e o que é medido.
        captura.set(cv2.CAP_PROP_BUFFERSIZE, 1)

        relatada = captura.get(cv2.CAP_PROP_FPS)
        if relatada and relatada > 0:
            self.fps = float(relatada)

        self._captura = captura
        return Ok(self)

    def quadros(self) -> Iterator[Quadro]:
        if self._captura is None:
            raise RuntimeError("A câmera precisa ser aberta antes de ler quadros.")

        self._inicio = time.perf_counter()
        while True:
            capturou, quadro = self._captura.read()
            if not capturou or quadro is None:
                break
            instante = time.perf_counter() - self._inicio
            if self.espelhar:
                # Espelhar deixa a imagem parecida com um espelho, que é o que a
                # pessoa espera ao se ver na tela.
                quadro = cv2.flip(quadro, 1)
            yield quadro, instante

    def fechar(self) -> None:
        if self._captura is not None:
            self._captura.release()
            self._captura = None

    def __enter__(self) -> "FonteWebcam":
        resultado = self.abrir()
        if resultado.falhou:
            raise resultado.erro
        return self

    def __exit__(self, *_: object) -> None:
        self.fechar()


def abrir_webcam(indice: int = 0, **opcoes: object) -> Resultado[FonteWebcam]:
    """Cria e abre uma fonte de webcam, devolvendo falha em vez de exceção."""
    fonte = FonteWebcam(indice=indice, **opcoes)  # type: ignore[arg-type]
    return fonte.abrir()
