"""Testes do núcleo bayesiano.

A estratégia é a mesma do resto do projeto: gerar dado cuja verdade nós
escolhemos e conferir que o código a recupera. Aqui a verdade é um vetor de
pesos; o teste gera rótulos a partir dele e cobra que o ajuste chegue perto.

Dois testes merecem destaque porque cobram a propriedade que justifica usar
modelo bayesiano em vez de classificador comum: o encolhimento da probabilidade
longe do treino, e a recusa a divergir com dado linearmente separável.
"""

from __future__ import annotations

import numpy as np
import pytest

from cardiocam.qualidade.bayes import (
    VARIANCIA_PRIORI_PADRAO,
    RegressaoLogisticaBayesiana,
    ajustar,
    sigmoide,
)

NOMES = ("a", "b")


def _dado_sintetico(
    n: int = 600, pesos_verdadeiros: tuple[float, float, float] = (0.5, 2.0, -1.5)
) -> tuple[np.ndarray, np.ndarray]:
    gerador = np.random.default_rng(42)
    matriz = gerador.normal(0.0, 1.0, (n, 2))
    logitos = (
        pesos_verdadeiros[0]
        + pesos_verdadeiros[1] * matriz[:, 0]
        + pesos_verdadeiros[2] * matriz[:, 1]
    )
    rotulos = (gerador.uniform(0.0, 1.0, n) < sigmoide(logitos)).astype(float)
    return matriz, rotulos


class TestSigmoide:
    def test_nao_transborda_nos_extremos(self):
        extremos = np.array([-1000.0, -50.0, 0.0, 50.0, 1000.0])
        saida = sigmoide(extremos)
        assert np.all(np.isfinite(saida))
        assert np.all((saida >= 0.0) & (saida <= 1.0))

    def test_vale_meio_na_origem(self):
        assert sigmoide(np.array([0.0]))[0] == pytest.approx(0.5)

    def test_e_simetrica(self):
        x = np.array([0.3, 1.7, 4.0])
        assert sigmoide(x) + sigmoide(-x) == pytest.approx(np.ones_like(x))


class TestAjuste:
    def test_recupera_os_pesos_que_geraram_o_dado(self):
        matriz, rotulos = _dado_sintetico()
        modelo = ajustar(matriz, rotulos, NOMES)
        # Tolerância larga de propósito: com 600 amostras o erro padrão do
        # estimador já é da ordem de 0,1, e exigir mais seria cobrar do teste
        # uma precisão que o dado não tem.
        assert modelo.pesos["a"] == pytest.approx(2.0, abs=0.35)
        assert modelo.pesos["b"] == pytest.approx(-1.5, abs=0.35)

    def test_a_priori_puxa_para_zero_com_pouco_dado(self):
        """Com 12 amostras a priori domina, e é isso que se quer.

        O peso ajustado tem que ficar entre zero e o valor verdadeiro, nunca
        além dele. Ultrapassar seria sinal de que a regularização não está
        agindo, que é exatamente o caminho para o ajuste divergir.
        """
        matriz, rotulos = _dado_sintetico(n=12)
        modelo = ajustar(matriz, rotulos, NOMES)
        assert abs(modelo.pesos["a"]) < 2.0

    def test_nao_diverge_com_dado_separavel(self):
        """Separação perfeita manda a logística sem priori para o infinito.

        É o modo de falha clássico, e o motivo de a priori ser própria e não
        uma formalidade. O caso aparece de verdade aqui: cenário sintético fácil
        produz janelas em que toda estimativa acerta.
        """
        matriz = np.array([[-3.0, 0.0], [-2.0, 0.0], [2.0, 0.0], [3.0, 0.0]])
        rotulos = np.array([0.0, 0.0, 1.0, 1.0])
        modelo = ajustar(matriz, rotulos, NOMES)
        assert np.all(np.isfinite(modelo.media))
        assert abs(modelo.pesos["a"]) < 50.0

    def test_covariancia_e_simetrica_e_positiva_na_diagonal(self):
        matriz, rotulos = _dado_sintetico()
        modelo = ajustar(matriz, rotulos, NOMES)
        assert np.allclose(modelo.covariancia, modelo.covariancia.T)
        assert np.all(np.diag(modelo.covariancia) > 0)

    def test_rejeita_rotulo_que_nao_e_binario(self):
        matriz, _ = _dado_sintetico(n=20)
        with pytest.raises(ValueError, match="0 ou 1"):
            ajustar(matriz, np.full(20, 0.5), NOMES)

    def test_rejeita_contagem_que_nao_casa(self):
        matriz, _ = _dado_sintetico(n=20)
        with pytest.raises(ValueError, match="casar"):
            ajustar(matriz, np.ones(19), NOMES)

    def test_rejeita_priori_nao_positiva(self):
        matriz, rotulos = _dado_sintetico(n=20)
        with pytest.raises(ValueError, match="positiva"):
            ajustar(matriz, rotulos, NOMES, variancia_priori=0.0)


