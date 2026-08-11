"""Testes da ferramenta de diagnóstico sobre captura.

Roda sobre vídeo sintético com frequência conhecida, então dá para verificar
não só que a ferramenta executa, mas que ela aponta a resposta certa.
"""

from __future__ import annotations

import numpy as np
import pytest

from cardiocam.avaliacao.diagnostico import (
    VARIANTES_ROI,
    Captura,
    Resultado,
    avaliar_captura,
    capturar,
    formatar_relatorio,
    gravar_csv,
)
from cardiocam.dominio.sinal import BandaCardiaca
from cardiocam.fontes.sintetica import FonteSintetica, ParametrosSimulacao


def cenario(bpm: float, duracao_s: float = 30.0) -> ParametrosSimulacao:
    return ParametrosSimulacao(
        bpm=bpm,
        duracao_s=duracao_s,
        fps=20.0,
        largura=320,
        altura=240,
        amplitude_pulso=0.02,
        ruido_sensor=2.0,
        semente=int(bpm),
    )


@pytest.fixture(scope="module")
def captura_de_72() -> Captura:
    """Uma captura só, reaproveitada pelos testes que não a alteram."""
    return capturar(FonteSintetica(cenario(72.0)), duracao_s=30.0)


@pytest.mark.lento
def test_captura_coleta_todas_as_variantes(captura_de_72: Captura) -> None:
    assert captura_de_72.total > 200
    assert set(captura_de_72.por_variante) == set(VARIANTES_ROI)
    for nome in VARIANTES_ROI:
        assert len(captura_de_72.por_variante[nome]) == captura_de_72.total
        assert len(captura_de_72.pixels_por_variante[nome]) == captura_de_72.total


@pytest.mark.lento
def test_captura_mede_a_taxa_de_quadros(captura_de_72: Captura) -> None:
    assert abs(captura_de_72.fps - 20.0) < 1.0


@pytest.mark.lento
def test_captura_registra_a_caixa_e_o_fundo(captura_de_72: Captura) -> None:
    assert len(captura_de_72.caixas) == captura_de_72.total
    assert len(captura_de_72.fundo) == captura_de_72.total
    assert all(len(c) == 4 for c in captura_de_72.caixas)


@pytest.mark.lento
def test_tremor_da_caixa_e_pequeno_com_rosto_parado(captura_de_72: Captura) -> None:
    """No vídeo sintético o rosto não se move, então o tremor mede apenas a
    instabilidade do próprio detector."""
    posicao, tamanho = captura_de_72.tremor_da_caixa()
    assert posicao < 6.0
    assert tamanho < 12.0


@pytest.mark.lento
def test_variante_maior_usa_mais_pixels(captura_de_72: Captura) -> None:
    pequeno = np.median(captura_de_72.pixels_por_variante["conjunto_pequeno"])
    grande = np.median(captura_de_72.pixels_por_variante["conjunto_grande"])
    assert grande > pequeno


@pytest.mark.lento
def test_avaliacao_encontra_a_frequencia_verdadeira(captura_de_72: Captura) -> None:
    """O teste que dá sentido à ferramenta: ela precisa apontar o valor certo."""
    resultados = avaliar_captura(captura_de_72, janela_s=12.0)
    assert resultados, "nenhuma configuração produziu estimativa"
    for resultado in resultados[:5]:
        assert abs(resultado.bpm_mediano - 72.0) < 3.0, resultado.rotulo


@pytest.mark.lento
def test_avaliacao_cobre_as_combinacoes(captura_de_72: Captura) -> None:
    resultados = avaliar_captura(captura_de_72, janela_s=12.0)
    algoritmos = {r.algoritmo for r in resultados}
    assert algoritmos == {"pos", "chrom", "verde"}
    assert {r.variante for r in resultados} == set(VARIANTES_ROI)


@pytest.mark.lento
def test_resultados_saem_ordenados_por_estabilidade(captura_de_72: Captura) -> None:
    """Numa medição real, consistência entre janelas vale mais que SNR alta."""
    resultados = avaliar_captura(captura_de_72, janela_s=12.0)
    dispersoes = [r.dispersao for r in resultados]
    assert dispersoes == sorted(dispersoes)


