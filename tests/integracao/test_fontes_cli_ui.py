"""Testes das fontes de vídeo, da avaliação, da interface e da linha de comando."""

from __future__ import annotations

import numpy as np
import pytest

from cardiocam.avaliacao.benchmark import (
    Cenario,
    ResultadoAlgoritmo,
    avaliar,
    cenarios_padrao,
    formatar_por_cenario,
    formatar_tabela,
    frequencia_interferente,
    por_cenario,
)
from cardiocam.cli import construir_analisador, main
from cardiocam.dominio.sinal import BandaCardiaca
from cardiocam.fontes.arquivo import FonteArquivo, abrir_arquivo
from cardiocam.fontes.sintetica import (
    FonteSintetica,
    ParametrosSimulacao,
    RenderizadorRosto,
    gerar_serie_rgb,
    instantes,
    onda_de_pulso,
)
from cardiocam.fontes.tela import FonteTela
from cardiocam.fontes.webcam import FonteWebcam
from cardiocam.pipeline.analisador import EstadoQuadro
from cardiocam.rppg import ALGORITMOS_DISPONIVEIS
from cardiocam.ui.hud import compor, construir_painel, desenhar_regioes
from cardiocam.ui.texto import ItemTexto, PincelTexto
from cardiocam.visao.extrator import ExtratorRGB
from cardiocam.visao.geometria import Retangulo
from tests.conftest import parametros


# --------------------------------------------------------------------------
# Fonte sintética
# --------------------------------------------------------------------------
@pytest.mark.parametrize("bpm", (45.0, 60.0, 90.0, 150.0, 220.0))
@pytest.mark.parametrize("fps", (15.0, 30.0, 60.0))
def test_fonte_gera_o_numero_certo_de_quadros(bpm: float, fps: float) -> None:
    fonte = FonteSintetica(ParametrosSimulacao(bpm=bpm, fps=fps, duracao_s=5.0))
    quadros = list(fonte.quadros())
    assert len(quadros) == fonte.total_quadros == int(round(5.0 * fps))


@pytest.mark.parametrize("largura,altura", ((240, 180), (320, 240), (640, 480)))
def test_quadros_tem_a_resolucao_pedida(largura: int, altura: int) -> None:
    fonte = FonteSintetica(
        ParametrosSimulacao(largura=largura, altura=altura, duracao_s=0.5)
    )
    quadro, _ = fonte.quadro_em(0)
    assert quadro.shape == (altura, largura, 3)
    assert quadro.dtype == np.uint8


@pytest.mark.parametrize("bpm", (0.0, -10.0))
def test_bpm_invalido_e_rejeitado(bpm: float) -> None:
    with pytest.raises(ValueError):
        ParametrosSimulacao(bpm=bpm)


@pytest.mark.parametrize("fps", (0.0, -5.0))
def test_fps_invalido_e_rejeitado(fps: float) -> None:
    with pytest.raises(ValueError):
        ParametrosSimulacao(fps=fps)


@pytest.mark.parametrize("duracao", (0.0, -1.0))
def test_duracao_invalida_e_rejeitada(duracao: float) -> None:
    with pytest.raises(ValueError):
        ParametrosSimulacao(duracao_s=duracao)


@pytest.mark.parametrize("lado", (8, 16, 31))
def test_quadro_pequeno_demais_e_rejeitado(lado: int) -> None:
    with pytest.raises(ValueError):
        ParametrosSimulacao(largura=lado, altura=lado)


@pytest.mark.parametrize("bpm", (50.0, 72.0, 120.0, 180.0))
def test_onda_de_pulso_tem_a_frequencia_pedida(bpm: float) -> None:
    tempos = np.arange(600) / 30.0
    onda = onda_de_pulso(tempos, bpm / 60.0, (1.0, 0.35, 0.12))
    espectro = np.abs(np.fft.rfft(onda - onda.mean()))
    frequencias = np.fft.rfftfreq(onda.size, d=1 / 30.0)
    assert abs(frequencias[int(np.argmax(espectro))] * 60.0 - bpm) < 2.0