class TestIncerteza:
    def test_a_probabilidade_encolhe_longe_do_treino(self):
        """A propriedade que justifica o modelo inteiro.

        Dois pontos com o mesmo logito médio: um dentro da nuvem de treino,
        outro muito fora. O classificador comum devolveria o mesmo número nos
        dois. O bayesiano devolve algo mais perto de 0,5 no ponto distante,
        porque lá a posteriori é larga.
        """
        matriz, rotulos = _dado_sintetico()
        modelo = ajustar(matriz, rotulos, NOMES)

        perto = np.array([[1.0, 0.0]])
        # Mesma direção, bem mais longe: logito médio proporcionalmente maior,
        # e variância muito maior.
        longe = np.array([[60.0, 0.0]])

        previsao_perto = modelo.prever_uma(perto[0])
        previsao_longe = modelo.prever_uma(longe[0])

        assert previsao_longe.desvio_do_logito > previsao_perto.desvio_do_logito
        # O efeito do encolhimento: a preditiva marginalizada fica mais perto de
        # 0,5 do que a do ponto, no caso distante.
        distancia_marginal = abs(previsao_longe.probabilidade - 0.5)
        distancia_do_ponto = abs(previsao_longe.probabilidade_do_ponto - 0.5)
        assert distancia_marginal < distancia_do_ponto

    def test_a_preditiva_fica_entre_meio_e_a_do_ponto(self):
        """Marginalizar nunca empurra para longe de 0,5, só para perto.

        Vale nos dois sentidos, e é a assinatura da aproximação probit: o
        denominador é sempre maior ou igual a 1.
        """
        matriz, rotulos = _dado_sintetico()
        modelo = ajustar(matriz, rotulos, NOMES)
        for ponto in ([0.5, 0.5], [2.0, -1.0], [-4.0, 3.0], [10.0, 10.0]):
            previsao = modelo.prever_uma(np.array(ponto))
            assert abs(previsao.probabilidade - 0.5) <= abs(
                previsao.probabilidade_do_ponto - 0.5
            ) + 1e-12

    def test_priori_mais_estreita_da_menos_incerteza(self):
        matriz, rotulos = _dado_sintetico(n=40)
        larga = ajustar(matriz, rotulos, NOMES, variancia_priori=100.0)
        estreita = ajustar(matriz, rotulos, NOMES, variancia_priori=0.01)
        ponto = np.array([3.0, -2.0])
        assert (
            estreita.prever_uma(ponto).desvio_do_logito
            < larga.prever_uma(ponto).desvio_do_logito
        )

    def test_desvio_dos_pesos_acompanha_o_tamanho_do_dado(self):
        pouco = ajustar(*_dado_sintetico(n=30), NOMES)
        muito = ajustar(*_dado_sintetico(n=3000), NOMES)
        assert muito.desvios_dos_pesos["a"] < pouco.desvios_dos_pesos["a"]


class TestFormato:
    def test_prever_devolve_uma_probabilidade_por_linha(self):
        matriz, rotulos = _dado_sintetico(n=50)
        modelo = ajustar(matriz, rotulos, NOMES)
        saida = modelo.prever(matriz)
        assert saida.shape == (50,)
        assert np.all((saida >= 0.0) & (saida <= 1.0))

    def test_rejeita_media_com_tamanho_errado(self):
        with pytest.raises(ValueError, match="intercepto"):
            RegressaoLogisticaBayesiana(
                media=np.zeros(2),
                covariancia=np.eye(3),
                nomes=NOMES,
                variancia_priori=VARIANCIA_PRIORI_PADRAO,
            )

    def test_rejeita_covariancia_com_tamanho_errado(self):
        with pytest.raises(ValueError, match="covariância"):
            RegressaoLogisticaBayesiana(
                media=np.zeros(3),
                covariancia=np.eye(2),
                nomes=NOMES,
                variancia_priori=VARIANCIA_PRIORI_PADRAO,
            )

    def test_rejeita_matriz_de_uma_dimensao(self):
        matriz, rotulos = _dado_sintetico(n=20)
        modelo = ajustar(matriz, rotulos, NOMES)
        with pytest.raises(ValueError, match="bidimensional"):
            modelo.prever(np.zeros(2))
