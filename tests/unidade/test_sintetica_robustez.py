"""Testes da física de movimento aplicada ao caminho analítico.

O primeiro teste é o mais importante e também o mais chato: com os parâmetros de
movimento no padrão neutro, a série gerada tem de sair **idêntica bit a bit** à
de antes. É o critério de aceitação escrito no plano de trabalho da iniciação
científica, e a razão é simples: um simulador que muda de resposta ao ganhar um
recurso invalida toda medição anterior sem avisar ninguém.

Estes testes também existem porque `fontes/movimento.py` passou meses a **zero
por cento de cobertura**. Ele tinha sido escrito para o caminho de vídeo, nunca
foi ligado em lugar nenhum, e a consequência apareceu quando a mesma física foi
reimplementada do zero dentro de `sintetica.py` sem ninguém notar a duplicata.
Código sem teste não é só código sem rede de proteção: é código que o próprio
projeto esquece que tem.
"""

from __future__ import annotations

import numpy as np
import pytest

from cardiocam.avaliacao.benchmark import iluminante_desviado
from cardiocam.fontes.movimento import (
    CROMATICIDADE_ESPECULAR,
    ParametrosMovimento,
    aplicar_especular,
    trajetoria,
)
from cardiocam.fontes.sintetica import ParametrosSimulacao, gerar_serie_rgb


def _base(**extras) -> ParametrosSimulacao:
    return ParametrosSimulacao(
        bpm=72.0, duracao_s=10.0, fps=30.0, semente=7, **extras
    )


class TestNeutralidade:
    def test_movimento_no_padrao_nao_muda_nada(self):
        """O critério de aceitação da etapa 2 do plano de trabalho.

        Passar um `ParametrosMovimento` todo no padrão tem de dar exatamente o
        mesmo que não passar nada. Qualquer diferença aqui significa que
        medições anteriores deixaram de ser comparáveis.
        """
        antes = gerar_serie_rgb(_base())
        depois = gerar_serie_rgb(_base(movimento=ParametrosMovimento()))
        assert np.array_equal(antes.vermelho, depois.vermelho)
        assert np.array_equal(antes.verde, depois.verde)
        assert np.array_equal(antes.azul, depois.azul)

    def test_a_trajetoria_neutra_e_o_elemento_identidade(self):
        """Fator difuso 1, todo o resto zero. É o que garante o teste acima."""
        tempos = np.arange(100) / 30.0
        caminho = trajetoria(tempos, ParametrosMovimento(), semente=0)
        assert np.array_equal(caminho.fator_difuso, np.ones(100))
        assert not np.any(caminho.deslocamento_cabeca)
        assert not np.any(caminho.termo_especular)
        assert not np.any(caminho.deslocamento_camera)

    def test_sem_com_fundo_a_serie_do_fundo_nao_existe(self):
        """Ligar o fundo muda o resultado da análise, porque a rectificação
        entra em cena. Por isso ele fica desligado por padrão."""
        assert gerar_serie_rgb(_base()).fundo is None

    def test_cromaticidade_nao_importa_sem_especular(self):
        """Sem componente especular não há o que colorir."""
        neutro = gerar_serie_rgb(
            _base(movimento=ParametrosMovimento(amplitude_px=10.0))
        )
        verde = gerar_serie_rgb(
            _base(
                movimento=ParametrosMovimento(
                    amplitude_px=10.0,
                    cromaticidade_iluminante=iluminante_desviado(1.0),
                )
            )
        )
        assert np.array_equal(neutro.verde, verde.verde)

    def test_movimento_de_camera_nao_toca_o_sinal_do_rosto(self):
        """Tremor de câmera desloca a imagem inteira sem mudar a pose em
        relação à luz. Ele age no fundo e no desregistro, não na cor da pele."""
        parado = gerar_serie_rgb(_base(movimento=ParametrosMovimento()))
        movendo = gerar_serie_rgb(
            _base(movimento=ParametrosMovimento(camera_px=30.0))
        )
        assert np.array_equal(parado.verde, movendo.verde)


