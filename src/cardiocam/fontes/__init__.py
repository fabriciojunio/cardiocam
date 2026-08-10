"""Fontes de quadros: webcam, arquivo de vídeo e simulador."""

from cardiocam.fontes.arquivo import FonteArquivo, abrir_arquivo
from cardiocam.fontes.base import FonteVideo, Quadro
from cardiocam.fontes.sintetica import (
    GANHO_CANAL,
    HARMONICOS_PADRAO,
    FonteSintetica,
    ParametrosSimulacao,
    RenderizadorRosto,
    gerar_serie_rgb,
    instantes,
    onda_de_pulso,
)
from cardiocam.fontes.tela import FonteTela, abrir_tela
from cardiocam.fontes.webcam import FonteWebcam, abrir_webcam

__all__ = [
    "FonteArquivo",
    "FonteSintetica",
    "FonteTela",
    "FonteVideo",
    "FonteWebcam",
    "GANHO_CANAL",
    "HARMONICOS_PADRAO",
    "ParametrosSimulacao",
    "Quadro",
    "RenderizadorRosto",
    "abrir_arquivo",
    "abrir_tela",
    "abrir_webcam",
    "gerar_serie_rgb",
    "instantes",
    "onda_de_pulso",
]
