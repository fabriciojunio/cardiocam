"""Testes do aplicativo de desktop.

A parte gráfica roda com a plataforma `offscreen` do Qt, que desenha num mapa de
bits em vez de numa tela. Não é teste de aparência: é teste de que o desenho
**acontece sem levantar exceção**, que é o modo de falha real de uma
sobreposição. Ela pinta a cada quadro, e uma exceção ali derruba a pintura num
momento em que não há ninguém olhando o console.

O caso que mais importa é o do número de três dígitos. A primeira versão
posicionava o rótulo "bpm" por estimativa de largura por caractere, e com 138 o
rótulo saía do painel. Dígito em negrito não tem a largura que o nome
"monoespaçada" promete.
"""

from __future__ import annotations

import os

import pytest

from cardiocam.desktop.janelas import JanelaDaTela, listar_janelas
from cardiocam.desktop.medicao import Origem, confianca_de


class TestConfianca:
    def test_os_limiares_sao_os_mesmos_do_resto_do_projeto(self):
        """Dois programas que dizem "confiança alta" para coisas diferentes é
        pior que um só. Estes quatro números aparecem no relatório, na linha de
        comando e aqui, e precisam concordar."""
        assert confianca_de(8.0) == "alta"
        assert confianca_de(6.0) == "alta"
        assert confianca_de(3.4) == "média"
        assert confianca_de(2.0) == "média"
        assert confianca_de(0.7) == "baixa"
        assert confianca_de(0.0) == "baixa"
        assert confianca_de(-1.1) == "descartada"

    def test_sem_medida_nao_e_confianca_baixa(self):
        """Ausência de medida e medida ruim são coisas diferentes, e misturá-las
        faria a tela dizer "baixa" antes de haver qualquer leitura."""
        assert confianca_de(None) == "aguardando"


class TestOrigem:
    def test_camera_se_descreve_sem_numero_de_indice(self):
        """O índice é detalhe de implementação; quem lê a tela quer saber de
        onde está sendo medido."""
        assert Origem(camera=0).descricao == "Câmera do computador"

    def test_janela_se_descreve_pelo_titulo(self):
        janela = JanelaDaTela(1, "Reunião — Microsoft Teams", 0, 0, 1280, 720)
        assert Origem(janela=janela).descricao == "Reunião — Microsoft Teams"


class TestJanelaDaTela:
    def test_a_regiao_sai_no_formato_da_captura(self):
        janela = JanelaDaTela(7, "Teams", 100, 50, 1280, 720)
        assert janela.regiao == {"left": 100, "top": 50, "width": 1280, "height": 720}

    def test_o_texto_mostra_o_tamanho(self):
        """O tamanho entra no rótulo porque é o que distingue a janela da
        reunião de uma janela de bate-papo lateral, quando as duas têm nome
        parecido."""
        assert str(JanelaDaTela(7, "Teams", 0, 0, 1280, 720)) == "Teams (1280x720)"

    def test_coordenada_negativa_e_valida(self):
        """Monitor à esquerda do principal tem x negativo. Tratar isso como
        erro deixaria de fora metade das telas de quem usa dois monitores."""
        janela = JanelaDaTela(7, "Teams", -1920, 68, 1920, 1032)
        assert janela.regiao["left"] == -1920


@pytest.mark.skipif(os.name != "nt", reason="a enumeração de janelas é da API do Windows")
class TestListarJanelas:
    def test_devolve_janelas_com_area_util(self):
        for janela in listar_janelas():
            assert janela.titulo
            assert janela.largura >= 320
            assert janela.altura >= 240

    def test_o_limiar_de_tamanho_e_respeitado(self):
        """Pedir janela grande devolve subconjunto do que pedir janela
        pequena. Se não devolver, o filtro não está filtrando."""
        poucas = listar_janelas(largura_minima=1600, altura_minima=900)
        muitas = listar_janelas(largura_minima=100, altura_minima=100)
        assert len(poucas) <= len(muitas)


class TestEscolhaDaReuniao:
    """A origem padrão é a reunião aberta, e não a câmera.

    Vem de uma observação de uso: durante a reunião o programa dela já está com
    a câmera, e pedir o mesmo dispositivo disputa com ele. A imagem que
    interessa, inclusive a do próprio rosto, já está na tela.
    """

    def _janela(self, titulo: str) -> JanelaDaTela:
        return JanelaDaTela(1, titulo, 0, 0, 1280, 720)

    def test_reconhece_os_programas_de_reuniao(self):
        from cardiocam.desktop.janelas import provavel_reuniao

        for titulo in (
            "Reunião | Microsoft Teams",
            "Meet - abc-defg-hij",
            "Zoom Meeting",
            "WhatsApp",
            "Webex | Sala pessoal",
        ):
            assert provavel_reuniao([self._janela(titulo)]) is not None, titulo

    def test_nao_confunde_janela_comum_com_reuniao(self):
        from cardiocam.desktop.janelas import provavel_reuniao

        comuns = [
            self._janela("README.md - cardiocam - Visual Studio Code"),
            self._janela("Downloads"),
        ]
        assert provavel_reuniao(comuns) is None

    def test_a_primeira_da_pilha_vence(self):
        """A enumeração vem em ordem de empilhamento, então a primeira que casa
        é a que está na frente, que é a que a pessoa está olhando."""
        from cardiocam.desktop.janelas import provavel_reuniao

        escolhida = provavel_reuniao(
            [self._janela("Zoom Meeting"), self._janela("Microsoft Teams")]
        )
        assert escolhida is not None and "Zoom" in escolhida.titulo

    def test_lista_vazia_nao_quebra(self):
        from cardiocam.desktop.janelas import provavel_reuniao

        assert provavel_reuniao([]) is None


