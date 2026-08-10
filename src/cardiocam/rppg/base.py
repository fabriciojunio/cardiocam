"""Contrato comum dos algoritmos de extração de pulso.

Todo algoritmo recebe a mesma coisa (três séries temporais, uma por canal de
cor) e devolve a mesma coisa (uma série só, o pulso). O que muda é como
combinam os canais para separar o que é sangue do que é iluminação e movimento.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

import numpy as np

from cardiocam.dominio.config import ConfiguracaoAnalise
from cardiocam.dominio.resultado import Falha, Ok, Resultado
from cardiocam.dominio.sinal import SerieRGB, SinalPulso
from cardiocam.sinais.filtros import aplicar_passa_faixa
from cardiocam.sinais.preprocessamento import remover_tendencia


@runtime_checkable
class AlgoritmoRPPG(Protocol):
    """Interface que o pipeline consome."""

    nome: str

    def extrair(
        self, serie: SerieRGB, config: ConfiguracaoAnalise
    ) -> Resultado[SinalPulso]:
        """Converte a série RGB em sinal de pulso."""
        ...


def finalizar(
    bruto: np.ndarray,
    serie: SerieRGB,
    config: ConfiguracaoAnalise,
    nome: str,
) -> Resultado[SinalPulso]:
    """Etapa final compartilhada: tira a tendência e filtra na banda cardíaca.

    Fica aqui, e não dentro de cada algoritmo, para que a comparação entre eles
    seja honesta: todos recebem exatamente o mesmo pós-processamento, e a única
    diferença medida é a combinação de canais.
    """
    sem_tendencia = remover_tendencia(bruto, config.lambda_detrend)
    filtrado = aplicar_passa_faixa(
        sem_tendencia, serie.fps, config.banda, config.ordem_filtro
    )
    if filtrado.falhou:
        return Falha(filtrado.erro)
    return Ok(SinalPulso(filtrado.desempacotar(), serie.fps, nome))
