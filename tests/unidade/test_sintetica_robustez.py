"""Testes dos mecanismos físicos acrescentados ao simulador.

O primeiro teste é o mais importante e também o mais chato: com os parâmetros
novos no padrão, a série gerada tem de sair **idêntica bit a bit** à de antes.
É o critério de aceitação escrito no plano de trabalho da iniciação científica, e
a razão é simples: um simulador que muda de resposta ao ganhar um recurso
invalida toda medição anterior sem avisar ninguém.

Como não dá para comparar com o código antigo, que não existe mais, a verificação
é por propriedade: ligar um parâmetro e desligá-lo tem de voltar exatamente ao
mesmo lugar, e nenhum dos parâmetros novos pode alterar nada enquanto estiver no
padrão.
"""

from __future__ import annotations

import numpy as np
import pytest

from cardiocam.avaliacao.benchmark import iluminante_desviado
from cardiocam.fontes.sintetica import ParametrosSimulacao, gerar_serie_rgb


def _base(**extras) -> ParametrosSimulacao:
    return ParametrosSimulacao(
        bpm=72.0, duracao_s=10.0, fps=30.0, semente=7, **extras
    )


class TestNeutralidade:
    def test_os_parametros_novos_no_padrao_nao_mudam_nada(self):
        """O critério de aceitação da etapa 2 do plano de trabalho.

        Passar explicitamente os padrões tem de dar exatamente o mesmo que não
        passar nada. Qualquer diferença aqui significa que medições anteriores
        deixaram de ser comparáveis.
        """
        antes = gerar_serie_rgb(_base())
        depois = gerar_serie_rgb(
            _base(
                amplitude_especular=0.0,
                especular_hz=0.0,
                cor_iluminante=(255, 255, 255),
                movimento_camera_px=0.0,
                movimento_camera_hz=0.3,
                cor_fundo_bgr=(60, 60, 60),
                com_fundo=False,
            )
        )
        assert np.array_equal(antes.vermelho, depois.vermelho)
        assert np.array_equal(antes.verde, depois.verde)
        assert np.array_equal(antes.azul, depois.azul)

    def test_sem_com_fundo_a_serie_do_fundo_nao_existe(self):
        """Ligar o fundo muda o resultado da análise, porque a rectificação
        entra em cena. Por isso ele fica desligado por padrão."""
        assert gerar_serie_rgb(_base()).fundo is None

    def test_cor_do_iluminante_nao_importa_sem_especular(self):
        """Sem componente especular não há o que colorir."""
        branco = gerar_serie_rgb(_base(cor_iluminante=(255, 255, 255)))
        verde = gerar_serie_rgb(_base(cor_iluminante=(90, 255, 90)))
        assert np.array_equal(branco.verde, verde.verde)

    def test_movimento_de_camera_nao_importa_sem_fundo(self):
        parado = gerar_serie_rgb(_base(movimento_camera_px=0.0))
        movendo = gerar_serie_rgb(_base(movimento_camera_px=30.0))
        assert np.array_equal(parado.verde, movendo.verde)


class TestEspecular:
    def test_acrescenta_variacao_ao_sinal(self):
        sem = gerar_serie_rgb(_base())
        com = gerar_serie_rgb(_base(amplitude_especular=0.12, movimento_hz=0.9))
        assert float(np.std(com.verde)) > float(np.std(sem.verde))

    def test_escala_pela_media_e_nao_pelo_canal(self):
        """A correção que fez o cenário passar a medir alguma coisa.

        A primeira versão escalava pela base de cada canal, o que torna o termo
        proporcional à cor da pele e o reduz a uma variação de brilho, que CHROM
        e POS cancelam por construção. Medido: o erro dos dois ficava em
        centésimos de bpm e o cenário não testava nada.

        Com a escala pela média, sob luz branca o acréscimo é o **mesmo nos três
        canais**, que é o que caracteriza luz refletida na superfície: ela não
        sabe de que cor é a pele.
        """
        sem = gerar_serie_rgb(_base(ruido_sensor=0.0))
        com = gerar_serie_rgb(
            _base(ruido_sensor=0.0, amplitude_especular=0.1, movimento_hz=0.9)
        )
        acrescimos = [
            com.vermelho - sem.vermelho,
            com.verde - sem.verde,
            com.azul - sem.azul,
        ]
        assert np.allclose(acrescimos[0], acrescimos[1], atol=1e-9)
        assert np.allclose(acrescimos[1], acrescimos[2], atol=1e-9)

    def test_iluminante_colorido_desequilibra_os_canais(self):
        """Com luz verde, o acréscimo no verde tem de superar o do vermelho."""
        sem = gerar_serie_rgb(_base(ruido_sensor=0.0))
        com = gerar_serie_rgb(
            _base(
                ruido_sensor=0.0,
                amplitude_especular=0.1,
                movimento_hz=0.9,
                cor_iluminante=(90, 255, 90),
            )
        )
        no_verde = float(np.std(com.verde - sem.verde))
        no_vermelho = float(np.std(com.vermelho - sem.vermelho))
        assert no_verde > no_vermelho * 2.0

    def test_a_frequencia_segue_a_do_movimento_quando_nao_e_dada(self):
        um = gerar_serie_rgb(
            _base(ruido_sensor=0.0, amplitude_especular=0.1, movimento_hz=1.5)
        )
        outro = gerar_serie_rgb(
            _base(
                ruido_sensor=0.0,
                amplitude_especular=0.1,
                movimento_hz=0.2,
                especular_hz=1.5,
            )
        )
        assert np.allclose(um.verde, outro.verde, atol=1e-9)


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
            _base(com_fundo=True, ruido_sensor=0.0, movimento_camera_px=20.0)
        )
        assert float(np.std(movendo.fundo[1, :])) > float(
            np.std(parada.fundo[1, :])
        )

    def test_a_corrupcao_cresce_com_o_deslocamento(self):
        pouco = gerar_serie_rgb(
            _base(com_fundo=True, ruido_sensor=0.0, movimento_camera_px=5.0)
        )
        muito = gerar_serie_rgb(
            _base(com_fundo=True, ruido_sensor=0.0, movimento_camera_px=40.0)
        )
        assert float(np.std(muito.fundo[1, :])) > float(np.std(pouco.fundo[1, :]))


class TestIluminanteDesviado:
    def test_zero_e_branco(self):
        assert iluminante_desviado(0.0) == (255, 255, 255)

    def test_um_e_o_extremo(self):
        assert iluminante_desviado(1.0) == (90, 255, 90)

    def test_o_verde_nunca_muda(self):
        """O eixo da varredura é o afastamento do branco mantendo o verde no
        topo, que é onde a hemoglobina absorve."""
        for desvio in (0.0, 0.25, 0.5, 0.75, 1.0):
            assert iluminante_desviado(desvio)[1] == 255

    def test_e_monotono(self):
        anteriores = 255
        for desvio in (0.2, 0.4, 0.6, 0.8, 1.0):
            atual = iluminante_desviado(desvio)[0]
            assert atual < anteriores
            anteriores = atual

    def test_rejeita_desvio_fora_do_intervalo(self):
        with pytest.raises(ValueError, match="entre 0 e 1"):
            iluminante_desviado(1.5)
