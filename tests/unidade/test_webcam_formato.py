"""Testes do pedido de formato à câmera.

Existe por causa de dezenove segundos medidos. No Media Foundation, que é o
primeiro backend tentado no Windows, cada `set` de largura, altura ou taxa
renegocia o formato com o dispositivo. Numa EMEET SmartCam S600 cada uma dessas
três chamadas custou **6,3 segundos**, e a abertura inteira levava 25,6 s.

O detalhe que transforma isso em desperdício puro: a câmera **já abria em 640x480
a 30 quadros por segundo**, exatamente o que estava sendo pedido. Eram dezenove
segundos gastos pedindo o que já estava feito.

Num programa de linha de comando isso é um incômodo. Num aplicativo com um botão
é um defeito: a pessoa clica em Ligar e durante meio minuto nada acontece.

O teste cobra as duas metades da regra, e a segunda é a que importa: pedir
quando o valor **difere** é tão necessário quanto não pedir quando ele já bate.
Uma correção que simplesmente removesse as chamadas passaria na primeira metade
e quebraria toda câmera que abre num formato diferente do que a medição precisa.
"""

from __future__ import annotations

import cv2
import pytest

from cardiocam.fontes.webcam import FonteWebcam


class CapturaFalsa:
    """Imita o `cv2.VideoCapture` no que esta regra usa.

    Guarda o que foi pedido, para o teste poder cobrar **ausência** de chamada,
    que é o ponto. Verificar o resultado não bastaria: a câmera acaba no formato
    certo dos dois jeitos, e a diferença entre eles são os dezenove segundos.
    """

    def __init__(self, atual: dict[int, float] | None = None) -> None:
        # O dicionário entra posicionado, e não como palavras-chave: as chaves
        # são as constantes inteiras do OpenCV, e nome de argumento em Python
        # precisa ser texto.
        self.atual = dict(atual or {})
        self.pedidos: list[tuple[int, float]] = []

    def get(self, propriedade: int) -> float:
        return float(self.atual.get(propriedade, 0.0))

    def set(self, propriedade: int, valor: float) -> bool:
        self.pedidos.append((propriedade, float(valor)))
        self.atual[propriedade] = float(valor)
        return True


@pytest.fixture
def fonte() -> FonteWebcam:
    return FonteWebcam(indice=0, largura=640, altura=480, fps_desejado=30.0)


class TestNaoPedirOQueJaEsta:
    def test_camera_ja_no_formato_certo_nao_recebe_pedido(self, fonte):
        """O caso medido: 640x480 a 30, que é o que ela já entregava."""
        captura = CapturaFalsa(
            {
                cv2.CAP_PROP_FRAME_WIDTH: 640.0,
                cv2.CAP_PROP_FRAME_HEIGHT: 480.0,
                cv2.CAP_PROP_FPS: 30.0,
            }
        )
        fonte._pedir_formato(captura)
        assert captura.pedidos == []

    def test_diferenca_abaixo_de_meio_nao_conta(self, fonte):
        """Taxa declarada como 29,97 é a mesma coisa que 30 para este fim.

        Câmera que anuncia a taxa de vídeo NTSC devolve 29,97, e tratar isso
        como divergência traria de volta os seis segundos por nada.
        """
        captura = CapturaFalsa(
            {
                cv2.CAP_PROP_FRAME_WIDTH: 640.0,
                cv2.CAP_PROP_FRAME_HEIGHT: 480.0,
                cv2.CAP_PROP_FPS: 29.97,
            }
        )
        fonte._pedir_formato(captura)
        assert captura.pedidos == []


class TestPedirQuandoDifere:
    def test_formato_diferente_recebe_os_tres_pedidos(self, fonte):
        captura = CapturaFalsa(
            {
                cv2.CAP_PROP_FRAME_WIDTH: 1920.0,
                cv2.CAP_PROP_FRAME_HEIGHT: 1080.0,
                cv2.CAP_PROP_FPS: 15.0,
            }
        )
        fonte._pedir_formato(captura)
        assert captura.pedidos == [
            (cv2.CAP_PROP_FRAME_WIDTH, 640.0),
            (cv2.CAP_PROP_FRAME_HEIGHT, 480.0),
            (cv2.CAP_PROP_FPS, 30.0),
        ]

    def test_pede_so_o_que_difere(self, fonte):
        """Resolução certa e taxa errada pede a taxa, e só ela."""
        captura = CapturaFalsa(
            {
                cv2.CAP_PROP_FRAME_WIDTH: 640.0,
                cv2.CAP_PROP_FRAME_HEIGHT: 480.0,
                cv2.CAP_PROP_FPS: 10.0,
            }
        )
        fonte._pedir_formato(captura)
        assert captura.pedidos == [(cv2.CAP_PROP_FPS, 30.0)]


class TestCameraQueNaoResponde:
    def test_valor_zero_significa_nao_sei(self, fonte):
        """Backend que devolve 0 não está dizendo "zero": está dizendo que não
        sabe. Nesse caso o pedido tem de ser feito, senão a câmera fica no
        formato que estiver."""
        captura = CapturaFalsa(
            {
                cv2.CAP_PROP_FRAME_WIDTH: 0.0,
                cv2.CAP_PROP_FRAME_HEIGHT: 0.0,
                cv2.CAP_PROP_FPS: 0.0,
            }
        )
        fonte._pedir_formato(captura)
        assert len(captura.pedidos) == 3

    def test_consulta_que_levanta_excecao_leva_ao_pedido(self, fonte):
        """Alguns backends levantam em vez de devolver valor. Engolir a
        exceção e pedir é o lado seguro: pedir à toa custa tempo, não pedir
        quando era preciso custa a medição."""

        class CapturaRabugenta(CapturaFalsa):
            def get(self, propriedade: int) -> float:
                raise RuntimeError("este backend não responde a consulta")

        captura = CapturaRabugenta()
        fonte._pedir_formato(captura)
        assert len(captura.pedidos) == 3
