"""Janela deslizante sobre o fluxo de quadros.

A análise não roda a cada quadro: acumulamos alguns segundos de sinal e só
então emitimos uma estimativa, deslizando a janela em passos menores. É o
compromisso clássico entre resolução em frequência (janela longa) e capacidade
de acompanhar mudanças (janela curta).
"""

from __future__ import annotations

from collections import deque

import numpy as np

from cardiocam.dominio.config import ConfiguracaoAnalise
from cardiocam.dominio.sinal import SerieRGB
from cardiocam.sinais.preprocessamento import estimar_fps, reamostrar_uniforme


class JanelaDeslizante:
    """Buffer circular de amostras RGB com carimbo de tempo."""

    def __init__(self, fps_nominal: float, config: ConfiguracaoAnalise | None = None) -> None:
        if not np.isfinite(fps_nominal) or fps_nominal <= 0:
            raise ValueError("A taxa de quadros nominal precisa ser positiva.")
        self.config = config or ConfiguracaoAnalise()
        self.fps_nominal = float(fps_nominal)

        capacidade = self.config.amostras_por_janela(fps_nominal)
        self._vermelho: deque[float] = deque()
        self._verde: deque[float] = deque()
        self._azul: deque[float] = deque()
        self._instantes: deque[float] = deque()
        self._fundo: deque[tuple[float, float, float] | None] = deque()

        self._capacidade = capacidade
        self._passo = self.config.amostras_por_passo(fps_nominal)
        self._desde_ultima_emissao = 0
        self._total_recebido = 0
        self._ultima_emissao: float | None = None

    @property
    def capacidade(self) -> int:
        return self._capacidade

    @property
    def total_recebido(self) -> int:
        return self._total_recebido

    def __len__(self) -> int:
        return len(self._verde)

    @property
    def cheia(self) -> bool:
        return len(self._verde) >= 2 and self.duracao_s >= self.config.janela_s - 1e-8

    @property
    def inicio(self) -> float | None:
        return self._instantes[0] if self._instantes else None

    @property
    def duracao_s(self) -> float:
        if not self._instantes:
            return 0.0
        return self._instantes[-1] - self._instantes[0] + self._periodo()

    @property
    def progresso(self) -> float:
        return min(1.0, self.duracao_s / self.config.janela_s)

    def _periodo(self) -> float:
        if len(self._instantes) < 2:
            return 1.0 / self.fps_nominal
        # A mediana local evita percorrer a janela inteira a cada quadro.
        recentes = list(self._instantes)[-30:]
        return float(np.median(np.diff(recentes)))

    def adicionar(
        self,
        vermelho: float,
        verde: float,
        azul: float,
        instante: float,
        fundo: tuple[float, float, float] | None = None,
    ) -> None:
        """Registra a média RGB de mais um quadro, e a do fundo quando houver."""
        if not np.isfinite(instante) or (self._instantes and instante <= self._instantes[-1]):
            raise ValueError("Os instantes precisam ser finitos e estritamente crescentes.")
        self._vermelho.append(float(vermelho))
        self._verde.append(float(verde))
        self._azul.append(float(azul))
        self._instantes.append(float(instante))
        self._fundo.append(fundo)
        self._desde_ultima_emissao += 1
        self._total_recebido += 1
        corte = instante - self.config.janela_s + self._periodo()
        # Mantém a amostra imediatamente anterior ao corte em captura irregular,
        # para não encurtar a janela por uma fração de quadro a cada atualização.
        while len(self._instantes) > 2 and self._instantes[1] <= corte + 1e-8:
            for buffer in (self._vermelho, self._verde, self._azul, self._instantes, self._fundo):
                buffer.popleft()

    def deve_emitir(self) -> bool:
        """Verdadeiro quando há janela cheia e já passou um passo desde a última
        estimativa."""
        return self.cheia and (
            self._ultima_emissao is None
            or self._instantes[-1] - self._ultima_emissao >= self.config.passo_s - 1e-8
        )

    def marcar_emissao(self) -> None:
        self._desde_ultima_emissao = 0
        self._ultima_emissao = self._instantes[-1] if self._instantes else None

    def limpar(self) -> None:
        """Zera o buffer. Chamado quando o rosto some por tempo demais e o sinal
        acumulado deixa de fazer sentido."""
        self._vermelho.clear()
        self._verde.clear()
        self._azul.clear()
        self._instantes.clear()
        self._fundo.clear()
        self._desde_ultima_emissao = 0
        self._ultima_emissao = None

    def fps_efetivo(self) -> float:
        """Taxa real medida pelos carimbos de tempo, com o nominal como reserva."""
        medido = estimar_fps(np.asarray(self._instantes, dtype=float))
        return medido if medido > 0 else self.fps_nominal

    def serie(self, uniformizar: bool = True) -> SerieRGB:
        """Conteúdo atual da janela como série RGB.

        Com `uniformizar`, reinterpola numa grade temporal regular usando a taxa
        efetiva medida, que é o que torna a FFT confiável apesar do jitter da
        câmera.
        """
        vermelho = np.asarray(self._vermelho, dtype=float)
        verde = np.asarray(self._verde, dtype=float)
        azul = np.asarray(self._azul, dtype=float)
        instantes = np.asarray(self._instantes, dtype=float)
        fundo = self._matriz_de_fundo()

        fps = self.fps_efetivo()
        if not uniformizar or len(verde) < 2:
            return SerieRGB(vermelho, verde, azul, fps, instantes, fundo)

        matriz = np.vstack([vermelho, verde, azul])
        if fundo is not None:
            matriz = np.vstack([matriz, fundo])
        reamostrado, grade = reamostrar_uniforme(matriz, instantes, fps)
        fundo_reamostrado = reamostrado[3:6] if fundo is not None else None
        return SerieRGB(
            reamostrado[0], reamostrado[1], reamostrado[2], fps, grade, fundo_reamostrado
        )

    def _matriz_de_fundo(self) -> np.ndarray | None:
        """Fundo como matriz 3xN, ou None se algum quadro ficou sem medida.

        Exigimos a série completa porque interpolar buracos na referência
        introduziria justamente o tipo de artefato lento que ela deveria
        remover.
        """
        if not self._fundo or any(f is None for f in self._fundo):
            return None
        return np.asarray(self._fundo, dtype=float).T
