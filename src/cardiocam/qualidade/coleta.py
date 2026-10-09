"""Transforma execuções reais do pipeline em amostras de treino.

Nada aqui é simulado duas vezes. O caminho é o mesmo que roda em produção:
série RGB, algoritmo rPPG, filtragem, espectro. O que este módulo acrescenta é
guardar, ao lado do resultado, as características da janela e o erro contra a
frequência verdadeira, que no cenário sintético nós escolhemos.

**O agrupamento é por condição, não por janela.** Isso é mais severo do que
parece e é de propósito: a partição coloca condições inteiras de um lado só, e
o número de teste passa a responder "o modelo de qualidade acerta numa
perturbação que ele nunca viu?". Agrupar por janela daria um número maior e
mediria outra coisa.

É a versão sintética do que, em dado real, precisa ser agrupamento por sujeito.
A troca está declarada em vez de escondida, porque é ela que decide se o
resultado é transferível.

**Falhas são contadas separadamente.** Uma janela sem estimativa não fornece
as características espectrais necessárias ao classificador e não entra como
amostra com erro inventado. O treino é condicionado às estimativas produzidas;
a cobertura do sistema completo deve incluir também as falhas do pipeline.
"""

from __future__ import annotations

from cardiocam.avaliacao.benchmark import Cenario, cenarios_padrao
from cardiocam.dominio.config import ConfiguracaoAnalise
from cardiocam.fontes.sintetica import gerar_serie_rgb
from cardiocam.pipeline.analisador import estimar_de_serie
from cardiocam.qualidade.extracao import caracteristicas_da_analise
from cardiocam.qualidade.treino import Amostra
from cardiocam.rppg import ALGORITMOS_DISPONIVEIS, criar_algoritmo

def coletar(
    cenarios: list[Cenario] | None = None,
    algoritmos: tuple[str, ...] = ALGORITMOS_DISPONIVEIS,
    config: ConfiguracaoAnalise | None = None,
    agrupar_por: str = "condicao",
) -> tuple[list[Amostra], int]:
    """Roda a bateria e devolve as amostras e quantas janelas falharam.

    `agrupar_por` aceita `"condicao"`, que é o padrão e o severo, ou
    `"frequencia"`, que separa por bpm e mede outra coisa: generalizar para uma
    frequência não vista, mantendo as perturbações conhecidas.
    """
    if agrupar_por not in {"condicao", "frequencia"}:
        raise ValueError(
            f"Agrupamento {agrupar_por!r} não existe. Use 'condicao' ou 'frequencia'."
        )

    cenarios = cenarios or cenarios_padrao()
    config = config or ConfiguracaoAnalise()
    amostras: list[Amostra] = []
    falhas = 0

    for cenario in cenarios:
        serie = gerar_serie_rgb(cenario.parametros)
        grupo = (
            cenario.nome
            if agrupar_por == "condicao"
            else f"{cenario.bpm_verdadeiro:.0f}"
        )
        for nome in algoritmos:
            resultado = estimar_de_serie(
                serie, config.com(algoritmo=nome), criar_algoritmo(nome)
            )
            if resultado.falhou:
                # A janela que não produziu estimativa NÃO vira amostra.
                #
                # A primeira versão a incluía com um vetor fabricado, para
                # evitar viés de sobrevivência. Medir mostrou que o efeito é o
                # oposto do pretendido: o vetor fabricado tem marcas próprias,
                # e o modelo aprende a reconhecer a fabricação em vez de
                # reconhecer janela ruim.
                #
                # E o argumento do viés não se sustenta aqui, porque essas
                # janelas já são recusadas pelo pipeline antes de chegar ao
                # modelo. O trabalho dele é outro: pegar a janela que **parece
                # boa e está errada**. As que falharam são contadas à parte e
                # entram no relatório como recusa automática.
                falhas += 1
                continue
            analise = resultado.desempacotar()
            amostras.append(
                Amostra(
                    caracteristicas=caracteristicas_da_analise(analise, serie),
                    erro_bpm=float(
                        abs(analise.estimativa.bpm - cenario.bpm_verdadeiro)
                    ),
                    grupo=grupo,
                )
            )

    return amostras, falhas
