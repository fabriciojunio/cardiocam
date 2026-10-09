"""Uma única extração de características para treino e medição."""

from __future__ import annotations

import numpy as np

from cardiocam.qualidade.caracteristicas import Caracteristicas, extrair


def caracteristicas_da_analise(analise, serie=None, contexto=None) -> Caracteristicas:
    """Combina o sinal da análise com o contexto dos mesmos quadros.

    O jitter usa os instantes anteriores à reamostragem. A série reamostrada
    mantém os canais e o fundo alinhados ao pulso que foi analisado.
    """
    serie = serie if serie is not None else getattr(analise, "serie", None)
    fundo = None
    if serie is not None and serie.fundo is not None:
        fundo = np.asarray(serie.fundo, dtype=float)[1, :]
        if fundo.size != len(analise.pulso):
            fundo = fundo[-len(analise.pulso):] if fundo.size > len(analise.pulso) else None
    instantes = getattr(analise, "instantes_originais", None)
    if instantes is None and serie is not None:
        instantes = serie.instantes
    return extrair(
        pulso=analise.pulso,
        espectro=analise.espectro,
        frequencia_hz=analise.estimativa.frequencia_hz,
        snr_db=analise.estimativa.snr_db,
        sinal_do_fundo=fundo,
        serie_rgb=None if serie is None else serie.como_matriz(),
        instantes=instantes,
        fracao_de_pele=1.0 if contexto is None else contexto.media_de_pele(),
        fracao_saturada=0.0 if contexto is None else contexto.media_saturada(),
        posicoes_roi=None if contexto is None else contexto.deslocamento(),
    )
