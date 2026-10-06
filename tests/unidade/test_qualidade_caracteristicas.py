"""Testes das características e da padronização.

Cada característica tem um caso em que a resposta é conhecida por argumento
físico, e não por execução anterior. Entropia de espectro plano é 1 por
definição; de um bin só é 0. Desvio cromático de uma série que oscila
exatamente na direção do pulso é 0.

Dois testes aqui guardam decisões que já custaram medição: a padronização
precisa sair só do treino, e `nan` de característica não observável precisa
virar a média, e não um extremo.
"""

from __future__ import annotations

import numpy as np
import pytest

from cardiocam.dominio.estimativa import Espectro
from cardiocam.dominio.sinal import SinalPulso
from cardiocam.fontes.sintetica import GANHO_CANAL
from cardiocam.qualidade.caracteristicas import (
    Caracteristicas,
    Padronizador,
    correlacao,
    desvio_cromatico,
    dispersao_do_pico,
    entropia_espectral,
    extrair,
    proeminencia,
    razao_harmonica,
)


class TestEntropiaEspectral:
    def test_espectro_plano_vale_um(self):
        assert entropia_espectral(np.ones(64)) == pytest.approx(1.0)

    def test_toda_energia_num_bin_vale_zero(self):
        potencias = np.zeros(64)
        potencias[10] = 1.0
        assert entropia_espectral(potencias) == pytest.approx(0.0)

    def test_concentrado_da_menos_que_espalhado(self):
        concentrado = np.array([10.0, 0.1, 0.1, 0.1])
        espalhado = np.array([2.0, 2.5, 2.0, 1.8])
        assert entropia_espectral(concentrado) < entropia_espectral(espalhado)

    def test_nao_depende_do_numero_de_bins(self):
        """Sem a normalização pelo log, janela mais longa daria entropia maior
        só por ter mais bins, e o modelo aprenderia a ler comprimento."""
        assert entropia_espectral(np.ones(32)) == pytest.approx(
            entropia_espectral(np.ones(512))
        )

    def test_espectro_vazio_vale_um(self):
        assert entropia_espectral(np.array([])) == 1.0


class TestProeminencia:
    def test_cresce_com_o_pico(self):
        base = np.ones(50)
        baixo = base.copy()
        baixo[10] = 5.0
        alto = base.copy()
        alto[10] = 500.0
        assert proeminencia(alto) > proeminencia(baixo)

    def test_e_logaritmica(self):
        """Razão de 376 mil de desvio dominava a padronização; em log não."""
        base = np.ones(50)
        pico = base.copy()
        pico[10] = 1e6
        assert proeminencia(pico) < 20.0

    def test_espectro_nulo_da_zero(self):
        assert proeminencia(np.zeros(10)) == 0.0


class TestRazaoHarmonica:
    def test_detecta_harmonico_presente(self):
        frequencias = np.linspace(0.7, 4.0, 200)
        potencias = np.zeros_like(frequencias)
        potencias[np.argmin(np.abs(frequencias - 1.2))] = 10.0
        potencias[np.argmin(np.abs(frequencias - 2.4))] = 4.0
        assert razao_harmonica(frequencias, potencias, 1.2) > 0.2

    def test_senoide_pura_nao_tem_harmonico(self):
        frequencias = np.linspace(0.7, 4.0, 200)
        potencias = np.zeros_like(frequencias)
        potencias[np.argmin(np.abs(frequencias - 1.2))] = 10.0
        assert razao_harmonica(frequencias, potencias, 1.2) == pytest.approx(0.0)

    def test_devolve_zero_quando_o_harmonico_cai_fora_da_banda(self):
        """É a limitação que tirou esta característica do centro do modelo.

        Acima de 120 bpm o primeiro harmônico sai da banda cardíaca, e zero
        aqui quer dizer "não observável", não "não tem".
        """
        frequencias = np.linspace(0.7, 4.0, 200)
        potencias = np.zeros_like(frequencias)
        potencias[np.argmin(np.abs(frequencias - 2.5))] = 10.0
        assert razao_harmonica(frequencias, potencias, 2.5) == pytest.approx(0.0)


