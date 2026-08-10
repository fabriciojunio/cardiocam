"""Tipo Result: erros como valor, sem exceção para fluxo esperado.

A regra do projeto é simples: exceção só para bug de programação. Tudo que pode
falhar por causa do mundo real (câmera ocupada, rosto ausente, janela curta
demais) devolve `Resultado` e obriga quem chamou a lidar com a falha.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Generic, NoReturn, TypeVar

from cardiocam.dominio.erros import ErroCardiocam

T = TypeVar("T")
U = TypeVar("U")


@dataclass(frozen=True, slots=True)
class Ok(Generic[T]):
    """Operação concluída, carrega o valor produzido."""

    valor: T

    @property
    def ok(self) -> bool:
        return True

    @property
    def falhou(self) -> bool:
        return False

    def mapear(self, funcao: Callable[[T], U]) -> "Resultado[U]":
        return Ok(funcao(self.valor))

    def encadear(self, funcao: Callable[[T], "Resultado[U]"]) -> "Resultado[U]":
        return funcao(self.valor)

    def ou_entao(self, padrao: U) -> T | U:
        return self.valor

    def desempacotar(self) -> T:
        return self.valor


@dataclass(frozen=True, slots=True)
class Falha(Generic[T]):
    """Operação não concluída, carrega o erro de domínio."""

    erro: ErroCardiocam

    @property
    def ok(self) -> bool:
        return False

    @property
    def falhou(self) -> bool:
        return True

    def mapear(self, funcao: Callable[[T], U]) -> "Resultado[U]":
        return Falha(self.erro)

    def encadear(self, funcao: Callable[[T], "Resultado[U]"]) -> "Resultado[U]":
        return Falha(self.erro)

    def ou_entao(self, padrao: U) -> T | U:
        return padrao

    def desempacotar(self) -> NoReturn:
        raise self.erro


Resultado = Ok[T] | Falha[T]


def tentar(funcao: Callable[[], T], erro: ErroCardiocam) -> Resultado[T]:
    """Converte uma chamada que pode levantar exceção em `Resultado`.

    Usado nas bordas do sistema, onde bibliotecas de terceiros (OpenCV, SciPy)
    sinalizam problema por exceção.
    """
    try:
        return Ok(funcao())
    except Exception as causa:  # noqa: BLE001 - fronteira com biblioteca externa
        erro.__cause__ = causa
        return Falha(erro)
