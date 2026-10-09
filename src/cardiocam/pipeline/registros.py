"""Registro de leituras e recusas, sem guardar quadros de vídeo."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RegistroMedicao:
    instante: float | None
    estimativa: object | None
    aceita: bool
    qualidade: float | None
    codigo_falha: str | None
    mensagem: str
    idade_analise_s: float | None
    caracteristicas_ausentes: tuple[str, ...] = ()

    @classmethod
    def do_estado(cls, estado):
        return cls(
            estado.instante,
            estado.analise.estimativa if estado.analise is not None else None,
            estado.bpm_exibido is not None and not estado.recusada,
            estado.qualidade, estado.codigo_falha, estado.mensagem,
            estado.idade_analise_s, estado.caracteristicas_ausentes,
        )
