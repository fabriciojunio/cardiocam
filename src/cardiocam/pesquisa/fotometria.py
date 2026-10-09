"""Normalizações optativas que conservam a escala temporal dentro da janela."""

import cv2
import numpy as np
from scipy import signal


def normalizar_imagem(imagem: np.ndarray, metodo: str = "nenhum") -> np.ndarray:
    if imagem.ndim != 3 or imagem.shape[2] != 3 or imagem.dtype != np.uint8:
        raise ValueError("Informe imagem BGR uint8.")
    if metodo == "nenhum":
        return imagem.copy()
    x = imagem.astype(np.float32) / 255
    if metodo == "retinex":
        # Baseline multiescala clássico; não representa Retinexformer.
        log = np.log(np.maximum(x, 1/255))
        y = sum(log-np.log(np.maximum(cv2.GaussianBlur(x, (0, 0), s), 1/255))
                for s in (5, 15, 40)) / 3
        # Escala fixa: normalizar por quadro pode destruir o pulso.
        y = .5 + y / 3
    elif metodo == "crominancia":
        y = np.divide(x, x.sum(axis=2, keepdims=True), out=np.zeros_like(x),
                      where=x.sum(axis=2, keepdims=True) > 0) * 1.5
    else:
        raise ValueError("Normalização desconhecida.")
    return np.clip(np.round(y*255), 0, 255).astype(np.uint8)


def corrigir_temporal(rgb: np.ndarray, fps: float, fundo: np.ndarray | None = None,
                      suavizacao_s: float = 0) -> np.ndarray:
    """Regressão de iluminação externa e Savitzky–Golay com janela curta.

    Sem fundo, nenhum componente comum é removido: ele pode conter pulso.
    A regressão não usa referência cardíaca. A suavização é uma ablação.
    """
    x = np.asarray(rgb, dtype=float)
    if (x.ndim != 2 or x.shape[0] != 3 or x.shape[1] < 8
            or not np.isfinite(x).all() or not np.isfinite([fps, suavizacao_s]).all()
            or fps <= 0 or not 0 <= suavizacao_s <= .2):
        raise ValueError("Série ou suavização temporal inválida.")
    y = x.copy()
    if fundo is not None:
        b = np.asarray(fundo, dtype=float)
        if b.shape != x.shape or not np.isfinite(b).all():
            raise ValueError("Fundo incompatível.")
        centrado = b-b.mean(axis=1, keepdims=True)
        # Usa o canal correspondente; não mistura a assinatura cromática.
        for c in range(3):
            energia = centrado[c] @ centrado[c]
            if energia > 1e-12:
                y[c] -= ((y[c]-y[c].mean()) @ centrado[c]) / energia * centrado[c]
    n = int(round(fps*suavizacao_s)) | 1
    if n >= 5:
        n = min(n, x.shape[1] if x.shape[1] % 2 else x.shape[1]-1)
        y = signal.savgol_filter(y, n, 2, axis=1)
    return y
