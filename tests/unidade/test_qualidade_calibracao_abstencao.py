"""Testes da aferição de calibração e da curva de abstenção.

O desenho dos testes segue o mesmo princípio do resto: construir um caso em que
a resposta certa é conhecida por argumento, e não por execução anterior do
código. Um previsor perfeitamente calibrado por construção tem ECE zero; um
descalibrado por uma constante conhecida tem ECE igual a essa constante. São
esses os dois âncoras.
"""

from __future__ import annotations

import numpy as np
import pytest

from cardiocam.qualidade.abstencao import (
    avaliar,
    construir,
    escolher_limiar,
)
from cardiocam.qualidade.calibracao import aferir, brier


class TestBrier:
    def test_previsao_perfeita_da_zero(self):
        assert brier(np.array([1.0, 0.0, 1.0]), np.array([1.0, 0.0, 1.0])) == 0.0

    def test_previsao_invertida_da_um(self):
        assert brier(np.array([1.0, 0.0]), np.array([0.0, 1.0])) == 1.0

    def test_chute_de_meio_da_um_quarto(self):
        """0,25 é a referência que dá sentido ao número.

        Qualquer modelo acima disso é pior do que não ter modelo nenhum.
        """
        assert brier(np.full(100, 0.5), np.zeros(100)) == pytest.approx(0.25)


class TestCalibracao:
    def test_previsor_calibrado_por_construcao_tem_ece_quase_zero(self):
        """Gera rótulos a partir das próprias probabilidades previstas.

        Por construção a frequência observada em cada faixa converge para a
        probabilidade média da faixa. O que sobra de ECE é ruído amostral, e
        cai com o número de amostras: é por isso que são 20 mil.
        """
        gerador = np.random.default_rng(7)
        probabilidades = gerador.uniform(0.0, 1.0, 20_000)
        rotulos = (gerador.uniform(0.0, 1.0, 20_000) < probabilidades).astype(float)
        resultado = aferir(probabilidades, rotulos)
        assert resultado.ece < 0.02

    def test_excesso_de_confianca_aparece_com_o_tamanho_certo(self):
        """Previsor que afirma 0,9 e acerta 0,6 tem ECE de 0,3."""
        probabilidades = np.full(1000, 0.9)
        rotulos = np.zeros(1000)
        rotulos[:600] = 1.0
        resultado = aferir(probabilidades, rotulos)
        assert resultado.ece == pytest.approx(0.3, abs=1e-9)
        assert resultado.maior_desvio == pytest.approx(0.3, abs=1e-9)

    def test_desvio_positivo_e_excesso_de_confianca(self):
        resultado = aferir(np.full(100, 0.9), np.concatenate([np.ones(60), np.zeros(40)]))
        povoadas = [f for f in resultado.faixas if f.quantidade > 0]
        assert len(povoadas) == 1
        assert povoadas[0].desvio > 0

    def test_probabilidade_um_cai_na_ultima_faixa(self):
        """O caso mais confiante não pode sumir do diagrama.

        `digitize` sem cuidado joga 1,0 para fora do último intervalo, e some
        justamente a faixa onde a decisão de recusa vive.
        """
        resultado = aferir(np.array([1.0, 1.0]), np.array([1.0, 0.0]), faixas=10)
        assert resultado.faixas[-1].quantidade == 2

    def test_a_tabela_sai_sem_faixa_vazia(self):
        resultado = aferir(np.array([0.95, 0.96]), np.array([1.0, 1.0]))
        texto = resultado.tabela()
        assert "ECE" in texto
        # Nove faixas estão vazias e nenhuma delas deve aparecer.
        assert texto.count("\n|") == 2

    def test_rejeita_probabilidade_fora_do_intervalo(self):
        with pytest.raises(ValueError, match=r"\[0, 1\]"):
            aferir(np.array([1.5]), np.array([1.0]))

    def test_rejeita_conjunto_vazio(self):
        with pytest.raises(ValueError, match="sem nenhuma"):
            aferir(np.array([]), np.array([]))

    def test_rejeita_zero_faixas(self):
        with pytest.raises(ValueError, match="ao menos uma faixa"):
            aferir(np.array([0.5]), np.array([1.0]), faixas=0)


