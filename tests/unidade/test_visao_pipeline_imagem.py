"""Testes do detector de rosto, do rastreador e do extrator RGB.

Estes testes rodam sobre imagens de fato renderizadas, não sobre matrizes
inventadas: a cascata de Haar precisa encontrar um rosto de verdade para que o
teste signifique alguma coisa.
"""

from __future__ import annotations

import numpy as np
import pytest

from cardiocam.dominio.erros import RegiaoInvalida, RostoNaoEncontrado
from cardiocam.fontes.sintetica import RenderizadorRosto
from cardiocam.visao.detector_face import (
    CASCATA_ALTERNATIVA,
    CASCATA_PADRAO,
    DetectorCentral,
    DetectorHaar,
    DetectorRegiaoFixa,
)
from cardiocam.visao.extrator import ExtratorRGB
from cardiocam.visao.geometria import Retangulo
from cardiocam.visao.rastreador import RastreadorRosto
from cardiocam.visao.roi import RegiaoInteresse

RESOLUCOES = ((240, 180), (320, 240), (400, 300), (640, 480))
TONS = ((170, 195, 225), (150, 175, 205), (105, 130, 160), (65, 85, 110))


class DetectorInstavel:
    """Detector controlado, para exercitar o rastreador sem depender do Haar."""

    def __init__(self, respostas: list[Retangulo | None]) -> None:
        self.respostas = respostas
        self.chamadas = 0

    def detectar(self, quadro):
        from cardiocam.dominio.resultado import Falha, Ok

        indice = min(self.chamadas, len(self.respostas) - 1)
        self.chamadas += 1
        resposta = self.respostas[indice]
        return Ok(resposta) if resposta is not None else Falha(RostoNaoEncontrado())


# --------------------------------------------------------------------------
# Detector
# --------------------------------------------------------------------------
@pytest.mark.parametrize("largura,altura", RESOLUCOES)
def test_haar_encontra_o_rosto_renderizado(largura: int, altura: int) -> None:
    quadro = RenderizadorRosto(largura=largura, altura=altura).desenhar(ruido=0.0)
    resultado = DetectorHaar().detectar(quadro)
    assert resultado.ok, f"nenhum rosto encontrado em {largura}x{altura}"


@pytest.mark.parametrize("largura,altura", RESOLUCOES)
def test_caixa_detectada_cobre_o_rosto_esperado(largura: int, altura: int) -> None:
    renderizador = RenderizadorRosto(largura=largura, altura=altura)
    quadro = renderizador.desenhar(ruido=0.0)
    detectada = DetectorHaar().detectar(quadro).desempacotar()
    esperada = renderizador.caixa_esperada()
    assert detectada.sobreposicao(esperada) > 0.35


@pytest.mark.parametrize("tom", TONS)
def test_haar_funciona_com_diferentes_tons_de_pele(tom: tuple) -> None:
    quadro = RenderizadorRosto(tom_pele=tom).desenhar(ruido=0.0)
    assert DetectorHaar().detectar(quadro).ok


@pytest.mark.parametrize("ruido", (0.0, 1.0, 3.0, 6.0))
def test_haar_tolera_ruido_moderado(ruido: float) -> None:
    quadro = RenderizadorRosto().desenhar(ruido=ruido, semente=1)
    assert DetectorHaar().detectar(quadro).ok


@pytest.mark.parametrize("cascata", (CASCATA_PADRAO, CASCATA_ALTERNATIVA))
def test_ambas_as_cascatas_carregam_e_detectam(cascata: str) -> None:
    quadro = RenderizadorRosto().desenhar(ruido=0.0)
    assert DetectorHaar(cascata=cascata).detectar(quadro).ok


def test_imagem_sem_rosto_devolve_falha() -> None:
    vazio = np.full((240, 320, 3), 90, dtype=np.uint8)
    resultado = DetectorHaar().detectar(vazio)
    assert resultado.falhou
    assert isinstance(resultado.erro, RostoNaoEncontrado)


@pytest.mark.parametrize("quadro", (None, np.zeros((0, 0, 3), dtype=np.uint8)))
def test_quadro_invalido_devolve_falha(quadro) -> None:
    assert DetectorHaar().detectar(quadro).falhou


def test_cascata_inexistente_avisa_claramente() -> None:
    with pytest.raises(RuntimeError, match="cascata"):
        DetectorHaar(cascata="haarcascade_que_nao_existe.xml")


