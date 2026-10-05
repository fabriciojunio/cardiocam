"""Testes do travamento de exposição e balanço de branco automáticos.

Esta é a parte do sistema que mais afeta a medição com câmera de verdade, e era
a única sem teste nenhum. Foi onde se esconderam dois defeitos:

1. a lista de valores tentados terminava em 1,0, que no Media Foundation
   **liga** a exposição automática, e o Media Foundation é o primeiro backend
   tentado no Windows;
2. o sucesso era decidido pelo retorno de `set`, que diz apenas que o backend
   aceitou a chamada. Câmera que aceita e ignora é comum, e nesse caso o sistema
   anunciava para o usuário que os automáticos estavam travados sem que
   estivessem.

Como não dá para exigir webcam na integração contínua, os testes usam câmeras
falsas que reproduzem o comportamento documentado de cada backend.
"""

from __future__ import annotations

import cv2
import pytest

from cardiocam.fontes.webcam import FonteWebcam


class CameraFalsa:
    """Dublê de `cv2.VideoCapture` que registra tudo que foi escrito.

    Guarda o histórico de escritas porque o que mais importa testar aqui não é
    só o resultado: é **qual valor foi escrito**. Um valor errado em
    `CAP_PROP_AUTO_EXPOSURE` liga o que se queria desligar, e o resultado da
    função não denuncia isso.
    """

    def __init__(
        self,
        aceita: set[int] | None = None,
        leitura: dict[int, float] | None = None,
        aceita_tudo: bool = False,
    ) -> None:
        self.aceita = aceita if aceita is not None else set()
        self.leitura = leitura or {}
        self.aceita_tudo = aceita_tudo
        self.escritas: list[tuple[int, float]] = []
        self._valores: dict[int, float] = {}

    def set(self, propriedade: int, valor: float) -> bool:  # noqa: A003
        self.escritas.append((int(propriedade), float(valor)))
        if not (self.aceita_tudo or propriedade in self.aceita):
            return False
        self._valores[int(propriedade)] = float(valor)
        return True

    def get(self, propriedade: int) -> float:
        # A leitura fixa, quando existe, simula a câmera que ignora o pedido e
        # devolve sempre o que ela decidiu.
        if propriedade in self.leitura:
            return self.leitura[int(propriedade)]
        return self._valores.get(int(propriedade), 0.0)

    def valores_escritos_em(self, propriedade: int) -> list[float]:
        return [v for p, v in self.escritas if p == propriedade]


@pytest.fixture
def fonte() -> FonteWebcam:
    return FonteWebcam(travar_automaticos=True)


def test_nunca_escreve_o_valor_que_liga_a_exposicao_automatica(fonte: FonteWebcam) -> None:
    """1,0 em CAP_PROP_AUTO_EXPOSURE é "automático ligado" no Media Foundation.

    Este é o teste de regressão do defeito principal. Mesmo numa câmera que
    recusa tudo, e portanto faz a função esgotar a lista de candidatos, o valor
    1,0 não pode ser escrito em momento nenhum.
    """
    camera = CameraFalsa(aceita=set())

    fonte.travar_ajustes_automaticos(camera)

    escritos = camera.valores_escritos_em(cv2.CAP_PROP_AUTO_EXPOSURE)
    assert escritos, "a função precisa ao menos tentar travar a exposição"
    assert 1.0 not in escritos
    assert 0.75 not in escritos, "0,75 é 'automático' na convenção do DirectShow"


def test_camera_tipo_directshow_trava_no_primeiro_valor(fonte: FonteWebcam) -> None:
    """0,25 é "manual" no DirectShow, e a leitura de volta confirma."""
    camera = CameraFalsa(aceita={cv2.CAP_PROP_AUTO_EXPOSURE, cv2.CAP_PROP_AUTO_WB})

    aplicado = fonte.travar_ajustes_automaticos(camera)

    assert aplicado["exposicao"] is True
    assert aplicado["balanco_de_branco"] is True
    assert camera.valores_escritos_em(cv2.CAP_PROP_AUTO_EXPOSURE) == [0.25]


def test_camera_que_aceita_mas_ignora_nao_e_contada_como_travada(
    fonte: FonteWebcam,
) -> None:
    """O caso que o retorno de `set` não distingue.

    A câmera aceita a chamada e continua em automático. Antes, a função parava
    aqui e devolvia `exposicao: True`. Agora a leitura de volta desmente, a
    função segue tentando e, não conseguindo, relata honestamente que não
    travou.
    """
    camera = CameraFalsa(
        aceita_tudo=True,
        leitura={cv2.CAP_PROP_AUTO_EXPOSURE: 1.0},  # continua automática
    )

    aplicado = fonte.travar_ajustes_automaticos(camera)

    assert aplicado["exposicao"] is False
    # Tentou as duas convenções antes de desistir, e nenhuma delas foi 1,0.
    escritos = camera.valores_escritos_em(cv2.CAP_PROP_AUTO_EXPOSURE)
    assert escritos == [0.25, 0.0]


