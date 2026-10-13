"""Grava e lê o modelo de qualidade, para ele existir fora do treino.

Sem isto o modelo de abstenção só vivia dentro do comando que o treinava. Ele é
a hipótese H4 do projeto, mede a diferença entre responder sempre e recusar
janela ruim, e **não estava rodando em lugar nenhum**: a cada medição o programa
voltava a decidir pela regra fixa de relação sinal-ruído, que é a peneira que o
modelo existe para complementar.

O formato é JSON, por três motivos. É legível, e um modelo que decide recusar
precisa poder ser inspecionado sem ferramenta. Não executa nada ao ser lido, o
que `pickle` faz e é motivo suficiente para não usá-lo num arquivo que acompanha
um executável. E é pequeno: são onze características, então o arquivo tem alguns
kilobytes.

**O que é gravado junto, e por que importa.** Os nomes das características vão
no arquivo e são conferidos na leitura. Se alguém acrescentar uma característica
ao extrator e esquecer de retreinar, o vetor novo tem doze posições e os pesos
têm onze, e a multiplicação ou quebra ou, pior, alinha errado e produz uma
probabilidade plausível a partir de colunas trocadas. A conferência transforma
isso num erro claro no lugar certo.

Vai também a procedência: quando foi treinado, com quantas janelas, sobre qual
bateria, e os números de erro contra cobertura que ele atingiu. Modelo que decide
recusar sem dizer de onde veio é modelo que ninguém pode defender.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from cardiocam.qualidade.bayes import RegressaoLogisticaBayesiana
from cardiocam.qualidade.calibracao import Temperatura
from cardiocam.qualidade.caracteristicas import Padronizador
from cardiocam.qualidade.treino import ModeloDeQualidade

VERSAO_DO_FORMATO = 1

# Onde o modelo distribuído com o programa fica. Dentro do pacote, e não ao lado
# do repositório, porque é assim que ele acompanha o executável: o empacotador
# leva os dados do pacote junto, e um caminho relativo à pasta de trabalho
# falharia no `.exe`.
CAMINHO_PADRAO = Path(__file__).parent / "modelo.json"


@dataclass(frozen=True)
class Procedencia:
    """De onde este modelo veio. Vai junto no arquivo."""

    treinado_em: str
    janelas: int
    bateria: str
    erro_respondendo_sempre: float
    erro_com_abstencao: float
    cobertura: float
    observacao: str = ""

    def como_dicionario(self) -> dict:
        def numero(valor):
            return float(valor) if valor is not None and np.isfinite(valor) else None
        return {
            "treinado_em": self.treinado_em,
            "janelas": self.janelas,
            "bateria": self.bateria,
            "erro_respondendo_sempre": numero(self.erro_respondendo_sempre),
            "erro_com_abstencao": numero(self.erro_com_abstencao),
            "cobertura": numero(self.cobertura),
            "observacao": self.observacao,
        }


def agora_em_texto() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def salvar(
    modelo: ModeloDeQualidade,
    procedencia: Procedencia,
    caminho: Path | str = CAMINHO_PADRAO,
) -> Path:
    """Grava o modelo em JSON, com a procedência junto."""
    destino = Path(caminho)
    conteudo = {
        "versao": VERSAO_DO_FORMATO,
        "procedencia": procedencia.como_dicionario(),
        "nomes": list(modelo.regressao.nomes),
        "tolerancia_bpm": float(modelo.tolerancia_bpm),
        "limiar": float(modelo.limiar),
        "calibracao_viavel": modelo.calibracao_viavel,
        "temperatura": float(modelo.temperatura.valor),
        "regressao": {
            "media": [float(v) for v in modelo.regressao.media],
            "covariancia": [[float(v) for v in linha] for linha in modelo.regressao.covariancia],
            "variancia_priori": float(modelo.regressao.variancia_priori),
        },
        "padronizador": {
            "media": [float(v) for v in modelo.padronizador.media],
            "desvio": [float(v) for v in modelo.padronizador.desvio],
        },
    }
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(
        json.dumps(conteudo, ensure_ascii=False, allow_nan=False, indent=1) + "\n", encoding="utf-8"
    )
    return destino


def carregar(caminho: Path | str = CAMINHO_PADRAO) -> tuple[ModeloDeQualidade, Procedencia]:
    """Lê o modelo, conferindo que ele combina com o extrator atual.

    Levanta `ValueError` quando não combina. Erro claro aqui é muito melhor que
    probabilidade plausível vinda de colunas trocadas, que é o que acontece
    quando um vetor de doze posições encontra pesos de onze e o alinhamento
    passa despercebido.
    """
    origem = Path(caminho)
    dados = json.loads(origem.read_text(encoding="utf-8"))
    if type(dados.get("calibracao_viavel", True)) is not bool:
        raise ValueError("calibracao_viavel precisa ser booleana.")

    if dados.get("versao") != VERSAO_DO_FORMATO:
        raise ValueError(
            f"O modelo em {origem} está na versão {dados.get('versao')} e este "
            f"programa lê a versão {VERSAO_DO_FORMATO}. Treine de novo com "
            f"`cardiocam qualidade --gravar-modelo`."
        )

    nomes = tuple(dados["nomes"])
    from cardiocam.qualidade.caracteristicas import Caracteristicas

    atuais = tuple(Caracteristicas.nomes())
    if nomes != atuais:
        faltando = set(atuais) - set(nomes)
        sobrando = set(nomes) - set(atuais)
        raise ValueError(
            "As características deste modelo não são as que o extrator produz "
            f"hoje. Faltando no modelo: {sorted(faltando) or 'nenhuma'}. "
            f"Sobrando: {sorted(sobrando) or 'nenhuma'}. Treine de novo."
        )

    regressao = RegressaoLogisticaBayesiana(
        media=np.array(dados["regressao"]["media"], dtype=float),
        covariancia=np.array(dados["regressao"]["covariancia"], dtype=float),
        nomes=nomes,
        variancia_priori=float(dados["regressao"]["variancia_priori"]),
    )
    padronizador = Padronizador(
        media=np.array(dados["padronizador"]["media"], dtype=float),
        desvio=np.array(dados["padronizador"]["desvio"], dtype=float),
        nomes=nomes,
    )
    modelo = ModeloDeQualidade(
        regressao=regressao,
        padronizador=padronizador,
        limiar=float(dados["limiar"]),
        tolerancia_bpm=float(dados["tolerancia_bpm"]),
        temperatura=Temperatura(float(dados["temperatura"])),
        calibracao_viavel=bool(dados.get("calibracao_viavel", True)),
    )
    bruto = dados.get("procedencia", {})
    procedencia = Procedencia(
        treinado_em=bruto.get("treinado_em", "desconhecido"),
        janelas=int(bruto.get("janelas", 0)),
        bateria=bruto.get("bateria", "desconhecida"),
        erro_respondendo_sempre=float(bruto["erro_respondendo_sempre"]) if bruto.get("erro_respondendo_sempre") is not None else float("nan"),
        erro_com_abstencao=float(bruto["erro_com_abstencao"]) if bruto.get("erro_com_abstencao") is not None else float("nan"),
        cobertura=float(bruto["cobertura"]) if bruto.get("cobertura") is not None else float("nan"),
        observacao=bruto.get("observacao", ""),
    )
    return modelo, procedencia


def carregar_se_houver(
    caminho: Path | str = CAMINHO_PADRAO,
) -> tuple[ModeloDeQualidade, Procedencia] | None:
    """Versão tolerante, para quem roda sem modelo treinado.

    O programa precisa funcionar sem o arquivo: nesse caso ele volta a decidir
    pela regra fixa de relação sinal-ruído, que é o comportamento que sempre
    existiu. Falta de modelo é uma situação prevista, e não um erro.
    """
    origem = Path(caminho)
    if not origem.exists():
        return None
    try:
        return carregar(origem)
    except (ValueError, KeyError, json.JSONDecodeError):
        return None
