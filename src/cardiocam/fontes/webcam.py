"""Captura ao vivo pela webcam."""

from __future__ import annotations

import sys
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
        travar_automaticos: bool = True,
    ) -> None:
        self.indice = indice
        self.largura = largura
        self.altura = altura
        self.fps = fps_desejado
        self.espelhar = espelhar
        self.travar_automaticos = travar_automaticos
        self.ajustes_travados: dict[str, bool] = {}
        self.backend = "não aberto"
        self._captura: cv2.VideoCapture | None = None
        self._inicio: float | None = None
        self.quadros_perdidos = 0

    def _backends(self) -> list[tuple[int, str]]:
        """Backends a tentar, em ordem de preferência para a plataforma."""
        if sys.platform.startswith("win"):
            # No Windows o MSMF é o padrão e costuma entregar o fps correto, mas
            # falha em algumas webcams quando outro programa já abriu o
            # dispositivo. O DirectShow é mais antigo e mais tolerante nesse
            # caso, então serve de reserva.
            return [
                (cv2.CAP_MSMF, "Media Foundation"),
                (cv2.CAP_DSHOW, "DirectShow"),
                (cv2.CAP_ANY, "padrão"),
            ]
        return [(cv2.CAP_ANY, "padrão")]

    @staticmethod
    def _consegue_capturar(captura: cv2.VideoCapture, tentativas: int = 12) -> bool:
        """Confirma que a câmera realmente entrega quadros.

        `isOpened` só diz que o dispositivo foi reservado, não que ele produz
        imagem. Várias webcams abrem e falham na primeira leitura quando outro
        programa está usando o sensor, ou quando a resolução pedida não é
        suportada. Sem esta checagem, o programa seguia em frente e só
        descobria o problema lá na frente, com a mensagem errada de que nenhuma
        janela produziu estimativa.
        """
        for _ in range(tentativas):
            capturou, quadro = captura.read()
            if capturou and quadro is not None and quadro.size > 0:
                return True
            time.sleep(0.05)
        return False

    def abrir(self) -> Resultado["FonteWebcam"]:
        """Abre a câmera, confirma que ela entrega imagem e ajusta a resolução."""
        ultimo_erro = "a câmera não foi encontrada"

        for backend, nome_backend in self._backends():
            captura = cv2.VideoCapture(self.indice, backend)
            if not captura.isOpened():
                captura.release()
                ultimo_erro = f"o backend {nome_backend} não conseguiu abrir o dispositivo"
                continue

            captura.set(cv2.CAP_PROP_FRAME_WIDTH, self.largura)
            captura.set(cv2.CAP_PROP_FRAME_HEIGHT, self.altura)
            captura.set(cv2.CAP_PROP_FPS, self.fps)
            # Buffer pequeno reduz o atraso entre o que acontece e o que é medido.
            captura.set(cv2.CAP_PROP_BUFFERSIZE, 1)

            if not self._consegue_capturar(captura):
                # Pedir uma resolução não suportada é uma causa comum de a
                # câmera abrir e não transmitir. Tenta de novo aceitando o que
                # o dispositivo oferecer.
                captura.release()
                captura = cv2.VideoCapture(self.indice, backend)
                if captura.isOpened():
                    captura.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                    if self._consegue_capturar(captura):
                        self._registrar(captura, nome_backend)
                        return Ok(self)
                captura.release()
                ultimo_erro = (
                    f"o backend {nome_backend} abriu a câmera mas não recebeu "
                    "nenhum quadro"
                )
                continue

            self._registrar(captura, nome_backend)
            return Ok(self)

        return Falha(
            FonteIndisponivel(
                f"Não foi possível usar a câmera {self.indice}: {ultimo_erro}.\n"
                "O motivo mais comum é outro programa estar com a câmera aberta. "
                "Feche navegador, Teams, Meet, Discord ou o app Câmera do Windows "
                "e tente de novo."
            )
        )

    # Valores que significam "exposição manual" em cada convenção de backend.
    #
    # 0,25 é a convenção do DirectShow e do V4L2, onde 0,75 significa
    # automático. 0 é a do Media Foundation, onde 1 significa automático.
    #
    # A ordem importa e a ausência do 1,0 é deliberada: a versão anterior desta
    # função tentava (0.25, 0.0, 1.0), e 1,0 **liga** a exposição automática no
    # Media Foundation, que é o primeiro backend tentado no Windows. Era o
    # oposto do objetivo da função, na câmera mais comum do público do projeto.
    VALORES_DE_EXPOSICAO_MANUAL = (0.25, 0.0)

    @staticmethod
    def _confirmou(captura: cv2.VideoCapture, propriedade: int, desejado: float) -> bool:
        """Grava a propriedade e confere lendo de volta.

        `set` devolve verdadeiro quando o backend aceitou a chamada, e isso não
        quer dizer que o valor pegou: há relato de sobra de câmera que aceita a
        chamada e ignora o pedido, e o comportamento varia entre DirectShow e
        Media Foundation. A versão anterior confiava no retorno de `set` e
        parava no primeiro verdadeiro, então anunciava "automáticos travados"
        sem ter travado nada, e a interface repetia a mentira para o usuário.

        Comparação com tolerância porque alguns backends devolvem o valor
        quantizado, por exemplo 0,25 lido como 0,249.
        """
        if not captura.set(propriedade, desejado):
            return False
        lido = captura.get(propriedade)
        return abs(float(lido) - desejado) < 0.05

    def travar_ajustes_automaticos(self, captura: cv2.VideoCapture) -> dict[str, bool]:
        """Tenta desligar exposição e balanço de branco automáticos.

        Este é o ajuste de câmera que mais afeta a qualidade da medição. Os dois
        controles trabalham exatamente contra o que queremos medir: quando a
        pele escurece por causa do pulso, a exposição automática compensa
        clareando a imagem, apagando parte do sinal; e o balanço de branco
        automático mexe no ganho de cada canal separadamente, criando uma
        variação de cor que os métodos cromáticos não conseguem cancelar, já que
        eles supõem distorção igual nos três canais.

        Muitas webcams simplesmente não expõem esses controles. Não é erro:
        devolvemos **só o que foi confirmado por leitura de volta**, para que a
        interface possa avisar que a medição vai depender da rectificação por
        referência de fundo.
        """
        aplicado = {"exposicao": False, "balanco_de_branco": False}

        for valor in self.VALORES_DE_EXPOSICAO_MANUAL:
            if self._confirmou(captura, cv2.CAP_PROP_AUTO_EXPOSURE, valor):
                aplicado["exposicao"] = True
                break

        if aplicado["exposicao"]:
            # Passar para manual sem fixar um tempo de exposição deixa a câmera
            # no último valor que o automático escolheu, que pode ser o de um
            # quadro em que a cena ainda estava escura. Fixar um valor do meio
            # da faixa evita abrir a sessão com a imagem estourada ou preta.
            atual = captura.get(cv2.CAP_PROP_EXPOSURE)
            if atual == 0.0:
                captura.set(cv2.CAP_PROP_EXPOSURE, -6.0)

        if self._confirmou(captura, cv2.CAP_PROP_AUTO_WB, 0.0):
            aplicado["balanco_de_branco"] = True

        return aplicado

    def _registrar(self, captura: cv2.VideoCapture, nome_backend: str) -> None:
        """Guarda a captura que funcionou e a taxa de quadros informada."""
        relatada = captura.get(cv2.CAP_PROP_FPS)
        if relatada and 1.0 < relatada < 240.0:
            self.fps = float(relatada)
        self.largura = int(captura.get(cv2.CAP_PROP_FRAME_WIDTH)) or self.largura
        self.altura = int(captura.get(cv2.CAP_PROP_FRAME_HEIGHT)) or self.altura
        self.backend = nome_backend
        self.ajustes_travados = (
            self.travar_ajustes_automaticos(captura) if self.travar_automaticos else {}
        )
        self._captura = captura

    def quadros(self) -> Iterator[Quadro]:
        if self._captura is None:
            raise RuntimeError("A câmera precisa ser aberta antes de ler quadros.")

        self._inicio = time.perf_counter()
        falhas_seguidas = 0
        while True:
            capturou, quadro = self._captura.read()
            if not capturou or quadro is None:
                # Uma falha isolada de leitura é comum e não deve encerrar a
                # sessão: webcams baratas perdem quadros esporadicamente. Só
                # desistimos quando o dispositivo para de responder de vez.
                self.quadros_perdidos += 1
                falhas_seguidas += 1
                if falhas_seguidas >= 30:
                    break
                time.sleep(0.01)
                continue
            falhas_seguidas = 0
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
