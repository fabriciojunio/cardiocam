"""A sobreposição que fica num canto da tela, por cima de tudo.

É o mesmo tipo de janela que o painel da NVIDIA usa: sem borda, sempre no topo,
fundo transparente e **transparente ao clique**. Essa última é a que importa e a
que costuma ser esquecida: sem ela a sobreposição rouba o clique de quem está na
reunião, e aí o programa que deveria ser discreto vira o que atrapalha.

O que ela mostra foi escolhido pelo que muda a decisão de quem olha, e nada mais.
O número grande, porque é o que se procura. O selo de confiança, porque um número
sem ele é uma afirmação sem lastro, e este projeto recusa afirmar o que não
sustenta. A relação sinal-ruído, porque é ela que explica o selo. E a barra de
progresso enquanto a janela de coleta não encheu, porque sem ela a espera de
vinte e cinco segundos parece travamento.

A onda de pulso entra por um motivo prático: é o que distingue, de relance, sinal
de ruído. Onda com ritmo visível e espectro com pico único é medida; onda que
parece grama é ruído, mesmo quando o número parece plausível.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget

# A mesma paleta da versão web, para as duas interfaces falarem a mesma língua.
COR_FUNDO = QColor(16, 20, 18, 214)
COR_BORDA = QColor(60, 70, 64, 200)
COR_TEXTO = QColor(226, 232, 228)
COR_FRACA = QColor(139, 147, 143)
COR_ONDA = QColor(78, 168, 122)

CORES_DE_CONFIANCA = {
    "alta": QColor(78, 168, 122),
    "média": QColor(91, 135, 168),
    "baixa": QColor(200, 153, 74),
    "descartada": QColor(184, 84, 76),
    "aguardando": QColor(139, 147, 143),
}

LARGURA = 228
ALTURA = 132
MARGEM_DA_TELA = 18


@dataclass
class LeituraNaTela:
    """O que a sobreposição precisa saber para desenhar um quadro."""

    bpm: float | None = None
    confianca: str = "aguardando"
    snr_db: float | None = None
    progresso: float = 0.0
    mensagem: str = ""
    pulso: list[float] = field(default_factory=list)
    qualidade: float | None = None
    instante_analise: float | None = None
    idade_analise_s: float | None = None
    """Probabilidade que o modelo de abstenção deu a esta janela.

    Separada da confiança de propósito: a confiança vem da relação sinal-ruído,
    que é a primeira peneira, e esta vem do modelo treinado, que pega o caso que
    a primeira deixa passar. Mostrar as duas permite ver qual delas reprovou.
    """


class Sobreposicao(QWidget):
    """Painel translúcido, sempre no topo e transparente ao clique."""

    def __init__(self) -> None:
        super().__init__(None)
        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            # `Tool` mantém a sobreposição fora da barra de tarefas e do
            # alternador de janelas. Sem isso ela aparece no Alt+Tab, o que é
            # ruído para uma coisa que nunca recebe foco.
            | Qt.Tool
            | Qt.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        # A transparência ao clique. Sem ela o retângulo da sobreposição engole
        # cliques da reunião que está embaixo.
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setWindowFlag(Qt.WindowTransparentForInput, True)
        self.resize(LARGURA, ALTURA)
        self._leitura = LeituraNaTela()

    def posicionar(self, canto: str = "superior-direito") -> None:
        """Encosta a sobreposição num canto da tela principal."""
        tela = self.screen() or self.windowHandle().screen()
        area = tela.availableGeometry()
        x = area.right() - LARGURA - MARGEM_DA_TELA
        y = area.top() + MARGEM_DA_TELA
        if canto.endswith("esquerdo"):
            x = area.left() + MARGEM_DA_TELA
        if canto.startswith("inferior"):
            y = area.bottom() - ALTURA - MARGEM_DA_TELA
        self.move(x, y)

    def atualizar_leitura(self, leitura: LeituraNaTela) -> None:
        self._leitura = leitura
        self.update()

    # ------------------------------------------------------------- desenho
    def paintEvent(self, _evento) -> None:  # noqa: N802  (nome da API do Qt)
        pintor = QPainter(self)
        pintor.setRenderHint(QPainter.Antialiasing, True)
        self._desenhar_painel(pintor)
        self._desenhar_numero(pintor)
        self._desenhar_dados(pintor)
        if self._leitura.progresso < 1.0:
            self._desenhar_progresso(pintor)
        else:
            self._desenhar_onda(pintor)
        pintor.end()

    def _desenhar_painel(self, pintor: QPainter) -> None:
        caixa = QRectF(0.5, 0.5, LARGURA - 1, ALTURA - 1)
        pintor.setPen(QPen(COR_BORDA, 1))
        pintor.setBrush(COR_FUNDO)
        pintor.drawRoundedRect(caixa, 10, 10)

    def _desenhar_numero(self, pintor: QPainter) -> None:
        leitura = self._leitura
        confiavel = leitura.confianca in ("alta", "média")
        texto = f"{leitura.bpm:.0f}" if leitura.bpm is not None else "--"

        fonte = QFont("Consolas", 34, QFont.DemiBold)
        pintor.setFont(fonte)
        # A largura real do número, e não uma estimativa por caractere. Com
        # estimativa, "74" e "bpm" encostavam e "138" empurrava o rótulo para
        # fora do painel: a fonte não é tão monoespaçada quanto o nome promete
        # para dígitos em negrito.
        largura_do_numero = 14 + pintor.fontMetrics().horizontalAdvance(texto) + 5
        # Número duvidoso sai esmaecido. É a mesma decisão da versão web: a
        # aparência do número precisa carregar a confiança, senão quem olha de
        # relance leva só o algarismo.
        pintor.setPen(COR_TEXTO if confiavel else COR_FRACA)
        pintor.drawText(QRectF(14, 8, 130, 48), Qt.AlignLeft | Qt.AlignVCenter, texto)

        pintor.setFont(QFont("Segoe UI", 9))
        pintor.setPen(COR_FRACA)
        pintor.drawText(
            QRectF(largura_do_numero, 26, 40, 20), Qt.AlignLeft | Qt.AlignVCenter, "bpm"
        )

        cor = CORES_DE_CONFIANCA.get(leitura.confianca, COR_FRACA)
        pintor.setFont(QFont("Consolas", 8, QFont.DemiBold))
        pintor.setPen(cor)
        pintor.drawText(
            QRectF(LARGURA - 96, 12, 82, 18),
            Qt.AlignRight | Qt.AlignVCenter,
            leitura.confianca.upper(),
        )

    def _desenhar_dados(self, pintor: QPainter) -> None:
        pintor.setFont(QFont("Consolas", 8))
        pintor.setPen(COR_FRACA)
        snr = self._leitura.snr_db
        texto = f"SNR {snr:+.1f} dB" if snr is not None else "SNR --"
        if self._leitura.qualidade is not None:
            texto += f"  q {self._leitura.qualidade:.2f}"
        pintor.drawText(QRectF(LARGURA - 130, 32, 116, 16), Qt.AlignRight, texto)

        if self._leitura.mensagem:
            pintor.setFont(QFont("Segoe UI", 7))
            pintor.drawText(
                QRectF(14, ALTURA - 20, LARGURA - 28, 16),
                Qt.AlignLeft | Qt.AlignVCenter,
                self._leitura.mensagem[:58],
            )

    def _desenhar_progresso(self, pintor: QPainter) -> None:
        trilho = QRectF(14, 62, LARGURA - 28, 4)
        pintor.setPen(Qt.NoPen)
        pintor.setBrush(QColor(44, 52, 48))
        pintor.drawRoundedRect(trilho, 2, 2)
        cheio = QRectF(trilho)
        cheio.setWidth(trilho.width() * max(0.0, min(1.0, self._leitura.progresso)))
        pintor.setBrush(COR_ONDA)
        pintor.drawRoundedRect(cheio, 2, 2)

    def _desenhar_onda(self, pintor: QPainter) -> None:
        sinal = self._leitura.pulso
        area = QRectF(14, 56, LARGURA - 28, 46)
        if len(sinal) < 2:
            return
        # Só o trecho recente, que é o que a pessoa reconhece como "agora".
        trecho = sinal[-220:]
        minimo, maximo = min(trecho), max(trecho)
        amplitude = (maximo - minimo) or 1.0

        caminho = QPainterPath()
        passo = area.width() / (len(trecho) - 1)
        for indice, valor in enumerate(trecho):
            x = area.left() + indice * passo
            y = area.bottom() - ((valor - minimo) / amplitude) * area.height()
            ponto = QPointF(x, y)
            if indice == 0:
                caminho.moveTo(ponto)
            else:
                caminho.lineTo(ponto)
        pintor.setBrush(Qt.NoBrush)
        pintor.setPen(QPen(COR_ONDA, 1.3))
        pintor.drawPath(caminho)
