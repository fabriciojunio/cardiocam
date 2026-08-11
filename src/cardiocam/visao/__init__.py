"""Visão computacional: detecção de rosto, regiões de interesse e extração RGB."""

from cardiocam.visao.detector_face import (
    CASCATA_ALTERNATIVA,
    CASCATA_PADRAO,
    DetectorCentral,
    DetectorFace,
    DetectorHaar,
    DetectorRegiaoFixa,
)
from cardiocam.visao.extrator import AmostraQuadro, ExtratorRGB
from cardiocam.visao.fundo import media_do_fundo, regioes_de_fundo
from cardiocam.visao.geometria import Retangulo
from cardiocam.visao.olhos import DetectorOlhos, Olhos, regioes_ancoradas
from cardiocam.visao.pele import (
    descartar_extremos,
    mascara_pele,
    proporcao_de_pele,
)
from cardiocam.visao.rastreador import RastreadorRosto
from cardiocam.visao.roi import RegiaoInteresse, descricao, regioes_de

__all__ = [
    "AmostraQuadro",
    "CASCATA_ALTERNATIVA",
    "CASCATA_PADRAO",
    "DetectorCentral",
    "DetectorFace",
    "DetectorHaar",
    "DetectorOlhos",
    "DetectorRegiaoFixa",
    "Olhos",
    "ExtratorRGB",
    "RastreadorRosto",
    "RegiaoInteresse",
    "Retangulo",
    "descartar_extremos",
    "descricao",
    "mascara_pele",
    "media_do_fundo",
    "proporcao_de_pele",
    "regioes_ancoradas",
    "regioes_de",
    "regioes_de_fundo",
]
