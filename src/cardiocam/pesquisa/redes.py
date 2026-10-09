"""Redes de referência independentes, optativas, sem pesos distribuídos.

As arquiteturas seguem DeepPhys (ECCV 2018), PhysNet-3DCNN-ED (2019),
EfficientPhys convolucional (WACV 2023) e curvas Zero-DCE (CVPR 2020).
São implementações locais para treino/avaliação, não checkpoints compatíveis
com repositórios externos nem reproduções de suas métricas publicadas.
"""

import torch
from torch import nn
from torch.nn import functional as F


class Atencao(nn.Module):
    def __init__(self, canais):
        super().__init__()
        self.projecao = nn.Conv2d(canais, 1, 1)

    def forward(self, x):
        mascara = torch.sigmoid(self.projecao(x))
        return mascara / (2*mascara.mean(dim=(-2, -1), keepdim=True).clamp_min(1e-8))


def _convs(entrada, saida):
    return nn.Sequential(nn.Conv2d(entrada, saida, 3, padding=1), nn.Tanh(),
                         nn.Conv2d(saida, saida, 3, padding=1), nn.Tanh())


class DeepPhys(nn.Module):
    """Entrada B×T×3×36×36 RGB [0,1]; saída B×(T-1), derivada de PPG."""
    def __init__(self):
        super().__init__()
        self.aparencia1, self.movimento1 = _convs(3, 32), _convs(3, 32)
        self.aparencia2, self.movimento2 = _convs(32, 64), _convs(32, 64)
        self.atencao1, self.atencao2 = Atencao(32), Atencao(64)
        self.saida = nn.Sequential(nn.Flatten(), nn.Dropout(.25), nn.Linear(64*9*9, 128),
                                   nn.Tanh(), nn.Dropout(.5), nn.Linear(128, 1))

    def forward(self, video):
        _validar_video(video, tamanho=36)
        b, t = video.shape[:2]
        diferenca = (video[:, 1:]-video[:, :-1])/(video[:, 1:]+video[:, :-1]).clamp_min(1e-6)
        std = diferenca.std(dim=(1, 2, 3, 4), keepdim=True, unbiased=False).clamp_min(1e-6)
        m = (diferenca.clamp(-3*std, 3*std)/std).reshape(-1, 3, 36, 36)
        media = video.mean(dim=(1, 2, 3, 4), keepdim=True)
        escala = video.std(dim=(1, 2, 3, 4), keepdim=True, unbiased=False).clamp_min(1e-6)
        a = ((video[:, :-1]-media)/escala).reshape(-1, 3, 36, 36)
        a, m = self.aparencia1(a), self.movimento1(m)
        m = F.avg_pool2d(m*self.atencao1(a), 2)
        a = self.aparencia2(F.avg_pool2d(a, 2))
        m = self.movimento2(m)
        return self.saida(F.avg_pool2d(m*self.atencao2(a), 2)).reshape(b, t-1)