@pytest.mark.parametrize("largura,altura", RESOLUCOES)
def test_detector_de_regiao_fixa_devolve_o_pedido(largura: int, altura: int) -> None:
    regiao = Retangulo(10, 10, 50, 50)
    quadro = np.zeros((altura, largura, 3), dtype=np.uint8)
    assert DetectorRegiaoFixa(regiao).detectar(quadro).desempacotar() == regiao


def test_regiao_fixa_vazia_e_rejeitada() -> None:
    with pytest.raises(ValueError):
        DetectorRegiaoFixa(Retangulo(0, 0, 0, 0))


def test_regiao_fixa_e_limitada_ao_quadro() -> None:
    detector = DetectorRegiaoFixa(Retangulo(0, 0, 500, 500))
    caixa = detector.detectar(np.zeros((100, 100, 3), dtype=np.uint8)).desempacotar()
    assert caixa.largura == 100 and caixa.altura == 100


@pytest.mark.parametrize("fracao", (0.2, 0.4, 0.6, 0.8, 1.0))
def test_detector_central_recorta_a_fracao_pedida(fracao: float) -> None:
    quadro = np.zeros((200, 300, 3), dtype=np.uint8)
    caixa = DetectorCentral(fracao).detectar(quadro).desempacotar()
    assert caixa.largura == pytest.approx(300 * fracao, abs=1)
    assert caixa.altura == pytest.approx(200 * fracao, abs=1)


@pytest.mark.parametrize("fracao", (0.0, -0.5, 1.5))
def test_fracao_central_invalida_e_rejeitada(fracao: float) -> None:
    with pytest.raises(ValueError):
        DetectorCentral(fracao)


# --------------------------------------------------------------------------
# Rastreador
# --------------------------------------------------------------------------
@pytest.mark.parametrize("suavizacao", (0.1, 0.25, 0.5, 1.0))
def test_primeira_deteccao_e_adotada_integralmente(suavizacao: float) -> None:
    caixa = Retangulo(10, 20, 60, 60)
    rastreador = RastreadorRosto(DetectorInstavel([caixa]), suavizacao=suavizacao)
    assert rastreador.atualizar(np.zeros((100, 100, 3), np.uint8)).desempacotar() == caixa


@pytest.mark.parametrize("suavizacao", (0.1, 0.25, 0.5))
def test_suavizacao_atrasa_a_convergencia(suavizacao: float) -> None:
    """Quanto menor o peso, mais devagar a caixa persegue a detecção nova."""
    inicial = Retangulo(0, 0, 60, 60)
    destino = Retangulo(20, 0, 60, 60)
    rastreador = RastreadorRosto(
        DetectorInstavel([inicial, destino, destino, destino]), suavizacao=suavizacao
    )
    quadro = np.zeros((200, 200, 3), np.uint8)
    rastreador.atualizar(quadro)
    apos_um = rastreador.atualizar(quadro).desempacotar()
    assert 0 < apos_um.x < 20
    assert apos_um.x == pytest.approx(20 * suavizacao, abs=1.5)


@pytest.mark.parametrize("suavizacao", (0.0, -0.1, 1.5))
def test_suavizacao_invalida_e_rejeitada(suavizacao: float) -> None:
    with pytest.raises(ValueError):
        RastreadorRosto(DetectorInstavel([]), suavizacao=suavizacao)


@pytest.mark.parametrize("intervalo", (0, -1))
def test_intervalo_de_deteccao_invalido_e_rejeitado(intervalo: int) -> None:
    with pytest.raises(ValueError):
        RastreadorRosto(DetectorInstavel([]), intervalo_deteccao=intervalo)


@pytest.mark.parametrize("tolerancia", (3, 5, 10, 15))
def test_perda_breve_mantem_a_ultima_caixa(tolerancia: int) -> None:
    caixa = Retangulo(10, 10, 50, 50)
    respostas = [caixa] + [None] * (tolerancia - 1)
    rastreador = RastreadorRosto(
        DetectorInstavel(respostas), tolerancia_quadros=tolerancia
    )
    quadro = np.zeros((100, 100, 3), np.uint8)
    for _ in range(tolerancia):
        resultado = rastreador.atualizar(quadro)
        assert resultado.ok, "a caixa deveria persistir durante a perda breve"


