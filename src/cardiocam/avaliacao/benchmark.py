"""Comparação quantitativa entre os algoritmos.

Roda os quatro métodos sobre os mesmos cenários sintéticos e mede o erro contra
a frequência verdadeira. Como todos recebem exatamente a mesma entrada e o mesmo
pós-processamento, a diferença observada é atribuível só à forma de combinar os
canais de cor.

As métricas são as usuais da literatura de rPPG: erro absoluto médio, raiz do
erro quadrático médio e a taxa de acerto dentro de uma tolerância, que é o que
de fato interessa numa aplicação.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from cardiocam.dominio.config import ConfiguracaoAnalise
from cardiocam.fontes.sintetica import (
    FonteSintetica,
    ParametrosSimulacao,
    gerar_serie_rgb,
)
from cardiocam.pipeline.analisador import analisar_fonte, estimar_de_serie
from cardiocam.rppg import ALGORITMOS_DISPONIVEIS, criar_algoritmo

TOLERANCIA_PADRAO_BPM = 3.0


@dataclass(frozen=True, slots=True)
class Cenario:
    """Uma condição de teste com nome legível."""

    nome: str
    parametros: ParametrosSimulacao

    @property
    def bpm_verdadeiro(self) -> float:
        return self.parametros.bpm


@dataclass
class ResultadoAlgoritmo:
    """Desempenho de um algoritmo num conjunto de cenários."""

    algoritmo: str
    erros: list[float] = field(default_factory=list)
    snrs: list[float] = field(default_factory=list)
    falhas: int = 0

    @property
    def total(self) -> int:
        return len(self.erros) + self.falhas

    @property
    def erro_medio(self) -> float:
        return float(np.mean(self.erros)) if self.erros else float("nan")

    @property
    def erro_maximo(self) -> float:
        return float(np.max(self.erros)) if self.erros else float("nan")

    @property
    def raiz_erro_quadratico(self) -> float:
        if not self.erros:
            return float("nan")
        return float(np.sqrt(np.mean(np.square(self.erros))))

    @property
    def snr_medio_db(self) -> float:
        validos = [s for s in self.snrs if np.isfinite(s)]
        return float(np.mean(validos)) if validos else float("nan")

    def taxa_de_acerto(self, tolerancia: float = TOLERANCIA_PADRAO_BPM) -> float:
        """Fração dos cenários em que o erro ficou dentro da tolerância.

        Falhas contam como erro, porque um sistema que não responde também não
        serve.
        """
        if self.total == 0:
            return 0.0
        acertos = sum(1 for erro in self.erros if erro <= tolerancia)
        return acertos / self.total


def frequencia_interferente(bpm: float, afastamento_hz: float = 0.7) -> float:
    """Escolhe uma frequência de interferência dentro da banda cardíaca, mas
    afastada da do pulso.

    Uma interferência fora da banda é removida pelo passa-faixa e não distingue
    algoritmo nenhum. Uma interferência exatamente sobre a frequência do pulso é
    impossível de separar por qualquer método. O caso interessante, e o que
    acontece de verdade quando alguém balança levemente a cabeça ou uma lâmpada
    oscila, fica no meio: dentro da banda e competindo com o pulso.
    """
    pulso_hz = bpm / 60.0
    candidata = pulso_hz + afastamento_hz
    if candidata > 3.8:
        candidata = pulso_hz - afastamento_hz
    return float(np.clip(candidata, 0.75, 3.9))


def cenarios_padrao(
    bpms: tuple[float, ...] = (48.0, 60.0, 72.0, 84.0, 96.0, 120.0, 150.0, 180.0),
) -> list[Cenario]:
    """Bateria que cobre as condições que aparecem no uso real.

    Vale explicar por que a deriva lenta de iluminação não aparece como cenário
    difícil: uma rampa é removida pelo detrend e pelo passa-faixa antes de
    qualquer algoritmo agir, então todos empatam. O que realmente separa os
    métodos é a interferência que cai dentro da banda cardíaca, porque aí a
    filtragem não ajuda e só resta explorar a diferença de comportamento entre
    os canais de cor.
    """
    cenarios: list[Cenario] = []
    for bpm in bpms:
        base = dict(bpm=bpm, duracao_s=20.0, fps=30.0, semente=int(bpm))
        interferente = frequencia_interferente(bpm)
        cenarios.extend(
            [
                Cenario(
                    "ideal",
                    ParametrosSimulacao(**base, amplitude_pulso=0.02, ruido_sensor=1.0),
                ),
                Cenario(
                    "pulso fraco",
                    ParametrosSimulacao(
                        **base, amplitude_pulso=0.005, ruido_sensor=3.0
                    ),
                ),
                Cenario(
                    "ruído alto",
                    ParametrosSimulacao(
                        **base, amplitude_pulso=0.008, ruido_sensor=14.0
                    ),
                ),
                Cenario(
                    "deriva de iluminação",
                    ParametrosSimulacao(
                        **base,
                        amplitude_pulso=0.015,
                        ruido_sensor=2.0,
                        deriva_iluminacao=0.25,
                    ),
                ),
                Cenario(
                    "interferência na banda",
                    ParametrosSimulacao(
                        **base,
                        amplitude_pulso=0.015,
                        ruido_sensor=2.0,
                        amplitude_tremor=0.02,
                        tremor_iluminacao_hz=interferente,
                    ),
                ),
                Cenario(
                    "interferência forte",
                    ParametrosSimulacao(
                        **base,
                        amplitude_pulso=0.012,
                        ruido_sensor=2.0,
                        amplitude_tremor=0.06,
                        tremor_iluminacao_hz=interferente,
                    ),
                ),
                Cenario(
                    "captura irregular",
                    ParametrosSimulacao(
                        **base,
                        amplitude_pulso=0.015,
                        ruido_sensor=2.0,
                        jitter_fps=0.015,
                    ),
                ),
            ]
        )
    return cenarios


def avaliar(
    cenarios: list[Cenario] | None = None,
    algoritmos: tuple[str, ...] = ALGORITMOS_DISPONIVEIS,
    config: ConfiguracaoAnalise | None = None,
    usar_video: bool = False,
) -> dict[str, ResultadoAlgoritmo]:
    """Executa a bateria e devolve o desempenho de cada algoritmo.

    Com `usar_video`, o caminho completo é exercitado, incluindo detecção de
    rosto e extração de pixels. Sem, apenas a parte de sinais, que é bem mais
    rápida e isola o mérito do algoritmo.
    """
    cenarios = cenarios or cenarios_padrao()
    config = config or ConfiguracaoAnalise()
    resultados = {nome: ResultadoAlgoritmo(nome) for nome in algoritmos}

    for cenario in cenarios:
        serie = None if usar_video else gerar_serie_rgb(cenario.parametros)
        for nome in algoritmos:
            algoritmo = criar_algoritmo(nome)
            resultado = resultados[nome]

            if usar_video:
                relatorio = analisar_fonte(
                    FonteSintetica(cenario.parametros),
                    config.com(algoritmo=nome),
                    algoritmo=algoritmo,
                )
                estimado = relatorio.bpm_mediano
                if not np.isfinite(estimado):
                    resultado.falhas += 1
                    continue
                resultado.erros.append(abs(estimado - cenario.bpm_verdadeiro))
                resultado.snrs.append(relatorio.snr_mediano_db)
                continue

            analise = estimar_de_serie(serie, config.com(algoritmo=nome), algoritmo)
            if analise.falhou:
                resultado.falhas += 1
                continue
            completa = analise.desempacotar()
            resultado.erros.append(
                abs(completa.estimativa.bpm - cenario.bpm_verdadeiro)
            )
            resultado.snrs.append(completa.estimativa.snr_db)

    return resultados


def por_cenario(
    cenarios: list[Cenario] | None = None,
    algoritmos: tuple[str, ...] = ALGORITMOS_DISPONIVEIS,
    config: ConfiguracaoAnalise | None = None,
) -> dict[str, dict[str, ResultadoAlgoritmo]]:
    """Mesma avaliação, separada por tipo de cenário.

    É aqui que aparece o ponto interessante para o relatório: o método do canal
    verde acompanha os demais em condição ideal e desaba quando entra variação
    de iluminação.
    """
    cenarios = cenarios or cenarios_padrao()
    agrupados: dict[str, list[Cenario]] = {}
    for cenario in cenarios:
        agrupados.setdefault(cenario.nome, []).append(cenario)

    return {
        nome: avaliar(lista, algoritmos, config)
        for nome, lista in agrupados.items()
    }


def formatar_tabela(resultados: dict[str, ResultadoAlgoritmo]) -> str:
    """Tabela em Markdown, pronta para colar no relatório."""
    linhas = [
        "| Algoritmo | Erro médio (bpm) | RMSE (bpm) | Erro máximo (bpm) | SNR médio (dB) | Acerto ±3 bpm | Falhas |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for nome, resultado in resultados.items():
        linhas.append(
            f"| {nome.upper()} | {resultado.erro_medio:.2f} | "
            f"{resultado.raiz_erro_quadratico:.2f} | {resultado.erro_maximo:.2f} | "
            f"{resultado.snr_medio_db:.1f} | "
            f"{resultado.taxa_de_acerto() * 100:.0f}% | {resultado.falhas} |"
        )
    return "\n".join(linhas)


def formatar_por_cenario(
    resultados: dict[str, dict[str, ResultadoAlgoritmo]]
) -> str:
    """Tabela cruzada de erro médio por cenário e algoritmo."""
    if not resultados:
        return ""
    algoritmos = list(next(iter(resultados.values())).keys())
    cabecalho = "| Cenário | " + " | ".join(a.upper() for a in algoritmos) + " |"
    separador = "| --- | " + " | ".join("---:" for _ in algoritmos) + " |"
    linhas = [cabecalho, separador]
    for cenario, por_algoritmo in resultados.items():
        valores = " | ".join(
            f"{por_algoritmo[a].erro_medio:.2f}" for a in algoritmos
        )
        linhas.append(f"| {cenario} | {valores} |")
    return "\n".join(linhas)
