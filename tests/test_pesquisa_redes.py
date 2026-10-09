"""Inferência, gradientes, pesos verificados e treino em CPU de referência."""

import json

import numpy as np
import pytest

pytestmark = pytest.mark.pesquisa_neural


@pytest.fixture
def torch_cpu():
    torch = pytest.importorskip("torch")
    torch.set_num_threads(1)
    torch.manual_seed(12)
    return torch


@pytest.mark.parametrize("nome", ["DeepPhys", "PhysNet", "EfficientPhys"])
def test_redes_tem_inferencia_e_gradiente_finitos(torch_cpu, nome):
    from cardiocam.pesquisa import redes
    t = torch_cpu
    modelo = getattr(redes, nome)()
    video = t.rand(2, 8, 3, 36, 36)
    saida = modelo(video)
    assert saida.shape == (2, 8 if nome == "PhysNet" else 7)
    assert t.isfinite(saida).all()
    referencia = t.sin(t.arange(saida.shape[1], dtype=t.float32)).expand_as(saida)
    loss = redes.perda_pearson(saida, referencia) if nome == "PhysNet" else (saida-referencia).square().mean()
    loss.backward()
    assert any(p.grad is not None and t.isfinite(p.grad).all() and p.grad.abs().sum() > 0 for p in modelo.parameters())


def test_temporal_shift_nao_mistura_participantes(torch_cpu):
    from cardiocam.pesquisa.redes import deslocar_temporal
    t = torch_cpu
    x = t.cat([t.ones(3, 6, 2, 2), t.full((3, 6, 2, 2), 100.)])
    y = deslocar_temporal(x, 2, 3).reshape(2, 3, 6, 2, 2)
    assert y[0].max() == 1
    assert set(y[1].unique().tolist()) == {0, 100}


def test_zero_dce_curvas_nulas_preservam_imagem_e_intervalo(torch_cpu):
    from cardiocam.pesquisa.redes import ZeroDCE
    t = torch_cpu
    modelo = ZeroDCE()
    x = t.rand(2, 3, 32, 40)
    assert t.isfinite(modelo(x)).all()
    for p in modelo.parameters(): p.data.zero_()
    assert t.equal(modelo(x), x)
    with pytest.raises(ValueError): modelo(x+1)


def manifesto_pesos(tmp_path, modelo, nome, torch_cpu):
    from cardiocam.pesquisa.arquivos import sha256
    peso = tmp_path / "pesos.pt"
    torch_cpu.save(modelo.state_dict(), peso)
    ficha = tmp_path / "pesos.json"
    ficha.write_text(json.dumps({"versao": 1, "formato": "torch_state_dict", "arquitetura": nome,
                                "arquivo": peso.name, "sha256": sha256(peso), "licenca": "Fixture sintética",
                                "procedencia": "Teste de integridade, sem validade fisiológica",
                                "preprocessamento": "rgb_0_1_local_v1"}), encoding="utf-8")
    return ficha


def test_carregamento_de_pesos_e_corrupcao(torch_cpu, tmp_path):
    from cardiocam.pesquisa.redes import DeepPhys
    from cardiocam.pesquisa.modelos import ModeloNeural
    ficha = manifesto_pesos(tmp_path, DeepPhys(), "deepphys", torch_cpu)
    modelo = ModeloNeural(ficha)
    video = np.random.default_rng(1).integers(0, 255, (8, 40, 50, 3), dtype=np.uint8)
    assert modelo.prever(video).shape == (7,)
    peso = tmp_path / "pesos.pt"
    with peso.open("ab") as arquivo: arquivo.write(b"alteracao")
    with pytest.raises(ValueError): ModeloNeural(ficha)


def test_realce_local_preserva_resolucao_e_pulso_com_curvas_nulas(torch_cpu, tmp_path):
    from cardiocam.pesquisa.redes import ZeroDCE
    from cardiocam.pesquisa.modelos import RealcadorLocal
    modelo = ZeroDCE()
    for p in modelo.parameters(): p.data.zero_()
    ficha = manifesto_pesos(tmp_path, modelo, "zero_dce", torch_cpu)
    imagem = np.random.default_rng(3).integers(0, 255, (48, 80, 3), dtype=np.uint8)
    assert np.array_equal(RealcadorLocal(ficha).aplicar(imagem), imagem)


