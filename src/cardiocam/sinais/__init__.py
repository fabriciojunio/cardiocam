"""Processamento de sinais: filtragem, detrend, espectro e análise de picos."""

from cardiocam.sinais.espectro import (
    AnaliseEspectral,
    analisar,
    periodograma,
    recortar_banda,
    refinar_pico,
    relacao_sinal_ruido,
    welch,
)
from cardiocam.sinais.filtros import (
    amostras_minimas,
    aplicar_passa_faixa,
    media_movel,
    projetar_passa_faixa,
    resposta_em_frequencia,
)
from cardiocam.sinais.janela import JanelaDeslizante
from cardiocam.sinais.picos import (
    bpm_por_picos,
    detectar_picos,
    filtrar_intervalos,
    intervalos_entre_batimentos,
    variabilidade,
)
from cardiocam.sinais.preprocessamento import (
    estimar_fps,
    normalizar,
    normalizar_pela_media,
    reamostrar_uniforme,
    remover_tendencia,
    remover_tendencia_movel,
)

__all__ = [
    "AnaliseEspectral",
    "JanelaDeslizante",
    "amostras_minimas",
    "analisar",
    "aplicar_passa_faixa",
    "bpm_por_picos",
    "detectar_picos",
    "estimar_fps",
    "filtrar_intervalos",
    "intervalos_entre_batimentos",
    "media_movel",
    "normalizar",
    "normalizar_pela_media",
    "periodograma",
    "projetar_passa_faixa",
    "reamostrar_uniforme",
    "recortar_banda",
    "refinar_pico",
    "relacao_sinal_ruido",
    "remover_tendencia",
    "remover_tendencia_movel",
    "resposta_em_frequencia",
    "variabilidade",
    "welch",
]
