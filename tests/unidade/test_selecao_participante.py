"""A seleção recorta somente a área escolhida e preserva os canais."""

import numpy as np
import pytest
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication

from cardiocam.desktop.medicao import Origem
from cardiocam.desktop.selecao import ImagemSelecionavel


def test_recorte_preserva_os_pixels_e_acompanha_resolucao():
    origem = Origem(area_relativa=(.25, .5, .75, 1))
    quadro = np.arange(200 * 100 * 3, dtype=np.uint8).reshape(100, 200, 3)
    assert np.array_equal(origem.recortar(quadro), quadro[50:100, 50:150])
    assert origem.recortar(np.zeros((200, 400, 3), np.uint8)).shape == (100, 200, 3)


@pytest.mark.parametrize("area", [(-.1, 0, 1, 1), (0, 0, 1.1, 1), (.5, 0, .4, 1), (0, 0, 1, float("nan"))])
def test_area_invalida_e_recusada(area):
    with pytest.raises(ValueError):
        Origem(area_relativa=area)


def test_arraste_na_imagem_define_area_valida():
    app = QApplication.instance() or QApplication([])
    imagem = ImagemSelecionavel(np.full((300, 400, 3), 100, np.uint8))
    inicio = QPointF(imagem.width() * .25, imagem.height() * .25)
    fim = QPointF(imagem.width() * .75, imagem.height() * .75)
    press = QMouseEvent(QMouseEvent.MouseButtonPress, inicio, inicio, Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
    release = QMouseEvent(QMouseEvent.MouseButtonRelease, fim, fim, Qt.LeftButton, Qt.NoButton, Qt.NoModifier)
    app.sendEvent(imagem, press)
    app.sendEvent(imagem, release)
    assert imagem.area_relativa == pytest.approx((.25, .25, .75, .75), abs=.005)
    assert not imagem.grab().isNull()
