"""A janela do aplicativo: um quadrado, com um botão de ligar e desligar.

A tela tem uma coisa só a fazer, e por isso tem um controle só. Algoritmo,
comprimento de janela e limiar de recusa ficam de fora de propósito: são decisões
que o projeto já tomou com medição, e devolvê-las ao usuário seria transferir
para ele uma escolha que ele não tem como avaliar olhando. Quem quiser mexer tem
a linha de comando.

A origem é a única pergunta que sobra, porque o programa não tem como adivinhar
se a pessoa quer medir a própria câmera ou o rosto de alguém numa reunião. Ela
fica numa linha discreta no rodapé do quadrado, que abre um menu: presente para
quem precisa, fora do caminho de quem não precisa.

Fechar a janela não encerra o programa. Ele desce para a bandeja e continua
medindo, que é o uso para o qual existe: encerrar ao fechar a janela seria
encerrar justamente quando a pessoa tira a janela da frente para ver a reunião.
"""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import (
    QAction,
    QColor,
    QFont,
    QIcon,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import (
    QApplication,
    QLabel,
    QMenu,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

from cardiocam.desktop.janelas import listar_janelas, provavel_reuniao
from cardiocam.desktop.medicao import LacoDeMedicao, Origem
from cardiocam.desktop.sobreposicao import LeituraNaTela, Sobreposicao

LADO = 240

VERDE = QColor(78, 168, 122)
VERMELHO = QColor(200, 112, 106)
FUNDO = QColor(16, 20, 18)
TEXTO = QColor(226, 232, 228)
FRACO = QColor(139, 147, 143)
LINHA = QColor(44, 52, 48)

FOLHA = """
QWidget#raiz { background: #101412; }
QLabel#marca {
  color: #8b938f; font-size: 10px; font-weight: 600; letter-spacing: 2px;
}
QLabel#estado { color: #8b938f; font-size: 11px; }
QLabel#origem { color: #6f7a75; font-size: 10px; }
QLabel#origem:hover { color: #e2e8e4; }
QMenu {
  background: #171c1a; color: #e2e8e4; border: 1px solid #2c3430; padding: 4px;
}
QMenu::item { padding: 6px 14px; border-radius: 4px; }
QMenu::item:selected { background: #1c2b23; }
"""


def icone_do_programa(lado: int = 64) -> QIcon:
    """Desenha o ícone em vez de carregar um arquivo.

    Evita que o empacotamento tenha de embutir e localizar um recurso, que é
    exatamente o tipo de coisa que funciona em desenvolvimento e falha no
    executável. O traçado é uma linha de pulso, a mesma marca do projeto.
    """
    mapa = QPixmap(lado, lado)
    mapa.fill(Qt.transparent)
    pintor = QPainter(mapa)
    pintor.setRenderHint(QPainter.Antialiasing, True)
    pintor.setBrush(FUNDO)
    pintor.setPen(Qt.NoPen)
    pintor.drawRoundedRect(2, 2, lado - 4, lado - 4, lado * 0.22, lado * 0.22)

    caminho = QPainterPath()
    pontos = [(0.14, 0.52), (0.34, 0.52), (0.42, 0.30), (0.54, 0.72), (0.63, 0.52), (0.86, 0.52)]
    caminho.moveTo(pontos[0][0] * lado, pontos[0][1] * lado)
    for x, y in pontos[1:]:
        caminho.lineTo(x * lado, y * lado)
    pintor.setPen(
        QPen(VERDE, max(2.0, lado * 0.055), Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
    )
    pintor.drawPath(caminho)
    pintor.end()
    return QIcon(mapa)


class BotaoDeEnergia(QWidget):
    """O interruptor: um círculo com o símbolo de energia.

    Desenhado à mão em vez de montado com folha de estilo porque o que se quer é
    um alvo redondo de verdade, que responde ao passar do mouse e muda de cor
    conforme o estado. Botão retangular com cantos arredondados nunca fica
    redondo o bastante para parecer um interruptor.
    """

    clicado = Signal()

    DIAMETRO = 96

    def __init__(self) -> None:
        super().__init__()
        self.setFixedSize(self.DIAMETRO, self.DIAMETRO)
        self.setCursor(Qt.PointingHandCursor)
        self.setAttribute(Qt.WA_Hover, True)
        self._ligado = False
        self._sob_o_mouse = False

    def definir_ligado(self, ligado: bool) -> None:
        self._ligado = ligado
        self.update()

    def enterEvent(self, evento) -> None:  # noqa: N802
        self._sob_o_mouse = True
        self.update()

    def leaveEvent(self, evento) -> None:  # noqa: N802
        self._sob_o_mouse = False
        self.update()

    def mousePressEvent(self, evento) -> None:  # noqa: N802
        if evento.button() == Qt.LeftButton:
            self.clicado.emit()

    def paintEvent(self, _evento) -> None:  # noqa: N802
        cor = VERMELHO if self._ligado else VERDE
        pintor = QPainter(self)
        pintor.setRenderHint(QPainter.Antialiasing, True)

        anel = QRectF(4, 4, self.DIAMETRO - 8, self.DIAMETRO - 8)
        preenchimento = QColor(cor)
        preenchimento.setAlpha(46 if self._sob_o_mouse else 26)
        pintor.setBrush(preenchimento)
        pintor.setPen(QPen(cor, 2))
        pintor.drawEllipse(anel)

        # O símbolo universal de energia: um arco aberto no topo e um traço
        # vertical saindo pela abertura.
        centro = QPointF(self.DIAMETRO / 2, self.DIAMETRO / 2 + 2)
        raio = self.DIAMETRO * 0.21
        arco = QRectF(centro.x() - raio, centro.y() - raio, raio * 2, raio * 2)
        caneta = QPen(cor, 3.2, Qt.SolidLine, Qt.RoundCap)
        pintor.setPen(caneta)
        pintor.setBrush(Qt.NoBrush)
        # Começa em 115 graus e varre 310, deixando a abertura para cima.
        pintor.drawArc(arco, int(115 * 16), int(310 * 16))
        pintor.drawLine(
            QPointF(centro.x(), centro.y() - raio - 6),
            QPointF(centro.x(), centro.y() - 1),
        )
        pintor.end()


class JanelaPrincipal(QWidget):
    """O quadrado. Liga, desliga, e diz o que está acontecendo."""

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("raiz")
        self.setWindowTitle("Cardiocam")
        self.setWindowIcon(icone_do_programa())
        self.setFixedSize(LADO, LADO)
        self.setStyleSheet(FOLHA)

        self._laco: LacoDeMedicao | None = None
        self._sobreposicao = Sobreposicao()
        # A reunião aberta é o padrão, e não a câmera. Durante a reunião o
        # programa dela já está com a câmera, e pedir o mesmo dispositivo
        # disputa com ele; a imagem que interessa já está na tela.
        reuniao = provavel_reuniao()
        self._origem = Origem(janela=reuniao) if reuniao else Origem(camera=0)
        self._ja_avisou_da_bandeja = False

        self._montar()
        self._montar_bandeja()

    # ------------------------------------------------------------- montagem
    def _montar(self) -> None:
        marca = QLabel("CARDIOCAM")
        marca.setObjectName("marca")
        marca.setAlignment(Qt.AlignCenter)

        self._botao = BotaoDeEnergia()
        self._botao.clicado.connect(self.alternar)

        self._estado = QLabel("Desligado")
        self._estado.setObjectName("estado")
        self._estado.setAlignment(Qt.AlignCenter)

        self._origem_rotulo = QLabel()
        self._origem_rotulo.setObjectName("origem")
        self._origem_rotulo.setAlignment(Qt.AlignCenter)
        self._origem_rotulo.setCursor(Qt.PointingHandCursor)
        self._origem_rotulo.mousePressEvent = lambda _evento: self._escolher_origem()
        self._pintar_origem()

        corpo = QVBoxLayout(self)
        corpo.setContentsMargins(16, 18, 16, 14)
        corpo.setSpacing(0)
        corpo.addWidget(marca)
        corpo.addStretch(1)
        corpo.addWidget(self._botao, 0, Qt.AlignCenter)
        corpo.addSpacing(14)
        corpo.addWidget(self._estado)
        corpo.addStretch(1)
        corpo.addWidget(self._origem_rotulo)

    def _montar_bandeja(self) -> None:
        self._bandeja = QSystemTrayIcon(icone_do_programa(), self)
        self._bandeja.setToolTip("Cardiocam")
        menu = QMenu()
        self._acao_alternar = QAction("Ligar", self)
        self._acao_alternar.triggered.connect(self.alternar)
        abrir = QAction("Abrir", self)
        abrir.triggered.connect(self._mostrar)
        sair = QAction("Sair", self)
        sair.triggered.connect(self._sair)
        menu.addAction(self._acao_alternar)
        menu.addAction(abrir)
        menu.addSeparator()
        menu.addAction(sair)
        self._bandeja.setContextMenu(menu)
        self._bandeja.activated.connect(
            lambda motivo: self._mostrar() if motivo == QSystemTrayIcon.Trigger else None
        )
        self._bandeja.show()

    # -------------------------------------------------------------- origem
    def _pintar_origem(self) -> None:
        nome = self._origem.descricao
        if len(nome) > 30:
            nome = nome[:29] + "…"
        self._origem_rotulo.setText(f"{nome}  ▾")

    def _escolher_origem(self) -> None:
        """Abre o menu de origens, relendo as janelas abertas na hora.

        Relê sempre, e não na inicialização: a reunião costuma ser aberta
        **depois** do programa, e uma lista montada uma vez só nunca teria a
        janela que interessa.
        """
        if self.esta_ligado:
            return
        menu = QMenu(self)
        camera = QAction("Câmera do computador", self)
        camera.triggered.connect(lambda: self._definir_origem(Origem(camera=0)))
        menu.addAction(camera)

        janelas = listar_janelas()
        if janelas:
            menu.addSeparator()
            for janela in janelas:
                acao = QAction(str(janela), self)
                acao.triggered.connect(
                    lambda _marcado=False, j=janela: self._definir_origem(Origem(janela=j))
                )
                menu.addAction(acao)
        menu.exec(self._origem_rotulo.mapToGlobal(self._origem_rotulo.rect().bottomLeft()))

    def _definir_origem(self, origem: Origem) -> None:
        self._origem = origem
        self._pintar_origem()

    # --------------------------------------------------------------- ligar
    @property
    def esta_ligado(self) -> bool:
        return self._laco is not None and self._laco.isRunning()

    def alternar(self) -> None:
        self.desligar() if self.esta_ligado else self.ligar()

    def ligar(self) -> None:
        self._laco = LacoDeMedicao(self._origem)
        self._laco.leitura_pronta.connect(self._receber)
        self._laco.falhou.connect(self._tratar_falha)
        self._laco.finished.connect(self._ao_terminar)
        self._laco.start()

        self._sobreposicao.atualizar_leitura(
            LeituraNaTela(mensagem="Abrindo a câmera…")
        )
        self._sobreposicao.show()
        self._sobreposicao.posicionar()
        self._pintar_estado(ligado=True)
        # Abrir a câmera leva segundos, e é tempo em que nada acontece na tela.
        # Medido nesta máquina: 7,7 s no Media Foundation, que é o custo da
        # enumeração do próprio backend. Sem dizer isso, o botão parece não ter
        # funcionado e a pessoa clica de novo.
        self._dizer("Abrindo…")

    def desligar(self) -> None:
        if self._laco is not None:
            self._laco.parar()
            self._laco.wait(2500)
            self._laco = None
        self._sobreposicao.hide()
        self._pintar_estado(ligado=False)
        self._dizer("Desligado")

    def _ao_terminar(self) -> None:
        self._sobreposicao.hide()
        self._pintar_estado(ligado=False)

    def _pintar_estado(self, ligado: bool) -> None:
        self._botao.definir_ligado(ligado)
        self._acao_alternar.setText("Desligar" if ligado else "Ligar")
        self._origem_rotulo.setEnabled(not ligado)

    # -------------------------------------------------------------- leitura
    def _receber(self, leitura: LeituraNaTela) -> None:
        self._sobreposicao.atualizar_leitura(leitura)
        if leitura.bpm is not None and leitura.confianca in ("alta", "média"):
            texto = f"{leitura.bpm:.0f} bpm"
            self._bandeja.setToolTip(
                f"Cardiocam: {texto}, confiança {leitura.confianca}"
            )
        else:
            texto = "Medindo"
            self._bandeja.setToolTip("Cardiocam: medindo")
        self._dizer(texto)

    def _tratar_falha(self, mensagem: str) -> None:
        self.desligar()
        self._dizer("Parou")
        self._bandeja.showMessage("Cardiocam", mensagem, icone_do_programa(), 6000)

    def _dizer(self, texto: str) -> None:
        self._estado.setText(texto)

    # ------------------------------------------------------------- bandeja
    def _mostrar(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def _sair(self) -> None:
        self.desligar()
        self._sobreposicao.close()
        self._bandeja.hide()
        QApplication.instance().quit()

    def closeEvent(self, evento) -> None:  # noqa: N802
        evento.ignore()
        self.hide()
        if not self._ja_avisou_da_bandeja:
            self._ja_avisou_da_bandeja = True
            self._bandeja.showMessage(
                "Cardiocam",
                "Continua aqui na bandeja. Para encerrar, use Sair neste ícone.",
                icone_do_programa(),
                5000,
            )