class TestCurvaDeAbstencao:
    @staticmethod
    def _caso_ideal() -> tuple[np.ndarray, np.ndarray]:
        """Probabilidade que ordena perfeitamente pelo erro.

        Erro cresce de 0 a 19 bpm; a probabilidade decresce junto. É o caso em
        que a abstenção funciona como deveria, e serve de limite superior.
        """
        erros = np.arange(20, dtype=float)
        probabilidades = 1.0 - erros / 20.0
        return probabilidades, erros

    def test_cobertura_cai_quando_o_limiar_sobe(self):
        probabilidades, erros = self._caso_ideal()
        curva = construir(probabilidades, erros)
        coberturas = [p.cobertura for p in curva.pontos]
        assert coberturas == sorted(coberturas, reverse=True)

    def test_erro_cai_quando_o_limiar_sobe(self):
        """Os pontos saem em ordem crescente de limiar, então o erro decresce.

        A primeira versão deste teste cobrava ordem crescente do erro e
        reprovou. A expectativa é que estava errada: limiar maior aceita menos
        janelas, e no caso ideal as que sobram são as de erro menor.
        """
        probabilidades, erros = self._caso_ideal()
        curva = construir(probabilidades, erros)
        erros_medios = [p.erro_medio for p in curva.pontos if p.quantidade > 0]
        assert erros_medios == sorted(erros_medios, reverse=True)

    def test_limiar_zero_responde_sempre(self):
        probabilidades, erros = self._caso_ideal()
        ponto = avaliar(probabilidades, erros, 0.0)
        assert ponto.cobertura == 1.0
        assert ponto.erro_medio == pytest.approx(float(np.mean(erros)))

    def test_probabilidade_sem_relacao_com_erro_nao_melhora_nada(self):
        """O controle que impede ler ganho onde não há.

        Com probabilidade aleatória, recusar não reduz o erro esperado. Se este
        teste passasse a mostrar ganho, seria sinal de defeito na curva, e não
        de um achado.
        """
        gerador = np.random.default_rng(3)
        erros = gerador.uniform(0.0, 20.0, 4000)
        probabilidades = gerador.uniform(0.0, 1.0, 4000)
        curva = construir(probabilidades, erros)
        meio = curva.em_cobertura(0.5)
        assert meio is not None
        assert meio.erro_medio == pytest.approx(curva.erro_sem_abstencao, abs=0.8)

    def test_em_cobertura_nunca_devolve_acima_do_alvo(self):
        probabilidades, erros = self._caso_ideal()
        curva = construir(probabilidades, erros)
        ponto = curva.em_cobertura(0.4)
        assert ponto is not None
        assert ponto.cobertura <= 0.4 + 1e-9

    def test_em_cobertura_devolve_nada_quando_ninguem_atende(self):
        """Pedir 1% e receber 30% em silêncio estragaria uma conclusão."""
        probabilidades, erros = self._caso_ideal()
        curva = construir(probabilidades, erros)
        assert curva.em_cobertura(0.001) is None

    def test_area_e_menor_quando_a_ordenacao_e_boa(self):
        gerador = np.random.default_rng(11)
        erros = gerador.uniform(0.0, 20.0, 2000)
        boa = construir(1.0 - erros / 20.0, erros)
        aleatoria = construir(gerador.uniform(0.0, 1.0, 2000), erros)
        assert boa.area_risco_cobertura < aleatoria.area_risco_cobertura

    def test_rejeita_tamanhos_que_nao_casam(self):
        with pytest.raises(ValueError, match="casar"):
            construir(np.array([0.5, 0.5]), np.array([1.0]))


class TestEscolhaDeLimiar:
    def test_escolhe_o_menor_limiar_que_atende(self):
        """Entre dois que atingem o erro, vence o que recusa menos."""
        erros = np.arange(20, dtype=float)
        probabilidades = 1.0 - erros / 20.0
        limiar = escolher_limiar(
            probabilidades, erros, cobertura_minima=0.2, erro_alvo_bpm=4.0
        )
        assert limiar is not None
        ponto = avaliar(probabilidades, erros, limiar)
        assert ponto.erro_medio <= 4.0
        assert ponto.cobertura >= 0.2

    def test_devolve_nada_quando_o_alvo_e_inalcancavel(self):
        """Esse `None` é achado, não caso de borda.

        Quer dizer que o erro pedido só existe recusando mais do que se quer.
        """
        erros = np.full(50, 10.0)
        probabilidades = np.linspace(0.0, 1.0, 50)
        assert (
            escolher_limiar(
                probabilidades, erros, cobertura_minima=0.5, erro_alvo_bpm=1.0
            )
            is None
        )

    def test_rejeita_cobertura_fora_do_intervalo(self):
        with pytest.raises(ValueError, match="entre 0 e 1"):
            escolher_limiar(np.array([0.5]), np.array([1.0]), 1.5, 2.0)

    def test_rejeita_erro_alvo_nao_positivo(self):
        with pytest.raises(ValueError, match="positivo"):
            escolher_limiar(np.array([0.5]), np.array([1.0]), 0.5, 0.0)