def test_onda_de_pulso_e_normalizada() -> None:
    tempos = np.arange(300) / 30.0
    onda = onda_de_pulso(tempos, 1.2, (1.0, 0.5, 0.2))
    assert float(np.max(np.abs(onda))) == pytest.approx(1.0, abs=1e-9)


@pytest.mark.parametrize("jitter", (0.0, 0.005, 0.02))
def test_instantes_sao_monotonicos(jitter: float) -> None:
    tempos = instantes(ParametrosSimulacao(duracao_s=10.0, jitter_fps=jitter, semente=3))
    assert np.all(np.diff(tempos) >= 0.0)


@pytest.mark.parametrize("bpm", (60.0, 90.0, 130.0))
def test_serie_analitica_e_serie_de_video_concordam(bpm: float) -> None:
    """O atalho analítico precisa reproduzir a mesma física do vídeo, senão os
    testes rápidos não diriam nada sobre o sistema real."""
    from cardiocam.dominio.config import ConfiguracaoAnalise
    from cardiocam.pipeline.analisador import analisar_fonte, estimar_de_serie
    from cardiocam.visao.detector_face import DetectorRegiaoFixa
    from cardiocam.visao.rastreador import RastreadorRosto

    parametro = parametros(bpm, duracao_s=16.0, largura=240, altura=180)
    analitico = estimar_de_serie(
        gerar_serie_rgb(parametro), ConfiguracaoAnalise(algoritmo="pos")
    )
    assert analitico.ok

    fonte = FonteSintetica(parametro)
    relatorio = analisar_fonte(
        fonte,
        ConfiguracaoAnalise(janela_s=10.0, algoritmo="pos"),
        rastreador=RastreadorRosto(
            DetectorRegiaoFixa(fonte.caixa_esperada()), suavizacao=1.0
        ),
    )
    assert abs(analitico.desempacotar().estimativa.bpm - relatorio.bpm_mediano) < 3.0


@pytest.mark.parametrize("movimento", (0.0, 3.0, 8.0))
def test_movimento_desloca_o_rosto(movimento: float) -> None:
    fonte = FonteSintetica(
        ParametrosSimulacao(duracao_s=8.0, movimento_px=movimento, movimento_hz=0.3)
    )
    deslocamentos = {fonte.deslocamento_em(i) for i in range(fonte.total_quadros)}
    if movimento == 0.0:
        assert deslocamentos == {(0, 0)}
    else:
        assert len(deslocamentos) > 1


@pytest.mark.parametrize("modulacao", (0.9, 1.0, 1.1))
def test_renderizador_aceita_modulacao_escalar(modulacao: float) -> None:
    quadro = RenderizadorRosto().desenhar(modulacao, ruido=0.0)
    assert quadro.shape == (240, 320, 3)


def test_renderizador_rejeita_modulacao_com_tamanho_errado() -> None:
    with pytest.raises(ValueError):
        RenderizadorRosto().desenhar(np.array([1.0, 1.0]), ruido=0.0)


def test_composicao_linear_do_renderizador() -> None:
    """A imagem precisa ser exatamente constante mais modulação vezes pele.

    É essa linearidade que garante que a modulação aplicada é a pretendida, sem
    erro de rasterização contaminando a medição.
    """
    renderizador = RenderizadorRosto()
    constante, pele = renderizador.camadas()
    esperado = np.clip(constante + pele * 1.05, 0, 255).astype(np.uint8)
    obtido = renderizador.desenhar(1.05, ruido=0.0)
    assert np.array_equal(obtido, esperado)


@pytest.mark.parametrize("canal", (0, 1, 2))
def test_modulacao_por_canal_afeta_apenas_o_canal(canal: int) -> None:
    renderizador = RenderizadorRosto()
    modulacao = np.ones(3)
    modulacao[canal] = 1.2
    base = renderizador.desenhar(1.0, ruido=0.0).astype(float)
    alterado = renderizador.desenhar(modulacao, ruido=0.0).astype(float)
    diferenca = alterado - base
    for outro in range(3):
        if outro == canal:
            assert float(np.max(diferenca[:, :, outro])) > 0
        else:
            assert float(np.max(np.abs(diferenca[:, :, outro]))) == 0.0


