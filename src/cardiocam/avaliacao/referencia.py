"""Avaliação de CSV de medições contra uma referência sincronizada.

A referência contém BPM previamente derivados de ECG ou PPG de contato.
Não estima a referência a partir do próprio vídeo e não extrapola lacunas.
"""

import argparse
import csv
import json
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np


@dataclass(frozen=True)
class MetricasDeReferencia:
    registros: int
    com_referencia: int
    aceitas: int
    cobertura_registros: float
    mae_bpm: float | None
    rmse_bpm: float | None
    vies_bpm: float | None
    limite_inferior_bpm: float | None
    limite_superior_bpm: float | None
    proporcao_dentro_5_bpm: float | None
    proporcao_aceitas_com_erro_acima_5_bpm: float | None


def ler_referencia(caminho):
    with Path(caminho).open(encoding="utf-8-sig", newline="") as arquivo:
        linhas = list(csv.DictReader(arquivo))
    tempos = np.array([float(l["instante_s"]) for l in linhas])
    bpm = np.array([float(l["bpm"]) for l in linhas])
    if (tempos.size < 2 or not np.all(np.isfinite(tempos))
            or not np.all(np.isfinite(bpm)) or np.any(bpm <= 0)
            or np.any(np.diff(tempos) <= 0)):
        raise ValueError("A referência precisa ter BPM positivos e instantes finitos e crescentes.")
    return tempos, bpm


def valor_referencia(tempos, bpm, instante, lacuna_maxima_s):
    if instante < tempos[0] or instante > tempos[-1]:
        return None
    direita = int(np.searchsorted(tempos, instante))
    if direita < len(tempos) and abs(tempos[direita] - instante) < 1e-8:
        return float(bpm[direita])
    if direita == 0 or direita == len(tempos):
        return None
    if tempos[direita] - tempos[direita - 1] > lacuna_maxima_s:
        return None
    return float(np.interp(instante, tempos[direita - 1:direita + 1], bpm[direita - 1:direita + 1]))


def avaliar_csv(leituras, referencia, offset_s=0.0, lacuna_maxima_s=2.0):
    if not np.isfinite(offset_s) or not np.isfinite(lacuna_maxima_s) or lacuna_maxima_s <= 0:
        raise ValueError("O alinhamento precisa ser finito e a lacuna máxima positiva.")
    tempos, bpm = ler_referencia(referencia)
    with Path(leituras).open(encoding="utf-8-sig", newline="") as arquivo:
        linhas = list(csv.DictReader(arquivo))
    erros = []
    com_referencia = 0
    for linha in linhas:
        instante = float(linha["instante_s"]) + offset_s
        if not np.isfinite(instante):
            raise ValueError("Uma leitura tem instante inválido.")
        aceita = linha["aceita"].strip().lower()
        if aceita not in ("true", "false"):
            raise ValueError("A coluna aceita precisa conter True ou False.")
        if aceita == "true":
            estimativa = float(linha["bpm"])
            if not np.isfinite(estimativa) or estimativa <= 0:
                raise ValueError("Uma leitura aceita tem BPM inválido.")
        verdade = valor_referencia(tempos, bpm, instante, lacuna_maxima_s)
        if verdade is None:
            continue
        com_referencia += 1
        if aceita == "true":
            erros.append(estimativa - verdade)
    vies = float(np.mean(erros)) if erros else None
    desvio = float(np.std(erros, ddof=1)) if len(erros) > 1 else None
    return MetricasDeReferencia(
        len(linhas), com_referencia, len(erros), len(erros) / len(linhas) if linhas else 0.0,
        float(np.mean(np.abs(erros))) if erros else None,
        float(np.sqrt(np.mean(np.square(erros)))) if erros else None, vies,
        vies - 1.96 * desvio if desvio is not None else None,
        vies + 1.96 * desvio if desvio is not None else None,
        float(np.mean(np.abs(erros) <= 5)) if erros else None,
        float(np.mean(np.abs(erros) > 5)) if erros else None,
    )


def avaliar_manifesto(caminho):
    origem = Path(caminho).resolve()
    dados = json.loads(origem.read_text(encoding="utf-8"))
    sessoes = dados["sessoes"]
    if not sessoes:
        raise ValueError("O manifesto precisa conter sessões.")
    resultados = []
    for sessao in sessoes:
        for campo in ("participante", "dispositivo", "condicao", "dataset", "licenca"):
            if not isinstance(sessao.get(campo), str) or not sessao[campo].strip():
                raise ValueError(f"A sessão precisa declarar {campo}.")
        metricas = avaliar_csv(origem.parent / sessao["leituras"],
                               origem.parent / sessao["referencia"],
                               sessao.get("offset_s", 0.0), sessao.get("lacuna_maxima_s", 2.0))
        resultados.append({**sessao, "metricas": asdict(metricas)})
    # Mantém cada participante explícito. Não soma janelas sobrepostas como
    # se fossem observações independentes ou participantes adicionais.
    return {"sessoes": resultados, "participantes": len({s["participante"] for s in sessoes}),
            "aviso": "Cobertura sobre registros exportados; não equivale à cobertura de todo o vídeo."}


def principal():
    from cardiocam.__main__ import _preparar_console
    _preparar_console()
    argumentos = argparse.ArgumentParser(description="Avalia leituras contra referência sincronizada de ECG ou PPG.")
    argumentos.add_argument("manifesto")
    argumentos.add_argument("--saida", required=True)
    opcoes = argumentos.parse_args()
    resultado = avaliar_manifesto(opcoes.manifesto)
    Path(opcoes.saida).write_text(json.dumps(resultado, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
                                 encoding="utf-8")


if __name__ == "__main__":
    principal()
