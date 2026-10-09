"""Coleta janelas percorrendo o caminho completo, com imagem.

Existe por um motivo medido: no caminho analítico, **quatro das onze
características não variam**, porque não há imagem. Fração de pele, fração
saturada, deslocamento da região e jitter ficam constantes, o modelo
corretamente lhes dá peso zero com o desvio da priori, e a decisão de recusar
acaba apoiada só no espectro.

Isso é uma limitação do instrumento, não do modelo, e ela importa: as
características de imagem são justamente as que descrevem os modos de falha que
o espectro não vê. Região que escorregou para o cabelo, rosto estourado de luz,
pouca pele dentro da caixa. Nenhum desses aparece como espectro feio, e todos
produzem número errado.

Aqui o vídeo sintético é renderizado quadro a quadro, a cascata de Haar procura
o rosto de verdade, a máscara de pele roda, e cada janela emitida vira uma
amostra com o contexto de imagem acumulado sobre os quadros que a formaram.

Custa caro: renderizar e detectar é duas ordens de grandeza mais lento que gerar
a série analítica. É por isso que a coleta analítica continua existindo, e é por
isso que esta roda com menos cenários.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass

import numpy as np

from cardiocam.avaliacao.benchmark import Cenario, cenarios_de_robustez
from cardiocam.dominio.config import ConfiguracaoAnalise
from cardiocam.fontes.sintetica import FonteSintetica
from cardiocam.pipeline.analisador import MonitorCardiaco
from cardiocam.qualidade.extracao import caracteristicas_da_analise
from cardiocam.qualidade.treino import Amostra
from cardiocam.rppg import ALGORITMOS_DISPONIVEIS, criar_algoritmo

# Limite superior e inferior da escala de 8 bits. Pixel encostado em qualquer um
# dos dois perdeu informação antes de virar número: o pulso que estava ali foi
# cortado pelo conversor, e nenhuma filtragem o traz de volta.
SATURADO_ALTO = 254
SATURADO_BAIXO = 1


@dataclass
class ContextoDaJanela:
    """Acumula o que a imagem mostra, nos quadros que formam uma janela.

    Público porque o aplicativo de desktop usa o mesmo acúmulo para alimentar o
    modelo de qualidade ao vivo. As características de imagem precisam descrever
    exatamente os quadros que produziram a estimativa, tanto na bateria quanto
    na medição de verdade; duas implementações disso seriam duas chances de
    divergirem em silêncio.

    Usa `deque` com tamanho máximo igual à capacidade da janela de sinal, para
    que o contexto descreva **os mesmos quadros** que produziram a estimativa.
    Acumular desde o início do vídeo misturaria quadros que já saíram da janela,
    e a característica passaria a falar de um passado que a estimativa não viu.
    """

    capacidade: int

    def __post_init__(self) -> None:
        self.pele: deque[float] = deque()
        self.saturacao: deque[float] = deque()
        self.centro_x: deque[float] = deque()
        self.instantes: deque[float | None] = deque()

    def registrar(self, proporcao_pele: float, saturada: float, centro: float,
                  instante: float | None = None, inicio: float | None = None) -> None:
        self.pele.append(float(proporcao_pele))
        self.saturacao.append(float(saturada))
        self.centro_x.append(float(centro))
        self.instantes.append(instante)
        if inicio is None:
            while len(self.pele) > self.capacidade:
                self._remover_primeiro()
        else:
            while self.instantes and (self.instantes[0] is None or self.instantes[0] < inicio - 1e-8):
                self._remover_primeiro()

    def _remover_primeiro(self) -> None:
        for buffer in (self.pele, self.saturacao, self.centro_x, self.instantes):
            buffer.popleft()

    def limpar(self) -> None:
        self.pele.clear()
        self.saturacao.clear()
        self.centro_x.clear()
        self.instantes.clear()

    @property
    def completo(self) -> bool:
        return len(self.pele) == self.capacidade

    def media_de_pele(self) -> float:
        return float(np.mean(self.pele)) if self.pele else 0.0

    def media_saturada(self) -> float:
        return float(np.mean(self.saturacao)) if self.saturacao else 0.0

    def deslocamento(self) -> np.ndarray:
        return np.array(self.centro_x, dtype=float)


def fracao_saturada(quadro: np.ndarray, caixa) -> float:
    """Fração de pixels encostados nos extremos da escala, dentro da caixa.

    Mede na caixa e não no quadro inteiro porque uma janela clara ao fundo
    estouraria o número sem nada ter acontecido com o rosto, que é o que
    interessa.
    """
    altura, largura = quadro.shape[:2]
    x0 = max(0, min(int(caixa.x), largura - 1))
    y0 = max(0, min(int(caixa.y), altura - 1))
    x1 = max(x0 + 1, min(int(caixa.x + caixa.largura), largura))
    y1 = max(y0 + 1, min(int(caixa.y + caixa.altura), altura))
    recorte = quadro[y0:y1, x0:x1]
    if recorte.size == 0:
        return 0.0
    extremos = (recorte >= SATURADO_ALTO) | (recorte <= SATURADO_BAIXO)
    return float(np.mean(extremos))


def coletar_de_video(
    cenarios: list[Cenario] | None = None,
    algoritmos: tuple[str, ...] = ALGORITMOS_DISPONIVEIS,
    config: ConfiguracaoAnalise | None = None,
    agrupar_por: str = "condicao",
) -> tuple[list[Amostra], int]:
    """Roda os cenários como vídeo e devolve uma amostra por janela emitida.

    Cada janela emitida vira uma amostra, e não só a última do vídeo: um vídeo
    de 20 segundos com passo de 1 segundo emite cerca de dez janelas, e
    descartar nove delas jogaria fora a maior parte do dado. É esta a razão de a
    coleta por vídeo render mais amostras por cenário que a analítica, apesar de
    custar muito mais.
    """
    if agrupar_por not in {"condicao", "frequencia"}:
        raise ValueError(
            f"Agrupamento {agrupar_por!r} não existe. Use 'condicao' ou 'frequencia'."
        )

    cenarios = cenarios or cenarios_de_robustez()
    config = config or ConfiguracaoAnalise()
    amostras: list[Amostra] = []
    sem_estimativa = 0

    for cenario in cenarios:
        grupo = (
            cenario.nome
            if agrupar_por == "condicao"
            else f"{cenario.bpm_verdadeiro:.0f}"
        )
        for nome in algoritmos:
            fonte = FonteSintetica(cenario.parametros)
            monitor = MonitorCardiaco(
                fps=cenario.parametros.fps,
                config=config.com(algoritmo=nome),
                algoritmo=criar_algoritmo(nome),
            )
            contexto = ContextoDaJanela(
                capacidade=config.amostras_por_janela(cenario.parametros.fps)
            )
            emitidas = 0

            for quadro, instante in fonte.quadros():
                estado = monitor.processar(quadro, instante)
                if estado.contexto_reiniciado:
                    contexto.limpar()
                if estado.amostra is not None and estado.caixa is not None:
                    contexto.registrar(
                        estado.amostra.proporcao_pele,
                        (estado.amostra.fracao_saturada if estado.amostra.fracao_saturada is not None
                         else fracao_saturada(quadro, estado.caixa)),
                        (estado.caixa.x + estado.caixa.largura / 2.0)
                        / max(1, quadro.shape[1]),
                        instante=instante, inicio=estado.inicio_janela,
                    )

                if monitor.total_estimativas <= emitidas:
                    continue
                emitidas = monitor.total_estimativas
                analise = monitor.ultima_analise
                if analise is None:
                    continue

                amostras.append(
                    Amostra(
                        caracteristicas=caracteristicas_da_analise(analise, contexto=contexto),
                        erro_bpm=float(
                            abs(analise.estimativa.bpm - cenario.bpm_verdadeiro)
                        ),
                        grupo=grupo,
                    )
                )

            if emitidas == 0:
                # O vídeo inteiro sem uma estimativa sequer. É recusa do
                # pipeline, e conta separado pelo mesmo motivo da coleta
                # analítica: essas janelas nunca chegam ao modelo em produção.
                sem_estimativa += 1

    return amostras, sem_estimativa
