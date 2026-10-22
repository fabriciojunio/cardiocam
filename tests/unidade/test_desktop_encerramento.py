"""O cancelamento preserva a thread até o encerramento real."""

import time
from threading import Event

import pytest
from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import QApplication

from cardiocam.desktop.aplicativo import JanelaPrincipal
from cardiocam.desktop.medicao import LacoDeMedicao, Origem
from cardiocam.desktop.sobreposicao import LeituraNaTela


@pytest.fixture
def app():
    return QApplication.instance() or QApplication([])


def test_cancelamento_antes_de_iniciar_nao_abre_camera(monkeypatch):
    laco = LacoDeMedicao(Origem(camera=0))
    monkeypatch.setattr(laco, "_medir_camera", lambda: pytest.fail("Captura cancelada foi aberta."))
    laco.parar()
    laco.run()
    assert not laco._rodando


def test_desligar_nao_descarta_thread_bloqueada(app, monkeypatch):
    liberar = Event()
    iniciou = Event()

    class CapturaLenta(QThread):
        leitura_pronta = Signal(object)
        falhou = Signal(str)

        def __init__(self, origem):
            super().__init__()
            self.cancelado = False

        def run(self):
            iniciou.set()
            liberar.wait(3)

        def parar(self):
            self.cancelado = True

    monkeypatch.setattr("cardiocam.desktop.aplicativo.LacoDeMedicao", CapturaLenta)
    janela = JanelaPrincipal()
    try:
        janela.ligar()
        laco = janela._laco
        assert iniciou.wait(1)
        janela.desligar()
        assert janela._laco is laco
        assert laco.isRunning()
        assert laco.cancelado
        assert not janela._botao.isEnabled()
        janela.ligar()
        assert janela._laco is laco
        janela._receber(LeituraNaTela(bpm=72, confianca="alta"))
        assert janela._estado.text() == "Encerrando captura…"
        liberar.set()
        assert laco.wait(1000)
        prazo = time.monotonic() + 1
        while janela._laco is not None and time.monotonic() < prazo:
            app.processEvents()
        assert janela._laco is None
        assert janela._botao.isEnabled()
    finally:
        liberar.set()
        if janela._laco is not None:
            janela._laco.wait(1000)
        janela._bandeja.hide()
        janela._sobreposicao.close()
        janela.deleteLater()


def test_camera_que_para_avisa_e_libera_recurso(monkeypatch):
    from cardiocam.dominio.resultado import Ok

    class Fonte:
        fps = 20
        fechou = False

        def quadros(self):
            return iter(())

        def fechar(self):
            self.fechou = True

    fonte = Fonte()
    monkeypatch.setattr("cardiocam.fontes.webcam.abrir_webcam", lambda **kwargs: Ok(fonte))
    laco = LacoDeMedicao(Origem(camera=0))
    laco._rodando = True
    mensagens = []
    laco.falhou.connect(mensagens.append)
    laco._medir_camera()
    assert fonte.fechou
    assert len(mensagens) == 1
    assert "parou" in mensagens[0]