class TestEspecular:
    @staticmethod
    def _com(esp: float, desvio: float = 0.0) -> ParametrosMovimento:
        return ParametrosMovimento(
            amplitude_px=12.0,
            banda_hz=(0.88, 0.92),
            especular_por_pose=esp,
            cromaticidade_iluminante=iluminante_desviado(desvio),
        )

    def test_acrescenta_variacao_ao_sinal(self):
        sem = gerar_serie_rgb(_base(ruido_sensor=0.0))
        com = gerar_serie_rgb(_base(ruido_sensor=0.0, movimento=self._com(0.5)))
        assert float(np.std(com.verde)) > float(np.std(sem.verde))

    def test_o_acrescimo_absoluto_nao_depende_da_cor_da_pele(self):
        """A propriedade que faz o termo mudar a cromaticidade, e não o brilho.

        A luz que quica na superfície não sabe de que cor é a pele. Então o
        acréscimo em intensidade absoluta tem de ser o mesmo para pele clara e
        para pele escura, e é por isso que ele **pesa mais** na escura, que é
        onde a hipótese de tom de pele fixo quebra primeiro.
        """
        claro = ParametrosSimulacao(
            bpm=72.0, duracao_s=10.0, fps=30.0, semente=7,
            ruido_sensor=0.0, tom_pele=(150, 175, 205), movimento=self._com(0.5),
        )
        escuro = ParametrosSimulacao(
            bpm=72.0, duracao_s=10.0, fps=30.0, semente=7,
            ruido_sensor=0.0, tom_pele=(45, 58, 78), movimento=self._com(0.5),
        )
        base_clara = ParametrosSimulacao(
            bpm=72.0, duracao_s=10.0, fps=30.0, semente=7,
            ruido_sensor=0.0, tom_pele=(150, 175, 205),
        )
        base_escura = ParametrosSimulacao(
            bpm=72.0, duracao_s=10.0, fps=30.0, semente=7,
            ruido_sensor=0.0, tom_pele=(45, 58, 78),
        )
        acrescimo_claro = (
            gerar_serie_rgb(claro).verde - gerar_serie_rgb(base_clara).verde
        )
        acrescimo_escuro = (
            gerar_serie_rgb(escuro).verde - gerar_serie_rgb(base_escura).verde
        )
        assert np.allclose(acrescimo_claro, acrescimo_escuro, atol=1e-9)

    def test_luz_neutra_acrescenta_quase_igual_nos_tres_canais(self):
        sem = gerar_serie_rgb(_base(ruido_sensor=0.0))
        com = gerar_serie_rgb(_base(ruido_sensor=0.0, movimento=self._com(0.5)))
        no_vermelho = float(np.std(com.vermelho - sem.vermelho))
        no_verde = float(np.std(com.verde - sem.verde))
        # A cromaticidade neutra é (1,00; 0,98; 0,92) em BGR: quase branca.
        assert no_verde == pytest.approx(no_vermelho, rel=0.15)

    def test_luz_desviada_desequilibra_os_canais(self):
        sem = gerar_serie_rgb(_base(ruido_sensor=0.0))
        com = gerar_serie_rgb(
            _base(ruido_sensor=0.0, movimento=self._com(0.5, desvio=1.0))
        )
        no_verde = float(np.std(com.verde - sem.verde))
        no_vermelho = float(np.std(com.vermelho - sem.vermelho))
        assert no_verde > no_vermelho * 2.0