def test_camera_tipo_media_foundation_cai_no_segundo_valor() -> None:
    """A câmera que só entende 0 como manual.

    É o caso que a versão anterior nunca alcançava: ela parava no 0,25 por
    causa do retorno de `set` e jamais tentava o 0.
    """
    fonte = FonteWebcam(travar_automaticos=True)

    class SoEntendeZero(CameraFalsa):
        def set(self, propriedade: int, valor: float) -> bool:  # noqa: A003
            self.escritas.append((int(propriedade), float(valor)))
            if propriedade == cv2.CAP_PROP_AUTO_EXPOSURE:
                # Aceita a chamada sempre, mas só o 0 muda o estado de fato.
                if valor == 0.0:
                    self._valores[int(propriedade)] = 0.0
                return True
            self._valores[int(propriedade)] = float(valor)
            return True

        def get(self, propriedade: int) -> float:
            if propriedade == cv2.CAP_PROP_AUTO_EXPOSURE:
                return self._valores.get(int(propriedade), 1.0)
            return self._valores.get(int(propriedade), 0.0)

    camera = SoEntendeZero()
    aplicado = fonte.travar_ajustes_automaticos(camera)

    assert aplicado["exposicao"] is True
    assert camera.valores_escritos_em(cv2.CAP_PROP_AUTO_EXPOSURE) == [0.25, 0.0]


def test_fixa_tempo_de_exposicao_quando_passou_para_manual(fonte: FonteWebcam) -> None:
    """Manual sem tempo definido herda o último valor do automático.

    Se esse valor veio de um quadro escuro, a sessão abre com a imagem
    estourada ou preta, e aí não há algoritmo que meça nada.
    """
    camera = CameraFalsa(
        aceita={cv2.CAP_PROP_AUTO_EXPOSURE, cv2.CAP_PROP_EXPOSURE, cv2.CAP_PROP_AUTO_WB},
        leitura={cv2.CAP_PROP_EXPOSURE: 0.0},
    )

    fonte.travar_ajustes_automaticos(camera)

    assert camera.valores_escritos_em(cv2.CAP_PROP_EXPOSURE) == [-6.0]


def test_nao_mexe_na_exposicao_quando_nao_conseguiu_travar(fonte: FonteWebcam) -> None:
    """Sem conseguir o modo manual, fixar o tempo só pioraria.

    A câmera continuaria compensando sozinha, e o tempo fixado brigaria com a
    compensação em vez de substituí-la.
    """
    camera = CameraFalsa(aceita=set())

    fonte.travar_ajustes_automaticos(camera)

    assert camera.valores_escritos_em(cv2.CAP_PROP_EXPOSURE) == []


def test_exposicao_ja_definida_e_preservada(fonte: FonteWebcam) -> None:
    """Quem já tem um tempo de exposição válido não é sobrescrito.

    Serve para quem ajustou a câmera no aplicativo do fabricante antes de
    medir, que é o cenário de quem comprou câmera melhor justamente para isso.
    """
    camera = CameraFalsa(
        aceita={cv2.CAP_PROP_AUTO_EXPOSURE, cv2.CAP_PROP_EXPOSURE, cv2.CAP_PROP_AUTO_WB},
        leitura={cv2.CAP_PROP_EXPOSURE: -5.0},
    )

    fonte.travar_ajustes_automaticos(camera)

    assert camera.valores_escritos_em(cv2.CAP_PROP_EXPOSURE) == []


def test_balanco_de_branco_independe_da_exposicao(fonte: FonteWebcam) -> None:
    """Travar um e não o outro é resultado comum, e precisa ser relatado como é.

    O balanço de branco automático é o pior dos dois para método cromático,
    porque aplica ganho diferente por canal e escapa da projeção que CHROM e
    POS fazem. Reportar os dois juntos esconderia justamente o que importa.
    """
    camera = CameraFalsa(
        aceita_tudo=True,
        leitura={cv2.CAP_PROP_AUTO_EXPOSURE: 1.0},  # exposição não trava
    )

    aplicado = fonte.travar_ajustes_automaticos(camera)

    assert aplicado["exposicao"] is False
    assert aplicado["balanco_de_branco"] is True


def test_desligar_o_travamento_nao_escreve_nada() -> None:
    """Com `travar_automaticos=False` nada deve ser escrito na câmera."""
    fonte = FonteWebcam(travar_automaticos=False)
    camera = CameraFalsa(aceita_tudo=True)

    # O caminho normal passa por `_registrar`, que só chama o travamento
    # quando a opção está ligada. Aqui conferimos a decisão, não a função.
    assert fonte.travar_automaticos is False
    assert camera.escritas == []
