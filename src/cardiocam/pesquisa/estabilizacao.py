"""Estabilização por fluxo óptico com checagem de ida e volta."""

from dataclasses import dataclass

import cv2
import numpy as np

from cardiocam.visao.geometria import Retangulo
from cardiocam.visao.olhos import Olhos


@dataclass(frozen=True)
class QuadroEstabilizado:
    imagem: np.ndarray
    valido: bool
    reiniciado: bool
    pontos: int
    movimento_px: tuple[float, float]
    motivo: str


def pose_aproveitavel(olhos: Olhos, rosto: Retangulo, angulo_maximo: float = 25) -> bool:
    """Critério geométrico de inclinação; não estima pose 3D nem identidade."""
    dx = olhos.direito[0]-olhos.esquerdo[0]
    dy = olhos.direito[1]-olhos.esquerdo[1]
    return (dx > 0 and .2*rosto.largura <= olhos.separacao <= .8*rosto.largura
            and abs(np.degrees(np.arctan2(dy, dx))) <= angulo_maximo)


def alinhar_pelos_olhos(imagem: np.ndarray, atuais: Olhos, referencia: Olhos) -> np.ndarray:
    """Similaridade definida por dois centros detectados; preserva os canais."""
    origem = np.array(atuais.esquerdo, float)
    destino = np.array(referencia.esquerdo, float)
    a = np.array(atuais.direito, float)-origem
    b = np.array(referencia.direito, float)-destino
    if not np.isfinite([*a, *b]).all() or np.linalg.norm(a) < 10 or np.linalg.norm(b) < 10:
        raise ValueError("Centros dos olhos inválidos para alinhamento.")
    real, imaginario = np.dot(a, b)/np.dot(a, a), (a[0]*b[1]-a[1]*b[0])/np.dot(a, a)
    linear = np.array([[real, -imaginario], [imaginario, real]])
    matriz = np.column_stack([linear, destino-linear@origem])
    return cv2.warpAffine(imagem, matriz, (imagem.shape[1], imagem.shape[0]), borderMode=cv2.BORDER_CONSTANT)


class EstabilizadorOptico:
    def __init__(self, maximo_intervalo_s: float = .3):
        if not np.isfinite(maximo_intervalo_s) or maximo_intervalo_s <= 0:
            raise ValueError("Intervalo máximo inválido.")
        self.maximo_intervalo_s = maximo_intervalo_s
        self.reiniciar()

    def reiniciar(self) -> None:
        self.anterior = self.pontos = self.rosto = self.instante = None
        self.transformacao = np.eye(3)

    def _iniciar(self, imagem, cinza, rosto, instante, motivo):
        self.reiniciar()
        self.anterior, self.rosto, self.instante = cinza, rosto, instante
        mascara = np.zeros(cinza.shape, np.uint8)
        seguro = rosto.limitar(cinza.shape[1], cinza.shape[0])
        mascara[seguro.y:seguro.base, seguro.x:seguro.direita] = 255
        self.pontos = cv2.goodFeaturesToTrack(cinza, 120, .01, 5, mask=mascara)
        n = 0 if self.pontos is None else len(self.pontos)
        return QuadroEstabilizado(imagem.copy(), n >= 8, True, n, (0., 0.), motivo)

    def atualizar(self, imagem: np.ndarray, rosto: Retangulo, instante: float) -> QuadroEstabilizado:
        if imagem.ndim != 3 or imagem.shape[2] != 3 or imagem.dtype != np.uint8 or not np.isfinite(instante):
            raise ValueError("Quadro ou instante inválido.")
        if self.instante is not None and instante <= self.instante:
            raise ValueError("Os instantes precisam avançar.")
        cinza = cv2.cvtColor(imagem, cv2.COLOR_BGR2GRAY)
        if (self.anterior is None or self.anterior.shape != cinza.shape
                or instante-self.instante > self.maximo_intervalo_s
                or self.pontos is None or len(self.pontos) < 8
                or self.rosto.sobreposicao(rosto) < .3):
            return self._iniciar(imagem, cinza, rosto, instante, "Aquisição da referência espacial.")
        atuais, st, _ = cv2.calcOpticalFlowPyrLK(self.anterior, cinza, self.pontos, None)
        if atuais is None:
            return self._iniciar(imagem, cinza, rosto, instante, "Fluxo óptico perdido.")
        retorno, stb, _ = cv2.calcOpticalFlowPyrLK(cinza, self.anterior, atuais, None)
        if retorno is None:
            return self._iniciar(imagem, cinza, rosto, instante, "Fluxo reverso perdido.")
        erro = np.linalg.norm((retorno-self.pontos).reshape(-1, 2), axis=1)
        bons = (st.ravel() == 1) & (stb.ravel() == 1) & (erro < 1.5)
        antes, depois = self.pontos[bons], atuais[bons]
        if len(antes) < 8:
            return self._iniciar(imagem, cinza, rosto, instante, "Poucos pontos consistentes.")
        matriz, inliers = cv2.estimateAffinePartial2D(antes, depois, method=cv2.RANSAC,
                                                     ransacReprojThreshold=2)
        if matriz is None or inliers is None or np.mean(inliers) < .6:
            return self._iniciar(imagem, cinza, rosto, instante, "Movimento sem transformação consistente.")
        escala = np.hypot(matriz[0, 0], matriz[1, 0])
        if not .9 <= escala <= 1.1:
            return self._iniciar(imagem, cinza, rosto, instante, "Variação de escala excessiva.")
        self.transformacao = np.vstack([matriz, [0, 0, 1]]) @ self.transformacao
        deslocamento = tuple(float(x) for x in np.median((depois-antes).reshape(-1, 2), axis=0))
        self.anterior, self.pontos = cinza, depois[inliers.ravel() == 1]
        self.rosto, self.instante = rosto, instante
        h, w = imagem.shape[:2]
        alinhada = cv2.warpAffine(imagem, np.linalg.inv(self.transformacao)[:2], (w, h),
                                 borderMode=cv2.BORDER_CONSTANT)
        return QuadroEstabilizado(alinhada, True, False, len(self.pontos), deslocamento, "Fluxo consistente.")
