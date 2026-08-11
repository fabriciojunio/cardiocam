"""Remoção de interferência de iluminação usando o fundo como referência.

A ideia vem de uma observação simples: a parede atrás da pessoa não tem pulso.
Tudo que oscila no fundo é iluminação do ambiente, tremulação da lâmpada, ou o
próprio controle automático de exposição e de balanço de branco da câmera
mexendo no ganho. Como o rosto e o fundo recebem a mesma luz, o fundo serve de
medida direta da perturbação, e o que for explicável por ele pode ser retirado
do sinal do rosto.

Isso cobre um caso que CHROM e POS não cobrem. Os dois cancelam variação de
intensidade comum aos três canais, mas o balanço de branco automático aplica
ganhos diferentes por canal, e a compressão aplica mapeamentos não lineares.
Nenhum dos dois é uma variação puramente de intensidade, e por isso escapa da
projeção cromática.

O método é o de mínimos quadrados: procuramos os coeficientes que fazem o fundo
melhor aproximar o sinal do rosto, e subtraímos essa parte. Vários atrasos são
considerados porque a resposta do controle automático não é instantânea.
"""

from __future__ import annotations

import numpy as np


def montar_atrasos(referencia: np.ndarray, atrasos: int) -> np.ndarray:
    """Matriz com a referência deslocada no tempo, uma coluna por atraso.

    Permite que a remoção compense o fato de o controle automático da câmera
    reagir alguns quadros depois da mudança de luz.
    """
    if atrasos < 1:
        raise ValueError("É preciso ao menos um atraso.")
    n = referencia.size
    colunas = []
    for k in range(atrasos):
        deslocada = np.zeros(n, dtype=float)
        if k == 0:
            deslocada[:] = referencia
        else:
            deslocada[k:] = referencia[:-k]
        colunas.append(deslocada)
    return np.vstack(colunas).T


def remover_referencia(
    sinal: np.ndarray,
    referencia: np.ndarray,
    atrasos: int = 3,
    ganho_maximo: float = 3.0,
) -> np.ndarray:
    """Remove do sinal a parte explicável pela referência.

    `ganho_maximo` é uma trava de segurança. Se a solução de mínimos quadrados
    pedir um coeficiente enorme, é sinal de que a referência não explica o sinal
    e está apenas casando com ruído; nesse caso subtrair pioraria as coisas e o
    sinal volta intocado.
    """
    entrada = np.asarray(sinal, dtype=float)
    fundo = np.asarray(referencia, dtype=float)

    if entrada.size == 0 or fundo.size != entrada.size:
        return entrada.copy()

    desvio_fundo = float(np.std(fundo))
    desvio_sinal = float(np.std(entrada))
    if desvio_fundo < 1e-12 or desvio_sinal < 1e-12:
        return entrada.copy()

    # Normalizar os dois deixa os coeficientes adimensionais, o que torna a
    # trava de ganho comparável entre cenas claras e escuras.
    fundo_normalizado = (fundo - float(np.mean(fundo))) / desvio_fundo
    sinal_centrado = entrada - float(np.mean(entrada))

    atrasos = max(1, min(atrasos, max(1, entrada.size // 8)))
    matriz = montar_atrasos(fundo_normalizado, atrasos)

    try:
        coeficientes, *_ = np.linalg.lstsq(matriz, sinal_centrado, rcond=None)
    except np.linalg.LinAlgError:  # pragma: sem cobertura
        return entrada.copy()

    if not np.all(np.isfinite(coeficientes)):
        return entrada.copy()
    if float(np.max(np.abs(coeficientes))) > ganho_maximo * desvio_sinal:
        return entrada.copy()

    estimado = matriz @ coeficientes
    limpo = sinal_centrado - estimado

    # Não há trava contra a remoção apagar quase tudo, e a ausência é
    # deliberada. Se o fundo explica todo o sinal do rosto, então não havia
    # pulso ali, apenas iluminação. Devolver o sinal original nesse caso faria o
    # sistema reportar a interferência como se fosse batimento. Deixando o
    # resultado próximo de zero, a verificação de sinal degenerado mais adiante
    # recusa a janela, que é a resposta certa. Um medidor deve errar para o lado
    # de dizer "não sei".
    return limpo


def energia_removida(sinal: np.ndarray, limpo: np.ndarray) -> float:
    """Fração da energia que a rectificação retirou, de 0 a 1.

    Serve de indicador: valores altos significam que boa parte do que parecia
    sinal era, na verdade, variação de iluminação.
    """
    original = float(np.var(sinal))
    if original <= 1e-18:
        return 0.0
    return float(max(0.0, min(1.0, 1.0 - np.var(limpo) / original)))