def test_fechar_a_fonte_sintetica_nao_falha() -> None:
    assert FonteSintetica(ParametrosSimulacao(duracao_s=1.0)).fechar() is None


# --------------------------------------------------------------------------
# Fontes de arquivo, webcam e tela: caminhos de erro
# --------------------------------------------------------------------------
def test_arquivo_inexistente_devolve_falha(tmp_path) -> None:
    resultado = abrir_arquivo(tmp_path / "nao_existe.mp4")
    assert resultado.falhou
    assert "não foi encontrado" in str(resultado.erro)


def test_arquivo_ilegivel_devolve_falha(tmp_path) -> None:
    invalido = tmp_path / "quebrado.mp4"
    invalido.write_bytes(b"isto nao e um video")
    assert abrir_arquivo(invalido).falhou


def test_ler_arquivo_sem_abrir_avisa() -> None:
    with pytest.raises(RuntimeError):
        list(FonteArquivo("qualquer.mp4").quadros())


def test_ler_webcam_sem_abrir_avisa() -> None:
    with pytest.raises(RuntimeError):
        list(FonteWebcam().quadros())


def test_webcam_inexistente_devolve_falha() -> None:
    resultado = FonteWebcam(indice=99).abrir()
    assert resultado.falhou
    assert "câmera" in str(resultado.erro).lower()


def test_fechar_webcam_nao_aberta_e_seguro() -> None:
    assert FonteWebcam().fechar() is None


@pytest.mark.parametrize("largura,altura", ((0, 100), (100, 0), (-1, 50)))
def test_regiao_de_tela_invalida_e_rejeitada(largura: int, altura: int) -> None:
    with pytest.raises(ValueError):
        FonteTela(largura=largura, altura=altura)


def test_ler_tela_sem_abrir_avisa() -> None:
    with pytest.raises(RuntimeError):
        list(FonteTela().quadros())


# --------------------------------------------------------------------------
# Avaliação
# --------------------------------------------------------------------------
@pytest.mark.parametrize("bpm", (48.0, 72.0, 120.0, 180.0, 220.0))
def test_frequencia_interferente_fica_na_banda(bpm: float) -> None:
    frequencia = frequencia_interferente(bpm)
    assert BandaCardiaca().contem_hz(frequencia)
    assert abs(frequencia - bpm / 60.0) > 0.3


def test_cenarios_padrao_cobrem_varias_condicoes() -> None:
    cenarios = cenarios_padrao()
    nomes = {cenario.nome for cenario in cenarios}
    assert len(nomes) >= 5
    assert "ideal" in nomes
    assert any("interferência" in nome for nome in nomes)


@pytest.mark.parametrize("algoritmo", ("chrom", "pos"))
def test_metodos_cromaticos_passam_na_bateria(algoritmo: str) -> None:
    """O critério que o sistema precisa cumprir para ser levado a sério."""
    resultados = avaliar(cenarios_padrao((60.0, 90.0, 130.0)), (algoritmo,))
    desempenho = resultados[algoritmo]
    assert desempenho.falhas == 0
    assert desempenho.taxa_de_acerto(3.0) == 1.0
    assert desempenho.erro_medio < 1.0


def test_resultado_vazio_devolve_nan() -> None:
    resultado = ResultadoAlgoritmo("teste")
    assert not np.isfinite(resultado.erro_medio)
    assert not np.isfinite(resultado.raiz_erro_quadratico)
    assert resultado.taxa_de_acerto() == 0.0


def test_falhas_contam_contra_a_taxa_de_acerto() -> None:
    resultado = ResultadoAlgoritmo("teste", erros=[0.5], falhas=1)
    assert resultado.total == 2
    assert resultado.taxa_de_acerto(3.0) == pytest.approx(0.5)


def test_tabela_em_markdown_tem_uma_linha_por_algoritmo() -> None:
    resultados = avaliar(cenarios_padrao((72.0,)), ALGORITMOS_DISPONIVEIS)
    tabela = formatar_tabela(resultados)
    for nome in ALGORITMOS_DISPONIVEIS:
        assert nome.upper() in tabela
    assert tabela.count("\n") == len(ALGORITMOS_DISPONIVEIS) + 1


