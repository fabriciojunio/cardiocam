"""Regressão logística bayesiana por aproximação de Laplace.

Existe para responder uma pergunta que a estimativa de frequência sozinha não
responde: **dá para confiar nesta janela?**

A escolha de um modelo bayesiano em vez de um classificador comum não é
preciosismo. Um classificador devolve um número entre 0 e 1 e não distingue
dois casos muito diferentes:

- "vi muitas janelas parecidas com esta, e 70% delas acertaram";
- "nunca vi nada parecido com esta, e meu chute é 70%".

O primeiro é informação, o segundo é ignorância disfarçada de informação. Num
sistema que vai **recusar medir** com base nesse número, confundir os dois é o
erro mais caro possível: a recusa passa a ser arbitrária justamente onde ela
mais importa, que é na região onde o modelo não tem experiência.

A posteriori sobre os pesos separa os dois casos, e a probabilidade preditiva
marginalizada é puxada em direção a 0,5 quando a entrada cai longe do que foi
visto no treino. É esse encolhimento que faz a abstenção ser honesta.

## Por que Laplace, e não amostragem

A posteriori da regressão logística não tem forma fechada. Há três caminhos:
Monte Carlo via cadeia de Markov, inferência variacional e aproximação de
Laplace. Para este problema a Laplace é a escolha certa por três motivos:

1. O modelo é **côncavo** com priori gaussiana, então existe um único máximo e
   o ponto em torno do qual se aproxima não depende de inicialização;
2. a dimensão é pequena, uma dezena de características, que é exatamente o
   regime em que a gaussiana em torno do máximo é uma boa aproximação;
3. não acrescenta dependência nenhuma ao projeto, e cabe em código que dá para
   ler inteiro.

A limitação honesta: Laplace é uma aproximação **local**. Ela descreve bem a
massa em torno do máximo e descreve mal uma posteriori assimétrica ou com mais
de um modo. Com priori gaussiana e verossimilhança logística isso não acontece,
mas vale saber que a garantia vem da concavidade, e não da aproximação em si.

Referência: Bishop, *Pattern Recognition and Machine Learning*, seção 4.5;
MacKay (1992) para a aproximação probit da preditiva.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

# Variância da priori sobre cada peso. Equivale a dizer que um peso de módulo
# maior que 3 é implausível antes de ver dado: com característica padronizada,
# peso 3 já leva a probabilidade de 0,5 para 0,95 com um desvio padrão de
# variação. Priori larga demais devolve o modelo sem regularização nenhuma e
# separa perfeitamente dado linearmente separável, mandando os pesos para o
# infinito; é o modo de falha clássico da logística sem priori.
VARIANCIA_PRIORI_PADRAO = 4.0

# Critérios do ajuste. O método é Newton, que em regressão logística converge
# em poucas iteracoes porque a função é côncava.
MAXIMO_DE_ITERACOES = 200
TOLERANCIA = 1e-8

# Piso da variância preditiva: evita divisão por zero quando a posteriori é
# degenerada por ter visto uma única classe.
VARIANCIA_MINIMA = 1e-12


def sigmoide(x: np.ndarray) -> np.ndarray:
    """Sigmoide estável nos dois extremos.

    `1 / (1 + exp(-x))` transborda para x muito negativo. A forma por ramos
    evita isso sem mudar o resultado.
    """
    saida = np.empty_like(x, dtype=float)
    positivo = x >= 0
    saida[positivo] = 1.0 / (1.0 + np.exp(-x[positivo]))
    exponencial = np.exp(x[~positivo])
    saida[~positivo] = exponencial / (1.0 + exponencial)
    return saida


@dataclass(frozen=True, slots=True)
class Previsao:
    """Probabilidade prevista, com a incerteza que a acompanha."""

    probabilidade: float
    """Probabilidade preditiva, já marginalizada sobre a posteriori dos pesos."""

    desvio_do_logito: float
    """Desvio padrão da posteriori na escala do logito.

    É a medida de ignorância do modelo naquele ponto: cresce quando a entrada
    cai longe do que o treino cobriu. Zero significaria certeza absoluta sobre
    o peso, que nunca acontece com priori própria.
    """

    @property
    def probabilidade_do_ponto(self) -> float:
        """Probabilidade pelo peso médio, sem marginalizar.

        Guardada só para comparação: é o que um classificador comum devolveria.
        A diferença entre ela e `probabilidade` é o efeito da incerteza.
        """
        return float(sigmoide(np.array([self._logito_medio]))[0])

    _logito_medio: float = 0.0


@dataclass(frozen=True, slots=True)
class RegressaoLogisticaBayesiana:
    """Modelo ajustado: média e covariância da posteriori sobre os pesos."""

    media: np.ndarray
    """Modo da posteriori, de tamanho n_caracteristicas + 1 (o primeiro é o
    intercepto)."""

    covariancia: np.ndarray
    """Inversa da hessiana no modo. É a aproximação de Laplace."""

    nomes: tuple[str, ...]
    """Nome de cada característica, na ordem dos pesos sem o intercepto."""

    variancia_priori: float = VARIANCIA_PRIORI_PADRAO

    def __post_init__(self) -> None:
        esperado = len(self.nomes) + 1
        if self.media.shape != (esperado,):
            raise ValueError(
                f"A média tem {self.media.shape} e deveria ter ({esperado},): "
                f"um peso por característica mais o intercepto."
            )
        if self.covariancia.shape != (esperado, esperado):
            raise ValueError(
                f"A covariância tem {self.covariancia.shape} e deveria ser "
                f"({esperado}, {esperado})."
            )

    def logitos(self, matriz: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Média e variância do logito, por linha da matriz de entrada.

        A variância do logito é `x' S x`, que é a propagação exata da
        covariância dos pesos por uma função linear. Só a passagem pela
        sigmoide depois é que precisa de aproximação.
        """
        projetada = _com_intercepto(matriz)
        media = projetada @ self.media
        # einsum em vez de diag(X S X'): a matriz completa é n x n e só a
        # diagonal interessa. Com 10 mil janelas isso é a diferença entre
        # 800 MB e 80 KB.
        variancia = np.einsum("ij,jk,ik->i", projetada, self.covariancia, projetada)
        return media, np.maximum(variancia, VARIANCIA_MINIMA)

    def prever(self, matriz: np.ndarray) -> np.ndarray:
        """Probabilidade preditiva marginalizada, uma por linha.

        Usa a aproximação probit de MacKay para a integral da sigmoide contra
        uma gaussiana, que não tem forma fechada. O fator `pi/8` é o que casa a
        inclinação da probit com a da sigmoide na origem; o erro máximo da
        aproximação fica abaixo de 0,01 em probabilidade.

        O efeito prático é o que justifica o modelo inteiro: onde a variância é
        grande, o denominador cresce e a probabilidade é empurrada para 0,5.
        Longe do que foi visto, o modelo responde "não sei" em vez de responder
        com confiança herdada de outra região do espaço.
        """
        media, variancia = self.logitos(matriz)
        atenuacao = np.sqrt(1.0 + (np.pi / 8.0) * variancia)
        return sigmoide(media / atenuacao)

    def prever_uma(self, caracteristicas: np.ndarray) -> Previsao:
        """Previsão de uma única janela, com a incerteza explicitada."""
        linha = np.asarray(caracteristicas, dtype=float).reshape(1, -1)
        media, variancia = self.logitos(linha)
        probabilidade = float(self.prever(linha)[0])
        return Previsao(
            probabilidade=probabilidade,
            desvio_do_logito=float(np.sqrt(variancia[0])),
            _logito_medio=float(media[0]),
        )

    @property
    def pesos(self) -> dict[str, float]:
        """Peso de cada característica, sem o intercepto, para leitura humana."""
        return dict(zip(self.nomes, self.media[1:].tolist(), strict=True))

    @property
    def desvios_dos_pesos(self) -> dict[str, float]:
        """Desvio padrão de cada peso.

        Peso cujo módulo é menor que o próprio desvio não está sustentado pelo
        dado, e dizer isso é mais útil do que exibir o número sozinho.
        """
        desvios = np.sqrt(np.diag(self.covariancia))[1:]
        return dict(zip(self.nomes, desvios.tolist(), strict=True))


