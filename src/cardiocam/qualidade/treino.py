"""Monta o conjunto, ajusta o modelo e escolhe o limiar, sem vazar nada.

O dado de treino sai de onde a resposta certa existe: os cenários sintéticos,
em que a frequência foi escolhida por nós. Cada janela vira uma linha, com as
características de um lado e, do outro, o rótulo "o erro desta janela ficou
dentro da tolerância".

Três cuidados definem a honestidade do número que sai daqui.

**Três partições, não duas.** Treino ajusta os pesos, calibração escolhe o
limiar de abstenção, teste reporta. Com duas partições o limiar seria escolhido
no mesmo dado em que é reportado, e o resultado publicado seria otimista por
construção. É o erro mais comum em trabalho com rejeição, e o mais fácil de
cometer sem perceber.

**A partição é por cenário, não por janela.** Janelas do mesmo vídeo são
parecidas entre si: partir por janela deixaria janelas quase idênticas dos dois
lados da divisão, e o teste mediria memorização. Agrupar por cenário é a versão
mínima do que, em dado real, precisa ser agrupamento por **sujeito**.

**O padronizador é ajustado só no treino.** Calcular média e desvio no conjunto
inteiro vaza a distribuição do teste para dentro do modelo.

A tolerância padrão de 3 bpm não é arbitrária: é a mesma usada nas tabelas de
acerto do projeto e é o critério corrente na literatura de rPPG, o que deixa o
número comparável com o que está publicado.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from cardiocam.qualidade import abstencao, calibracao
from cardiocam.qualidade.bayes import RegressaoLogisticaBayesiana, ajustar
from cardiocam.qualidade.calibracao import Temperatura
from cardiocam.qualidade.caracteristicas import Caracteristicas, Padronizador

TOLERANCIA_PADRAO_BPM = 3.0

# Proporções das três partições. A de calibração é a menor porque escolher um
# limiar numa varredura de vinte valores pede muito menos dado do que ajustar
# dez pesos ou estimar um erro médio com precisão.
FRACAO_TREINO = 0.6
FRACAO_CALIBRACAO = 0.15


@dataclass(frozen=True, slots=True)
class Amostra:
    """Uma janela avaliada: o que se viu, de que cenário veio, e quanto errou."""

    caracteristicas: Caracteristicas
    erro_bpm: float
    grupo: str
    """Identificador do cenário ou do sujeito. É por ele que a partição é
    feita."""

    def rotulo(self, tolerancia_bpm: float = TOLERANCIA_PADRAO_BPM) -> float:
        return 1.0 if abs(self.erro_bpm) <= tolerancia_bpm else 0.0


@dataclass(frozen=True, slots=True)
class Particao:
    """Índices das três partes, já separados por grupo."""

    treino: np.ndarray
    calibracao: np.ndarray
    teste: np.ndarray


@dataclass(frozen=True, slots=True)
class ModeloDeQualidade:
    """O que o sistema carrega em produção para decidir se responde."""

    regressao: RegressaoLogisticaBayesiana
    padronizador: Padronizador
    limiar: float
    """Limiar de abstenção escolhido na partição de calibração."""
    tolerancia_bpm: float
    temperatura: Temperatura = Temperatura(1.0)
    """Correção de confiança, ajustada na mesma partição de calibração.

    Vem depois do limiar na ordem de aplicação e **antes** dele na ordem de
    ajuste: a temperatura é monótona, então não muda qual janela é melhor que
    qual, só o número que acompanha. O limiar é escolhido já sobre a
    probabilidade corrigida, e assim ele passa a significar risco de verdade e
    não apenas uma posição na ordenação.
    """

    calibracao_viavel: bool = True

    def probabilidade(self, caracteristicas: Caracteristicas) -> float:
        """Chance de esta janela estar dentro da tolerância, já calibrada."""
        bruta = caracteristicas.vetor().reshape(1, -1)
        crua = self.regressao.prever(self.padronizador.aplicar(bruta))
        return float(self.temperatura.aplicar(crua)[0])

    def aceita(self, caracteristicas: Caracteristicas) -> bool:
        """A decisão de responder ou recusar."""
        return self.calibracao_viavel and self.probabilidade(caracteristicas) >= self.limiar


@dataclass(frozen=True, slots=True)
class RelatorioDeTreino:
    """Tudo que o treino produziu, para entrar no relatório sem recomputar."""

    modelo: ModeloDeQualidade
    calibracao_no_teste: calibracao.Calibracao
    curva_no_teste: abstencao.CurvaDeAbstencao
    ponto_adotado: abstencao.Ponto
    quantidade_treino: int
    quantidade_calibracao: int
    quantidade_teste: int
    grupos: int

    def resumo(self) -> str:
        """Texto curto com os números que decidem, para o pôster e o relatório."""
        ganho = self.curva_no_teste.erro_sem_abstencao - self.ponto_adotado.erro_medio
        return (
            f"{self.grupos} grupos, {self.quantidade_treino} janelas de treino, "
            f"{self.quantidade_calibracao} de calibração e {self.quantidade_teste} "
            f"de teste.\n"
            f"Respondendo sempre: {self.curva_no_teste.erro_sem_abstencao:.2f} bpm.\n"
            f"Com abstenção no limiar {self.modelo.limiar:.2f}: "
            f"{self.ponto_adotado.erro_medio:.2f} bpm com "
            f"{self.ponto_adotado.cobertura * 100:.1f}% de cobertura "
            f"(ganho de {ganho:.2f} bpm, recusando "
            f"{self.ponto_adotado.recusa * 100:.1f}%).\n"
            f"Calibração: ECE {self.calibracao_no_teste.ece:.4f}, "
            f"Brier {self.calibracao_no_teste.brier:.4f}, "
            f"temperatura {self.modelo.temperatura.valor:.2f}."
        )


def particionar(
    grupos: list[str],
    semente: int = 0,
    fracao_treino: float = FRACAO_TREINO,
    fracao_calibracao: float = FRACAO_CALIBRACAO,
) -> Particao:
    """Divide por grupo, com embaralhamento reprodutível.

    Nenhum grupo aparece em duas partições. É a propriedade que o teste
    `test_particao_nao_vaza_grupo` cobra, e é o que impede o número final de
    medir memorização.
    """
    if not 0.0 < fracao_treino < 1.0 or not 0.0 < fracao_calibracao < 1.0:
        raise ValueError("As frações precisam estar entre 0 e 1.")
    if fracao_treino + fracao_calibracao >= 1.0:
        raise ValueError(
            "Treino e calibração juntos precisam deixar espaço para o teste."
        )

    unicos = sorted(set(grupos))
    if len(unicos) < 3:
        raise ValueError(
            f"São {len(unicos)} grupo(s) distinto(s), e a partição por grupo "
            f"precisa de ao menos 3 para que cada parte receba um."
        )

    gerador = np.random.default_rng(semente)
    embaralhados = list(unicos)
    gerador.shuffle(embaralhados)

    corte_treino = max(1, int(round(len(embaralhados) * fracao_treino)))
    corte_calibracao = max(
        corte_treino + 1,
        corte_treino + int(round(len(embaralhados) * fracao_calibracao)),
    )
    # Garante ao menos um grupo no teste mesmo com poucos grupos.
    corte_calibracao = min(corte_calibracao, len(embaralhados) - 1)

    de_treino = set(embaralhados[:corte_treino])
    de_calibracao = set(embaralhados[corte_treino:corte_calibracao])

    array = np.array(grupos)
    return Particao(
        treino=np.flatnonzero(np.isin(array, list(de_treino))),
        calibracao=np.flatnonzero(np.isin(array, list(de_calibracao))),
        teste=np.flatnonzero(
            ~np.isin(array, list(de_treino | de_calibracao))
        ),
    )


def treinar(
    amostras: list[Amostra],
    tolerancia_bpm: float = TOLERANCIA_PADRAO_BPM,
    cobertura_minima: float = 0.5,
    erro_alvo_bpm: float = 2.0,
    semente: int = 0,
) -> RelatorioDeTreino:
    """Treina, calibra, escolhe o limiar e mede no teste, nessa ordem.

    `cobertura_minima` e `erro_alvo_bpm` são a política de uso, e ficam na
    assinatura porque são decisão de quem opera, não do modelo: um demonstrador
    quer responder quase sempre, uma medição de pesquisa prefere recusar.

    Quando nenhum limiar atinge os dois ao mesmo tempo, a calibração é marcada
    como inviável e o modelo recusa as leituras. A ausência de limiar viável
    aparece no relatório, em vez de ser interpretada como permissão para aceitar.
    """
    if len(amostras) < 10:
        raise ValueError(
            f"São {len(amostras)} amostras. Abaixo de uma dezena não há o que "
            f"ajustar, e o número que sairia seria ruído."
        )

    nomes = Caracteristicas.nomes()
    matriz = np.vstack([a.caracteristicas.vetor() for a in amostras])
    rotulos = np.array([a.rotulo(tolerancia_bpm) for a in amostras])
    erros = np.array([abs(a.erro_bpm) for a in amostras])
    grupos = [a.grupo for a in amostras]

    particao = particionar(grupos, semente=semente)
    if particao.treino.size == 0 or particao.teste.size == 0:
        raise ValueError("A partição deixou treino ou teste vazios.")

    # Uma classe só no treino: a posteriori fica dominada pela priori e o
    # modelo devolve a probabilidade de base em todo lugar. Isso é correto do
    # ponto de vista bayesiano, e inútil na prática, então é melhor dizer.
    if len(np.unique(rotulos[particao.treino])) < 2:
        raise ValueError(
            "O treino tem uma classe só: todas as janelas acertaram ou todas "
            "erraram. Sem contraste não há o que aprender; varie os cenários."
        )

    padronizador = Padronizador.ajustar(matriz[particao.treino], nomes)
    regressao = ajustar(
        padronizador.aplicar(matriz[particao.treino]),
        rotulos[particao.treino],
        nomes,
    )

    def cru(indices: np.ndarray) -> np.ndarray:
        return regressao.prever(padronizador.aplicar(matriz[indices]))

    # Temperatura e limiar saem da MESMA partição, que não é a de teste. Os
    # dois são parâmetros de decisão, e ajustar qualquer um deles no teste
    # tornaria o número reportado otimista por construção.
    temperatura = Temperatura(1.0)
    if particao.calibracao.size > 0:
        temperatura = Temperatura.ajustar(
            cru(particao.calibracao), rotulos[particao.calibracao]
        )

    def prever(indices: np.ndarray) -> np.ndarray:
        return temperatura.aplicar(cru(indices))

    limiar = None
    if particao.calibracao.size > 0:
        limiar = abstencao.escolher_limiar(
            prever(particao.calibracao),
            erros[particao.calibracao],
            cobertura_minima=cobertura_minima,
            erro_alvo_bpm=erro_alvo_bpm,
        )
    calibracao_viavel = limiar is not None
    limiar = 1.0 if limiar is None else limiar

    probabilidades_teste = prever(particao.teste)
    modelo = ModeloDeQualidade(
        regressao=regressao,
        padronizador=padronizador,
        limiar=limiar,
        tolerancia_bpm=tolerancia_bpm,
        temperatura=temperatura,
        calibracao_viavel=calibracao_viavel,
    )

    return RelatorioDeTreino(
        modelo=modelo,
        calibracao_no_teste=calibracao.aferir(
            probabilidades_teste, rotulos[particao.teste]
        ),
        curva_no_teste=abstencao.construir(
            probabilidades_teste, erros[particao.teste]
        ),
        ponto_adotado=abstencao.avaliar(
            probabilidades_teste, erros[particao.teste],
            limiar if calibracao_viavel else float("inf"),
        ),
        quantidade_treino=int(particao.treino.size),
        quantidade_calibracao=int(particao.calibracao.size),
        quantidade_teste=int(particao.teste.size),
        grupos=len(set(grupos)),
    )