def test_tabela_por_cenario() -> None:
    cenarios = cenarios_padrao((72.0,))
    tabela = formatar_por_cenario(por_cenario(cenarios, ("pos", "verde")))
    assert "POS" in tabela and "VERDE" in tabela
    assert "ideal" in tabela


def test_tabela_por_cenario_vazia() -> None:
    assert formatar_por_cenario({}) == ""


# --------------------------------------------------------------------------
# Interface
# --------------------------------------------------------------------------
def test_pincel_desenha_texto_acentuado() -> None:
    """Acentuação correta é requisito: a interface é em português."""
    pincel = PincelTexto()
    imagem = np.zeros((100, 400, 3), dtype=np.uint8)
    resultado = pincel.escrever(
        imagem, [ItemTexto("Frequência cardíaca, confiança e relação", (5, 20), 18)]
    )
    assert resultado.shape == imagem.shape
    assert int(np.sum(resultado)) > 0, "nada foi desenhado"


def test_pincel_sem_itens_devolve_a_imagem() -> None:
    imagem = np.zeros((50, 50, 3), dtype=np.uint8)
    assert np.array_equal(PincelTexto().escrever(imagem, []), imagem)


@pytest.mark.parametrize("tamanho", (12, 16, 24, 48, 64))
def test_medicao_de_texto_cresce_com_a_fonte(tamanho: int) -> None:
    largura, altura = PincelTexto().medir("Cardiocam", tamanho)
    assert largura > 0 and altura > 0


def test_medicao_maior_para_fonte_maior() -> None:
    pincel = PincelTexto()
    pequena, _ = pincel.medir("Cardiocam", 12)
    grande, _ = pincel.medir("Cardiocam", 48)
    assert grande > pequena


def test_painel_sem_analise_mostra_espera() -> None:
    painel, textos = construir_painel(EstadoQuadro())
    assert painel.shape[2] == 3
    assert any("Aguardando" in item.texto for item in textos)


@pytest.mark.parametrize("largura,altura", ((320, 200), (380, 240), (420, 300)))
def test_painel_respeita_as_dimensoes(largura: int, altura: int) -> None:
    painel, _ = construir_painel(EstadoQuadro(), largura=largura, altura=altura)
    assert painel.shape[:2] == (altura, largura)


def test_desenho_das_regioes_marca_a_imagem() -> None:
    quadro = np.zeros((200, 200, 3), dtype=np.uint8)
    estado = EstadoQuadro(caixa=Retangulo(50, 50, 100, 100))
    assert int(np.sum(desenhar_regioes(quadro.copy(), estado))) > 0


def test_composicao_completa_da_interface() -> None:
    """Percorre o caminho que a janela ao vivo usa a cada quadro."""
    from cardiocam.dominio.config import ConfiguracaoAnalise
    from cardiocam.pipeline.analisador import estimar_de_serie
    from tests.conftest import serie_de

    analise = estimar_de_serie(
        serie_de(72.0, duracao_s=16.0), ConfiguracaoAnalise(algoritmo="pos")
    ).desempacotar()

    renderizador = RenderizadorRosto(largura=320, altura=240)
    quadro = renderizador.desenhar(ruido=1.0)
    caixa = renderizador.caixa_esperada()
    amostra = ExtratorRGB().extrair(quadro, caixa).desempacotar()

    estado = EstadoQuadro(
        caixa=caixa,
        amostra=amostra,
        analise=analise,
        bpm_exibido=analise.estimativa.bpm,
        mensagem="Confiança alta.",
        progresso=1.0,
    )
    composto = compor(quadro, estado, PincelTexto())
    assert composto.shape[0] == quadro.shape[0]
    assert composto.shape[1] > quadro.shape[1]


def test_composicao_sem_medida_ainda_desenha() -> None:
    renderizador = RenderizadorRosto(largura=320, altura=240)
    quadro = renderizador.desenhar(ruido=1.0)
    estado = EstadoQuadro(mensagem="Coletando sinal.", progresso=0.4)
    composto = compor(quadro, estado, PincelTexto())
    assert composto.shape[1] > quadro.shape[1]


