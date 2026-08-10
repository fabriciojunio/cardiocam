"""Preparo do sinal antes da análise espectral.

Dois problemas dominam o sinal de uma webcam e são tratados aqui:

1. Tendência lenta. A iluminação muda, a pessoa se aproxima, o ganho automático
   da câmera atua. Isso gera uma rampa que concentra energia em baixa frequência
   e vaza para dentro da banda cardíaca.
2. Amostragem irregular. Webcam não entrega quadros em intervalos constantes; o
   "30 fps" é nominal. Analisar o sinal como se fosse uniforme borra o espectro.
"""

from __future__ import annotations

import numpy as np
from scipy import sparse
from scipy.sparse import linalg as sparse_linalg

from cardiocam.sinais.filtros import media_movel

_CACHE_OPERADOR: dict[tuple[int, float], sparse.csc_matrix] = {}
_LIMITE_CACHE = 32


def _operador_detrend(n: int, lambda_: float) -> sparse.csc_matrix:
    """Monta (e memoriza) o operador de detrend por priores de suavidade.

    Segue Tarvainen, Ranta-aho e Karjalainen (2002): a tendência é a solução de
    um problema de mínimos quadrados regularizado pela segunda diferença, e o
    sinal sem tendência é `z - tendência`, o que equivale a aplicar

        (I + λ² D₂ᵀ D₂)⁻¹

    e subtrair do original. Guardamos a fatoração porque `n` e `λ` repetem a
    cada janela.
    """
    chave = (n, float(lambda_))
    if chave in _CACHE_OPERADOR:
        return _CACHE_OPERADOR[chave]

    # Matriz de segunda diferença: cada linha vale [1, -2, 1] deslocada de uma
    # coluna. Usamos `diags` e não `spdiags` de propósito: o segundo herda a
    # convenção do MATLAB, em que uma diagonal de deslocamento k descarta os k
    # primeiros valores fornecidos, o que trunca a última linha da matriz.
    segunda_diferenca = sparse.diags(
        [1.0, -2.0, 1.0], offsets=[0, 1, 2], shape=(n - 2, n), format="csc"
    )
    identidade = sparse.eye(n, format="csc")
    operador = (identidade + (lambda_**2) * (segunda_diferenca.T @ segunda_diferenca)).tocsc()

    if len(_CACHE_OPERADOR) >= _LIMITE_CACHE:
        _CACHE_OPERADOR.clear()
    _CACHE_OPERADOR[chave] = operador
    return operador


def remover_tendencia(amostras: np.ndarray, lambda_: float = 100.0) -> np.ndarray:
    """Remove a tendência lenta preservando a oscilação do pulso.

    Para sinais muito curtos (menos de 4 amostras) não há segunda diferença
    definida e caímos na simples remoção de média.
    """
    entrada = np.asarray(amostras, dtype=float)
    n = entrada.size
    if n < 4:
        return entrada - np.mean(entrada) if n else entrada.copy()
    if lambda_ <= 0:
        return entrada - np.mean(entrada)

    operador = _operador_detrend(n, lambda_)
    tendencia = sparse_linalg.spsolve(operador, entrada)
    return entrada - np.asarray(tendencia, dtype=float)


def remover_tendencia_movel(amostras: np.ndarray, janela: int) -> np.ndarray:
    """Detrend barato: subtrai a média móvel. Usado quando o custo importa."""
    entrada = np.asarray(amostras, dtype=float)
    if entrada.size == 0:
        return entrada.copy()
    return entrada - media_movel(entrada, janela)


def normalizar(amostras: np.ndarray) -> np.ndarray:
    """Escore z de um vetor ou de cada linha de uma matriz.

    Sinal constante devolve zeros em vez de dividir por zero.
    """
    entrada = np.asarray(amostras, dtype=float)
    if entrada.size == 0:
        return entrada.copy()
    media = np.mean(entrada, axis=-1, keepdims=True)
    desvio = np.std(entrada, axis=-1, keepdims=True)
    seguro = np.where(desvio < 1e-12, 1.0, desvio)
    resultado = (entrada - media) / seguro
    return np.where(desvio < 1e-12, 0.0, resultado)


def normalizar_pela_media(amostras: np.ndarray) -> np.ndarray:
    """Divide cada canal pela própria média temporal.

    É o primeiro passo de CHROM e POS: transforma intensidade absoluta em
    variação relativa, o que cancela boa parte do efeito da cor da pele e do
    nível de iluminação.
    """
    entrada = np.asarray(amostras, dtype=float)
    if entrada.size == 0:
        return entrada.copy()
    media = np.mean(entrada, axis=-1, keepdims=True)
    seguro = np.where(np.abs(media) < 1e-12, 1.0, media)
    return entrada / seguro


def reamostrar_uniforme(
    amostras: np.ndarray, instantes: np.ndarray, fps_alvo: float
) -> tuple[np.ndarray, np.ndarray]:
    """Reinterpola o sinal numa grade temporal uniforme.

    Corrige o jitter de captura da webcam. Aceita vetor 1-D ou matriz com canais
    nas linhas, e devolve `(sinal_reamostrado, instantes_uniformes)`.
    """
    if fps_alvo <= 0:
        raise ValueError("A taxa de quadros alvo precisa ser positiva.")
    entrada = np.asarray(amostras, dtype=float)
    tempos = np.asarray(instantes, dtype=float)
    if entrada.shape[-1] != tempos.size:
        raise ValueError("O número de instantes não casa com o número de amostras.")
    if tempos.size < 2:
        return entrada.copy(), tempos.copy()

    ordem = np.argsort(tempos)
    tempos = tempos[ordem]
    entrada = entrada[..., ordem]

    duracao = tempos[-1] - tempos[0]
    quantidade = max(2, int(round(duracao * fps_alvo)) + 1)
    grade = np.linspace(tempos[0], tempos[-1], quantidade)

    if entrada.ndim == 1:
        return np.interp(grade, tempos, entrada), grade
    reamostrado = np.vstack([np.interp(grade, tempos, linha) for linha in entrada])
    return reamostrado, grade


def estimar_fps(instantes: np.ndarray) -> float:
    """Taxa efetiva de quadros a partir dos carimbos de tempo.

    Usa a mediana dos intervalos, que é robusta a travadas pontuais da captura,
    ao contrário da média.
    """
    tempos = np.asarray(instantes, dtype=float)
    if tempos.size < 2:
        return 0.0
    intervalos = np.diff(np.sort(tempos))
    intervalos = intervalos[intervalos > 0]
    if intervalos.size == 0:
        return 0.0
    return float(1.0 / np.median(intervalos))
