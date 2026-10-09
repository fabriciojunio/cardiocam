"""Treino de referência com onda PPG e seleção na calibração, nunca no teste."""

import json
from pathlib import Path

import numpy as np

from cardiocam.pesquisa.arquivos import gravar_json, sha256


def carregar_clipes(manifesto):
    origem = Path(manifesto).resolve()
    dados = json.loads(origem.read_text(encoding="utf-8"))
    if dados.get("versao") != 1 or not dados.get("clipes"):
        raise ValueError("Manifesto neural vazio ou desconhecido.")
    partes = {p: [] for p in ("treino", "calibracao", "teste")}
    sujeitos = {}
    for clip in dados["clipes"]:
        for chave in ("participante", "particao", "dataset", "licenca", "arquivo"):
            if not isinstance(clip.get(chave), str) or not clip[chave].strip():
                raise ValueError(f"Clipe sem {chave}.")
        pessoa, parte = clip["participante"], clip["particao"]
        if parte not in partes or (pessoa in sujeitos and sujeitos[pessoa] != parte):
            raise ValueError("Participante compartilhado ou partição desconhecida.")
        sujeitos[pessoa] = parte
        with np.load(origem.parent / clip["arquivo"], allow_pickle=False) as arquivo:
            video, ppg = arquivo["video"].copy(), arquivo["ppg"].astype(np.float32)
            fps = float(arquivo["fps"])
        if (video.ndim != 4 or video.shape[-1] != 3 or video.dtype != np.uint8
                or len(video) < 8 or len(video) > 600 or ppg.shape != (len(video),)
                or not np.isfinite(ppg).all() or np.std(ppg) < 1e-6
                or not np.isfinite(fps) or fps < 8):
            raise ValueError("Clipe exige vídeo RGB uint8, onda PPG sincronizada variável e FPS válido.")
        partes[parte].append((video, ppg, fps, clip))
    if any(not p for p in partes.values()):
        raise ValueError("As três partições precisam de clipes.")
    return partes, dados


def treinar_rede(manifesto, arquitetura, pasta_saida, epocas=10, taxa=1e-3, semente=0):
    import cv2
    import torch
    from cardiocam.pesquisa.redes import DeepPhys, EfficientPhys, PhysNet, perda_pearson
    tipos = {"deepphys": DeepPhys, "physnet": PhysNet, "efficientphys": EfficientPhys}
    if arquitetura not in tipos or type(epocas) is not int or epocas < 1 or not np.isfinite(taxa) or taxa <= 0:
        raise ValueError("Arquitetura ou parâmetros de treino inválidos.")
    partes, dados = carregar_clipes(manifesto)
    pasta = Path(pasta_saida).resolve()
    peso, ficha = pasta / "pesos.pt", pasta / "pesos.json"
    if peso.exists() or ficha.exists() or (pasta / "treino.json").exists():
        raise ValueError("Escolha uma pasta sem resultados anteriores.")
    torch.manual_seed(semente)
    modelo = tipos[arquitetura]()
    otimizador = torch.optim.Adam(modelo.parameters(), lr=taxa)
    tamanho = 64 if arquitetura == "physnet" else 36

    def preparar(amostra):
        video, ppg, _, _ = amostra
        rgb = np.array([cv2.resize(q, (tamanho, tamanho), interpolation=cv2.INTER_CUBIC)
                        for q in video], np.float32)/255
        x = torch.from_numpy(rgb.transpose(0, 3, 1, 2).copy()).unsqueeze(0)
        y = ppg if arquitetura == "physnet" else np.diff(ppg)
        y = (y-y.mean())/max(y.std(), 1e-6)
        return x, torch.from_numpy(y.copy()).unsqueeze(0)

    def perda(predito, y):
        return perda_pearson(predito, y) if arquitetura == "physnet" else torch.nn.functional.mse_loss(predito, y)

    def avaliar_parte(parte):
        modelo.eval()
        valores = []
        with torch.inference_mode():
            for amostra in parte:
                x, y = preparar(amostra)
                valores.append(float(perda(modelo(x), y)))
        return float(np.mean(valores))

    historico, melhor, estado = [], float("inf"), None
    for epoca in range(epocas):
        modelo.train()
        erros = []
        for amostra in partes["treino"]:
            x, y = preparar(amostra)
            otimizador.zero_grad(set_to_none=True)
            erro = perda(modelo(x), y)
            if not torch.isfinite(erro):
                raise ValueError("Treino produziu perda não finita.")
            erro.backward()
            torch.nn.utils.clip_grad_norm_(modelo.parameters(), 5)
            otimizador.step()
            erros.append(float(erro.detach()))
        calibracao = avaliar_parte(partes["calibracao"])
        historico.append({"epoca": epoca+1, "perda_treino": float(np.mean(erros)), "perda_calibracao": calibracao})
        if calibracao < melhor:
            melhor = calibracao
            estado = {k: v.detach().clone() for k, v in modelo.state_dict().items()}
    modelo.load_state_dict(estado)
    teste = avaliar_parte(partes["teste"])
    if not np.isfinite(teste):
        raise ValueError("Avaliação neural não finita.")
    pasta.mkdir(parents=True, exist_ok=True)
    with peso.open("xb") as arquivo:
        torch.save(estado, arquivo)
    gravar_json(ficha, {"versao": 1, "formato": "torch_state_dict", "arquitetura": arquitetura,
                       "arquivo": peso.name, "sha256": sha256(peso), "licenca": "Pesos locais; verificar licenças dos datasets declarados",
                       "procedencia": str(Path(manifesto).resolve()), "preprocessamento": "rgb_0_1_local_v1",
                       "experimental": True, "datasets": sorted({c["dataset"] for c in dados["clipes"]})})
    resultado = {"arquitetura": arquitetura, "epocas": epocas, "semente": semente,
                 "historico": historico, "perda_teste": teste,
                 "clipes": {p: len(v) for p, v in partes.items()},
                 "aviso": "Perda de onda não comprova precisão cardíaca nem validade clínica."}
    gravar_json(pasta / "treino.json", resultado)
    return resultado
