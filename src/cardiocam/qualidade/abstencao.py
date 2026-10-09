"""A curva que é o produto da hipótese H4: erro contra cobertura.

Um medidor que sempre responde e um que nunca responde são igualmente inúteis,
e nenhum dos dois é descrito por um número de erro sozinho. A pergunta correta
não é "qual o erro do sistema", é **"qual o erro, respondendo em que fração dos
casos"**. Essas duas coisas se compram uma com a outra, e a curva é o par.

É a mesma ideia que o PermaneIA aplica ao assistente e o Cautela ao agente: a
recusa é parte do produto, não falha dele. Aqui ela ganha a forma que a área de
medição exige, que é cobertura declarada ao lado do erro.

Dois cuidados que a literatura de seleção com rejeição cobra, e que mudam o
número:

**O limiar tem que ser escolhido fora do dado em que é medido.** Escolher o
limiar que minimiza o erro no mesmo conjunto onde ele é reportado é ajustar ao
ruído e publicar o ajuste. Por isso `escolher_limiar` e `avaliar` são funções
separadas: a primeira roda na partição de calibração, a segunda na de teste.

**Erro médio entre as janelas aceitas não é comparável entre coberturas
diferentes.** Comparar 2 bpm com 40% de cobertura contra 3 bpm com 95% não diz
nada sem o eixo inteiro. Daí a área sob a curva, que resume a troca num número
e permite comparar duas estratégias de rejeição de verdade.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.integrate import trapezoid


@dataclass(frozen=True, slots=True)
class Ponto:
    """Um ponto da curva: o que se paga e o que se ganha."""

    limiar: float
    cobertura: float
    """Fração das janelas em que o sistema respondeu."""
    erro_medio: float
    """Erro absoluto médio entre as aceitas, em bpm."""
    erro_mediano: float
    quantidade: int

    @property
    def recusa(self) -> float:
        return 1.0 - self.cobertura


@dataclass(frozen=True, slots=True)
class CurvaDeAbstencao:
    """A curva inteira, mais o resumo num número."""

    pontos: tuple[Ponto, ...]
    erro_sem_abstencao: float
    """Erro médio respondendo sempre. É a linha de base que a curva precisa
    bater para a abstenção ter valido a pena."""

    @property
    def area_risco_cobertura(self) -> float:
        """Área sob a curva de erro contra cobertura, por trapézios.

        Menor é melhor. Serve para comparar estratégias de rejeição entre si,
        e só isso: o valor absoluto não tem interpretação física, porque mistura
        bpm com fração.
        """
        if len(self.pontos) < 2:
            return float("nan")
        ordenados = sorted(self.pontos, key=lambda p: p.cobertura)
        coberturas = np.array([p.cobertura for p in ordenados])
        erros = np.array([p.erro_medio for p in ordenados])
        valido = np.isfinite(erros)
        if int(np.sum(valido)) < 2:
            return float("nan")
        return float(trapezoid(erros[valido], coberturas[valido]))

    def em_cobertura(self, alvo: float) -> Ponto | None:
        """O ponto de maior cobertura que ainda não passa do alvo.

        Devolve `None` quando nenhum ponto atende, em vez de devolver o mais
        próximo: pedir 80% e receber silenciosamente 30% seria o tipo de
        gentileza que estraga uma conclusão.
        """
        candidatos = [p for p in self.pontos if p.cobertura <= alvo + 1e-9]
        if not candidatos:
            return None
        return max(candidatos, key=lambda p: p.cobertura)

    def tabela(self) -> str:
        """A curva em texto, do jeito que entra no relatório e no pôster."""
        linhas = [
            "| Limiar | Cobertura | Erro médio (bpm) | Erro mediano (bpm) | Janelas |",
            "| ---: | ---: | ---: | ---: | ---: |",
        ]
        for p in self.pontos:
            if p.quantidade == 0:
                continue
            linhas.append(
                f"| {p.limiar:.2f} | {p.cobertura * 100:.1f}% | {p.erro_medio:.2f} | "
                f"{p.erro_mediano:.2f} | {p.quantidade} |"
            )
        linhas.append("")
        linhas.append(
            f"Respondendo sempre: {self.erro_sem_abstencao:.2f} bpm · "
            f"área risco-cobertura {self.area_risco_cobertura:.3f}"
        )
        return "\n".join(linhas)


def construir(
    probabilidades: np.ndarray,
    erros_bpm: np.ndarray,
    limiares: np.ndarray | None = None,
) -> CurvaDeAbstencao:
    """Varre limiares e mede erro e cobertura em cada um.

    `erros_bpm` é o erro absoluto de cada janela contra a referência. Note que
    a probabilidade **não** precisa estar calibrada para a curva fazer sentido,
    porque a varredura só usa a ordenação. A calibração importa para outra
    coisa: escolher o limiar por risco desejado em vez de por cobertura
    desejada, que é o que `escolher_limiar` permite.
    """
    p = np.asarray(probabilidades, dtype=float).ravel()
    erros = np.asarray(erros_bpm, dtype=float).ravel()
    if p.size != erros.size:
        raise ValueError(
            f"São {p.size} probabilidades e {erros.size} erros; precisam casar."
        )
    if p.size == 0:
        raise ValueError("Não dá para construir a curva sem nenhuma janela.")

    if limiares is None:
        limiares = np.round(np.arange(0.0, 1.0, 0.05), 2)

    pontos: list[Ponto] = []
    for limiar in np.asarray(limiares, dtype=float):
        aceitas = p >= limiar
        quantidade = int(np.sum(aceitas))
        if quantidade == 0:
            pontos.append(Ponto(float(limiar), 0.0, float("nan"), float("nan"), 0))
            continue
        selecionados = erros[aceitas]
        pontos.append(
            Ponto(
                limiar=float(limiar),
                cobertura=quantidade / p.size,
                erro_medio=float(np.mean(selecionados)),
                erro_mediano=float(np.median(selecionados)),
                quantidade=quantidade,
            )
        )

    return CurvaDeAbstencao(
        pontos=tuple(pontos),
        erro_sem_abstencao=float(np.mean(erros)),
    )


def escolher_limiar(
    probabilidades: np.ndarray,
    erros_bpm: np.ndarray,
    cobertura_minima: float,
    erro_alvo_bpm: float,
) -> float | None:
    """O menor limiar que atinge o erro alvo sem cair abaixo da cobertura.

    Roda na partição de **calibração**, nunca na de teste. A ordem das duas
    exigências é deliberada: entre dois limiares que atingem o erro, vence o
    que recusa menos, porque recusar é um custo real para quem está medindo.

    Devolve `None` quando nenhum limiar atende às duas coisas ao mesmo tempo.
    Esse `None` é informação de primeira ordem, e não um caso de borda: quer
    dizer que, naquele cenário, o erro alvo só é alcançável recusando mais do
    que se está disposto a recusar. Num relatório, isso é um achado.
    """
    if not 0.0 <= cobertura_minima <= 1.0:
        raise ValueError("A cobertura mínima precisa estar entre 0 e 1.")
    if erro_alvo_bpm <= 0:
        raise ValueError("O erro alvo precisa ser positivo.")

    curva = construir(probabilidades, erros_bpm)
    atendem = [
        p
        for p in curva.pontos
        if p.quantidade > 0
        and p.cobertura >= cobertura_minima
        and p.erro_medio <= erro_alvo_bpm
    ]
    if not atendem:
        return None
    return min(atendem, key=lambda p: p.limiar).limiar


def avaliar(
    probabilidades: np.ndarray,
    erros_bpm: np.ndarray,
    limiar: float,
) -> Ponto:
    """Aplica um limiar já escolhido e relata o que ele produz.

    É a função que roda na partição de teste. Separada de `escolher_limiar` de
    propósito: é essa separação que impede reportar um número que foi
    otimizado no mesmo dado em que é medido.
    """
    p = np.asarray(probabilidades, dtype=float).ravel()
    erros = np.asarray(erros_bpm, dtype=float).ravel()
    curva = construir(p, erros, limiares=np.array([limiar]))
    return curva.pontos[0]
