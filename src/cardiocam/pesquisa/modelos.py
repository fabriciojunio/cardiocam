"""Carregamento explícito de pesos e inferência com procedência verificável."""

import json
from pathlib import Path

import cv2
import numpy as np

from cardiocam.pesquisa.arquivos import sha256


def ler_manifesto(caminho):
    origem = Path(caminho).resolve()
    dados = json.loads(origem.read_text(encoding="utf-8"))
    if dados.get("versao") != 1 or dados.get("formato") not in ("torch_state_dict", "onnx"):
        raise ValueError("Manifesto de pesos desconhecido.")
    for campo in ("arquitetura", "arquivo", "sha256", "licenca", "procedencia", "preprocessamento"):
        if not isinstance(dados.get(campo), str) or not dados[campo].strip():
            raise ValueError(f"Declare {campo} no manifesto dos pesos.")
    peso = (origem.parent / dados["arquivo"]).resolve()
    if not peso.is_file() or sha256(peso) != dados["sha256"]:
        raise ValueError("Pesos ausentes ou SHA-256 divergente.")
    return dados, peso


class ModeloNeural:
    def __init__(self, manifesto):
        dados, peso = ler_manifesto(manifesto)
        self.procedencia = dados
        self.nome = dados["arquitetura"]
        if dados["formato"] != "torch_state_dict" or dados["preprocessamento"] != "rgb_0_1_local_v1":
            raise ValueError("Redes locais exigem state_dict e preprocessamento rgb_0_1_local_v1.")
        from cardiocam.pesquisa.redes import DeepPhys, EfficientPhys, PhysNet, ZeroDCE
        import torch
        tipos = {"deepphys": DeepPhys, "physnet": PhysNet, "efficientphys": EfficientPhys, "zero_dce": ZeroDCE}
        if self.nome not in tipos:
            raise ValueError("Arquitetura local desconhecida.")
        self.modelo = tipos[self.nome]()
        self.modelo.load_state_dict(torch.load(peso, map_location="cpu", weights_only=True), strict=True)
        self.modelo.eval()

    def prever(self, imagens_bgr: np.ndarray) -> np.ndarray:
        import torch
        video = np.asarray(imagens_bgr)
        if video.ndim != 4 or video.shape[-1] != 3 or video.dtype != np.uint8 or len(video) < 2:
            raise ValueError("Informe quadros BGR uint8 T×H×W×3.")
        tamanho = 64 if self.nome == "physnet" else 36
        rgb = np.array([cv2.resize(q, (tamanho, tamanho), interpolation=cv2.INTER_CUBIC)[:, :, ::-1]
                        for q in video], dtype=np.float32)/255
        tensor = torch.from_numpy(rgb.transpose(0, 3, 1, 2).copy())
        with torch.inference_mode():
            saida = self.modelo(tensor if self.nome == "zero_dce" else tensor.unsqueeze(0)).numpy()
        if not np.isfinite(saida).all():
            raise ValueError("O modelo produziu saída não finita.")
        if self.nome == "zero_dce":
            return saida.transpose(0, 2, 3, 1)
        return saida.ravel()


class RealcadorONNX:
    """Adaptador para Retinexformer/realçadores exportados, sem baixar pesos."""
    def __init__(self, manifesto):
        dados, peso = ler_manifesto(manifesto)
        if dados["formato"] != "onnx" or dados["preprocessamento"] != "rgb_nchw_0_1":
            raise ValueError("Realçador exige ONNX e contrato rgb_nchw_0_1.")
        self.procedencia = dados
        self.rede = cv2.dnn.readNetFromONNX(str(peso))

    def aplicar(self, imagem):
        if imagem.ndim != 3 or imagem.shape[2] != 3 or imagem.dtype != np.uint8:
            raise ValueError("Informe imagem BGR uint8.")
        entrada = (imagem[:, :, ::-1].transpose(2, 0, 1)[None].astype(np.float32)/255).copy()
        self.rede.setInput(entrada)
        saida = self.rede.forward()
        if saida.shape != entrada.shape or not np.isfinite(saida).all():
            raise ValueError("O realçador não conservou dimensões ou produziu valores inválidos.")
        return np.clip(np.round(saida[0].transpose(1, 2, 0)[:, :, ::-1]*255), 0, 255).astype(np.uint8)


class RealcadorLocal:
    """Zero-DCE local em resolução original, sem normalização entre quadros."""
    def __init__(self, manifesto):
        self.rede = ModeloNeural(manifesto)
        if self.rede.nome != "zero_dce":
            raise ValueError("O realçador local precisa de pesos Zero-DCE.")
        self.procedencia = self.rede.procedencia

    def aplicar(self, imagem):
        import torch
        if imagem.ndim != 3 or imagem.shape[2] != 3 or imagem.dtype != np.uint8:
            raise ValueError("Informe imagem BGR uint8.")
        x = torch.from_numpy((imagem[:, :, ::-1].transpose(2, 0, 1).astype(np.float32)/255).copy()).unsqueeze(0)
        with torch.inference_mode():
            y = self.rede.modelo(x).numpy()[0].transpose(1, 2, 0)[:, :, ::-1]
        if not np.isfinite(y).all():
            raise ValueError("O realçador produziu valores não finitos.")
        return np.clip(np.round(y*255), 0, 255).astype(np.uint8)


class ModeloPPGONNX:
    """Adaptador de redes adicionais exportadas com contrato temporal explícito."""
    def __init__(self, manifesto):
        dados, peso = ler_manifesto(manifesto)
        if dados["formato"] != "onnx" or dados["preprocessamento"] != "rgb_ncthw_0_1":
            raise ValueError("Rede PPG ONNX exige contrato rgb_ncthw_0_1.")
        tamanho = dados.get("tamanho", 64)
        if type(tamanho) is not int or not 16 <= tamanho <= 256:
            raise ValueError("Tamanho espacial ONNX inválido.")
        self.nome, self.procedencia, self.tamanho = dados["arquitetura"], dados, tamanho
        self.rede = cv2.dnn.readNetFromONNX(str(peso))

    def prever(self, imagens_bgr):
        video = np.asarray(imagens_bgr)
        if video.ndim != 4 or video.shape[-1] != 3 or video.dtype != np.uint8 or len(video) < 8:
            raise ValueError("Informe ao menos oito quadros BGR uint8.")
        rgb = np.array([cv2.resize(q, (self.tamanho, self.tamanho))[:, :, ::-1] for q in video], np.float32)/255
        entrada = rgb.transpose(3, 0, 1, 2)[None].copy()
        self.rede.setInput(entrada)
        y = self.rede.forward().ravel()
        if len(y) not in (len(video), len(video)-1) or not np.isfinite(y).all():
            raise ValueError("A rede ONNX não produziu uma onda temporal válida.")
        return y