@pytest.mark.lento
def test_relatorio_traz_as_secoes_esperadas(captura_de_72: Captura) -> None:
    texto = formatar_relatorio(captura_de_72, avaliar_captura(captura_de_72, janela_s=12.0))
    assert "CAPTURA" in texto
    assert "CONFIGURAÇÕES" in texto
    assert "LEITURA DO RESULTADO" in texto
    assert "quadros por segundo" in texto


@pytest.mark.lento
def test_csv_tem_uma_linha_por_quadro(captura_de_72: Captura, tmp_path) -> None:
    destino = tmp_path / "diag.csv"
    gravar_csv(captura_de_72, str(destino))
    linhas = destino.read_text(encoding="utf-8").strip().split("\n")
    assert len(linhas) == captura_de_72.total + 1
    assert linhas[0].startswith("instante;")
    for nome in VARIANTES_ROI:
        assert f"{nome}_g" in linhas[0]


@pytest.mark.lento
def test_csv_nao_guarda_imagem(captura_de_72: Captura, tmp_path) -> None:
    """Só números saem no arquivo. É requisito de privacidade, não detalhe."""
    destino = tmp_path / "diag.csv"
    gravar_csv(captura_de_72, str(destino))
    conteudo = destino.read_text(encoding="utf-8")
    permitidos = set("0123456789.;-\n\r_abcdefghijklmnopqrstuvwxyz")
    assert set(conteudo.lower()) <= permitidos


# --------------------------------------------------------------------------
# Casos de borda, rápidos
# --------------------------------------------------------------------------
def test_captura_vazia_nao_produz_resultados() -> None:
    assert avaliar_captura(Captura()) == []


def test_captura_vazia_tem_fps_zero() -> None:
    assert Captura().fps == 0.0


def test_tremor_de_captura_vazia_e_zero() -> None:
    assert Captura().tremor_da_caixa() == (0.0, 0.0)


def test_relatorio_de_captura_vazia_avisa() -> None:
    captura = Captura()
    captura.instantes = [0.0]
    captura.caixas = [(0, 0, 10, 10)]
    texto = formatar_relatorio(captura, [])
    assert "Não houve dados suficientes" in texto


@pytest.mark.parametrize("duracao", (0.5, 1.0))
def test_captura_curta_demais_nao_avalia(duracao: float) -> None:
    captura = capturar(FonteSintetica(cenario(72.0, duracao)), duracao_s=duracao)
    assert avaliar_captura(captura) == []


def test_video_sem_rosto_descarta_todos_os_quadros() -> None:
    class ParedeLisa:
        fps = 20.0

        def quadros(self):
            for indice in range(120):
                yield np.full((240, 320, 3), 110, dtype=np.uint8), indice / 20.0

        def fechar(self):
            return None

    captura = capturar(ParedeLisa(), duracao_s=6.0)
    assert captura.total == 0
    assert captura.quadros_sem_rosto > 0


@pytest.mark.parametrize(
    "dispersao,esperado",
    ((0.5, "consistente"), (4.0, "indicativo"), (12.0, "não confiável")),
)
def test_relatorio_classifica_a_dispersao(dispersao: float, esperado: str) -> None:
    captura = Captura()
    captura.instantes = [0.0, 1.0]
    captura.caixas = [(0, 0, 10, 10), (0, 0, 10, 10)]
    captura.por_variante = {nome: [] for nome in VARIANTES_ROI}
    captura.pixels_por_variante = {nome: [100, 100] for nome in VARIANTES_ROI}
    resultado = Resultado("conjunto_pequeno", "pos", True, 72.0, dispersao, 10.0, 5)
    assert esperado in formatar_relatorio(captura, [resultado])


def test_rotulo_do_resultado_descreve_a_configuracao() -> None:
    com = Resultado("bochechas", "chrom", True, 70.0, 1.0, 8.0, 4)
    sem = Resultado("bochechas", "chrom", False, 70.0, 1.0, 8.0, 4)
    assert "com fundo" in com.rotulo and "chrom" in com.rotulo
    assert "sem fundo" in sem.rotulo


@pytest.mark.lento
def test_banda_personalizada_e_respeitada(captura_de_72: Captura) -> None:
    estreita = BandaCardiaca(1.0, 1.5)
    resultados = avaliar_captura(captura_de_72, janela_s=12.0, banda=estreita)
    for resultado in resultados:
        assert estreita.contem_bpm(resultado.bpm_mediano)
