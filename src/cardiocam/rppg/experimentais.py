"""Métodos de pesquisa, separados dos quatro algoritmos do aplicativo.

Implementações NumPy das operações matemáticas descritas na literatura.
LGI: Pilz et al. (2018), doi:10.1109/CVPRW.2018.00172.
OMIT: Álvarez Casado e Bordallo López, arXiv:2202.04101, seção 5.
PBV: de Haan e van Leest (2014), doi:10.1088/0967-3334/35/9/1913.

O PBV adaptativo estima a assinatura pela dispersão dos canais. É uma variante
experimental; não substitui uma assinatura calibrada para câmera e iluminante.
Não houve cópia de implementação de outros projetos.
"""

import numpy as np

from cardiocam.rppg.base import finalizar


class Lgi:
    nome = "lgi"

    def extrair(self, serie, config):
        canais = serie.como_matriz()
        dominante = np.linalg.svd(canais, full_matrices=False)[0][:, 0]
        # Calcula somente a linha verde da projeção I - uuᵀ.
        pulso = canais[1] - dominante[1] * (dominante @ canais)
        return finalizar(pulso, serie, config, self.nome)


class Omit:
    nome = "omit"

    def extrair(self, serie, config):
        canais = serie.como_matriz().T
        base = np.linalg.qr(canais, mode="reduced")[0][:, 0]
        # Projeção temporal descrita no artigo, sem alocar uma matriz NxN.
        pulso = canais[:, 1] - base * (base @ canais[:, 1])
        return finalizar(pulso, serie, config, self.nome)


class PbvAdaptativo:
    nome = "pbv_adaptativo"

    def extrair(self, serie, config):
        canais = serie.como_matriz()
        medias = np.mean(canais, axis=1, keepdims=True)
        normalizados = np.divide(canais, medias, out=np.zeros_like(canais),
                                 where=np.abs(medias) > 1e-12)
        assinatura = np.std(normalizados, axis=1)
        norma = np.linalg.norm(assinatura)
        if norma < 1e-12:
            return finalizar(np.zeros(len(serie)), serie, config, self.nome)
        assinatura /= norma
        gram = normalizados @ normalizados.T
        pesos = np.linalg.pinv(gram, rcond=1e-10) @ assinatura
        ganho = float(assinatura @ pesos)
        pulso = (pesos @ normalizados) / ganho if abs(ganho) > 1e-12 else np.zeros(len(serie))
        return finalizar(pulso, serie, config, self.nome)


ALGORITMOS_EXPERIMENTAIS = (Lgi, Omit, PbvAdaptativo)