def test_adaptador_ppg_onnx_com_frequencia_conhecida(tmp_path):
    onnx = pytest.importorskip("onnx")
    from onnx import TensorProto, helper
    from cardiocam.pesquisa.modelos import ModeloPPGONNX
    from cardiocam.pesquisa.arquivos import sha256
    from cardiocam.pesquisa.estimacao import comparar_estimadores
    from cardiocam.dominio.sinal import SinalPulso
    peso = tmp_path / "controle.onnx"
    entrada = helper.make_tensor_value_info("entrada", TensorProto.FLOAT, [1, 3, 200, 32, 32])
    saida = helper.make_tensor_value_info("saida", TensorProto.FLOAT, [1, 200])
    grafo = helper.make_graph([helper.make_node("ReduceMean", ["entrada"], ["saida"], axes=[1, 3, 4], keepdims=0)],
                              "controle", [entrada], [saida])
    modelo = helper.make_model(grafo, opset_imports=[helper.make_opsetid("", 13)])
    modelo.ir_version = 8
    onnx.save(modelo, peso)
    ficha = tmp_path / "onnx.json"
    ficha.write_text(json.dumps({"versao": 1, "formato": "onnx", "arquitetura": "controle_media",
                                "arquivo": peso.name, "sha256": sha256(peso), "licenca": "Fixture sintética",
                                "procedencia": "Grafo de controle, não é rede treinada",
                                "preprocessamento": "rgb_ncthw_0_1", "tamanho": 32}), encoding="utf-8")
    video = np.array([np.full((32, 32, 3), round(120+10*np.sin(2*np.pi*1.4*i/20)), np.uint8)
                      for i in range(200)])
    onda = ModeloPPGONNX(ficha).prever(video)
    assert abs(comparar_estimadores(SinalPulso(onda, 20))["periodograma"]-84) < 1


def test_adaptador_onnx_executa_grafo_real(tmp_path):
    onnx = pytest.importorskip("onnx")
    from onnx import TensorProto, helper
    from cardiocam.pesquisa.modelos import RealcadorONNX
    from cardiocam.pesquisa.arquivos import sha256
    peso = tmp_path / "identidade.onnx"
    entrada = helper.make_tensor_value_info("entrada", TensorProto.FLOAT, [1, 3, 32, 40])
    saida = helper.make_tensor_value_info("saida", TensorProto.FLOAT, [1, 3, 32, 40])
    grafo = helper.make_graph([helper.make_node("Identity", ["entrada"], ["saida"])], "controle", [entrada], [saida])
    modelo = helper.make_model(grafo, opset_imports=[helper.make_opsetid("", 13)])
    modelo.ir_version = 8
    onnx.save(modelo, peso)
    ficha = tmp_path / "onnx.json"
    ficha.write_text(json.dumps({"versao": 1, "formato": "onnx", "arquitetura": "controle_identidade",
                                "arquivo": peso.name, "sha256": sha256(peso), "licenca": "Fixture sintética",
                                "procedencia": "Grafo de controle, não é Retinexformer",
                                "preprocessamento": "rgb_nchw_0_1"}), encoding="utf-8")
    imagem = np.random.default_rng(1).integers(0, 255, (32, 40, 3), dtype=np.uint8)
    assert np.array_equal(RealcadorONNX(ficha).aplicar(imagem), imagem)


@pytest.mark.parametrize("nome", ["deepphys", "physnet", "efficientphys"])
def test_treino_completo_seleciona_na_calibracao_e_grava_pesos(torch_cpu, tmp_path, nome):
    from cardiocam.pesquisa.treino_neural import treinar_rede
    from cardiocam.pesquisa.modelos import ModeloNeural
    clipes = []
    for i, parte in enumerate(("treino", "calibracao", "teste")):
        t = np.arange(12)/20
        video = np.empty((12, 36, 36, 3), np.uint8)
        for j in range(12): video[j] = np.round([180, 130+8*np.sin(2*np.pi*1.2*t[j]), 80])
        np.savez(tmp_path / (parte+".npz"), video=video, ppg=np.sin(2*np.pi*1.2*t), fps=20)
        clipes.append({"participante": f"p{i}", "particao": parte, "dataset": "controle_sintetico",
                       "licenca": "Fixture sintética", "arquivo": parte+".npz"})
    manifesto = tmp_path / "dados.json"
    manifesto.write_text(json.dumps({"versao": 1, "clipes": clipes}), encoding="utf-8")
    resultado = treinar_rede(manifesto, nome, tmp_path / "resultado", epocas=2)
    assert np.isfinite(resultado["perda_teste"]) and len(resultado["historico"]) == 2
    modelo = ModeloNeural(tmp_path / "resultado/pesos.json")
    assert np.isfinite(modelo.prever(video[:, :, :, ::-1].copy())).all()
    with pytest.raises(ValueError): treinar_rede(manifesto, nome, tmp_path / "resultado", epocas=1)
