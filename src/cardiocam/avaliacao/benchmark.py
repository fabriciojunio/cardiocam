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
from cardiocam.fontes.movimento import CROMATICIDADE_ESPECULAR, ParametrosMovimento
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


# Tons de pele em BGR, cobrindo a faixa que os conjuntos públicos de rPPG
# cobrem mal. UBFC-rPPG e PURE foram coletados quase só com fototipos 2 e 3 de
# Fitzpatrick, e é dessa lacuna que a hipótese H3 trata. Os valores não são
# medidas colorimétricas: são três pontos afastados o suficiente para que a
# diferença de intensidade refletida apareça, e estão aqui como parâmetro
# nomeado justamente para não parecerem mais precisos do que são.
TONS_DE_PELE: dict[str, tuple[int, int, int]] = {
    "claro": (150, 175, 205),
    "medio": (95, 120, 150),
    "escuro": (45, 58, 78),
}


def iluminante_desviado(desvio: float) -> tuple[float, float, float]:
    """Cromaticidade do iluminante, do neutro ao extremo, em BGR normalizado.

    `desvio` zero é a luz de escritório que `movimento.CROMATICIDADE_ESPECULAR`
    descreve; um é o extremo verde. O eixo escolhido é o verde porque é o canal
    em que a hemoglobina mais absorve, e portanto o que mais confunde um método
    que lê pulso a partir da cor.

    Serve para varrer o afastamento da hipótese em que CHROM e POS se apoiam, em
    vez de testar só "neutro" contra "muito colorido".
    """
    if not 0.0 <= desvio <= 1.0:
        raise ValueError("O desvio do iluminante precisa estar entre 0 e 1.")
    extremo = (0.35, 1.00, 0.35)
    return tuple(
        float(neutro * (1.0 - desvio) + alvo * desvio)
        for neutro, alvo in zip(CROMATICIDADE_ESPECULAR, extremo, strict=True)
    )


def cenarios_de_robustez(
    bpms: tuple[float, ...] = (54.0, 72.0, 96.0, 132.0),
) -> list[Cenario]:
    """Bateria das condições que o projeto de iniciação científica investiga.

    A bateria padrão não serve para estudar abstenção, e isso foi medido: cinco
    das suas sete condições acertam 100% das janelas dentro de 3 bpm, e as duas
    restantes erram exatamente 50%, que é o GREEN e o ICA falhando na
    interferência. Um modelo de qualidade treinado só ali aprenderia a
    identificar qual algoritmo rodou, e não se a janela presta.

    A física vem de `fontes/movimento.py`, que modela os quatro mecanismos com
    ruído de banda larga em vez de senoide. As condições daqui são as três
    primeiras hipóteses do projeto.

    **Especular (H1).** A reflexão de superfície tem a cor do iluminante e não a
    da pele, e por isso move a direção cromática em que CHROM e POS se apoiam. A
    varredura de `desvio` é o experimento: com luz neutra os dois **cancelam o
    especular como foram projetados para cancelar**, e o que mede a hipótese é
    onde essa proteção acaba.

    **Câmera em movimento (H2).** O fundo deixa de ser referência válida de
    iluminação, porque o trecho enquadrado muda. Por isso estes cenários ligam
    `com_fundo`, sem o qual a rectificação nem entra em cena.

    **Tom de pele (H3).** Pele mais escura reflete menos, e com ruído de sensor
    fixo isso é perda direta de relação sinal-ruído.

    As últimas condições combinam efeitos de propósito. Hipótese testada uma de
    cada vez diz se o efeito existe; combinada diz se as correções continuam
    valendo com dois problemas juntos, que é o caso real.
    """
    cenarios: list[Cenario] = []
    for bpm in bpms:
        base = dict(bpm=bpm, duracao_s=20.0, fps=30.0, semente=int(bpm))

        def com_especular(desvio: float) -> ParametrosMovimento:
            # Banda ESTREITA em torno de 0,9 Hz, que é movimento rítmico:
            # alguém balançando a cabeça, caminhando ou numa esteira. A escolha
            # é o que separa os dois regimes, e os dois foram medidos.
            #
            # Movimento de banda larga derruba a relação sinal-ruído e o
            # sistema **recusa**, que é a falha benigna. Movimento rítmico cria
            # um pico concorrente limpo dentro da banda cardíaca, e aí o método
            # trava nele e responde com confiança um número errado. É a falha
            # perigosa, e é a que um estudo de abstenção precisa ter.
            return ParametrosMovimento(
                amplitude_px=12.0,
                banda_hz=(0.88, 0.92),
                especular_por_pose=0.5,
                cromaticidade_iluminante=iluminante_desviado(desvio),
            )

        cenarios.extend(
            [
                Cenario(
                    "especular sob luz neutra",
                    ParametrosSimulacao(
                        **base,
                        amplitude_pulso=0.02,
                        ruido_sensor=2.0,
                        movimento=com_especular(0.0),
                        com_fundo=True,
                    ),
                ),
                Cenario(
                    "especular com luz desviada 0,5",
                    ParametrosSimulacao(
                        **base,
                        amplitude_pulso=0.02,
                        ruido_sensor=2.0,
                        movimento=com_especular(0.5),
                        com_fundo=True,
                    ),
                ),
                Cenario(
                    "especular com luz desviada 0,75",
                    ParametrosSimulacao(
                        **base,
                        amplitude_pulso=0.02,
                        ruido_sensor=2.0,
                        movimento=com_especular(0.75),
                        com_fundo=True,
                    ),
                ),
                Cenario(
                    "especular com luz desviada 1,0",
                    ParametrosSimulacao(
                        **base,
                        amplitude_pulso=0.02,
                        ruido_sensor=2.0,
                        movimento=com_especular(1.0),
                        com_fundo=True,
                    ),
                ),
                Cenario(
                    "tremor de luz na banda",
                    ParametrosSimulacao(
                        **base,
                        amplitude_pulso=0.012,
                        ruido_sensor=3.0,
                        amplitude_tremor=0.05,
                        tremor_iluminacao_hz=0.9,
                        com_fundo=True,
                    ),
                ),
                Cenario(
                    "camera movendo",
                    ParametrosSimulacao(
                        **base,
                        amplitude_pulso=0.012,
                        ruido_sensor=3.0,
                        movimento=ParametrosMovimento(
                            camera_px=18.0, camera_banda_hz=(0.5, 3.0)
                        ),
                        amplitude_tremor=0.02,
                        com_fundo=True,
                    ),
                ),
                Cenario(
                    "pele escura com pouca luz",
                    ParametrosSimulacao(
                        **base,
                        amplitude_pulso=0.004,
                        ruido_sensor=5.0,
                        tom_pele=TONS_DE_PELE["escuro"],
                        com_fundo=True,
                    ),
                ),
                Cenario(
                    "pele escura com especular desviado",
                    ParametrosSimulacao(
                        **base,
                        amplitude_pulso=0.006,
                        ruido_sensor=4.0,
                        tom_pele=TONS_DE_PELE["escuro"],
                        movimento=com_especular(0.75),
                        com_fundo=True,
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
