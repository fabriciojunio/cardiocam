"""Detecção de rosto.

Usamos o detector de Viola-Jones em cascata que acompanha o OpenCV. Ele é de
2001, roda em CPU sem esforço e é exatamente o tipo de técnica que a disciplina
cobre: características de Haar calculadas em tempo constante via imagem
integral, selecionadas por AdaBoost e organizadas em cascata, de modo que a
maioria das janelas candidatas é descartada nos primeiros estágios.

A alternativa moderna seria uma rede neural (o YuNet, que também vem no
OpenCV). Ela é mais robusta a rosto de perfil, mas exige baixar um arquivo de
pesos, e a cascata basta para alguém sentado de frente para a câmera.
"""

from __future__ import annotations

from typing import Protocol

import cv2
import numpy as np

from cardiocam.dominio.erros import RostoNaoEncontrado
from cardiocam.dominio.resultado import Falha, Ok, Resultado
from cardiocam.visao.geometria import Retangulo

CASCATA_PADRAO = "haarcascade_frontalface_default.xml"
CASCATA_ALTERNATIVA = "haarcascade_frontalface_alt2.xml"


class DetectorFace(Protocol):
    """Contrato de qualquer detector, para o pipeline não depender do OpenCV."""

    def detectar(self, quadro: np.ndarray) -> Resultado[Retangulo]:
        """Devolve o rosto mais proeminente do quadro."""
        ...


class DetectorHaar:
    """Detector em cascata de Haar.

    `escala` controla o passo da pirâmide de resoluções: valores próximos de 1
    encontram mais rostos e custam mais tempo. O padrão de 1,05 foi escolhido
    por medição, não por hábito: com 1,1 a taxa de detecção cai visivelmente em
    rostos menores dentro do quadro, e perder o rosto custa mais caro que gastar
    alguns milissegundos a mais, já que o rastreador só roda o detector a cada
    poucos quadros.

    `vizinhos_minimos` é quantas detecções sobrepostas são exigidas para aceitar
    a região, e funciona como controle de falso positivo.
    """

    def __init__(
        self,
        cascata: str = CASCATA_PADRAO,
        escala: float = 1.05,
        vizinhos_minimos: int = 5,
        tamanho_minimo_relativo: float = 0.15,
        equalizar: bool = True,
    ) -> None:
        caminho = cv2.data.haarcascades + cascata
        self._classificador = cv2.CascadeClassifier(caminho)
        if self._classificador.empty():
            raise RuntimeError(
                f"Não foi possível carregar a cascata em {caminho}. "
                "A instalação do OpenCV parece incompleta."
            )
        self.escala = escala
        self.vizinhos_minimos = vizinhos_minimos
        self.tamanho_minimo_relativo = tamanho_minimo_relativo
        self.equalizar = equalizar

    def _preparar(self, quadro: np.ndarray) -> np.ndarray:
        if quadro.ndim == 3:
            cinza = cv2.cvtColor(quadro, cv2.COLOR_BGR2GRAY)
        else:
            cinza = quadro
        # A equalização de histograma normaliza o contraste, o que ajuda quando
        # a pessoa está contra a luz ou o ambiente está mal iluminado.
        return cv2.equalizeHist(cinza) if self.equalizar else cinza

    def detectar_todos(self, quadro: np.ndarray) -> list[Retangulo]:
        """Todos os rostos encontrados, do maior para o menor."""
        if quadro is None or quadro.size == 0:
            return []
        cinza = self._preparar(quadro)
        altura, largura = cinza.shape[:2]
        lado_minimo = max(20, int(min(altura, largura) * self.tamanho_minimo_relativo))

        deteccoes = self._classificador.detectMultiScale(
            cinza,
            scaleFactor=self.escala,
            minNeighbors=self.vizinhos_minimos,
            minSize=(lado_minimo, lado_minimo),
        )
        if len(deteccoes) == 0:
            return []
        caixas = [Retangulo(int(x), int(y), int(w), int(h)) for x, y, w, h in deteccoes]
        return sorted(caixas, key=lambda caixa: caixa.area, reverse=True)

    def detectar(self, quadro: np.ndarray) -> Resultado[Retangulo]:
        """O maior rosto do quadro.

        Escolhemos o maior porque, numa medição, quem está sendo medido é quem
        está mais perto da câmera; rostos ao fundo são distração.
        """
        caixas = self.detectar_todos(quadro)
        if not caixas:
            return Falha(RostoNaoEncontrado())
        return Ok(caixas[0])


class DetectorRegiaoFixa:
    """Detector degenerado que devolve sempre a mesma região.

    Serve para medir a pele de alguém sem depender da detecção facial, para
    analisar vídeos onde o rosto está parado e enquadrado, e para isolar a parte
    de sinais nos testes.
    """

    def __init__(self, regiao: Retangulo) -> None:
        if regiao.vazio:
            raise ValueError("A região fixa não pode ser vazia.")
        self.regiao = regiao

    def detectar(self, quadro: np.ndarray) -> Resultado[Retangulo]:
        if quadro is None or quadro.size == 0:
            return Falha(RostoNaoEncontrado())
        altura, largura = quadro.shape[:2]
        limitada = self.regiao.limitar(largura, altura)
        if limitada.vazio:
            return Falha(RostoNaoEncontrado())
        return Ok(limitada)


class DetectorCentral:
    """Recorta uma fração central do quadro.

    É a rede de segurança quando não há detecção disponível: a pessoa
    normalmente está no meio da imagem.
    """

    def __init__(self, fracao: float = 0.4) -> None:
        if not 0.0 < fracao <= 1.0:
            raise ValueError("A fração precisa estar entre 0 e 1.")
        self.fracao = fracao

    def detectar(self, quadro: np.ndarray) -> Resultado[Retangulo]:
        if quadro is None or quadro.size == 0:
            return Falha(RostoNaoEncontrado())
        altura, largura = quadro.shape[:2]
        lado_l = int(largura * self.fracao)
        lado_a = int(altura * self.fracao)
        if lado_l <= 0 or lado_a <= 0:
            return Falha(RostoNaoEncontrado())
        return Ok(
            Retangulo(
                (largura - lado_l) // 2, (altura - lado_a) // 2, lado_l, lado_a
            )
        )
