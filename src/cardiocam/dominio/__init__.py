"""Camada de domínio: entidades e regras que não dependem de OpenCV nem de I/O."""

from cardiocam.dominio.config import ConfiguracaoAnalise
from cardiocam.dominio.erros import (
    BandaInvalida,
    ErroCardiocam,
    FonteIndisponivel,
    FrequenciaAmostragemInvalida,
    JanelaInsuficiente,
    RegiaoInvalida,
    RostoNaoEncontrado,
    SinalSemQualidade,
)
from cardiocam.dominio.estimativa import (
    Confianca,
    Espectro,
    EstimativaBPM,
    VariabilidadeCardiaca,
)
from cardiocam.dominio.resultado import Falha, Ok, Resultado, tentar
from cardiocam.dominio.sinal import BandaCardiaca, SerieRGB, SinalPulso

__all__ = [
    "BandaCardiaca",
    "BandaInvalida",
    "Confianca",
    "ConfiguracaoAnalise",
    "ErroCardiocam",
    "Espectro",
    "EstimativaBPM",
    "Falha",
    "FonteIndisponivel",
    "FrequenciaAmostragemInvalida",
    "JanelaInsuficiente",
    "Ok",
    "RegiaoInvalida",
    "Resultado",
    "RostoNaoEncontrado",
    "SerieRGB",
    "SinalPulso",
    "SinalSemQualidade",
    "VariabilidadeCardiaca",
    "tentar",
]
