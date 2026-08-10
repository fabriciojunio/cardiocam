"""Captura de uma região da tela.

Serve para medir alguém que aparece numa chamada de vídeo, num vídeo do
navegador ou em qualquer janela: em vez de ler a câmera local, lemos os pixels
que já estão sendo exibidos.

Duas ressalvas importantes, e ambas valem para o relatório.

A primeira é técnica. O sinal aqui já passou por compressão com perdas. Codecs
de videoconferência usam subamostragem de crominância, tipicamente 4:2:0, o que
significa que a informação de cor é guardada com metade da resolução em cada
eixo. Pior: o controle de taxa descarta justamente variações sutis e espalhadas
por regiões homogêneas, que é a descrição exata do sinal que procuramos. Dá para
medir, mas a relação sinal-ruído cai bastante e exige boa banda, boa iluminação
e a pessoa parada.

A segunda é ética e legal. Medir sinal fisiológico de alguém é tratamento de
dado pessoal sensível segundo a LGPD. Capturar a tela de uma reunião para medir
os batimentos de outra pessoa sem que ela saiba não é aceitável. Use com
consentimento explícito.
"""

from __future__ import annotations

from typing import Iterator

import numpy as np

from cardiocam.dominio.erros import FonteIndisponivel
from cardiocam.dominio.resultado import Falha, Ok, Resultado
from cardiocam.fontes.base import Quadro

try:
    import mss

    MSS_DISPONIVEL = True
except ImportError:  # pragma: sem cobertura
    MSS_DISPONIVEL = False

import time

import cv2


class FonteTela:
    """Quadros lidos de um retângulo da tela."""

    def __init__(
        self,
        x: int = 0,
        y: int = 0,
        largura: int = 640,
        altura: int = 480,
        fps_alvo: float = 30.0,
        monitor: int = 1,
    ) -> None:
        if largura <= 0 or altura <= 0:
            raise ValueError("A região capturada precisa ter área positiva.")
        self.regiao = {"left": x, "top": y, "width": largura, "height": altura}
        self.fps = fps_alvo
        self.monitor = monitor
        self._captura = None

    def abrir(self) -> Resultado["FonteTela"]:
        if not MSS_DISPONIVEL:
            return Falha(
                FonteIndisponivel(
                    "A captura de tela precisa do pacote mss. "
                    "Instale com: pip install mss"
                )
            )
        try:
            self._captura = mss.mss()
        except Exception as causa:  # noqa: BLE001 - fronteira com o sistema gráfico
            erro = FonteIndisponivel(
                "Não foi possível acessar a tela. Em Linux, confira se há "
                "servidor gráfico disponível."
            )
            erro.__cause__ = causa
            return Falha(erro)
        return Ok(self)

    def tela_inteira(self) -> Resultado["FonteTela"]:
        """Ajusta a região para o monitor inteiro."""
        if self._captura is None:
            abertura = self.abrir()
            if abertura.falhou:
                return abertura
        monitores = self._captura.monitors  # type: ignore[union-attr]
        indice = min(self.monitor, len(monitores) - 1)
        self.regiao = dict(monitores[indice])
        return Ok(self)

    def quadros(self) -> Iterator[Quadro]:
        if self._captura is None:
            raise RuntimeError("A captura precisa ser aberta antes de ler quadros.")

        intervalo = 1.0 / self.fps if self.fps > 0 else 0.0
        inicio = time.perf_counter()
        proximo = inicio

        while True:
            agora = time.perf_counter()
            if agora < proximo:
                time.sleep(max(0.0, proximo - agora))
            proximo += intervalo

            bruto = self._captura.grab(self.regiao)
            quadro = cv2.cvtColor(np.asarray(bruto), cv2.COLOR_BGRA2BGR)
            yield quadro, time.perf_counter() - inicio

    def fechar(self) -> None:
        if self._captura is not None:
            self._captura.close()
            self._captura = None

    def __enter__(self) -> "FonteTela":
        resultado = self.abrir()
        if resultado.falhou:
            raise resultado.erro
        return self

    def __exit__(self, *_: object) -> None:
        self.fechar()


def abrir_tela(
    x: int = 0, y: int = 0, largura: int = 640, altura: int = 480, **opcoes: object
) -> Resultado[FonteTela]:
    """Cria e abre uma captura de tela, devolvendo falha em vez de exceção."""
    fonte = FonteTela(x=x, y=y, largura=largura, altura=altura, **opcoes)  # type: ignore[arg-type]
    return fonte.abrir()
