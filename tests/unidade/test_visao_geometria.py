"""Testes do retângulo e das operações geométricas."""

from __future__ import annotations

import numpy as np
import pytest

from cardiocam.dominio.erros import RegiaoInvalida
from cardiocam.visao.geometria import Retangulo

RETANGULOS = (
    (0, 0, 10, 10),
    (5, 5, 20, 30),
    (100, 50, 64, 64),
    (0, 0, 1, 1),
    (37, 91, 13, 7),
)


@pytest.mark.parametrize("x,y,largura,altura", RETANGULOS)
def test_area_e_produto_dos_lados(x: int, y: int, largura: int, altura: int) -> None:
    assert Retangulo(x, y, largura, altura).area == largura * altura


@pytest.mark.parametrize("x,y,largura,altura", RETANGULOS)
def test_bordas_direita_e_base(x: int, y: int, largura: int, altura: int) -> None:
    retangulo = Retangulo(x, y, largura, altura)
    assert retangulo.direita == x + largura
    assert retangulo.base == y + altura


@pytest.mark.parametrize("x,y,largura,altura", RETANGULOS)
def test_centro(x: int, y: int, largura: int, altura: int) -> None:
    centro = Retangulo(x, y, largura, altura).centro
    assert centro == (x + largura / 2.0, y + altura / 2.0)


@pytest.mark.parametrize("largura,altura", ((0, 10), (10, 0), (0, 0)))
def test_retangulo_sem_area_e_vazio(largura: int, altura: int) -> None:
    assert Retangulo(0, 0, largura, altura).vazio


@pytest.mark.parametrize("largura,altura", ((-1, 10), (10, -1), (-5, -5)))
def test_dimensao_negativa_e_rejeitada(largura: int, altura: int) -> None:
    with pytest.raises(RegiaoInvalida):
        Retangulo(0, 0, largura, altura)


@pytest.mark.parametrize("x,y,largura,altura", RETANGULOS)
def test_como_tupla(x: int, y: int, largura: int, altura: int) -> None:
    assert Retangulo(x, y, largura, altura).como_tupla() == (x, y, largura, altura)


@pytest.mark.parametrize(
    "retangulo,limites",
    (
        ((-10, -10, 50, 50), (100, 100)),
        ((90, 90, 50, 50), (100, 100)),
        ((0, 0, 200, 200), (100, 100)),
        ((10, 10, 20, 20), (100, 100)),
    ),
)
def test_limitar_mantem_dentro_da_imagem(
    retangulo: tuple, limites: tuple
) -> None:
    limitado = Retangulo(*retangulo).limitar(*limites)
    assert limitado.x >= 0 and limitado.y >= 0
    assert limitado.direita <= limites[0]
    assert limitado.base <= limites[1]


@pytest.mark.parametrize("fora", ((-100, -100, 10, 10), (500, 500, 10, 10)))
def test_limitar_retangulo_totalmente_fora_gera_vazio(fora: tuple) -> None:
    assert Retangulo(*fora).limitar(100, 100).vazio


@pytest.mark.parametrize("fator", (0.5, 0.8, 1.0, 1.5, 2.0, 3.0))
def test_escalar_mantem_o_centro(fator: float) -> None:
    original = Retangulo(50, 50, 40, 60)
    escalado = original.escalar(fator)
    assert escalado.centro == pytest.approx(original.centro, abs=1.0)
    assert escalado.largura == pytest.approx(40 * fator, abs=1.0)


@pytest.mark.parametrize(
    "fracao", ((0.0, 0.0, 1.0, 1.0), (0.25, 0.25, 0.75, 0.75), (0.3, 0.15, 0.7, 0.3))
)
def test_fracao_produz_sub_retangulo(fracao: tuple) -> None:
    caixa = Retangulo(100, 200, 80, 120)
    sub = caixa.fracao(*fracao)
    assert sub.x >= caixa.x and sub.y >= caixa.y
    assert sub.direita <= caixa.direita + 1
    assert sub.base <= caixa.base + 1


@pytest.mark.parametrize(
    "fracao",
    (
        (-0.1, 0.0, 1.0, 1.0),
        (0.0, 0.0, 1.1, 1.0),
        (0.5, 0.0, 0.5, 1.0),
        (0.8, 0.0, 0.2, 1.0),
    ),
)
def test_fracao_invalida_e_rejeitada(fracao: tuple) -> None:
    with pytest.raises(RegiaoInvalida):
        Retangulo(0, 0, 100, 100).fracao(*fracao)


@pytest.mark.parametrize("x,y,largura,altura", RETANGULOS)
def test_recorte_tem_o_tamanho_pedido(
    x: int, y: int, largura: int, altura: int
) -> None:
    imagem = np.zeros((300, 300, 3), dtype=np.uint8)
    recorte = Retangulo(x, y, largura, altura).recortar(imagem)
    assert recorte.shape[:2] == (altura, largura)


def test_recorte_fora_da_imagem_devolve_vazio() -> None:
    imagem = np.zeros((100, 100, 3), dtype=np.uint8)
    assert Retangulo(500, 500, 20, 20).recortar(imagem).size == 0


@pytest.mark.parametrize("peso", (0.0, 0.1, 0.25, 0.5, 0.75, 1.0))
def test_interpolacao_entre_retangulos(peso: float) -> None:
    a = Retangulo(0, 0, 100, 100)
    b = Retangulo(100, 100, 200, 200)
    misturado = a.interpolar(b, peso)
    assert misturado.x == pytest.approx(peso * 100, abs=1)
    assert misturado.largura == pytest.approx(100 + peso * 100, abs=1)


@pytest.mark.parametrize("peso", (-1.0, 2.0, 100.0))
def test_interpolacao_limita_o_peso(peso: float) -> None:
    a = Retangulo(0, 0, 100, 100)
    b = Retangulo(100, 100, 100, 100)
    misturado = a.interpolar(b, peso)
    assert 0 <= misturado.x <= 100


def test_sobreposicao_identica_e_um() -> None:
    caixa = Retangulo(10, 10, 50, 50)
    assert caixa.sobreposicao(caixa) == pytest.approx(1.0)


@pytest.mark.parametrize(
    "outro", ((200, 200, 10, 10), (100, 0, 10, 10), (0, 100, 10, 10))
)
def test_sobreposicao_disjunta_e_zero(outro: tuple) -> None:
    assert Retangulo(0, 0, 50, 50).sobreposicao(Retangulo(*outro)) == 0.0


@pytest.mark.parametrize("deslocamento", (10, 20, 30, 40))
def test_sobreposicao_cai_com_o_afastamento(deslocamento: int) -> None:
    base = Retangulo(0, 0, 50, 50)
    deslocado = Retangulo(deslocamento, 0, 50, 50)
    valor = base.sobreposicao(deslocado)
    assert 0.0 <= valor <= 1.0
    mais_longe = base.sobreposicao(Retangulo(deslocamento + 5, 0, 50, 50))
    assert mais_longe <= valor
