"""Põe o modelo de abstenção para decidir durante a medição de verdade.

Até aqui o modelo de qualidade existia, era testado, tinha um ADR explicando por
que é bayesiano, e **não rodava em lugar nenhum**: ele vivia dentro do comando
que o treinava. Toda medição real continuava decidindo pela regra fixa de relação
sinal-ruído, que é a primeira peneira e deixa passar justamente o caso que
machuca: janela com SNR alto, pico proeminente e estimativa a quarenta batimentos
da verdade.

Aqui ele entra no caminho. A cada janela emitida, as onze características são
extraídas dos mesmos quadros que produziram a estimativa, o modelo devolve
`P(|erro| ≤ tolerância)` já calibrada, e abaixo do limiar escolhido na partição
de calibração o número é recusado em vez de exibido.

**A ressalva, e ela é grande o bastante para estar no código e não só no
relatório.** O modelo foi treinado em bateria sintética, e o modo de falha dele
foi medido: com um tipo de artefato que não estava no treino, o ganho some em
cobertura razoável (10,52 bpm caindo para 8,01 só recusando 84% das janelas).
Medir pela janela de uma reunião é exatamente esse caso: compressão com
subamostragem de croma é um artefato que a bateria não contém. Então o veredito
do modelo aqui vale como indicação, não como garantia, e a interface mostra a
probabilidade em vez de esconder a decisão atrás de um selo.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from cardiocam.qualidade.caracteristicas import Caracteristicas
from cardiocam.qualidade.extracao import caracteristicas_da_analise
from cardiocam.qualidade.coleta_de_video import ContextoDaJanela, fracao_saturada
from cardiocam.qualidade.persistencia import Procedencia, carregar_se_houver
from cardiocam.qualidade.treino import ModeloDeQualidade


@dataclass(frozen=True)
class Veredito:
    """O que o modelo achou desta janela."""

    probabilidade: float
    limiar: float
    tolerancia_bpm: float

    @property
    def recusa(self) -> bool:
        return self.probabilidade < self.limiar

    @property
    def texto(self) -> str:
        return f"qualidade {self.probabilidade:.2f}"


class JuizDeQualidade:
    """Acumula o contexto de imagem e julga cada janela emitida.

    Sem modelo no disco, `disponivel` fica falso e tudo o que ele faz é guardar
    o contexto. Isso é previsto: o programa precisa funcionar sem o arquivo, e
    nesse caso volta a decidir pela regra fixa, que é o comportamento que sempre
    existiu.
    """

    def __init__(self, capacidade_da_janela: int) -> None:
        carregado = carregar_se_houver()
        self.modelo: ModeloDeQualidade | None = carregado[0] if carregado else None
        self.procedencia: Procedencia | None = carregado[1] if carregado else None
        self.contexto = ContextoDaJanela(capacidade=max(1, capacidade_da_janela))
        self._analise_julgada = None
        self._veredito: Veredito | None = None

    def reiniciar(self) -> None:
        self.contexto.limpar()
        self._analise_julgada = None
        self._veredito = None

    @property
    def disponivel(self) -> bool:
        return self.modelo is not None

    def registrar_quadro(self, quadro: np.ndarray, estado) -> None:
        """Guarda o que a imagem mostra neste quadro.

        Precisa ser chamada em **todo** quadro com rosto, e não só nos que
        emitem janela: as características de imagem descrevem o conjunto de
        quadros que formou a estimativa, e não o último deles.
        """
        if getattr(estado, "contexto_reiniciado", False):
            self.reiniciar()
        if estado.amostra is None or estado.caixa is None:
            return
        largura = quadro.shape[1] or 1
        self.contexto.registrar(
            estado.amostra.proporcao_pele,
            fracao_saturada(quadro, estado.caixa),
            (estado.caixa.x + estado.caixa.largura / 2.0) / largura,
            instante=getattr(estado, "instante", None),
            inicio=getattr(estado, "inicio_janela", None),
        )

    def caracteristicas(self, analise) -> Caracteristicas:
        return caracteristicas_da_analise(analise, contexto=self.contexto)

    def julgar(self, analise) -> Veredito | None:
        """Probabilidade de a estimativa estar dentro da tolerância.

        Devolve `None` quando não há modelo, e também quando a extração falha:
        característica que não pôde ser calculada vira recusa silenciosa se
        entrar como zero, e recusa silenciosa é pior que ausência de veredito.
        """
        if self.modelo is None or analise is None:
            return None
        if analise is self._analise_julgada:
            return self._veredito
        self._analise_julgada = analise
        self._veredito = None
        try:
            probabilidade = self.modelo.probabilidade(self.caracteristicas(analise))
        except (ValueError, FloatingPointError):
            return None
        if not np.isfinite(probabilidade):
            return None
        self._veredito = Veredito(
            probabilidade=float(probabilidade),
            limiar=float(self.modelo.limiar),
            tolerancia_bpm=float(self.modelo.tolerancia_bpm),
        )
        return self._veredito
