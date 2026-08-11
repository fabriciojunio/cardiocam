"""Localização dos olhos, usada para ancorar as regiões de medição.

Definir a testa como uma fração fixa da caixa do rosto parece razoável e não é.
A caixa que a cascata devolve depende de quanto cabelo a pessoa tem e de onde
começa a implantação: em quem tem cabelo volumoso e testa curta, a faixa que
deveria ser testa cai em cima das sobrancelhas e dos olhos.

Isso não é um detalhe estético. Piscar produz uma variação de intensidade muito
maior que a do pulso, e numa frequência que cai dentro da banda cardíaca. Medir
a região dos olhos é a maneira mais eficiente de estragar a medição.

Os olhos são uma referência anatômica confiável: a distância entre eles dá a
escala do rosto, e todas as outras regiões podem ser posicionadas em relação a
ela.
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from cardiocam.visao.geometria import Retangulo

CASCATA_OLHOS = "haarcascade_eye.xml"


@dataclass(frozen=True, slots=True)
class Olhos:
    """Posição dos dois olhos e a escala que eles definem."""

    esquerdo: tuple[float, float]
    direito: tuple[float, float]

    @property
    def separacao(self) -> float:
        """Distância entre os centros dos olhos, que é a escala do rosto."""
        return float(
            np.hypot(
                self.direito[0] - self.esquerdo[0], self.direito[1] - self.esquerdo[1]
            )
        )

    @property
    def linha(self) -> float:
        """Altura média dos olhos."""
        return (self.esquerdo[1] + self.direito[1]) / 2.0

    @property
    def centro_x(self) -> float:
        return (self.esquerdo[0] + self.direito[0]) / 2.0


class DetectorOlhos:
    """Encontra os dois olhos dentro da caixa do rosto."""

    def __init__(self, escala: float = 1.08, vizinhos_minimos: int = 6) -> None:
        caminho = cv2.data.haarcascades + CASCATA_OLHOS
        self._classificador = cv2.CascadeClassifier(caminho)
        if self._classificador.empty():
            raise RuntimeError(f"Não foi possível carregar a cascata em {caminho}.")
        self.escala = escala
        self.vizinhos_minimos = vizinhos_minimos

    def detectar(self, quadro: np.ndarray, caixa_rosto: Retangulo) -> Olhos | None:
        """Devolve os dois olhos, ou None quando não houver detecção confiável."""
        if quadro is None or quadro.size == 0:
            return None

        altura, largura = quadro.shape[:2]
        # Procurar só na metade superior do rosto evita confundir narina e boca
        # com olho, que é um erro comum desta cascata.
        busca = caixa_rosto.fracao(0.0, 0.05, 1.0, 0.62).limitar(largura, altura)
        recorte = busca.recortar(quadro)
        if recorte.size == 0:
            return None

        cinza = cv2.cvtColor(recorte, cv2.COLOR_BGR2GRAY) if recorte.ndim == 3 else recorte
        cinza = cv2.equalizeHist(cinza)

        lado_minimo = max(8, int(caixa_rosto.largura * 0.10))
        deteccoes = self._classificador.detectMultiScale(
            cinza,
            scaleFactor=self.escala,
            minNeighbors=self.vizinhos_minimos,
            minSize=(lado_minimo, lado_minimo),
        )
        if len(deteccoes) < 2:
            return None

        centros = [
            (busca.x + x + w / 2.0, busca.y + y + h / 2.0, w * h)
            for x, y, w, h in deteccoes
        ]
        # Fica com os dois maiores, que são os olhos de verdade; o resto costuma
        # ser sobrancelha ou sombra.
        centros.sort(key=lambda c: c[2], reverse=True)
        candidatos = centros[:2]
        candidatos.sort(key=lambda c: c[0])
        esquerdo, direito = candidatos[0][:2], candidatos[1][:2]

        olhos = Olhos(esquerdo, direito)

        # Verificações de sanidade. Dois olhos ficam lado a lado, separados por
        # algo em torno de um terço a metade da largura do rosto, e quase na
        # mesma altura.
        separacao = olhos.separacao
        if not (0.22 * caixa_rosto.largura <= separacao <= 0.75 * caixa_rosto.largura):
            return None
        desnivel = abs(esquerdo[1] - direito[1])
        if desnivel > 0.35 * separacao:
            return None

        return olhos


def regioes_ancoradas(olhos: Olhos, largura: int, altura: int) -> list[Retangulo]:
    """Testa e bochechas posicionadas a partir dos olhos.

    As proporções vêm da anatomia do rosto, tomando a distância entre os olhos
    como unidade. A sobrancelha fica cerca de 0,3 dessa unidade acima do centro
    do olho e a implantação do cabelo por volta de 1,3, então a faixa entre 0,5
    e 1,1 acima é testa em praticamente qualquer pessoa, com folga dos dois
    lados.

    As bochechas ficam abaixo dos olhos, na vertical de cada um, evitando o
    nariz no meio e a boca embaixo.
    """
    separacao = olhos.separacao
    linha = olhos.linha
    centro = olhos.centro_x

    def retangulo(x0: float, y0: float, x1: float, y1: float) -> Retangulo:
        return Retangulo(
            int(round(x0)), int(round(y0)), int(round(x1 - x0)), int(round(y1 - y0))
        ).limitar(largura, altura)

    # O limite superior é 1,0 e não mais alto de propósito: a implantação do
    # cabelo varia muito entre pessoas, e subir demais coloca cabelo dentro da
    # região. A máscara de pele ainda descarta o que entrar, mas região
    # aproveitada de verdade vale mais que região grande no papel.
    testa = retangulo(
        centro - 0.55 * separacao,
        linha - 1.00 * separacao,
        centro + 0.55 * separacao,
        linha - 0.50 * separacao,
    )
    bochecha_esquerda = retangulo(
        olhos.esquerdo[0] - 0.30 * separacao,
        linha + 0.38 * separacao,
        olhos.esquerdo[0] + 0.22 * separacao,
        linha + 0.95 * separacao,
    )
    bochecha_direita = retangulo(
        olhos.direito[0] - 0.22 * separacao,
        linha + 0.38 * separacao,
        olhos.direito[0] + 0.30 * separacao,
        linha + 0.95 * separacao,
    )

    return [r for r in (testa, bochecha_esquerda, bochecha_direita) if not r.vazio]