class TestAplicarEspecular:
    def test_intensidade_zero_nao_muda_o_multiplicador(self):
        modulacao = np.array([1.0, 1.0, 1.0])
        assert np.array_equal(
            aplicar_especular(modulacao, (150, 175, 205), 0.0), modulacao
        )

    def test_pesa_mais_no_canal_de_base_mais_fraca(self):
        """O azul da pele é o canal mais fraco, então o mesmo acréscimo
        absoluto rende o maior acréscimo relativo nele. É essa assimetria que
        move a direção cromática."""
        saida = aplicar_especular(np.zeros(3), (45, 175, 205), 10.0)
        # Ordem BGR: o índice 0 é o azul, que tem a menor base.
        assert saida[0] > saida[1]
        assert saida[1] > saida[2]

    def test_a_cromaticidade_entra_no_resultado(self):
        neutro = aplicar_especular(np.zeros(3), (150, 175, 205), 10.0)
        verde = aplicar_especular(
            np.zeros(3), (150, 175, 205), 10.0, (0.35, 1.0, 0.35)
        )
        assert verde[1] > neutro[1]
        assert verde[2] < neutro[2]


class TestFundo:
    def test_tem_tres_canais_e_o_mesmo_comprimento(self):
        serie = gerar_serie_rgb(_base(com_fundo=True))
        assert serie.fundo is not None
        assert serie.fundo.shape == (3, len(serie.verde))

    def test_camera_parada_deixa_o_fundo_so_com_iluminacao(self):
        """Fundo sem movimento de câmera é referência válida: o que varia nele
        é iluminação comum, e nada mais."""
        serie = gerar_serie_rgb(
            _base(com_fundo=True, ruido_sensor=0.0, deriva_iluminacao=0.0)
        )
        assert float(np.std(serie.fundo[1, :])) < 1e-9

    def test_camera_movendo_corrompe_a_referencia(self):
        """É o mecanismo que a hipótese H2 prevê."""
        parada = gerar_serie_rgb(_base(com_fundo=True, ruido_sensor=0.0))
        movendo = gerar_serie_rgb(
            _base(
                com_fundo=True,
                ruido_sensor=0.0,
                movimento=ParametrosMovimento(camera_px=20.0),
            )
        )
        assert float(np.std(movendo.fundo[1, :])) > float(
            np.std(parada.fundo[1, :])
        )

    def test_a_corrupcao_cresce_com_o_deslocamento(self):
        pouco = gerar_serie_rgb(
            _base(
                com_fundo=True,
                ruido_sensor=0.0,
                movimento=ParametrosMovimento(camera_px=5.0),
            )
        )
        muito = gerar_serie_rgb(
            _base(
                com_fundo=True,
                ruido_sensor=0.0,
                movimento=ParametrosMovimento(camera_px=40.0),
            )
        )
        assert float(np.std(muito.fundo[1, :])) > float(np.std(pouco.fundo[1, :]))

    def test_o_fundo_usa_o_mesmo_deslocamento_que_a_imagem(self):
        """Fundo e rosto precisam se mover **juntos**, senão H2 não é testada.

        A primeira versão sorteava uma senoide própria para o fundo, o que
        simula duas câmeras independentes em vez de uma tremendo.
        """
        parametros = _base(
            com_fundo=True,
            ruido_sensor=0.0,
            movimento=ParametrosMovimento(camera_px=20.0),
        )
        serie = gerar_serie_rgb(parametros)
        caminho = trajetoria(
            serie.instantes, parametros.movimento, parametros.semente
        )
        esperado = 60.0 * (1.0 + caminho.deslocamento_camera / 100.0)
        assert np.allclose(serie.fundo[1, :], esperado, atol=1e-9)


class TestIluminanteDesviado:
    def test_zero_e_a_cromaticidade_neutra(self):
        assert iluminante_desviado(0.0) == pytest.approx(CROMATICIDADE_ESPECULAR)

    def test_um_e_o_extremo_verde(self):
        assert iluminante_desviado(1.0) == pytest.approx((0.35, 1.0, 0.35))

    def test_e_monotono_no_vermelho(self):
        anterior = 2.0
        for desvio in (0.0, 0.25, 0.5, 0.75, 1.0):
            # Índice 2 é o vermelho em BGR.
            atual = iluminante_desviado(desvio)[2]
            assert atual < anterior
            anterior = atual

    def test_rejeita_desvio_fora_do_intervalo(self):
        with pytest.raises(ValueError, match="entre 0 e 1"):
            iluminante_desviado(1.5)