def _conv3d(entrada, saida, kernel=3):
    padding = tuple(k//2 for k in kernel) if isinstance(kernel, tuple) else 1
    return nn.Sequential(nn.Conv3d(entrada, saida, kernel, padding=padding),
                         nn.BatchNorm3d(saida), nn.ReLU())


class PhysNet(nn.Module):
    """Variante 3DCNN-ED; entrada B×T×3×H×W; saída PPG B×T."""
    def __init__(self):
        super().__init__()
        self.codificador = nn.Sequential(
            _conv3d(3, 16, (1, 5, 5)), nn.MaxPool3d((1, 2, 2)),
            _conv3d(16, 32), _conv3d(32, 64), nn.MaxPool3d(2),
            _conv3d(64, 64), _conv3d(64, 64), nn.MaxPool3d(2),
            _conv3d(64, 64), _conv3d(64, 64), nn.MaxPool3d((1, 2, 2)),
            _conv3d(64, 64), _conv3d(64, 64))
        self.decodificador = nn.Sequential(
            nn.ConvTranspose3d(64, 64, (4, 1, 1), (2, 1, 1), (1, 0, 0)), nn.BatchNorm3d(64), nn.ELU(),
            nn.ConvTranspose3d(64, 64, (4, 1, 1), (2, 1, 1), (1, 0, 0)), nn.BatchNorm3d(64), nn.ELU())
        self.projecao = nn.Conv3d(64, 1, 1)

    def forward(self, video):
        _validar_video(video)
        if video.shape[1] < 8 or min(video.shape[-2:]) < 32:
            raise ValueError("PhysNet exige oito quadros e resolução mínima 32×32.")
        x = self.decodificador(self.codificador(video.transpose(1, 2)))
        x = F.adaptive_avg_pool3d(x, (video.shape[1], 1, 1))
        return self.projecao(x).flatten(1)


def deslocar_temporal(x, lote, quadros):
    """TSM dentro de cada vídeo; nenhum quadro atravessa a fronteira do lote."""
    y = x.reshape(lote, quadros, *x.shape[1:])
    z = torch.zeros_like(y)
    faixa = x.shape[1]//3
    z[:, :-1, :faixa] = y[:, 1:, :faixa]
    z[:, 1:, faixa:2*faixa] = y[:, :-1, faixa:2*faixa]
    z[:, :, 2*faixa:] = y[:, :, 2*faixa:]
    return z.reshape_as(x)


class EfficientPhys(nn.Module):
    """Baseline convolucional com diferença, BN, TSM e atenção própria."""
    def __init__(self):
        super().__init__()
        self.normalizacao = nn.BatchNorm2d(3)
        self.convs = nn.ModuleList([nn.Conv2d(a, b, 3, padding=1)
                                   for a, b in ((3, 32), (32, 32), (32, 64), (64, 64))])
        self.atencoes = nn.ModuleList([Atencao(32), Atencao(64)])
        self.saida = nn.Sequential(nn.Flatten(), nn.Dropout(.25), nn.Linear(64*9*9, 128),
                                   nn.Tanh(), nn.Dropout(.5), nn.Linear(128, 1))

    def forward(self, video):
        _validar_video(video, tamanho=36)
        b, t = video.shape[:2]
        x = self.normalizacao((video[:, 1:]-video[:, :-1]).reshape(-1, 3, 36, 36))
        for i, conv in enumerate(self.convs):
            x = torch.tanh(conv(deslocar_temporal(x, b, t-1)))
            if i % 2:
                x = F.avg_pool2d(x*self.atencoes[i//2](x), 2)
        return self.saida(x).reshape(b, t-1)


class ZeroDCE(nn.Module):
    """Estimador de oito curvas por pixel; requer treino/licença dos pesos."""
    def __init__(self):
        super().__init__()
        self.convs = nn.ModuleList(nn.Conv2d(a, b, 3, padding=1)
                                   for a, b in ((3, 32), (32, 32), (32, 32), (32, 32),
                                                (64, 32), (64, 32), (64, 24)))

    def forward(self, x):
        if x.ndim != 4 or x.shape[1] != 3 or not torch.isfinite(x).all() or x.min() < 0 or x.max() > 1:
            raise ValueError("Zero-DCE requer imagens RGB N×3×H×W entre zero e um.")
        a = F.relu(self.convs[0](x))
        b = F.relu(self.convs[1](a))
        c = F.relu(self.convs[2](b))
        d = F.relu(self.convs[3](c))
        e = F.relu(self.convs[4](torch.cat([c, d], dim=1)))
        f = F.relu(self.convs[5](torch.cat([b, e], dim=1)))
        curvas = torch.tanh(self.convs[6](torch.cat([a, f], dim=1)))
        y = x
        for curva in curvas.split(3, dim=1):
            y = y + curva*(y.square()-y)
        return y


def _validar_video(video, tamanho=None):
    if (video.ndim != 5 or video.shape[2] != 3 or video.shape[1] < 2
            or not torch.isfinite(video).all() or video.min() < 0 or video.max() > 1
            or (tamanho and video.shape[-2:] != (tamanho, tamanho))):
        raise ValueError("Informe vídeos RGB B×T×3×H×W finitos entre zero e um.")


def perda_pearson(predito, referencia):
    if predito.shape != referencia.shape or not torch.isfinite(referencia).all():
        raise ValueError("Referência incompatível.")
    a = predito-predito.mean(dim=-1, keepdim=True)
    b = referencia-referencia.mean(dim=-1, keepdim=True)
    return (1-(a*b).sum(dim=-1)/(a.square().sum(dim=-1)*b.square().sum(dim=-1)).sqrt().clamp_min(1e-8)).mean()