class TestDesvioCromatico:
    @staticmethod
    def _serie(direcao: tuple[float, float, float], n: int = 300) -> np.ndarray:
        """Série 3xN que oscila numa direção escolhida, sobre bases distintas.

        As bases diferentes importam: a normalização por média é o que põe os
        canais na mesma escala, e sem bases distintas o teste não exerceria
        essa parte.
        """
        tempo = np.arange(n) / 30.0
        onda = np.sin(2.0 * np.pi * 1.2 * tempo)
        bases = np.array([180.0, 150.0, 120.0]).reshape(3, 1)
        variacao = np.array(direcao, dtype=float).reshape(3, 1) * onda.reshape(1, -1)
        return bases * (1.0 + 0.02 * variacao)

    def test_oscilacao_na_direcao_do_pulso_nao_desvia(self):
        direcao = (
            GANHO_CANAL["vermelho"],
            GANHO_CANAL["verde"],
            GANHO_CANAL["azul"],
        )
        assert desvio_cromatico(self._serie(direcao)) == pytest.approx(0.0, abs=1e-6)

    def test_oscilacao_ortogonal_desvia_ao_maximo(self):
        """Vetor escolhido para ter produto interno nulo com (0,30; 1,00; 0,55).

        Um e menos um no vermelho e no azul na proporção certa, e zero no
        verde: 0,30·a + 0,55·b = 0 com a = 55 e b = -30.
        """
        assert desvio_cromatico(self._serie((55.0, 0.0, -30.0))) == pytest.approx(
            1.0, abs=1e-6
        )

    def test_serie_constante_devolve_zero(self):
        assert desvio_cromatico(np.full((3, 100), 150.0)) == 0.0

    def test_formato_errado_devolve_zero(self):
        assert desvio_cromatico(np.zeros((2, 100))) == 0.0
        assert desvio_cromatico(np.zeros(100)) == 0.0

    def test_polaridade_invertida_nao_muda_nada(self):
        """CHROM e POS produzem projeção de polaridade arbitrária."""
        direcao = (0.3, 1.0, 0.55)
        invertida = tuple(-v for v in direcao)
        assert desvio_cromatico(self._serie(direcao)) == pytest.approx(
            desvio_cromatico(self._serie(invertida)), abs=1e-9
        )


class TestCorrelacao:
    def test_identicos_dao_um(self):
        x = np.array([1.0, 2.0, 3.0, 2.0])
        assert correlacao(x, x) == pytest.approx(1.0)

    def test_opostos_tambem_dao_um_porque_e_em_modulo(self):
        x = np.array([1.0, 2.0, 3.0, 2.0])
        assert correlacao(x, -x) == pytest.approx(1.0)

    def test_constante_nao_tem_correlacao_definida(self):
        x = np.array([1.0, 2.0, 3.0])
        assert correlacao(x, np.ones(3)) == 0.0


class TestDispersaoDoPico:
    def test_senoide_estavel_tem_dispersao_pequena(self):
        tempo = np.arange(600) / 30.0
        pulso = SinalPulso(np.sin(2.0 * np.pi * 1.2 * tempo), 30.0)
        assert dispersao_do_pico(pulso) < 5.0

    def test_frequencia_que_muda_no_meio_dispersa(self):
        tempo = np.arange(600) / 30.0
        onda = np.concatenate(
            [
                np.sin(2.0 * np.pi * 1.0 * tempo[:300]),
                np.sin(2.0 * np.pi * 2.5 * tempo[300:]),
            ]
        )
        estavel = SinalPulso(np.sin(2.0 * np.pi * 1.2 * tempo), 30.0)
        assert dispersao_do_pico(SinalPulso(onda, 30.0)) > dispersao_do_pico(estavel)

    def test_janela_curta_devolve_nao_observavel(self):
        assert np.isnan(dispersao_do_pico(SinalPulso(np.zeros(10), 30.0)))

    def test_rejeita_menos_de_duas_subjanelas(self):
        with pytest.raises(ValueError, match="duas subjanelas"):
            dispersao_do_pico(SinalPulso(np.zeros(600), 30.0), subjanelas=1)


