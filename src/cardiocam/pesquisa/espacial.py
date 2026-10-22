"""Estatísticas espaciais de pele e rotação de subespaços (2SR).

Implementação independente das equações de Wang, Stuijk e de Haan,
doi:10.1109/TBME.2015.2508602. A entrada é o segundo momento NÃO centrado
dos pixels RGB de cada quadro; médias RGB não contêm essa informação.
"""

from dataclasses import dataclass

import numpy as np

from cardiocam.dominio.sinal import SinalPulso
from cardiocam.visao.geometria import Retangulo
from cardiocam.visao.pele import mascara_pele


@dataclass(frozen=True)
class AmostraEspacial:
    rgb: np.ndarray
    segundo_momento: np.ndarray
    pixels: int
    fracao_pele: float
    fracao_saturada: float


def extrair_regioes(imagem: np.ndarray, rosto: Retangulo,
                   grade: int = 3, minimo_pixels: int = 50) -> dict[str, AmostraEspacial]:
    """Uma série por célula; células sem pele são ausentes, nunca preenchidas."""
    if grade < 1 or grade > 8 or minimo_pixels < 3:
        raise ValueError("Grade entre 1 e 8 e mínimo de três pixels são necessários.")
    if imagem.ndim != 3 or imagem.shape[2] != 3 or imagem.dtype != np.uint8:
        raise ValueError("Informe um quadro BGR uint8.")
    recorte = rosto.recortar(imagem)
    if not recorte.size:
        return {}
    h, w = recorte.shape[:2]
    saida = {}
    for linha in range(grade):
        for coluna in range(grade):
            trecho = recorte[linha*h//grade:(linha+1)*h//grade,
                            coluna*w//grade:(coluna+1)*w//grade]
            if not trecho.size:
                continue
            mascara = mascara_pele(trecho)
            n = int(mascara.sum())
            if n < minimo_pixels:
                continue
            rgb = trecho[mascara][:, ::-1].astype(float) / 255.0
            saida[f"r{linha}c{coluna}"] = AmostraEspacial(
                rgb.mean(axis=0), rgb.T @ rgb / n, n, n / mascara.size,
                float(np.mean(np.any((rgb <= 1/255) | (rgb >= 254/255), axis=1))),
            )
    return saida


def extrair_ssr(momentos: np.ndarray, fps: float, janela_s: float = 1.6) -> SinalPulso:
    """2SR com alinhamento do sinal dos autovetores e soma de janelas.

    A ausência de posto espacial é erro, em vez de um pulso artificial.
    A saída bruta não passa por filtro; a avaliação aplica o mesmo filtro
    aos métodos comparados. Não se normaliza a soma de janelas do artigo.
    """
    entrada = np.asarray(momentos, dtype=float)
    if (entrada.ndim != 3 or entrada.shape[1:] != (3, 3)
            or not np.isfinite(entrada).all() or not np.isfinite(fps) or fps <= 0
            or not np.isfinite(janela_s) or janela_s <= 0):
        raise ValueError("SSR requer matrizes finitas Nx3x3 e tempos positivos.")
    tamanho = max(8, round(janela_s * fps))
    if len(entrada) < tamanho:
        raise ValueError("A série espacial é menor que a janela SSR.")
    if not np.allclose(entrada, entrada.swapaxes(1, 2), atol=1e-10):
        raise ValueError("Os segundos momentos precisam ser simétricos.")
    valores, vetores = np.linalg.eigh(entrada)
    valores, vetores = valores[:, ::-1], vetores[:, :, ::-1]
    if np.any(valores[:, 2] <= np.maximum(valores[:, 0] * 1e-10, 1e-14)):
        raise ValueError("Pele sem diversidade espacial suficiente para SSR.")
    for i in range(1, len(vetores)):
        sinais = np.sign(np.sum(vetores[i-1] * vetores[i], axis=0))
        vetores[i] *= np.where(sinais == 0, 1, sinais)
    pulso = np.zeros(len(entrada))
    for inicio in range(len(entrada) - tamanho + 1):
        fim = inicio + tamanho
        referencia = vetores[inicio, :, 1:]
        rotacao = vetores[inicio:fim, :, 0] @ referencia
        escala = np.sqrt(valores[inicio:fim, :1] / valores[inicio, 1:])
        reconstrucao = (rotacao * escala) @ referencia.T
        primeiro, segundo = reconstrucao[:, 0], reconstrucao[:, 1]
        desvio = segundo.std()
        if desvio > 1e-14:
            p = primeiro - primeiro.std() / desvio * segundo
            pulso[inicio:fim] += p - p.mean()
    return SinalPulso(pulso, fps, "ssr")
