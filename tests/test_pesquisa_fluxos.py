"""Experimentos completos sobre quadros e vídeos de frequência conhecida."""

import json
from pathlib import Path
import shutil

import cv2
import numpy as np
import pytest

from cardiocam.pesquisa.arquivos import gravar_json, sha256
from cardiocam.pesquisa.compressao import VarianteCompressao, comparar_compressao, transcodificar
from cardiocam.pesquisa.experimento import OpcoesExperimento, analisar_video
from cardiocam.pesquisa.perturbacoes import Perturbacao
from cardiocam.visao.detector_face import DetectorRegiaoFixa
from cardiocam.visao.geometria import Retangulo


class FonteDeTeste:
    def __init__(self, duracao=12, congelada=False, lacuna=False):
        self.duracao, self.congelada, self.lacuna = duracao, congelada, lacuna
    def quadros(self):
        for i in range(round(self.duracao*20)):
            t = i/20
            imagem = np.full((96, 128, 3), 30, np.uint8)
            cor = np.array([80, 130, 180])+np.sin(2*np.pi*1.4*t)*np.array([1, 6, 3])
            imagem[8:88, 16:112] = np.round(cor).astype(np.uint8)
            imagem[0, 0] = i % 255
            if self.congelada:
                imagem[:] = [80, 130, 180]
            yield imagem, t + (1 if self.lacuna and i >= 90 else 0)


def avaliar(fonte, **kwargs):
    return analisar_video(fonte, OpcoesExperimento(janela_s=8, passo_s=1, grade=2,
                          metodos=("verde", "pos", "chrom", "ssr")),
                          DetectorRegiaoFixa(Retangulo(16, 8, 96, 80)), **kwargs)


def test_video_com_referencia_e_caracteristicas_sem_vazamento():
    correto = avaliar(FonteDeTeste(), referencia=lambda t: 84)
    referencia_errada = avaliar(FonteDeTeste(), referencia=lambda t: 130)
    assert correto["metricas"]["aceitas_com_referencia"] > 0
    assert correto["metricas"]["mae_bpm"] < 2
    assert [r["bpm"] for r in correto["janelas"]] == [r["bpm"] for r in referencia_errada["janelas"]]
    assert correto["caracteristicas"] and "snr_db" in correto["caracteristicas"][0]
    assert any(f["algoritmo"] == "ssr" for r in correto["janelas"] for f in r["falhas"])
    json.dumps(correto, allow_nan=False)


def test_congelamento_e_lacuna_nao_reaproveitam_janelas():
    congelada = avaliar(FonteDeTeste(congelada=True))
    assert congelada["janelas"] and all(not r["aceita"] for r in congelada["janelas"])
    lacuna = avaliar(FonteDeTeste(lacuna=True))
    assert lacuna["reinicios"] > 0
    assert any("descontínua" in r["motivo"] for r in lacuna["janelas"])


def test_ablacao_congelada_e_observada_depois_da_transformacao():
    r = avaliar(FonteDeTeste(), transformador=Perturbacao(congelar_cada=2).criar())
    assert all(not q["aceita"] for q in r["janelas"])


@pytest.mark.parametrize("alteracoes", [{"janela_s": float("nan")}, {"janela_s": 2}, {"metodos": ()},
                                       {"metodos": ("desconhecido",)}, {"grade": 9}, {"fotometria": "outro"}])
def test_opcoes_invalidas(alteracoes):
    with pytest.raises(ValueError): OpcoesExperimento(**alteracoes)


def test_json_utf8_preserva_arquivo_existente(tmp_path):
    destino = tmp_path / "resultado.json"
    gravar_json(destino, {"mensagem": "Medição cardíaca"})
    assert "cardíaca" in destino.read_text(encoding="utf-8")
    assert len(sha256(destino)) == 64
    with pytest.raises(FileExistsError): gravar_json(destino, {})
    with pytest.raises(ValueError): gravar_json(tmp_path / "outro.json", {"valor": float("nan")})
    assert not (tmp_path / "outro.json").exists()


