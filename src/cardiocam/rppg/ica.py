"""ICA: separação cega de fontes.

Poh, McDuff e Picard (2010) tratam o problema como coquetel: os três canais de
cor são três misturas de fontes independentes, sendo uma delas o pulso e as
outras movimento, iluminação e ruído. A análise de componentes independentes
tenta desfazer a mistura sem saber nada sobre ela, procurando as combinações
lineares mais estatisticamente independentes possíveis.

A vantagem é não precisar de modelo físico da pele. A desvantagem é a ambiguidade
inerente ao método: ICA não sabe qual componente é o pulso, nem preserva ordem,
escala ou sinal entre execuções. Resolvemos escolhendo, entre as componentes, a
que tem o pico espectral mais destacado dentro da banda cardíaca.

É também o método mais caro e o menos previsível dos quatro, porque o FastICA é
iterativo e pode não convergir.
"""

from __future__ import annotations

import warnings

import numpy as np
from sklearn.decomposition import FastICA

from cardiocam.dominio.config import ConfiguracaoAnalise
from cardiocam.dominio.resultado import Falha, Ok, Resultado
from cardiocam.dominio.sinal import SerieRGB, SinalPulso
from cardiocam.rppg.base import finalizar
from cardiocam.sinais.espectro import periodograma, relacao_sinal_ruido
from cardiocam.sinais.preprocessamento import normalizar


class Ica:
    """Extração de pulso por análise de componentes independentes."""

    nome = "ica"

    def __init__(self, semente: int = 0, iteracoes: int = 400) -> None:
        self.semente = semente
        self.iteracoes = iteracoes

    def _melhor_componente(
        self, componentes: np.ndarray, fps: float, config: ConfiguracaoAnalise
    ) -> np.ndarray:
        """Escolhe a componente com maior relação sinal-ruído na banda cardíaca."""
        melhor = componentes[0]
        melhor_snr = float("-inf")
        for componente in componentes:
            frequencias, potencias = periodograma(componente, fps)
            if frequencias.size == 0:
                continue
            na_banda = (frequencias >= config.banda.minima_hz) & (
                frequencias <= config.banda.maxima_hz
            )
            if not np.any(na_banda):
                continue
            indices = np.flatnonzero(na_banda)
            pico = frequencias[indices[np.argmax(potencias[indices])]]
            snr = relacao_sinal_ruido(frequencias, potencias, float(pico), config.banda)
            if snr > melhor_snr:
                melhor_snr = snr
                melhor = componente
        return melhor

    def extrair(
        self, serie: SerieRGB, config: ConfiguracaoAnalise
    ) -> Resultado[SinalPulso]:
        entrada = normalizar(serie.como_matriz())

        try:
            with warnings.catch_warnings():
                # A não convergência do FastICA é comum com janelas curtas e não
                # invalida o resultado; tratamos abaixo pela escolha da melhor
                # componente.
                warnings.simplefilter("ignore")
                separador = FastICA(
                    n_components=3,
                    random_state=self.semente,
                    max_iter=self.iteracoes,
                    whiten="unit-variance",
                )
                componentes = separador.fit_transform(entrada.T).T
        except Exception as causa:  # noqa: BLE001 - fronteira com o scikit-learn
            from cardiocam.dominio.erros import SinalSemQualidade

            erro = SinalSemQualidade(float("-inf"), 0.0)
            erro.__cause__ = causa
            return Falha(erro)

        escolhida = self._melhor_componente(componentes, serie.fps, config)
        return finalizar(escolhida, serie, config, self.nome)
