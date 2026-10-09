"""Controles positivos e negativos dos métodos optativos."""

import cv2
import numpy as np
import pytest

from cardiocam.dominio.sinal import SinalPulso
from cardiocam.pesquisa.espacial import extrair_regioes, extrair_ssr
from cardiocam.pesquisa.estabilizacao import EstabilizadorOptico, pose_aproveitavel, alinhar_pelos_olhos
from cardiocam.pesquisa.estimacao import Candidato, Consenso, RastreadorTemporal, comparar_estimadores, fundir
from cardiocam.pesquisa.exposicao import ControleExposicaoPele, LimitesExposicao
from cardiocam.pesquisa.fotometria import corrigir_temporal, normalizar_imagem
from cardiocam.pesquisa.modalidades import extrair_bcg, medir_pupila, regioes_perioculares
from cardiocam.pesquisa.perturbacoes import Perturbacao
from cardiocam.visao.geometria import Retangulo
from cardiocam.visao.olhos import Olhos


@pytest.mark.parametrize("bpm", [45, 60, 72, 84, 120, 160, 200])
def test_estimadores_com_frequencia_conhecida(bpm):
    t = np.arange(600)/30
    onda = np.sin(2*np.pi*bpm/60*t)+.1*np.sin(4*np.pi*bpm/60*t)
    for valor in comparar_estimadores(SinalPulso(onda, 30)).values():
        assert abs(valor-bpm) < 1


@pytest.mark.parametrize("onda", [np.zeros(600), np.full(600, np.nan), np.full(600, np.inf)])
def test_sem_sinal_nao_inventa_bpm(onda):
    with pytest.raises(ValueError):
        comparar_estimadores(SinalPulso(onda, 30))


def test_ssr_recebe_segundo_momento_e_recupera_pulso():
    rng = np.random.default_rng(41)
    pixels = rng.normal([.65, .42, .29], [.03, .02, .015], (600, 3))
    momentos = []
    for t in np.arange(600)/30:
        quadro = pixels + np.sin(2*np.pi*1.4*t)*np.array([.003, .006, .002])
        momentos.append(quadro.T@quadro/len(quadro))
    pulso = extrair_ssr(np.array(momentos), 30)
    assert np.std(pulso.amostras) > 1e-8
    assert abs(comparar_estimadores(pulso)["periodograma"]-84) < 2


@pytest.mark.parametrize("momentos,fps", [(np.ones((50, 3, 3)), 30), (np.ones((2, 3, 3)), 30),
                                        (np.zeros((60, 3, 2)), 30), (np.full((60, 3, 3), np.nan), 30),
                                        (np.tile(np.eye(3), (60, 1, 1)), float("nan"))])
def test_ssr_rejeita_estatistica_inviavel(momentos, fps):
    with pytest.raises(ValueError):
        extrair_ssr(momentos, fps)


def test_extracao_espacial_sem_fallback_de_pele():
    imagem = np.full((90, 90, 3), [80, 130, 180], np.uint8)
    r = extrair_regioes(imagem, Retangulo(0, 0, 90, 90))
    assert len(r) == 9
    amostra = r["r0c0"]
    assert amostra.fracao_pele == 1
    assert np.allclose(amostra.segundo_momento, np.outer(amostra.rgb, amostra.rgb))
    assert extrair_regioes(np.zeros_like(imagem), Retangulo(0, 0, 90, 90)) == {}


def test_consenso_exige_regioes_e_metodos_e_nao_premia_snr():
    candidatos = [Candidato("a", "pos", 72, 5), Candidato("b", "chrom", 74, 4),
                  Candidato("c", "ica", 140, 60)]
    assert fundir(candidatos).bpm == 73
    assert fundir(candidatos[:1]).bpm is None
    assert fundir([Candidato("a", "pos", 72, 5), Candidato("a", "chrom", 72, 5)]).bpm is None
    assert fundir([Candidato("a", "pos", 72, 60, correlacao_fundo=.99), candidatos[1]]).bpm is None
    assert fundir(candidatos[:2]+[Candidato("x", "pos", 130, 5), Candidato("y", "chrom", 131, 5)]).bpm is None
    assert fundir([Candidato("a", "pos", 72, 20, correlacao_fundo=None), candidatos[1]]).bpm is None


def test_rastreador_temporal_recusa_salto_e_reinicia_sem_valor_antigo():
    r = RastreadorTemporal()
    c = lambda v: Consenso(v, (), "teste")
    assert r.atualizar(0, c(72)) == 72
    assert r.atualizar(1, c(140)) is None
    assert r.atualizar(2, c(None)) is None
    assert r.atualizar(5, c(140)) == 140
    with pytest.raises(ValueError):
        r.atualizar(5, c(141))


def test_estabilizacao_corrige_translacao_sem_perder_cor():
    rng = np.random.default_rng(42)
    imagem = rng.integers(20, 220, (160, 160, 3), dtype=np.uint8)
    s = EstabilizadorOptico()
    assert s.atualizar(imagem, Retangulo(20, 20, 100, 100), 0).reiniciado
    movida = cv2.warpAffine(imagem, np.float32([[1, 0, 3], [0, 1, 2]]), (160, 160))
    resultado = s.atualizar(movida, Retangulo(23, 22, 100, 100), 1/30)
    assert resultado.valido and not resultado.reiniciado
    assert np.allclose(resultado.movimento_px, [3, 2], atol=.2)
    assert np.mean(np.abs(resultado.imagem[30:100, 30:100].astype(float)-imagem[30:100, 30:100])) < 3
    assert s.atualizar(movida, Retangulo(23, 22, 100, 100), 2).reiniciado
    with pytest.raises(ValueError):
        s.atualizar(imagem, Retangulo(0, 0, 100, 100), 2)


