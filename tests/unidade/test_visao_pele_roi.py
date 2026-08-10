"""Testes da segmentação de pele e da escolha de regiões."""

from __future__ import annotations

import cv2
import numpy as np
import pytest

from cardiocam.visao.geometria import Retangulo
from cardiocam.visao.pele import (
    descartar_extremos,
    mascara_pele,
    proporcao_de_pele,
)
from cardiocam.visao.roi import RegiaoInteresse, descricao, regioes_de

# Tons de pele variados em BGR, do mais claro ao mais escuro. A segmentação
# precisa funcionar para todos: é um requisito de correção, não de estética.
TONS_DE_PELE = (
    (170, 195, 225),
    (150, 175, 205),
    (130, 155, 185),
    (105, 130, 160),
    (85, 105, 135),
    (65, 85, 110),
    (48, 65, 88),
    (38, 52, 72),
)

CORES_NAO_PELE = (
    (255, 0, 0),
    (0, 255, 0),
    (255, 255, 0),
    (200, 30, 30),
    (20, 20, 20),
    (250, 250, 250),
)


def bloco(cor: tuple[int, int, int], lado: int = 60) -> np.ndarray:
    return np.full((lado, lado, 3), cor, dtype=np.uint8)


@pytest.mark.parametrize("cor", TONS_DE_PELE)
def test_tons_de_pele_sao_reconhecidos(cor: tuple[int, int, int]) -> None:
    proporcao = float(np.mean(mascara_pele(bloco(cor))))
    assert proporcao > 0.9, f"tom {cor} reconhecido em apenas {proporcao:.2%}"


@pytest.mark.parametrize("cor", CORES_NAO_PELE)
def test_cores_que_nao_sao_pele_sao_rejeitadas(cor: tuple[int, int, int]) -> None:
    assert float(np.mean(mascara_pele(bloco(cor)))) < 0.5


@pytest.mark.parametrize("cor", TONS_DE_PELE)
@pytest.mark.parametrize("suavizar", (True, False))
def test_mascara_tem_o_tamanho_da_imagem(
    cor: tuple[int, int, int], suavizar: bool
) -> None:
    imagem = bloco(cor, 40)
    mascara = mascara_pele(imagem, suavizar=suavizar)
    assert mascara.shape == imagem.shape[:2]
    assert mascara.dtype == bool


@pytest.mark.parametrize("cor", TONS_DE_PELE[:4])
def test_pixel_escuro_demais_e_descartado(cor: tuple[int, int, int]) -> None:
    """Em sombra fechada a informação de cor deixa de ser confiável."""
    escuro = tuple(int(c * 0.08) for c in cor)
    assert float(np.mean(mascara_pele(bloco(escuro)))) < 0.5


def test_imagem_vazia_devolve_mascara_vazia() -> None:
    assert mascara_pele(np.zeros((0, 0, 3), dtype=np.uint8)).size == 0


@pytest.mark.parametrize("formato", ((10, 10), (10, 10, 1), (10, 10, 4)))
def test_imagem_sem_tres_canais_e_rejeitada(formato: tuple) -> None:
    with pytest.raises(ValueError):
        mascara_pele(np.zeros(formato, dtype=np.uint8))


@pytest.mark.parametrize("cor", TONS_DE_PELE)
def test_proporcao_de_pele_alta_em_bloco_uniforme(cor: tuple[int, int, int]) -> None:
    assert proporcao_de_pele(bloco(cor)) > 0.9


@pytest.mark.parametrize("cor", CORES_NAO_PELE)
def test_proporcao_de_pele_baixa_em_cor_estranha(cor: tuple[int, int, int]) -> None:
    assert proporcao_de_pele(bloco(cor)) < 0.5


def test_proporcao_de_imagem_vazia_e_zero() -> None:
    assert proporcao_de_pele(np.zeros((0, 0, 3), dtype=np.uint8)) == 0.0


