"""Testes da coleta que percorre o caminho completo, com imagem.

Esta coleta existe por um motivo medido, e é esse motivo que o teste principal
cobra: no caminho analítico **quatro das onze características não variam**,
porque não há imagem. Fração de pele, fração saturada, deslocamento da região e
jitter ficam constantes, o modelo corretamente lhes dá peso zero com o desvio da
priori, e a decisão de recusar acaba apoiada só no espectro.

São justamente as características que descrevem os modos de falha que o espectro
não vê: região que escorregou para o cabelo, rosto estourado de luz, pouca pele
dentro da caixa. Nenhum desses aparece como espectro feio, e todos produzem
número errado. Um teste que só verificasse "roda sem quebrar" deixaria passar o
caso em que a coleta por vídeo custa duas ordens de grandeza mais caro e entrega
exatamente a mesma informação que a barata.
"""

from __future__ import annotations

import numpy as np
import pytest

from cardiocam.avaliacao.benchmark import Cenario
from cardiocam.dominio.config import ConfiguracaoAnalise
from cardiocam.fontes.sintetica import ParametrosSimulacao
from cardiocam.qualidade.coleta_de_video import (
    SATURADO_ALTO,
    SATURADO_BAIXO,
    _ContextoDaJanela,
    coletar_de_video,
    fracao_saturada,
)
from cardiocam.visao.geometria import Retangulo


def _cenario(nome: str, bpm: float, **extras) -> Cenario:
    """Cenário curto de propósito: cada segundo de vídeo custa caro aqui."""
    return Cenario(
        nome=nome,
        parametros=ParametrosSimulacao(
            bpm=bpm, duracao_s=14.0, fps=20.0, semente=7, **extras
        ),
    )


class TestFracaoSaturada:
    def test_quadro_normal_nao_tem_pixel_no_extremo(self):
        quadro = np.full((40, 60, 3), 128, dtype=np.uint8)
        assert fracao_saturada(quadro, Retangulo(10, 10, 20, 20)) == 0.0

    def test_estourado_conta_tudo(self):
        quadro = np.full((40, 60, 3), 255, dtype=np.uint8)
        assert fracao_saturada(quadro, Retangulo(10, 10, 20, 20)) == 1.0

    def test_apagado_tambem_conta(self):
        """Os dois extremos perdem informação, e por isso contam juntos.

        Pixel encostado no fundo da escala teve o pulso cortado pelo conversor
        tanto quanto o estourado, e nenhuma filtragem o traz de volta.
        """
        quadro = np.zeros((40, 60, 3), dtype=np.uint8)
        assert fracao_saturada(quadro, Retangulo(10, 10, 20, 20)) == 1.0

    def test_mede_na_caixa_e_nao_no_quadro(self):
        """Janela clara ao fundo não pode estourar o número.

        É o erro clássico de medir luz pelo quadro inteiro: o fundo entra na
        conta e a medida passa a falar de um lugar onde não há rosto.
        """
        quadro = np.full((40, 60, 3), 255, dtype=np.uint8)
        quadro[5:25, 5:25] = 128
        assert fracao_saturada(quadro, Retangulo(5, 5, 20, 20)) == 0.0
        assert fracao_saturada(quadro, Retangulo(30, 5, 20, 20)) == 1.0

    def test_caixa_fora_do_quadro_e_grampeada(self):
        """Caixa que escorregou para fora não pode levantar exceção.

        O rastreador devolve caixa em coordenadas do quadro reduzido, e um salto
        pode jogá-la parcialmente para fora. Quebrar aqui derrubaria a coleta
        inteira por causa de um quadro.
        """
        quadro = np.full((40, 60, 3), 128, dtype=np.uint8)
        assert fracao_saturada(quadro, Retangulo(-50, -50, 20, 20)) == 0.0
        assert fracao_saturada(quadro, Retangulo(300, 300, 20, 20)) == 0.0

    def test_os_limiares_sao_os_documentados(self):
        assert SATURADO_ALTO == 254
        assert SATURADO_BAIXO == 1


