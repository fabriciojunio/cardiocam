"""Seleção visual da área de um participante, sem salvar a imagem."""

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QImage, QPainter, QPen, QColor, QPixmap
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QVBoxLayout


class ImagemSelecionavel(QLabel):
    def __init__(self, quadro, parent=None):
        super().__init__(parent)
        altura, largura = quadro.shape[:2]
        imagem = QImage(quadro.data, largura, altura, quadro.strides[0], QImage.Format_BGR888).copy()
        pixmap = QPixmap.fromImage(imagem).scaled(900, 600, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.setPixmap(pixmap)
        self.setFixedSize(pixmap.size())
        self.setCursor(Qt.CrossCursor)
        self._inicio = None
        self._retangulo = QRect()

    @property
    def area_relativa(self):
        r = self._retangulo.normalized().intersected(self.rect())
        if r.width() < 20 or r.height() < 20:
            return None
        return (r.x() / self.width(), r.y() / self.height(),
                (r.x() + r.width()) / self.width(), (r.y() + r.height()) / self.height())

    def mousePressEvent(self, evento):
        if evento.button() == Qt.LeftButton:
            self._inicio = evento.position().toPoint()
            self._retangulo = QRect(self._inicio, self._inicio)
            self.update()

    def mouseMoveEvent(self, evento):
        if self._inicio is not None:
            self._retangulo = QRect(self._inicio, evento.position().toPoint())
            self.update()

    def mouseReleaseEvent(self, evento):
        if self._inicio is not None:
            self._retangulo = QRect(self._inicio, evento.position().toPoint())
            self._inicio = None
            self.update()

    def paintEvent(self, evento):
        super().paintEvent(evento)
        pintor = QPainter(self)
        pintor.setPen(QPen(QColor(78, 168, 122), 2))
        pintor.drawRect(self._retangulo.normalized().intersected(self.rect()))
        pintor.end()


class SelecionadorRegiao(QDialog):
    def __init__(self, quadro, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Selecionar participante")
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Arraste para selecionar a área do participante que deseja medir."))
        self.imagem = ImagemSelecionavel(quadro, self)
        layout.addWidget(self.imagem)
        botoes = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        botoes.accepted.connect(self._confirmar)
        botoes.rejected.connect(self.reject)
        layout.addWidget(botoes)

    def _confirmar(self):
        if self.imagem.area_relativa is not None:
            self.accept()