@pytest.mark.parametrize("tolerancia", (2, 5, 10))
def test_perda_prolongada_desiste(tolerancia: int) -> None:
    caixa = Retangulo(10, 10, 50, 50)
    respostas = [caixa] + [None] * (tolerancia + 5)
    rastreador = RastreadorRosto(
        DetectorInstavel(respostas), tolerancia_quadros=tolerancia
    )
    quadro = np.zeros((100, 100, 3), np.uint8)
    for _ in range(tolerancia + 5):
        resultado = rastreador.atualizar(quadro)
    assert resultado.falhou
    assert rastreador.perdeu_o_rosto


@pytest.mark.parametrize("salto", (60, 90, 120))
def test_deteccao_com_salto_absurdo_e_rejeitada(salto: int) -> None:
    """Um falso positivo do outro lado da imagem não deve mover a região."""
    estavel = Retangulo(10, 10, 50, 50)
    disparate = Retangulo(10 + salto, 10, 50, 50)
    rastreador = RastreadorRosto(
        DetectorInstavel([estavel, disparate]), salto_maximo=0.35
    )
    quadro = np.zeros((300, 300, 3), np.uint8)
    rastreador.atualizar(quadro)
    rastreador.atualizar(quadro)
    assert rastreador.deteccoes_rejeitadas >= 1


@pytest.mark.parametrize("razao", (2.0, 3.0, 0.4, 0.3))
def test_mudanca_brusca_de_escala_e_rejeitada(razao: float) -> None:
    estavel = Retangulo(100, 100, 50, 50)
    redimensionado = Retangulo(100, 100, int(50 * razao), int(50 * razao))
    rastreador = RastreadorRosto(DetectorInstavel([estavel, redimensionado]))
    quadro = np.zeros((400, 400, 3), np.uint8)
    rastreador.atualizar(quadro)
    rastreador.atualizar(quadro)
    assert rastreador.deteccoes_rejeitadas >= 1


@pytest.mark.parametrize("intervalo", (1, 2, 3, 5))
def test_intervalo_de_deteccao_reduz_chamadas(intervalo: int) -> None:
    caixa = Retangulo(10, 10, 50, 50)
    detector = DetectorInstavel([caixa] * 50)
    rastreador = RastreadorRosto(detector, intervalo_deteccao=intervalo)
    quadro = np.zeros((100, 100, 3), np.uint8)
    for _ in range(20):
        rastreador.atualizar(quadro)
    esperado = len([i for i in range(20) if i % intervalo == 0])
    assert detector.chamadas <= esperado + 1


def test_reiniciar_limpa_o_estado() -> None:
    caixa = Retangulo(10, 10, 50, 50)
    rastreador = RastreadorRosto(DetectorInstavel([caixa]))
    rastreador.atualizar(np.zeros((100, 100, 3), np.uint8))
    assert rastreador.caixa_atual is not None
    rastreador.reiniciar()
    assert rastreador.caixa_atual is None


def test_rastreador_estabiliza_deteccao_tremida() -> None:
    """O teste que justifica o módulo: tremor na detecção precisa virar uma
    trajetória suave, senão o tremor entra no sinal como artefato."""
    gerador = np.random.default_rng(0)
    respostas = [
        Retangulo(100 + int(gerador.normal(0, 3)), 100 + int(gerador.normal(0, 3)), 60, 60)
        for _ in range(60)
    ]
    detector = DetectorInstavel(respostas)
    rastreador = RastreadorRosto(detector, suavizacao=0.2)
    quadro = np.zeros((300, 300, 3), np.uint8)

    posicoes = []
    for _ in range(60):
        posicoes.append(rastreador.atualizar(quadro).desempacotar().x)

    tremor_entrada = float(np.std([r.x for r in respostas]))
    tremor_saida = float(np.std(posicoes[10:]))
    assert tremor_saida < tremor_entrada


# --------------------------------------------------------------------------
# Extrator
# --------------------------------------------------------------------------
@pytest.mark.parametrize("largura,altura", RESOLUCOES)
@pytest.mark.parametrize("regiao", tuple(RegiaoInteresse))
def test_extracao_devolve_medias_plausiveis(
    largura: int, altura: int, regiao: RegiaoInteresse
) -> None:
    renderizador = RenderizadorRosto(largura=largura, altura=altura)
    quadro = renderizador.desenhar(ruido=1.0, semente=0)
    caixa = renderizador.caixa_esperada()

    resultado = ExtratorRGB(regiao=regiao).extrair(quadro, caixa)
    assert resultado.ok
    amostra = resultado.desempacotar()
    for canal in (amostra.vermelho, amostra.verde, amostra.azul):
        assert 0.0 <= canal <= 255.0
    assert amostra.pixels_usados > 0


