"""Recalibração com dados reais declarados, separados por participante."""

import json
from pathlib import Path

import numpy as np

from cardiocam.qualidade.caracteristicas import Caracteristicas
from cardiocam.qualidade.treino import Amostra, Particao, treinar


def carregar_amostras(manifesto):
    origem = Path(manifesto).resolve()
    dados = json.loads(origem.read_text(encoding="utf-8"))
    if dados.get("versao") != 1 or not dados.get("sessoes"):
        raise ValueError("Manifesto de calibração vazio ou desconhecido.")
    amostras, indices, sujeitos, datasets = [], {p: [] for p in ("treino", "calibracao", "teste")}, {}, {}
    for sessao in dados["sessoes"]:
        for chave in ("participante", "dataset", "licenca", "dispositivo", "condicao", "caracteristicas", "particao"):
            if not isinstance(sessao.get(chave), str) or not sessao[chave].strip():
                raise ValueError(f"Sessão sem {chave}.")
        parte, pessoa = sessao["particao"], sessao["participante"]
        if parte not in indices or (pessoa in sujeitos and sujeitos[pessoa] != parte):
            raise ValueError("Partição inválida ou participante compartilhado entre partições.")
        sujeitos[pessoa] = parte
        datasets.setdefault(parte, set()).add(sessao["dataset"])
        relatorio = json.loads((origem.parent / sessao["caracteristicas"]).read_text(encoding="utf-8"))
        for linha in relatorio["caracteristicas"]:
            if linha.get("erro_bpm") is None:
                raise ValueError("Há janela sem referência sincronizada; não é possível rotulá-la.")
            valores = [linha.get(n) for n in Caracteristicas.nomes()]
            if any(v is None for v in valores) or not np.isfinite([*valores, linha["erro_bpm"]]).all():
                raise ValueError("Há características ausentes ou não finitas; colete contexto completo.")
            if linha.get("caracteristicas_ausentes"):
                raise ValueError("O contexto da janela está incompleto.")
            indices[parte].append(len(amostras))
            amostras.append(Amostra(Caracteristicas(*valores), float(linha["erro_bpm"]), pessoa))
    if any(not indices[p] for p in indices):
        raise ValueError("Treino, calibração e teste precisam conter janelas.")
    if dados.get("teste_dataset_inedito", False) and datasets["teste"] & (datasets["treino"] | datasets["calibracao"]):
        raise ValueError("O dataset de teste também aparece no ajuste.")
    particao = Particao(*(np.array(indices[p], dtype=int) for p in indices))
    return amostras, particao, dados


def recalibrar(manifesto, destino, **politica):
    from cardiocam.qualidade.persistencia import Procedencia, agora_em_texto, salvar
    from cardiocam.qualidade.persistencia import CAMINHO_PADRAO
    destino = Path(destino).resolve()
    if destino.exists() or destino == CAMINHO_PADRAO.resolve():
        raise ValueError("Grave o modelo real em um caminho novo para preservar o distribuído.")
    amostras, particao, dados = carregar_amostras(manifesto)
    relatorio = treinar(amostras, particao=particao, **politica)
    ponto = relatorio.ponto_adotado
    salvar(relatorio.modelo, Procedencia(
        agora_em_texto(), len(amostras), "Dados declarados em " + str(Path(manifesto).resolve()),
        float(relatorio.curva_no_teste.erro_sem_abstencao), float(ponto.erro_medio), float(ponto.cobertura),
        "Partição explícita por participante; procedência e licenças no manifesto. "
        + ("Teste em dataset inédito." if dados.get("teste_dataset_inedito") else "Teste em participantes inéditos.")), destino)
    return relatorio