@pytest.mark.parametrize("fracao_pele", (0.25, 0.5, 0.75))
def test_proporcao_acompanha_a_area_de_pele(fracao_pele: float) -> None:
    imagem = np.full((100, 100, 3), (255, 0, 0), dtype=np.uint8)
    linhas = int(100 * fracao_pele)
    imagem[:linhas] = (150, 175, 205)
    assert abs(proporcao_de_pele(imagem) - fracao_pele) < 0.1


@pytest.mark.parametrize("percentil", (0.0, 1.0, 5.0, 10.0, 25.0, 49.0))
def test_descarte_de_extremos_reduz_a_dispersao(percentil: float) -> None:
    valores = np.concatenate(
        [np.random.default_rng(0).normal(100, 5, 1000), np.array([0.0, 255.0])]
    )
    filtrado = descartar_extremos(valores, percentil)
    if percentil > 0:
        assert float(np.std(filtrado)) <= float(np.std(valores))
    assert filtrado.size > 0


@pytest.mark.parametrize("percentil", (-1.0, 50.0, 80.0))
def test_percentil_invalido_e_rejeitado(percentil: float) -> None:
    with pytest.raises(ValueError):
        descartar_extremos(np.arange(100.0), percentil)


def test_descarte_de_vetor_vazio() -> None:
    assert descartar_extremos(np.zeros(0)).size == 0


# --------------------------------------------------------------------------
# Regiões de interesse
# --------------------------------------------------------------------------
CAIXAS = (
    Retangulo(0, 0, 100, 100),
    Retangulo(50, 60, 120, 140),
    Retangulo(200, 100, 80, 80),
    Retangulo(10, 10, 300, 320),
)


@pytest.mark.parametrize("caixa", CAIXAS)
@pytest.mark.parametrize("regiao", tuple(RegiaoInteresse))
def test_regioes_ficam_dentro_da_caixa_do_rosto(
    caixa: Retangulo, regiao: RegiaoInteresse
) -> None:
    for sub in regioes_de(caixa, regiao):
        assert sub.x >= caixa.x
        assert sub.y >= caixa.y
        assert sub.direita <= caixa.direita + 1
        assert sub.base <= caixa.base + 1
        assert not sub.vazio


@pytest.mark.parametrize("caixa", CAIXAS)
def test_testa_fica_na_metade_superior(caixa: Retangulo) -> None:
    testa = regioes_de(caixa, RegiaoInteresse.TESTA)[0]
    assert testa.base < caixa.y + caixa.altura * 0.5


@pytest.mark.parametrize("caixa", CAIXAS)
def test_bochechas_sao_duas_e_simetricas(caixa: Retangulo) -> None:
    bochechas = regioes_de(caixa, RegiaoInteresse.BOCHECHAS)
    assert len(bochechas) == 2
    esquerda, direita = bochechas
    assert esquerda.x < direita.x
    assert esquerda.largura == direita.largura


@pytest.mark.parametrize("caixa", CAIXAS)
def test_conjunto_completo_tem_tres_regioes(caixa: Retangulo) -> None:
    assert len(regioes_de(caixa, RegiaoInteresse.TESTA_E_BOCHECHAS)) == 3


@pytest.mark.parametrize("caixa", CAIXAS)
def test_regioes_nao_se_sobrepoem(caixa: Retangulo) -> None:
    regioes = regioes_de(caixa, RegiaoInteresse.TESTA_E_BOCHECHAS)
    for i, primeira in enumerate(regioes):
        for segunda in regioes[i + 1 :]:
            assert primeira.sobreposicao(segunda) == 0.0


@pytest.mark.parametrize("regiao", tuple(RegiaoInteresse))
def test_descricao_e_texto_legivel(regiao: RegiaoInteresse) -> None:
    texto = descricao(regiao)
    assert isinstance(texto, str) and len(texto) > 3


@pytest.mark.parametrize("caixa", CAIXAS)
def test_regiao_central_evita_as_bordas(caixa: Retangulo) -> None:
    central = regioes_de(caixa, RegiaoInteresse.ROSTO_CENTRAL)[0]
    assert central.x > caixa.x
    assert central.direita < caixa.direita
