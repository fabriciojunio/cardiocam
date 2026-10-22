"""Arquivos reutilizados não se tornam independentes por mudar o participante."""

import json

import numpy as np
import pytest

from cardiocam.pesquisa.treino_neural import carregar_clipes


def manifesto_neural(tmp_path):
    clipes = []
    for indice, parte in enumerate(("treino", "calibracao", "teste")):
        video = np.full((12, 8, 8, 3), 120 + indice, np.uint8)
        np.savez(tmp_path / (parte + ".npz"), video=video,
                 ppg=np.sin(np.arange(12) * (.4 + indice * .1)), fps=20)
        clipes.append({"participante": f"p{indice}", "particao": parte,
                       "dataset": "controle_sintetico", "licenca": "Fixture sintética",
                       "arquivo": parte + ".npz"})
    caminho = tmp_path / "manifesto.json"
    caminho.write_text(json.dumps({"versao": 1, "clipes": clipes}), encoding="utf-8")
    return caminho


def test_loader_neural_aceita_clipes_independentes(tmp_path):
    partes, _ = carregar_clipes(manifesto_neural(tmp_path))
    assert {nome: len(clipes) for nome, clipes in partes.items()} == {
        "treino": 1, "calibracao": 1, "teste": 1}


@pytest.mark.parametrize("parte", ["calibracao", "teste"])
@pytest.mark.parametrize("copiar", [False, True])
def test_loader_neural_rejeita_arquivo_compartilhado_com_outro_participante(tmp_path, parte, copiar):
    caminho = manifesto_neural(tmp_path)
    dados = json.loads(caminho.read_text(encoding="utf-8"))
    if copiar:
        (tmp_path / (parte + ".npz")).write_bytes((tmp_path / "treino.npz").read_bytes())
    else:
        next(c for c in dados["clipes"] if c["particao"] == parte)["arquivo"] = "treino.npz"
    caminho.write_text(json.dumps(dados), encoding="utf-8")
    with pytest.raises(ValueError, match="Arquivo repetido entre partições"):
        carregar_clipes(caminho)


def test_loader_neural_rejeita_mesmo_video_com_onda_reempacotada(tmp_path):
    caminho = manifesto_neural(tmp_path)
    with np.load(tmp_path / "treino.npz") as arquivo:
        video = arquivo["video"].copy()
        fps = float(arquivo["fps"])
    np.savez_compressed(tmp_path / "teste.npz", video=video,
                        ppg=np.sin(np.arange(12) * .7), fps=fps)
    with pytest.raises(ValueError, match="Arquivo repetido entre partições"):
        carregar_clipes(caminho)