class TestExtrair:
    @staticmethod
    def _entrada():
        tempo = np.arange(600) / 30.0
        pulso = SinalPulso(np.sin(2.0 * np.pi * 1.2 * tempo), 30.0)
        frequencias = np.linspace(0.7, 4.0, 128)
        potencias = np.exp(-((frequencias - 1.2) ** 2) / 0.01)
        return pulso, Espectro(frequencias, potencias)

    def test_devolve_todas_as_caracteristicas(self):
        pulso, espectro = self._entrada()
        caracteristicas = extrair(pulso, espectro, 1.2, 12.0)
        assert len(caracteristicas.vetor()) == len(Caracteristicas.nomes())
        assert caracteristicas.snr_db == 12.0

    def test_snr_infinito_vira_piso_declarado(self):
        """Infinito como entrada de modelo linear envenena o ajuste inteiro."""
        pulso, espectro = self._entrada()
        assert extrair(pulso, espectro, 1.2, float("-inf")).snr_db == -60.0

    def test_contexto_ausente_usa_o_neutro_documentado(self):
        pulso, espectro = self._entrada()
        caracteristicas = extrair(pulso, espectro, 1.2, 12.0)
        assert caracteristicas.fracao_de_pele == 1.0
        assert caracteristicas.deslocamento_roi == 0.0
        assert caracteristicas.correlacao_com_fundo == 0.0
        assert caracteristicas.desvio_cromatico == 0.0

    def test_os_nomes_batem_com_a_ordem_do_vetor(self):
        pulso, espectro = self._entrada()
        caracteristicas = extrair(pulso, espectro, 1.2, 12.0)
        indice = Caracteristicas.nomes().index("snr_db")
        assert caracteristicas.vetor()[indice] == caracteristicas.snr_db


class TestPadronizador:
    def test_deixa_media_zero_e_desvio_um(self):
        matriz = np.random.default_rng(0).normal(5.0, 3.0, (200, 4))
        padronizador = Padronizador.ajustar(matriz, ("a", "b", "c", "d"))
        saida = padronizador.aplicar(matriz)
        assert np.allclose(np.mean(saida, axis=0), 0.0, atol=1e-9)
        assert np.allclose(np.std(saida, axis=0), 1.0, atol=1e-9)

    def test_coluna_constante_nao_vira_nan(self):
        matriz = np.hstack([np.ones((50, 1)), np.arange(50).reshape(-1, 1)])
        padronizador = Padronizador.ajustar(matriz, ("fixa", "variavel"))
        saida = padronizador.aplicar(matriz)
        assert np.all(np.isfinite(saida))
        assert np.all(saida[:, 0] == 0.0)

    def test_nan_vira_a_media_do_treino_e_nao_um_extremo(self):
        """Característica não observável é "nada de anormal", não valor extremo."""
        matriz = np.arange(40, dtype=float).reshape(-1, 1)
        padronizador = Padronizador.ajustar(matriz, ("x",))
        saida = padronizador.aplicar(np.array([[np.nan]]))
        assert saida[0, 0] == 0.0

    def test_parametros_saem_so_do_treino(self):
        """Ajustar no conjunto inteiro vaza a distribuição do teste."""
        treino = np.zeros((20, 1))
        treino[:, 0] = np.arange(20)
        padronizador = Padronizador.ajustar(treino, ("x",))
        media_esperada = float(np.mean(treino))
        assert padronizador.media[0] == pytest.approx(media_esperada)
        # Aplicar num teste deslocado não pode mudar os parâmetros.
        padronizador.aplicar(np.full((5, 1), 1000.0))
        assert padronizador.media[0] == pytest.approx(media_esperada)

    def test_rejeita_matriz_de_uma_dimensao(self):
        with pytest.raises(ValueError, match="bidimensional"):
            Padronizador.ajustar(np.zeros(10), ("x",))