def _com_intercepto(matriz: np.ndarray) -> np.ndarray:
    matriz = np.asarray(matriz, dtype=float)
    if matriz.ndim != 2:
        raise ValueError(
            f"A matriz de características precisa ser bidimensional, "
            f"e veio com {matriz.ndim} dimensão(ões)."
        )
    return np.hstack([np.ones((matriz.shape[0], 1)), matriz])


def ajustar(
    matriz: np.ndarray,
    rotulos: np.ndarray,
    nomes: tuple[str, ...],
    variancia_priori: float = VARIANCIA_PRIORI_PADRAO,
) -> RegressaoLogisticaBayesiana:
    """Ajusta o modelo por Newton e devolve a posteriori aproximada.

    O rótulo é binário: 1 quando a janela foi aceitável, 0 quando não foi. Quem
    define "aceitável" é quem chama, e essa separação é proposital — o critério
    de aceitação é uma decisão de domínio, não de estatística.

    A hessiana da log-posteriori é `X' R X + S0^-1`, com R diagonal de
    `p(1-p)`. Ela é definida positiva por causa da priori, mesmo quando o dado
    é linearmente separável e a verossimilhança sozinha seria degenerada. É por
    isso que o ajuste não diverge nesse caso, que é comum aqui: cenário
    sintético fácil gera janela em que toda estimativa acerta.
    """
    projetada = _com_intercepto(matriz)
    alvo = np.asarray(rotulos, dtype=float).ravel()
    if alvo.size != projetada.shape[0]:
        raise ValueError(
            f"São {projetada.shape[0]} linhas de característica e {alvo.size} "
            f"rótulos. Os dois precisam casar."
        )
    if not np.all((alvo == 0.0) | (alvo == 1.0)):
        raise ValueError("Os rótulos precisam ser 0 ou 1.")
    if variancia_priori <= 0:
        raise ValueError("A variância da priori precisa ser positiva.")

    n_pesos = projetada.shape[1]
    precisao_priori = np.eye(n_pesos) / variancia_priori
    pesos = np.zeros(n_pesos)

    for _ in range(MAXIMO_DE_ITERACOES):
        probabilidades = sigmoide(projetada @ pesos)
        gradiente = projetada.T @ (alvo - probabilidades) - precisao_priori @ pesos
        variancias = np.clip(probabilidades * (1.0 - probabilidades), 1e-10, None)
        hessiana = (projetada.T * variancias) @ projetada + precisao_priori
        # solve em vez de inv: numericamente melhor, e a inversa só é calculada
        # uma vez no fim, quando ela de fato é o produto desejado.
        passo = np.linalg.solve(hessiana, gradiente)
        pesos = pesos + passo
        if float(np.max(np.abs(passo))) < TOLERANCIA:
            break

    probabilidades = sigmoide(projetada @ pesos)
    variancias = np.clip(probabilidades * (1.0 - probabilidades), 1e-10, None)
    hessiana = (projetada.T * variancias) @ projetada + precisao_priori
    covariancia = np.linalg.inv(hessiana)
    # Simetriza: a inversa numérica sai assimétrica na última casa, e isso
    # propaga para variâncias levemente negativas no einsum.
    covariancia = 0.5 * (covariancia + covariancia.T)

    return RegressaoLogisticaBayesiana(
        media=pesos,
        covariancia=covariancia,
        nomes=tuple(nomes),
        variancia_priori=variancia_priori,
    )
