"""Pupila RGB, pele periocular e deslocamento de cabeça, sem diagnóstico."""

from dataclasses import dataclass

import cv2
import numpy as np
from scipy import signal

from cardiocam.dominio.sinal import SinalPulso
from cardiocam.visao.geometria import Retangulo
from cardiocam.visao.olhos import Olhos


@dataclass(frozen=True)
class Pupila:
    centro: tuple[float, float]
    diametro_px: float
    contraste: float


def medir_pupila(olho_bgr: np.ndarray) -> Pupila | None:
    """Elipse escura no recorte do olho. Piscada/reflexo forte podem impedir leitura."""
    if olho_bgr.ndim != 3 or olho_bgr.shape[2] != 3 or olho_bgr.dtype != np.uint8:
        raise ValueError("Informe um recorte BGR uint8 do olho.")
    if min(olho_bgr.shape[:2]) < 16:
        return None
    cinza = cv2.cvtColor(olho_bgr, cv2.COLOR_BGR2GRAY)
    if np.mean(cinza >= 250) > .15 or np.std(cinza) < 5:
        return None
    _, escura = cv2.threshold(cv2.GaussianBlur(cinza, (3, 3), 0), 0, 255,
                             cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)
    contornos, _ = cv2.findContours(escura, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    h, w = cinza.shape
    candidatas = []
    for contorno in contornos:
        if len(contorno) < 5:
            continue
        x, y, cw, ch = cv2.boundingRect(contorno)
        area = cv2.contourArea(contorno)
        if x <= 0 or y <= 0 or x+cw >= w or y+ch >= h or not .01*w*h < area < .3*w*h:
            continue
        (cx, cy), (a, b), _ = cv2.fitEllipse(contorno)
        if min(a, b)/max(a, b) < .55 or not .15*w < cx < .85*w or not .15*h < cy < .85*h:
            continue
        mascara = np.zeros(cinza.shape, np.uint8)
        cv2.drawContours(mascara, [contorno], -1, 1, -1)
        contraste = float(np.median(cinza[mascara == 0])-np.median(cinza[mascara == 1]))
        if contraste > 15:
            candidatas.append(Pupila((float(cx), float(cy)), float(np.sqrt(a*b)), contraste))
    return max(candidatas, key=lambda p: p.contraste, default=None)


def regioes_perioculares(olhos: Olhos) -> tuple[Retangulo, Retangulo]:
    """Pele abaixo dos olhos; a pupila não integra a média RGB de pele."""
    d = olhos.separacao
    if not np.isfinite(d) or d < 10:
        raise ValueError("Distância entre olhos insuficiente.")
    return tuple(Retangulo(round(x-.16*d), round(y+.15*d), round(.32*d), round(.15*d))
                 for x, y in (olhos.esquerdo, olhos.direito))


def extrair_bcg(trajetorias: np.ndarray, fps: float) -> SinalPulso:
    """PCA de trajetórias verticais rastreadas, modalidade separada de rPPG."""
    x = np.asarray(trajetorias, float)
    if (x.ndim != 3 or x.shape[2] != 2 or x.shape[1] < 3 or len(x) < 8
            or not np.isfinite(x).all() or not np.isfinite(fps) or fps <= 0):
        raise ValueError("BCG requer trajetórias finitas T×pontos×2.")
    vertical = signal.detrend(x[:, :, 1], axis=0)
    u, s, _ = np.linalg.svd(vertical, full_matrices=False)
    if s[0] < 1e-8:
        raise ValueError("Trajetórias sem deslocamento mensurável.")
    return SinalPulso(u[:, 0]*s[0], fps, "video_bcg")