def test_salvar_serie_em_csv(tmp_path) -> None:
    from cardiocam.dominio.estimativa import EstimativaBPM
    from cardiocam.pipeline.analisador import RelatorioSessao
    from cardiocam.ui.app import salvar_serie

    relatorio = RelatorioSessao(
        estimativas=[EstimativaBPM.criar(1.2, 10.0, "pos", 10.0) for _ in range(3)]
    )
    destino = tmp_path / "sessao.csv"
    salvar_serie(str(destino), relatorio)

    linhas = destino.read_text(encoding="utf-8").strip().split("\n")
    assert linhas[0].startswith("janela,bpm")
    assert len(linhas) == 4
    assert "72.000" in linhas[1]


# --------------------------------------------------------------------------
# Linha de comando
# --------------------------------------------------------------------------
def test_analisador_exige_subcomando() -> None:
    with pytest.raises(SystemExit):
        construir_analisador().parse_args([])


@pytest.mark.parametrize(
    "argumentos",
    (
        ["ao-vivo"],
        ["arquivo", "video.mp4"],
        ["simular"],
        ["avaliar"],
        ["tela"],
    ),
)
def test_subcomandos_sao_reconhecidos(argumentos: list[str]) -> None:
    opcoes = construir_analisador().parse_args(argumentos)
    assert hasattr(opcoes, "funcao")


@pytest.mark.parametrize("algoritmo", ALGORITMOS_DISPONIVEIS)
def test_escolha_de_algoritmo_pela_linha_de_comando(algoritmo: str) -> None:
    opcoes = construir_analisador().parse_args(["simular", "--algoritmo", algoritmo])
    assert opcoes.algoritmo == algoritmo


def test_algoritmo_invalido_e_recusado() -> None:
    with pytest.raises(SystemExit):
        construir_analisador().parse_args(["simular", "--algoritmo", "magia"])


@pytest.mark.parametrize("bpm", (55.0, 72.0, 100.0))
def test_comando_simular_roda_de_ponta_a_ponta(bpm: float, capsys) -> None:
    # A janela vai explícita para o teste não quebrar quando o padrão mudar. O
    # que ele verifica é o caminho de ponta a ponta, não o valor do padrão.
    codigo = main(
        [
            "simular", "--bpm", str(bpm), "--duracao", "22",
            "--janela", "15", "--algoritmo", "pos",
        ]
    )
    assert codigo == 0
    saida = capsys.readouterr().out
    assert "Frequência cardíaca" in saida
    assert "Erro absoluto" in saida


def test_video_mais_curto_que_a_janela_avisa_o_motivo(capsys) -> None:
    """Não basta não medir: o programa precisa dizer por quê."""
    assert main(["simular", "--bpm", "72", "--duracao", "8", "--janela", "15"]) == 0
    saida = capsys.readouterr().out
    assert "Nenhuma janela" in saida
    assert "mais curto que a janela" in saida


def test_janela_padrao_da_linha_de_comando() -> None:
    """A janela padrão de 25 s foi escolhida por medição em rosto real: passar
    de 15 para 25 derrubou a dispersão entre janelas de 8,7 para 3,2 bpm."""
    assert construir_analisador().parse_args(["ao-vivo"]).janela == 25.0


def test_comando_avaliar_imprime_tabela(capsys) -> None:
    assert main(["avaliar"]) == 0
    saida = capsys.readouterr().out
    assert "Algoritmo" in saida
    assert "POS" in saida


def test_comando_avaliar_grava_relatorio(tmp_path, capsys) -> None:
    destino = tmp_path / "relatorio.md"
    assert main(["avaliar", "--saida", str(destino)]) == 0
    conteudo = destino.read_text(encoding="utf-8")
    assert "# Avaliação dos algoritmos" in conteudo
    assert "CHROM" in conteudo


def test_comando_arquivo_inexistente_devolve_erro(capsys) -> None:
    assert main(["arquivo", "inexistente_de_verdade.mp4"]) == 1
    assert "Erro" in capsys.readouterr().err


def test_comando_ao_vivo_sem_camera_devolve_erro(capsys) -> None:
    assert main(["ao-vivo", "--camera", "99"]) == 1
    assert "Erro" in capsys.readouterr().err