@pytest.fixture
def video_lossless(tmp_path):
    caminho = tmp_path / "pulso.avi"
    gravador = cv2.VideoWriter(str(caminho), cv2.VideoWriter_fourcc(*"FFV1"), 20, (128, 96))
    if not gravador.isOpened(): pytest.skip("FFV1 indisponível nesta instalação do OpenCV")
    for q, _ in FonteDeTeste(duracao=5).quadros(): gravador.write(q)
    gravador.release()
    return caminho


@pytest.mark.parametrize("codec", ["h264", "h265", "vp9"])
def test_codecs_reais_preservam_frequencia(video_lossless, tmp_path, codec):
    if not shutil.which("ffmpeg"): pytest.skip("FFmpeg não instalado")
    destino = tmp_path / (codec+".mkv")
    transcodificar(video_lossless, destino, VarianteCompressao(codec, 1000, 128, 96))
    captura = cv2.VideoCapture(str(destino))
    medias = []
    try:
        while True:
            ok, q = captura.read()
            if not ok: break
            medias.append(q[20:70, 30:100, 1].mean())
        fps = captura.get(cv2.CAP_PROP_FPS)
    finally: captura.release()
    from cardiocam.dominio.sinal import SinalPulso
    from cardiocam.pesquisa.estimacao import comparar_estimadores
    assert abs(comparar_estimadores(SinalPulso(np.array(medias), fps))["periodograma"]-84) < 2
    with pytest.raises(ValueError): transcodificar(video_lossless, destino, VarianteCompressao())


def test_benchmark_de_compressao_executa_avaliador_e_registra_procedencia(video_lossless, tmp_path):
    if not shutil.which("ffmpeg"): pytest.skip("FFmpeg não instalado")
    chamados = []
    def avaliador(caminho):
        chamados.append(Path(caminho))
        c = cv2.VideoCapture(str(caminho))
        n = 0
        while c.read()[0]:
            n += 1
        c.release()
        return {"quadros": n}
    r = comparar_compressao(video_lossless, tmp_path / "resultados", [VarianteCompressao(perder_cada=5)], avaliador)
    assert len(chamados) == 2 and r["original_sha256"] == sha256(video_lossless)
    assert r["resultados"][1]["avaliacao"]["quadros"] < r["resultados"][0]["avaliacao"]["quadros"]


def test_cli_de_pesquisa_real(video_lossless, tmp_path):
    from cardiocam.cli import main
    destino = tmp_path / "analise.json"
    assert main(["pesquisa", "video", str(video_lossless), "--saida", str(destino), "--janela", "4",
                 "--metodos", "verde", "pos", "--grade", "2", "--area", "16", "8", "96", "80"]) == 0
    assert json.loads(destino.read_text(encoding="utf-8"))["janelas"]
    assert main(["pesquisa", "video", str(video_lossless), "--saida", str(destino)]) == 1


def test_cli_compressao_e_ablacao(video_lossless, tmp_path):
    from cardiocam.cli import main
    base = [str(video_lossless), "--janela", "4", "--grade", "2", "--metodos", "verde", "pos",
            "--area", "16", "8", "96", "80"]
    if shutil.which("ffmpeg"):
        assert main(["pesquisa", "compressao", *base, "--saida", str(tmp_path / "codecs"),
                     "--codecs", "h264", "--bitrates", "800", "--resolucoes", "64x48"]) == 0
        assert list((tmp_path / "codecs").glob("compressao-*/comparacao.json"))
    assert main(["pesquisa", "ablacao", *base, "--saida", str(tmp_path / "ablacao.json"), "--iluminacao", "0.2"]) == 0


def test_exposicao_rejeita_duracao_invalida_antes_da_camera(tmp_path):
    from cardiocam.cli import main
    assert main(["pesquisa", "exposicao", "--minimo", "-10", "--maximo", "-1", "--incremento", "1",
                 "--duracao", "nan", "--saida", str(tmp_path / "exposicao.json")]) == 1


def test_entrada_instalada_emite_utf8_no_console_legado():
    import os
    import subprocess
    import sys
    ambiente = dict(os.environ, PYTHONIOENCODING="cp1252")
    processo = subprocess.run([sys.executable, "-c", "from cardiocam.cli import main; main(['--help'])"],
                              capture_output=True, env=ambiente, timeout=30)
    assert processo.returncode == 0
    assert "frequência cardíaca" in processo.stdout.decode("utf-8")
