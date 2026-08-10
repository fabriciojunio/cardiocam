"""Escolha das regiões de interesse dentro do rosto.

Nem todo pedaço de rosto serve igual. A testa é a melhor região: pele fina,
bem vascularizada, quase sem pelos e pouco deformada pela expressão facial. As
bochechas vêm em seguida. Boca e olhos são ruins de propósito — piscar e falar
produzem movimento na banda de frequência do coração, que é justamente o tipo de
artefato que não conseguimos filtrar depois.

As regiões são definidas em coordenadas relativas à caixa do rosto, então
funcionam igual perto ou longe da câmera, em qualquer resolução.
"""

from __future__ import annotations

from enum import Enum

from cardiocam.visao.geometria import Retangulo


class RegiaoInteresse(str, Enum):
    """Conjuntos de regiões disponíveis."""

    TESTA = "testa"
    BOCHECHAS = "bochechas"
    TESTA_E_BOCHECHAS = "testa_e_bochechas"
    ROSTO_CENTRAL = "rosto_central"


# Frações (x_inicio, y_inicio, x_fim, y_fim) relativas à caixa do rosto.
_TESTA = (0.30, 0.15, 0.70, 0.30)
_BOCHECHA_ESQUERDA = (0.13, 0.55, 0.35, 0.75)
_BOCHECHA_DIREITA = (0.65, 0.55, 0.87, 0.75)
_ROSTO_CENTRAL = (0.20, 0.20, 0.80, 0.80)

_MAPA: dict[RegiaoInteresse, tuple[tuple[float, float, float, float], ...]] = {
    RegiaoInteresse.TESTA: (_TESTA,),
    RegiaoInteresse.BOCHECHAS: (_BOCHECHA_ESQUERDA, _BOCHECHA_DIREITA),
    RegiaoInteresse.TESTA_E_BOCHECHAS: (_TESTA, _BOCHECHA_ESQUERDA, _BOCHECHA_DIREITA),
    RegiaoInteresse.ROSTO_CENTRAL: (_ROSTO_CENTRAL,),
}


def regioes_de(
    caixa_rosto: Retangulo, regiao: RegiaoInteresse = RegiaoInteresse.TESTA_E_BOCHECHAS
) -> list[Retangulo]:
    """Converte a caixa do rosto na lista de sub-regiões a serem medidas."""
    fracoes = _MAPA[RegiaoInteresse(regiao)]
    return [caixa_rosto.fracao(*fracao) for fracao in fracoes]


def descricao(regiao: RegiaoInteresse) -> str:
    """Texto curto para a interface e para os relatórios."""
    return {
        RegiaoInteresse.TESTA: "testa",
        RegiaoInteresse.BOCHECHAS: "bochechas",
        RegiaoInteresse.TESTA_E_BOCHECHAS: "testa e bochechas",
        RegiaoInteresse.ROSTO_CENTRAL: "região central do rosto",
    }[RegiaoInteresse(regiao)]
