"""Partições explícitas e recalibração sem exposição do conjunto de teste."""

import json

import numpy as np
import pytest

from cardiocam.pesquisa.calibracao import carregar_amostras, recalibrar
from cardiocam.qualidade.caracteristicas import Caracteristicas
from cardiocam.qualidade.persistencia import carregar
from cardiocam.qualidade.treino import Particao, treinar


def manifesto_em(tmp_path):
    sessoes = []
    for i, parte in enumerate(("treino", "calibracao", "teste")):
        linhas = []
        for j in range(20):
            bom = j % 2 == 0
            vetor = [15 if bom else -5, 8 if bom else 1, .2 if bom else .9, .1,
                     1 if bom else 15, .9, .01, .01, .1, .01, .1]
            linhas.append({**dict(zip(Caracteristicas.nomes(), vetor)), "erro_bpm": 1 if bom else 20,
                           "caracteristicas_ausentes": []})
        arquivo = tmp_path / (parte+".json")
        arquivo.write_text(json.dumps({"caracteristicas": linhas}), encoding="utf-8")
        sessoes.append({"participante": f"p{i}", "dataset": "inédito" if parte == "teste" else "ajuste",
                        "licenca": "Fixture sintética de teste", "dispositivo": "simulado", "condicao": "controle",
                        "caracteristicas": arquivo.name, "particao": parte})
    caminho = tmp_path / "manifesto.json"
    caminho.write_text(json.dumps({"versao": 1, "sessoes": sessoes, "teste_dataset_inedito": True}), encoding="utf-8")
    return caminho


def test_recalibracao_reprodutivel_e_modelo_carregavel(tmp_path):
    origem = manifesto_em(tmp_path)
    amostras, particao, _ = carregar_amostras(origem)
    r = recalibrar(origem, tmp_path / "modelo-real.json")
    modelo, procedencia = carregar(tmp_path / "modelo-real.json")
    assert r.quantidade_teste == 20 and r.quantidade_calibracao == 20
    assert modelo.probabilidade(amostras[0].caracteristicas) > modelo.probabilidade(amostras[1].caracteristicas)
    assert "dataset inédito" in procedencia.observacao
    antes = r.modelo.regressao.media.copy()
    # Modificar só os rótulos de teste não pode alterar pesos nem limiar.
    from dataclasses import replace
    outros = [replace(a, erro_bpm=50) if i in particao.teste else a for i, a in enumerate(amostras)]
    novo = treinar(outros, particao=particao)
    assert np.array_equal(antes, novo.modelo.regressao.media)
    assert r.modelo.limiar == novo.modelo.limiar
    with pytest.raises(ValueError): recalibrar(origem, tmp_path / "modelo-real.json")


@pytest.mark.parametrize("mudanca", ["participante", "dataset", "sem_referencia", "ausente", "nao_finito", "sem_licenca"])
def test_recalibracao_rejeita_vazamento_e_contexto_incompleto(tmp_path, mudanca):
    origem = manifesto_em(tmp_path)
    dados = json.loads(origem.read_text(encoding="utf-8"))
    if mudanca == "participante": dados["sessoes"][2]["participante"] = "p0"
    elif mudanca == "dataset": dados["sessoes"][2]["dataset"] = "ajuste"
    elif mudanca == "sem_licenca": dados["sessoes"][0]["licenca"] = ""
    else:
        arquivo = tmp_path / "treino.json"
        linhas = json.loads(arquivo.read_text(encoding="utf-8"))
        if mudanca == "sem_referencia": linhas["caracteristicas"][0]["erro_bpm"] = None
        elif mudanca == "ausente": linhas["caracteristicas"][0]["caracteristicas_ausentes"] = ["correlacao_com_fundo"]
        else: linhas["caracteristicas"][0]["snr_db"] = float("nan")
        arquivo.write_text(json.dumps(linhas), encoding="utf-8")
    origem.write_text(json.dumps(dados), encoding="utf-8")
    with pytest.raises(ValueError): carregar_amostras(origem)


def test_particao_explicitamente_nao_pode_repetir_indices(tmp_path):
    amostras, p, _ = carregar_amostras(manifesto_em(tmp_path))
    with pytest.raises(ValueError): treinar(amostras, particao=Particao(p.treino, p.calibracao, p.treino))
    with pytest.raises(ValueError): treinar(amostras, particao=Particao(np.arange(30), np.arange(30, 40), np.arange(40, 60)))


def test_modelo_recusa_booleano_textual(tmp_path):
    origem = manifesto_em(tmp_path)
    recalibrar(origem, tmp_path / "modelo.json")
    arquivo = tmp_path / "modelo.json"
    dados = json.loads(arquivo.read_text(encoding="utf-8"))
    dados["calibracao_viavel"] = "false"
    arquivo.write_text(json.dumps(dados), encoding="utf-8")
    with pytest.raises(ValueError): carregar(arquivo)


def test_cli_de_recalibracao(tmp_path):
    from cardiocam.cli import main
    origem = manifesto_em(tmp_path)
    assert main(["pesquisa", "recalibrar", str(origem), "--saida", str(tmp_path / "novo-modelo.json")]) == 0


def test_modelo_escolhido_e_aplicado_sem_fallback(tmp_path):
    from dataclasses import replace
    from cardiocam.desktop.qualidade_ao_vivo import JuizDeQualidade
    from cardiocam.dominio.config import ConfiguracaoAnalise
    from cardiocam.fontes.sintetica import FonteSintetica, ParametrosSimulacao
    from cardiocam.pipeline.analisador import analisar_fonte
    from cardiocam.qualidade.persistencia import salvar
    origem = manifesto_em(tmp_path)
    caminho = tmp_path / "modelo.json"
    recalibrar(origem, caminho)
    modelo, procedencia = carregar(caminho)
    salvar(replace(modelo, calibracao_viavel=False), procedencia, caminho)
    juiz = JuizDeQualidade(100, str(caminho))
    assert not juiz.modelo.calibracao_viavel
    fonte = FonteSintetica(ParametrosSimulacao(bpm=84, duracao_s=12, fps=20))
    r = analisar_fonte(fonte, ConfiguracaoAnalise(janela_s=8, modelo_qualidade=str(caminho)))
    assert r.total_estimativas > 0 and r.registros
    assert all(not registro.aceita for registro in r.registros)
    with pytest.raises(FileNotFoundError): JuizDeQualidade(100, str(tmp_path / "ausente.json"))


def test_cli_valida_modelo_antes_de_abrir_camera(tmp_path):
    from cardiocam.cli import construir_analisador
    origem = manifesto_em(tmp_path)
    caminho = tmp_path / "modelo.json"
    recalibrar(origem, caminho)
    args = construir_analisador().parse_args(["ao-vivo", "--modelo-qualidade", str(caminho)])
    assert args.modelo_qualidade == str(caminho)
    with pytest.raises(SystemExit):
        construir_analisador().parse_args(["ao-vivo", "--modelo-qualidade", str(tmp_path / "ausente.json")])