class TestEncolher:
    """Reduzir a largura antes da análise não piora a imagem: com `INTER_AREA`
    cada pixel de saída é a média dos de entrada, e média espacial reduz ruído
    de leitura. O que ela compra é tempo de detecção."""

    def test_quadro_grande_e_reduzido_ao_teto(self):
        import numpy as np

        from cardiocam.desktop.medicao import LARGURA_MAXIMA_DA_TELA, LacoDeMedicao

        grande = np.zeros((1032, 1920, 3), dtype=np.uint8)
        saida = LacoDeMedicao._encolher(grande)
        assert saida.shape[1] == LARGURA_MAXIMA_DA_TELA
        # A proporção precisa ser mantida, senão o rosto sai esticado e a
        # cascata, que foi treinada em rosto de proporção normal, o perde.
        assert saida.shape[0] == round(1032 * LARGURA_MAXIMA_DA_TELA / 1920)

    def test_quadro_pequeno_nao_e_ampliado(self):
        """Ampliar não acrescenta informação e custa tempo. Janela pequena
        passa como está."""
        import numpy as np

        from cardiocam.desktop.medicao import LacoDeMedicao

        pequeno = np.zeros((480, 640, 3), dtype=np.uint8)
        assert LacoDeMedicao._encolher(pequeno).shape == pequeno.shape

    def test_a_media_e_preservada(self):
        """`INTER_AREA` promedia, e a média do quadro tem de sobreviver: é dela
        que a medição de cor sai."""
        import numpy as np

        from cardiocam.desktop.medicao import LacoDeMedicao

        gerador = np.random.default_rng(2)
        quadro = gerador.integers(60, 200, size=(1032, 1920, 3), dtype=np.uint8)
        reduzido = LacoDeMedicao._encolher(quadro)
        assert abs(float(reduzido.mean()) - float(quadro.mean())) < 0.5


@pytest.fixture(scope="module")
def aplicacao():
    """Uma aplicação Qt sem tela, para o desenho poder ser exercitado."""
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication

    existente = QApplication.instance()
    yield existente or QApplication([])


class TestSobreposicao:
    def _pintar(self, sobreposicao):
        """Desenha num mapa de bits e devolve se saiu alguma coisa."""
        mapa = sobreposicao.grab()
        return not mapa.isNull()

    def test_desenha_sem_leitura_nenhuma(self, aplicacao):
        """O primeiro quadro acontece antes de existir medida, e a tela não
        pode quebrar nele."""
        from cardiocam.desktop.sobreposicao import Sobreposicao

        assert self._pintar(Sobreposicao())

    def test_desenha_com_numero_de_tres_digitos(self, aplicacao):
        """A regressão: com 138 o rótulo "bpm" saía do painel, porque a largura
        era estimada por caractere em vez de medida."""
        from cardiocam.desktop.sobreposicao import LeituraNaTela, Sobreposicao

        tela = Sobreposicao()
        tela.atualizar_leitura(
            LeituraNaTela(
                bpm=138.0,
                confianca="alta",
                snr_db=8.2,
                progresso=1.0,
                pulso=[float(i % 7) for i in range(240)],
            )
        )
        assert self._pintar(tela)

    def test_desenha_a_barra_enquanto_a_janela_enche(self, aplicacao):
        from cardiocam.desktop.sobreposicao import LeituraNaTela, Sobreposicao

        tela = Sobreposicao()
        tela.atualizar_leitura(LeituraNaTela(progresso=0.42, mensagem="Coletando sinal"))
        assert self._pintar(tela)

    def test_onda_curta_demais_nao_quebra(self, aplicacao):
        """Um ponto só não forma linha, e o desenho precisa desistir em vez de
        dividir por zero."""
        from cardiocam.desktop.sobreposicao import LeituraNaTela, Sobreposicao

        tela = Sobreposicao()
        tela.atualizar_leitura(LeituraNaTela(progresso=1.0, pulso=[0.5]))
        assert self._pintar(tela)

    def test_onda_constante_nao_divide_por_zero(self, aplicacao):
        """Sinal sem variação dá amplitude zero. Acontece de verdade, com a
        lente tapada."""
        from cardiocam.desktop.sobreposicao import LeituraNaTela, Sobreposicao

        tela = Sobreposicao()
        tela.atualizar_leitura(LeituraNaTela(progresso=1.0, pulso=[0.5] * 60))
        assert self._pintar(tela)

    def test_nao_recebe_clique(self, aplicacao):
        """A propriedade que faz a sobreposição ser discreta: o clique atravessa
        e chega na reunião que está embaixo. Sem isso o programa que deveria
        ficar fora do caminho vira o que atrapalha."""
        from PySide6.QtCore import Qt

        from cardiocam.desktop.sobreposicao import Sobreposicao

        tela = Sobreposicao()
        assert tela.testAttribute(Qt.WA_TransparentForMouseEvents)
        assert tela.windowFlags() & Qt.WindowTransparentForInput

    def test_fica_sempre_no_topo_e_fora_da_barra_de_tarefas(self, aplicacao):
        from PySide6.QtCore import Qt

        from cardiocam.desktop.sobreposicao import Sobreposicao

        bandeiras = Sobreposicao().windowFlags()
        assert bandeiras & Qt.WindowStaysOnTopHint
        assert bandeiras & Qt.FramelessWindowHint
        assert bandeiras & Qt.Tool
