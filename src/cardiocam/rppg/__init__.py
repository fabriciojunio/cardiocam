"""Algoritmos de extração de pulso a partir da série RGB."""

from __future__ import annotations

from cardiocam.rppg.base import AlgoritmoRPPG, finalizar
from cardiocam.rppg.chrom import Chrom
from cardiocam.rppg.ica import Ica
from cardiocam.rppg.pos import Pos
from cardiocam.rppg.verde import Verde

_REGISTRO: dict[str, type] = {
    Verde.nome: Verde,
    Chrom.nome: Chrom,
    Pos.nome: Pos,
    Ica.nome: Ica,
}

ALGORITMOS_DISPONIVEIS = tuple(_REGISTRO)


def criar_algoritmo(nome: str) -> AlgoritmoRPPG:
    """Instancia um algoritmo pelo nome.

    Mantém o pipeline e a linha de comando desacoplados das classes concretas.
    """
    chave = nome.strip().lower()
    if chave not in _REGISTRO:
        disponiveis = ", ".join(ALGORITMOS_DISPONIVEIS)
        raise ValueError(
            f"Algoritmo desconhecido: {nome!r}. Disponíveis: {disponiveis}."
        )
    return _REGISTRO[chave]()  # type: ignore[return-value]


__all__ = [
    "ALGORITMOS_DISPONIVEIS",
    "AlgoritmoRPPG",
    "Chrom",
    "Ica",
    "Pos",
    "Verde",
    "criar_algoritmo",
    "finalizar",
]
