"""Vídeo real decodificado para modalidades independentes e adaptador neural."""

import cv2
import numpy as np
import pytest

from cardiocam.pesquisa.neural_video import avaliar_modalidades, avaliar_rede_video
from cardiocam.visao.detector_face import DetectorRegiaoFixa
from cardiocam.visao.geometria import Retangulo
from cardiocam.visao.olhos import Olhos


@pytest.fixture
def video_de_movimento(tmp_path):
    caminho = tmp_path / "movimento.avi"
    writer = cv2.VideoWriter(str(caminho), cv2.VideoWriter_fourcc(*"FFV1"), 20, (128, 96))
    if not writer.isOpened(): pytest.skip("FFV1 indisponível")
    rng = np.random.default_rng(5)
    textura = rng.integers(-20, 21, (96, 128, 1))
    for i in range(240):
        t = i/20
        imagem = np.clip(np.array([80, 130, 180])+textura+np.sin(2*np.pi*1.4*t)*np.array([1, 6, 3]), 0, 255).astype(np.uint8)
        imagem = cv2.warpAffine(imagem, np.float32([[1, 0, 0], [0, 1, 2*np.sin(2*np.pi*1.2*t)]]), (128, 96), borderMode=cv2.BORDER_REFLECT)
        writer.write(imagem)
    writer.release()
    return caminho


def test_avaliacao_adaptador_neural_e_modalidades(video_de_movimento):
    class ExtracaoDeControle:
        nome = "physnet"
        procedencia = {"aviso": "Controle verde, não é uma rede treinada"}
        def prever(self, q): return q[:, :, :, 1].mean(axis=(1, 2))
    detector = DetectorRegiaoFixa(Retangulo(8, 8, 112, 80))
    r = avaliar_rede_video(video_de_movimento, ExtracaoDeControle(), 8, lambda t: 84, detector=detector)
    assert r["janelas"] and r["janelas"][0]["estimadores"]
    assert abs(r["janelas"][0]["estimadores"]["periodograma"]-84) < 2
    class OlhosDeControle:
        def detectar(self, *_): return Olhos((40, 32), (88, 32))
    m = avaliar_modalidades(video_de_movimento, 8, detector, OlhosDeControle())
    assert m["pupilas"] and m["periocular"] and m["video_bcg"]
    assert m["video_bcg"][0]["estimadores"] is not None
    assert abs(m["video_bcg"][0]["estimadores"]["periodograma"]-72) < 4


def test_onda_neural_constante_e_rejeitada(video_de_movimento):
    class ControleConstante:
        nome = "physnet"
        procedencia = {"controle": "sem sinal"}
        def prever(self, q): return np.zeros(len(q))
    r = avaliar_rede_video(video_de_movimento, ControleConstante(), 8,
                           detector=DetectorRegiaoFixa(Retangulo(8, 8, 112, 80)))
    assert r["janelas"] and all(q["estimadores"] is None for q in r["janelas"])


def test_cli_modalidades(video_de_movimento, tmp_path):
    from cardiocam.cli import main
    assert main(["pesquisa", "modalidades", str(video_de_movimento), "--saida", str(tmp_path / "modalidades.json")]) == 0
