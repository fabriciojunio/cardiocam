"""Quadros idênticos não constituem uma medição atual."""

import numpy as np

from cardiocam.pipeline.analisador import MonitorCardiaco
from cardiocam.visao.continuidade import VigilanteDeQuadros
from cardiocam.visao.detector_face import DetectorRegiaoFixa
from cardiocam.visao.geometria import Retangulo


def test_congelamento_persiste_ate_imagem_mudar():
    v = VigilanteDeQuadros(2)
    q = np.full((20, 20, 3), 100, np.uint8)
    assert not v.congelado(q, 0)
    assert not v.congelado(q.copy(), 1.9)
    assert v.congelado(q, 2)
    assert v.congelado(q, 4)
    q[0, 0, 0] += 1
    assert not v.congelado(q, 4.1)


def test_pipeline_remove_leitura_e_contexto_ao_congelar():
    monitor = MonitorCardiaco(20, detector=DetectorRegiaoFixa(Retangulo(0, 0, 100, 100)))
    q = np.full((100, 100, 3), (150, 175, 205), np.uint8)
    for i in range(80):
        estado = monitor.processar(q, i / 20)
    assert estado.codigo_falha == "video_congelado"
    assert estado.bpm_exibido is None
    assert estado.analise is None
    assert estado.contexto_reiniciado
    assert len(monitor.janela) == 0
    q[0, 0] = 90
    estado = monitor.processar(q, 4)
    assert estado.codigo_falha is None
    assert len(monitor.janela) == 1