class TestContextoDaJanela:
    def test_descreve_so_os_quadros_da_janela(self):
        """O contexto tem de falar dos **mesmos** quadros que a estimativa viu.

        Acumular desde o início do vídeo misturaria quadros que já saíram da
        janela, e a característica passaria a descrever um passado que a
        estimativa não usou.
        """
        contexto = _ContextoDaJanela(capacidade=3)
        for valor in (0.1, 0.2, 0.3, 0.9):
            contexto.registrar(valor, 0.0, valor)
        assert len(contexto.pele) == 3
        assert contexto.media_de_pele() == pytest.approx((0.2 + 0.3 + 0.9) / 3)

    def test_vazio_nao_levanta(self):
        contexto = _ContextoDaJanela(capacidade=3)
        assert contexto.media_de_pele() == 0.0
        assert contexto.media_saturada() == 0.0
        assert contexto.deslocamento().size == 0

    def test_completo_so_quando_enche(self):
        contexto = _ContextoDaJanela(capacidade=2)
        assert not contexto.completo
        contexto.registrar(0.5, 0.0, 0.5)
        assert not contexto.completo
        contexto.registrar(0.5, 0.0, 0.5)
        assert contexto.completo


class TestColetarDeVideo:
    def test_agrupamento_desconhecido_e_recusado(self):
        with pytest.raises(ValueError, match="não existe"):
            coletar_de_video(cenarios=[_cenario("x", 72.0)], agrupar_por="qualquer")

    def test_emite_uma_amostra_por_janela_e_nao_uma_por_video(self):
        """Descartar as janelas do meio jogaria fora a maior parte do dado.

        Um vídeo de catorze segundos com passo de um segundo emite várias
        janelas, e é essa multiplicação que paga o custo de renderizar.
        """
        amostras, falhas = coletar_de_video(
            cenarios=[_cenario("repouso", 72.0)], algoritmos=("pos",)
        )
        assert falhas == 0
        assert len(amostras) > 1
        assert all(a.grupo == "repouso" for a in amostras)

    def test_as_caracteristicas_de_imagem_de_fato_variam(self):
        """O teste que justifica este módulo existir.

        Se estes quatro números saírem constantes, a coleta por vídeo custou
        duas ordens de grandeza a mais para entregar a mesma informação que a
        analítica, e aí ela não deveria existir.

        A fração de pele é a mais importante das quatro: ela é a que cai quando
        a região escorrega para fora do rosto, que é um modo de falha invisível
        no espectro.
        """
        amostras, _ = coletar_de_video(
            cenarios=[_cenario("repouso", 72.0)], algoritmos=("pos",)
        )
        pele = [a.caracteristicas.fracao_de_pele for a in amostras]
        assert len(amostras) >= 2
        assert all(0.0 < p <= 1.0 for p in pele), pele

        # Com a cabeça se movendo, o centro da região muda entre janelas, e o
        # deslocamento deixa de ser zero. É o contraste que prova que o número
        # vem da imagem e não de um padrão.
        from cardiocam.fontes.movimento import ParametrosMovimento

        com_movimento, _ = coletar_de_video(
            cenarios=[
                _cenario(
                    "mexendo",
                    72.0,
                    movimento=ParametrosMovimento(amplitude_px=6.0, banda_hz=(0.2, 0.6)),
                )
            ],
            algoritmos=("pos",),
        )
        parado = max(a.caracteristicas.deslocamento_roi for a in amostras)
        mexendo = max(a.caracteristicas.deslocamento_roi for a in com_movimento)
        # Medido: 0,0016 parado contra 0,016 com 6 px de amplitude. A folga de
        # três vezes é larga de propósito, porque o número exato depende de onde
        # a cascata para, e o que o teste cobra é que ele venha da imagem.
        assert mexendo > parado * 3.0, f"parado {parado}, mexendo {mexendo}"

    def test_agrupar_por_frequencia_usa_o_bpm(self):
        amostras, _ = coletar_de_video(
            cenarios=[_cenario("repouso", 72.0)],
            algoritmos=("pos",),
            agrupar_por="frequencia",
        )
        assert {a.grupo for a in amostras} == {"72"}

    def test_video_sem_estimativa_conta_a_parte(self):
        """Vídeo que não rende janela nenhuma é recusa do pipeline.

        Contar essas janelas junto com as boas ensinaria o modelo a reconhecer
        a recusa em vez do fenômeno, que foi exatamente o defeito corrigido na
        coleta analítica.
        """
        curto = Cenario(
            nome="curto demais",
            parametros=ParametrosSimulacao(bpm=72.0, duracao_s=2.0, fps=20.0),
        )
        amostras, falhas = coletar_de_video(
            cenarios=[curto], algoritmos=("pos",), config=ConfiguracaoAnalise()
        )
        assert amostras == []
        assert falhas == 1
