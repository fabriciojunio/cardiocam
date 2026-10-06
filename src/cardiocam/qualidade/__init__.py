"""Decide se a medição desta janela é confiável, e recusa quando não é.

É a segunda metade do sistema. A primeira estima a frequência; esta estima
**quanto acreditar na estimativa**, e tem autoridade para calar a resposta.

A razão de existir é que um medidor sem essa metade não tem como errar de forma
visível. Ele sempre devolve um número, e um número errado com a mesma cara de um
número certo é pior do que silêncio: quem lê não tem como distinguir. Os três
testes que o projeto já tinha, para parede lisa, imagem saturada e vídeo curto,
atacavam o mesmo problema por regra fixa. Aqui ele é atacado por modelo, com a
probabilidade de acerto estimada e a taxa de recusa declarada ao lado do erro.

O caminho é:

```
janela  →  características (nada que dependa da resposta certa)
            →  regressão logística bayesiana  →  P(erro ≤ tolerância)
                →  limiar escolhido em partição própria  →  responde ou recusa
```

E a avaliação do conjunto é a curva de erro contra cobertura, que é o produto
da hipótese H4 do projeto de iniciação científica.
"""

from cardiocam.qualidade.abstencao import (
    CurvaDeAbstencao,
    Ponto,
    avaliar,
    construir,
    escolher_limiar,
)
from cardiocam.qualidade.bayes import (
    Previsao,
    RegressaoLogisticaBayesiana,
    ajustar,
    sigmoide,
)
from cardiocam.qualidade.calibracao import Calibracao, Faixa, aferir, brier
from cardiocam.qualidade.caracteristicas import (
    Caracteristicas,
    Padronizador,
    correlacao,
    desvio_cromatico,
    dispersao_do_pico,
    entropia_espectral,
    extrair,
    proeminencia,
    razao_harmonica,
)
from cardiocam.qualidade.treino import (
    Amostra,
    ModeloDeQualidade,
    Particao,
    RelatorioDeTreino,
    particionar,
    treinar,
)

__all__ = [
    "Amostra",
    "Calibracao",
    "Caracteristicas",
    "CurvaDeAbstencao",
    "Faixa",
    "ModeloDeQualidade",
    "Padronizador",
    "Particao",
    "Ponto",
    "Previsao",
    "RegressaoLogisticaBayesiana",
    "RelatorioDeTreino",
    "aferir",
    "ajustar",
    "avaliar",
    "brier",
    "construir",
    "correlacao",
    "desvio_cromatico",
    "dispersao_do_pico",
    "entropia_espectral",
    "escolher_limiar",
    "extrair",
    "particionar",
    "proeminencia",
    "razao_harmonica",
    "sigmoide",
    "treinar",
]