def test_pose_olhos_observados_e_regioes_perioculares():
    olhos = Olhos((30, 40), (70, 40))
    assert pose_aproveitavel(olhos, Retangulo(0, 0, 100, 100))
    assert not pose_aproveitavel(Olhos((30, 20), (70, 70)), Retangulo(0, 0, 100, 100))
    for r in regioes_perioculares(olhos):
        assert r.y > olhos.linha


def test_alinhamento_de_olhos_observados_corrige_deslocamento():
    imagem = np.zeros((100, 100, 3), np.uint8)
    imagem[30:50, 30:50] = [80, 130, 180]
    alinhada = alinhar_pelos_olhos(imagem, Olhos((35, 40), (75, 40)), Olhos((30, 30), (70, 30)))
    assert np.array_equal(alinhada[20:40, 25:45], imagem[30:50, 30:50])


def test_pupila_rgb_mede_elipse_e_recusa_piscada_reflexo():
    olho = np.full((60, 100, 3), 180, np.uint8)
    cv2.ellipse(olho, (50, 30), (10, 9), 0, 0, 360, (20, 20, 20), -1)
    p = medir_pupila(olho)
    assert p is not None and np.allclose(p.centro, (50, 30), atol=1)
    assert 17 < p.diametro_px < 22
    assert medir_pupila(np.zeros_like(olho)) is None
    assert medir_pupila(np.full_like(olho, 255)) is None


def test_bcg_com_deslocamento_conhecido_nao_e_referencia_fisiologica():
    t = np.arange(600)/30
    trajetorias = np.zeros((600, 4, 2))
    trajetorias[:, :, 1] = 20+np.sin(2*np.pi*1.2*t[:, None])*[.5, .8, 1, 1.1]
    p = extrair_bcg(trajetorias, 30)
    assert abs(comparar_estimadores(p)["periodograma"]-72) < 1
    with pytest.raises(ValueError):
        extrair_bcg(np.zeros((600, 4, 2)), 30)


def test_correcao_remove_luz_do_fundo_preservando_pulso():
    t = np.arange(600)/30
    pulso, luz = np.sin(2*np.pi*1.2*t), np.sin(2*np.pi*.2*t)
    rgb = np.array([100+luz*10+pulso, 80+luz*8+pulso*2, 60+luz*6+pulso*.5])
    fundo = np.array([100+luz*10, 80+luz*8, 60+luz*6])
    y = corrigir_temporal(rgb, 30, fundo)
    assert np.corrcoef(y[1], pulso)[0, 1] > .99
    assert np.array_equal(corrigir_temporal(rgb, 30), rgb)
    assert abs(comparar_estimadores(SinalPulso(corrigir_temporal(rgb, 30, fundo, .16)[1], 30))["periodograma"]-72) < 1


@pytest.mark.parametrize("metodo", ["nenhum", "retinex", "crominancia"])
def test_fotometria_nao_muta_imagem(metodo):
    imagem = np.full((60, 80, 3), [80, 130, 180], np.uint8)
    original = imagem.copy()
    resultado = normalizar_imagem(imagem, metodo)
    assert resultado.shape == imagem.shape and resultado.dtype == np.uint8
    assert np.array_equal(imagem, original)


def test_exposicao_confirma_driver_e_trava_antes_de_medir():
    class Dispositivo:
        valor = -6.
        ignorar = False
        def get(self, _): return self.valor
        def set(self, _, v):
            if not self.ignorar: self.valor = v
            return True
    d = Dispositivo()
    c = ControleExposicaoPele(LimitesExposicao(-10, -1, 1))
    assert c.ajustar(d, np.full((60, 3), 40)).confirmado
    assert d.valor == -5
    d.ignorar = True
    assert not c.ajustar(d, np.full((60, 3), 40)).confirmado
    assert d.valor == -5
    d.ignorar = False
    for _ in range(3): ajuste = c.ajustar(d, np.full((60, 3), 120))
    assert ajuste.estavel
    assert c.ajustar(d, np.full((60, 3), 250)).estavel and d.valor == -5
    d.valor = -4
    assert not c.ajustar(d, np.full((60, 3), 120)).estavel


def test_perturbacao_e_reproduzivel_e_nao_altera_entrada():
    imagem = np.full((60, 80, 3), 120, np.uint8)
    opcoes = Perturbacao(movimento_px=2, iluminacao=.3, ruido=5, congelar_cada=2, semente=4)
    a, b = opcoes.criar(), opcoes.criar()
    sequencia_a = [a(imagem, i/30, i) for i in range(5)]
    sequencia_b = [b(imagem, i/30, i) for i in range(5)]
    assert all(np.array_equal(x, y) for x, y in zip(sequencia_a, sequencia_b))
    assert np.array_equal(sequencia_a[1], sequencia_a[2])
    assert np.all(imagem == 120)
