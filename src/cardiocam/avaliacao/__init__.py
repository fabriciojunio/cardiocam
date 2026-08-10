"""Avaliação quantitativa dos algoritmos contra frequência conhecida."""

from cardiocam.avaliacao.benchmark import (
    TOLERANCIA_PADRAO_BPM,
    Cenario,
    ResultadoAlgoritmo,
    avaliar,
    cenarios_padrao,
    formatar_por_cenario,
    formatar_tabela,
    por_cenario,
)

__all__ = [
    "Cenario",
    "ResultadoAlgoritmo",
    "TOLERANCIA_PADRAO_BPM",
    "avaliar",
    "cenarios_padrao",
    "formatar_por_cenario",
    "formatar_tabela",
    "por_cenario",
]
