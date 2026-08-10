"""Configuração da análise, em um único objeto imutável."""

from __future__ import annotations

from dataclasses import dataclass, replace

from cardiocam.dominio.sinal import BandaCardiaca


@dataclass(frozen=True, slots=True)
class ConfiguracaoAnalise:
    """Parâmetros que governam a extração e a estimativa.

    Os padrões foram escolhidos para webcam comum de notebook: 30 fps nominais,
    rosto a cerca de meio metro e iluminação de ambiente interno.
    """

    janela_s: float = 10.0
    """Comprimento da janela deslizante. Janela maior estabiliza a estimativa e
    melhora a resolução em frequência, mas atrasa a resposta a mudanças."""

    passo_s: float = 1.0
    """De quanto em quanto tempo uma nova estimativa é emitida."""

    banda: BandaCardiaca = BandaCardiaca()

    ordem_filtro: int = 4
    """Ordem do Butterworth passa-faixa aplicado antes da análise espectral."""

    lambda_detrend: float = 100.0
    """Regularização do detrend por priores de suavidade (Tarvainen, 2002).
    Valores altos removem tendências mais lentas."""

    snr_minimo_db: float = 0.0
    """Abaixo disso a janela é descartada em vez de reportar um número duvidoso."""

    suavizacao_bpm: float = 0.3
    """Peso do valor novo na média exponencial do BPM exibido. 1.0 desliga a
    suavização."""

    algoritmo: str = "pos"

    def amostras_por_janela(self, fps: float) -> int:
        return max(2, int(round(self.janela_s * fps)))

    def amostras_por_passo(self, fps: float) -> int:
        return max(1, int(round(self.passo_s * fps)))

    def com(self, **alteracoes: object) -> "ConfiguracaoAnalise":
        """Cópia com campos trocados, para não mutar a configuração original."""
        return replace(self, **alteracoes)  # type: ignore[arg-type]
