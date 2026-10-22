"""Registro de leituras e recusas, sem guardar quadros de vídeo."""

from dataclasses import dataclass
import numpy as np
from cardiocam.dominio.estimativa import EstimativaBPM


@dataclass(frozen=True, slots=True)
class RegistroMedicao:
    instante: float | None
    estimativa: EstimativaBPM | None
    aceita: bool
    qualidade: float | None
    codigo_falha: str | None
    mensagem: str
    idade_analise_s: float | None
    caracteristicas_ausentes: tuple[str, ...] = ()
    luminancia_pele_p05_quadro: float | None = None
    luminancia_pele_mediana_quadro: float | None = None
    luminancia_pele_p95_quadro: float | None = None
    fracao_pele_quadro: float | None = None
    fracao_saturada_quadro: float | None = None
    fps_janela: float | None = None
    jitter_intervalos_s: float | None = None

    @classmethod
    def do_estado(cls, estado):
        amostra = estado.amostra
        instantes = estado.analise.instantes_originais if estado.analise is not None else None
        intervalos = np.diff(instantes) if instantes is not None else np.array([])
        validos = intervalos.size > 0 and np.all(np.isfinite(intervalos)) and np.all(intervalos > 0)
        return cls(
            estado.instante,
            estado.analise.estimativa if estado.analise is not None else None,
            estado.bpm_exibido is not None and not estado.recusada,
            estado.qualidade, estado.codigo_falha, estado.mensagem,
            estado.idade_analise_s, estado.caracteristicas_ausentes,
            getattr(amostra, "luminancia_p05", None),
            getattr(amostra, "luminancia_mediana", None),
            getattr(amostra, "luminancia_p95", None),
            getattr(amostra, "proporcao_pele", None),
            getattr(amostra, "fracao_saturada", None),
            float(1.0 / np.mean(intervalos)) if validos else None,
            float(np.std(intervalos)) if validos else None,
        )