@pytest.mark.parametrize("modulacao", (0.90, 0.95, 1.0, 1.05, 1.10))
def test_media_extraida_acompanha_a_modulacao(modulacao: float) -> None:
    """Se a pele clareia, a média medida precisa subir. É a premissa de todo o
    resto do sistema."""
    renderizador = RenderizadorRosto()
    caixa = renderizador.caixa_esperada()
    extrator = ExtratorRGB()

    referencia = extrator.extrair(
        renderizador.desenhar(1.0, ruido=0.0), caixa
    ).desempacotar()
    medida = extrator.extrair(
        renderizador.desenhar(modulacao, ruido=0.0), caixa
    ).desempacotar()

    if modulacao > 1.0:
        assert medida.verde > referencia.verde
    elif modulacao < 1.0:
        assert medida.verde < referencia.verde


@pytest.mark.parametrize("amplitude", (0.02, 0.05, 0.10))
def test_sensibilidade_relativa_da_media(amplitude: float) -> None:
    renderizador = RenderizadorRosto()
    caixa = renderizador.caixa_esperada()
    extrator = ExtratorRGB()
    base = extrator.extrair(renderizador.desenhar(1.0, ruido=0.0), caixa).desempacotar()
    alterado = extrator.extrair(
        renderizador.desenhar(1.0 + amplitude, ruido=0.0), caixa
    ).desempacotar()
    variacao = (alterado.verde - base.verde) / base.verde
    assert variacao == pytest.approx(amplitude, rel=0.35)


@pytest.mark.parametrize("usar_mascara", (True, False))
@pytest.mark.parametrize("percentil", (0.0, 5.0, 10.0))
def test_opcoes_do_extrator_nao_quebram(usar_mascara: bool, percentil: float) -> None:
    renderizador = RenderizadorRosto()
    quadro = renderizador.desenhar(ruido=2.0, semente=2)
    resultado = ExtratorRGB(
        usar_mascara_pele=usar_mascara, percentil_descarte=percentil
    ).extrair(quadro, renderizador.caixa_esperada())
    assert resultado.ok


@pytest.mark.parametrize("percentil", (-1.0, 50.0, 90.0))
def test_percentil_invalido_no_extrator(percentil: float) -> None:
    with pytest.raises(ValueError):
        ExtratorRGB(percentil_descarte=percentil)


def test_extracao_em_quadro_vazio_falha() -> None:
    resultado = ExtratorRGB().extrair(
        np.zeros((0, 0, 3), np.uint8), Retangulo(0, 0, 10, 10)
    )
    assert resultado.falhou
    assert isinstance(resultado.erro, RegiaoInvalida)


def test_extracao_em_imagem_de_um_canal_falha() -> None:
    resultado = ExtratorRGB().extrair(
        np.zeros((100, 100), np.uint8), Retangulo(0, 0, 50, 50)
    )
    assert resultado.falhou


def test_regiao_totalmente_fora_do_quadro_falha() -> None:
    quadro = np.full((100, 100, 3), 150, np.uint8)
    resultado = ExtratorRGB().extrair(quadro, Retangulo(500, 500, 50, 50))
    assert resultado.falhou


def test_regiao_pequena_demais_falha() -> None:
    quadro = np.full((100, 100, 3), (150, 175, 205), np.uint8)
    resultado = ExtratorRGB(pixels_minimos=10_000).extrair(
        quadro, Retangulo(0, 0, 20, 20)
    )
    assert resultado.falhou


@pytest.mark.parametrize("largura,altura", RESOLUCOES)
def test_amostra_registra_as_regioes_medidas(largura: int, altura: int) -> None:
    renderizador = RenderizadorRosto(largura=largura, altura=altura)
    quadro = renderizador.desenhar(ruido=0.0)
    amostra = ExtratorRGB().extrair(quadro, renderizador.caixa_esperada()).desempacotar()
    assert len(amostra.regioes) == 3
    assert np.allclose(amostra.como_vetor(), [amostra.vermelho, amostra.verde, amostra.azul])
