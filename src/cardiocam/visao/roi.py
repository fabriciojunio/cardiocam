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
#
# As regiões são generosas de propósito. Como a média espacial reduz o ruído
# por um fator de raiz de N, dobrar a área de pele medida vale cerca de 1,5 dB
# de relação sinal-ruído, e com webcam ruim esse ganho decide entre uma leitura
# confiável e uma leitura descartada. A máscara de pele fica encarregada de
# excluir cabelo, sobrancelha e fundo que entrem nas bordas, então ampliar
# custa pouco e rende bastante.
_TESTA = (0.24, 0.12, 0.76, 0.32)
_BOCHECHA_ESQUERDA = (0.08, 0.50, 0.38, 0.80)
_BOCHECHA_DIREITA = (0.62, 0.50, 0.92, 0.80)
_ROSTO_CENTRAL = (0.15, 0.15, 0.85, 0.85)

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
