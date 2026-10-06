"""Mede se a probabilidade prevista quer dizer o que diz querer dizer.

Um modelo pode separar bem e mentir no número. Se entre as janelas a que ele
atribuiu 0,9 apenas 60% de fato acertaram, o 0,9 não é uma probabilidade, é uma
ordenação disfarçada de probabilidade. Para ranquear, tanto faz. Para **decidir
recusar**, não: o limiar de abstenção é escolhido em cima desse número, e um
número descalibrado produz uma taxa de recusa que não corresponde a risco
nenhum.

Daí este módulo existir separado do modelo. Discriminação e calibração são
qualidades diferentes e podem andar em direções opostas, e medir só a primeira
é o engano mais comum em classificação probabilística.

As três medidas aqui são complementares:

- **Brier** é o erro quadrático médio da probabilidade. Mede discriminação e
  calibração juntas, num número só.
- **ECE** isola a calibração: agrupa as previsões em faixas e compara, em cada
  faixa, a probabilidade média prevista com a frequência observada.
- O **diagrama de confiabilidade** é o ECE antes de virar média, e é o que
  mostra *onde* o modelo erra: excesso de confiança costuma aparecer só na
  ponta alta.

Uma ressalva que o próprio ECE obriga: ele depende do número de faixas, e com
poucas amostras por faixa o ruído amostral vira viés. Por isso `faixas`
aparece na assinatura em vez de ficar escondido, e por isso cada faixa devolve
sua contagem.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

FAIXAS_PADRAO = 10


@dataclass(frozen=True, slots=True)
class Faixa:
    """Uma faixa do diagrama de confiabilidade."""

    inicio: float
    fim: float
    quantidade: int
    probabilidade_media: float
    """Média das probabilidades previstas dentro da faixa."""
    frequencia_observada: float
    """Fração de acertos de fato observada dentro da faixa."""

    @property
    def desvio(self) -> float:
        """Quanto o modelo errou nesta faixa. Positivo é excesso de confiança."""
        return self.probabilidade_media - self.frequencia_observada


@dataclass(frozen=True, slots=True)
class Calibracao:
    """Resultado completo da aferição."""

    brier: float
    ece: float
    faixas: tuple[Faixa, ...]
    quantidade: int

    @property
    def maior_desvio(self) -> float:
        """O pior erro de calibração entre as faixas povoadas.

        O ECE é uma média ponderada e pode esconder uma faixa muito ruim com
        poucas amostras. Quando a decisão de recusa vive justamente na ponta
        alta, essa faixa é a que importa.
        """
        povoadas = [f for f in self.faixas if f.quantidade > 0]
        if not povoadas:
            return float("nan")
        return max(abs(f.desvio) for f in povoadas)

    def tabela(self) -> str:
        """Diagrama de confiabilidade em texto, para relatório e para o CIC."""
        linhas = [
            "| Faixa | Janelas | Prevista | Observada | Desvio |",
            "| --- | ---: | ---: | ---: | ---: |",
        ]
        for f in self.faixas:
            if f.quantidade == 0:
                continue
            linhas.append(
                f"| {f.inicio:.1f} a {f.fim:.1f} | {f.quantidade} | "
                f"{f.probabilidade_media:.3f} | {f.frequencia_observada:.3f} | "
                f"{f.desvio:+.3f} |"
            )
        linhas.append("")
        linhas.append(
            f"Brier {self.brier:.4f} · ECE {self.ece:.4f} · "
            f"maior desvio {self.maior_desvio:.4f} · {self.quantidade} janelas"
        )
        return "\n".join(linhas)


def brier(probabilidades: np.ndarray, rotulos: np.ndarray) -> float:
    """Erro quadrático médio da probabilidade.

    Prever 0,5 em tudo dá 0,25. Qualquer coisa acima disso é pior que não
    tentar, o que o torna uma referência útil para ler o número.
    """
    p = np.asarray(probabilidades, dtype=float).ravel()
    y = np.asarray(rotulos, dtype=float).ravel()
    _conferir(p, y)
    return float(np.mean((p - y) ** 2))


def aferir(
    probabilidades: np.ndarray,
    rotulos: np.ndarray,
    faixas: int = FAIXAS_PADRAO,
) -> Calibracao:
    """Diagrama de confiabilidade, ECE e Brier de uma vez."""
    p = np.asarray(probabilidades, dtype=float).ravel()
    y = np.asarray(rotulos, dtype=float).ravel()
    _conferir(p, y)
    if faixas < 1:
        raise ValueError("Precisa de ao menos uma faixa.")

    bordas = np.linspace(0.0, 1.0, faixas + 1)
    # O lado direito é fechado para que a probabilidade 1,0 caia na última
    # faixa em vez de cair fora. Sem isso, o caso mais confiante some do
    # diagrama, que é justamente o que não se pode perder aqui.
    indices = np.clip(np.digitize(p, bordas[1:-1], right=False), 0, faixas - 1)

    construidas: list[Faixa] = []
    erro_total = 0.0
    for i in range(faixas):
        dentro = indices == i
        quantidade = int(np.sum(dentro))
        if quantidade == 0:
            construidas.append(Faixa(bordas[i], bordas[i + 1], 0, float("nan"), float("nan")))
            continue
        media = float(np.mean(p[dentro]))
        observada = float(np.mean(y[dentro]))
        erro_total += quantidade * abs(media - observada)
        construidas.append(
            Faixa(bordas[i], bordas[i + 1], quantidade, media, observada)
        )

    return Calibracao(
        brier=brier(p, y),
        ece=float(erro_total / p.size),
        faixas=tuple(construidas),
        quantidade=int(p.size),
    )


def _conferir(p: np.ndarray, y: np.ndarray) -> None:
    if p.size != y.size:
        raise ValueError(
            f"São {p.size} probabilidades e {y.size} rótulos; precisam casar."
        )
    if p.size == 0:
        raise ValueError("Não dá para aferir calibração sem nenhuma previsão.")
    if np.any(p < 0.0) or np.any(p > 1.0):
        raise ValueError("Probabilidade fora de [0, 1].")
    if not np.all((y == 0.0) | (y == 1.0)):
        raise ValueError("Os rótulos precisam ser 0 ou 1.")


@dataclass(frozen=True, slots=True)
class Temperatura:
    """Reescala os logitos por uma constante, para corrigir confiança.

    É a correção de calibração mais simples que existe e, para este caso, a
    certa. Ela divide o logito por um escalar aprendido: temperatura maior que
    1 achata as probabilidades em direção a 0,5, menor que 1 as afasta.

    Três propriedades a tornam preferível à regressão isotônica aqui:

    - **não muda a ordenação**, porque é monótona. A curva de erro contra
      cobertura fica idêntica, e só o eixo do limiar é reinterpretado. Quem
      escolheu um ponto de operação não precisa reescolher;
    - tem **um parâmetro só**, e por isso cabe numa partição de calibração
      pequena. Isotônica com algumas dezenas de pontos decora;
    - é reversível e auditável: o número aparece no relatório.

    A limitação, que é real: temperatura corrige confiança **global**. Se o
    modelo for confiante demais numa faixa e de menos em outra, ela não
    resolve, e o diagrama de confiabilidade continua sendo o juiz.

    Referência: Guo et al., *On Calibration of Modern Neural Networks*, 2017.
    """

    valor: float

    def aplicar(self, probabilidades: np.ndarray) -> np.ndarray:
        """Reescala probabilidades já prontas, passando pelo logito e voltando."""
        p = np.clip(np.asarray(probabilidades, dtype=float), 1e-12, 1 - 1e-12)
        logitos = np.log(p / (1.0 - p))
        return 1.0 / (1.0 + np.exp(-logitos / self.valor))

    @classmethod
    def ajustar(
        cls,
        probabilidades: np.ndarray,
        rotulos: np.ndarray,
        candidatas: np.ndarray | None = None,
    ) -> "Temperatura":
        """Escolhe a temperatura que minimiza a log-perda.

        Busca em grade, e não por otimização: o problema é unidimensional e
        suave, a grade é reprodutível sem depender de inicialização, e o custo é
        irrelevante. Otimizador aqui seria mais código para o mesmo resultado.

        Minimiza log-perda e não ECE de propósito. ECE depende do número de
        faixas e é uma função escada do parâmetro, cheia de mínimos locais
        falsos; log-perda é suave e é uma regra de pontuação própria, isto é,
        só é minimizada pela probabilidade verdadeira.
        """
        p = np.asarray(probabilidades, dtype=float).ravel()
        y = np.asarray(rotulos, dtype=float).ravel()
        _conferir(p, y)
        if candidatas is None:
            # Geométrica em vez de linear: o efeito de 0,5 para 1,0 é o mesmo
            # que o de 1,0 para 2,0, e uma grade linear gastaria resolução no
            # lado errado.
            candidatas = np.exp(np.linspace(np.log(0.2), np.log(10.0), 200))

        melhor, menor_perda = 1.0, float("inf")
        for t in np.asarray(candidatas, dtype=float):
            if t <= 0:
                continue
            ajustada = np.clip(cls(float(t)).aplicar(p), 1e-12, 1 - 1e-12)
            perda = -float(
                np.mean(y * np.log(ajustada) + (1.0 - y) * np.log(1.0 - ajustada))
            )
            if perda < menor_perda:
                melhor, menor_perda = float(t), perda
        return cls(melhor)
