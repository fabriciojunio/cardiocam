"""Orquestração: do quadro de vídeo até o número na tela.

A sequência completa é:

    quadro -> detecção do rosto -> estabilização da caixa -> regiões de
    interesse -> máscara de pele -> média RGB -> janela deslizante ->
    reamostragem uniforme -> algoritmo rPPG -> detrend -> passa-faixa ->
    espectro -> pico refinado -> BPM

As três primeiras etapas são processamento de imagem, as demais são
processamento de sinais, e a média RGB é a fronteira entre os dois mundos.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from cardiocam.dominio.config import ConfiguracaoAnalise
from cardiocam.dominio.erros import SinalSemQualidade
from cardiocam.dominio.estimativa import (
    Confianca,
    Espectro,
    EstimativaBPM,
    VariabilidadeCardiaca,
)
from cardiocam.dominio.resultado import Falha, Ok, Resultado
from cardiocam.dominio.sinal import SerieRGB, SinalPulso
from cardiocam.rppg import AlgoritmoRPPG, criar_algoritmo
from cardiocam.sinais import analisar as analisar_espectro
from cardiocam.sinais import variabilidade
from cardiocam.sinais.rectificacao import remover_referencia
from cardiocam.sinais.janela import JanelaDeslizante
from cardiocam.visao.detector_face import DetectorFace, DetectorHaar
from cardiocam.visao.extrator import AmostraQuadro, ExtratorRGB
from cardiocam.visao.geometria import Retangulo
from cardiocam.visao.rastreador import RastreadorRosto


def _rectificar_pelo_fundo(serie: SerieRGB) -> SerieRGB:
    """Retira de cada canal do rosto a parte explicável pelo mesmo canal do fundo.

    A média de cada canal é reposta depois da subtração, porque os algoritmos
    cromáticos normalizam pela média temporal e precisam do nível original.
    """
    canais = serie.como_matriz()
    limpos = np.empty_like(canais)
    for indice in range(3):
        media_original = float(np.mean(canais[indice]))
        limpos[indice] = (
            remover_referencia(canais[indice], serie.fundo[indice]) + media_original
        )
    return SerieRGB(
        limpos[0], limpos[1], limpos[2], serie.fps, serie.instantes, serie.fundo
    )


@dataclass(frozen=True, slots=True)
class AnaliseCompleta:
    """Tudo que uma janela produz."""

    estimativa: EstimativaBPM
    pulso: SinalPulso
    espectro: Espectro
    hrv: VariabilidadeCardiaca
    bpm_por_picos: float

    @property
    def concordancia_bpm(self) -> float:
        """Diferença absoluta entre a estimativa espectral e a por contagem de
        picos. Valores pequenos reforçam a confiança no resultado."""
        if not np.isfinite(self.bpm_por_picos):
            return float("nan")
        return abs(self.estimativa.bpm - self.bpm_por_picos)


def estimar_de_serie(
    serie: SerieRGB,
    config: ConfiguracaoAnalise | None = None,
    algoritmo: AlgoritmoRPPG | None = None,
) -> Resultado[AnaliseCompleta]:
    """Analisa uma janela de série RGB e devolve a estimativa completa.

    É a função pura do sistema: mesma entrada, mesma saída, sem estado nem I/O.
    Tanto o modo ao vivo quanto o processamento de arquivo passam por aqui.
    """
    config = config or ConfiguracaoAnalise()
    algoritmo = algoritmo or criar_algoritmo(config.algoritmo)

    # Rectificação por referência de fundo, aplicada canal a canal antes do
    # algoritmo. A ordem importa: o balanço de branco automático age sobre cada
    # canal separadamente, então é aí que a correção pertence. Depois do
    # algoritmo já não há como desfazer, porque a combinação cromática mistura
    # os canais.
    if config.usar_fundo and serie.fundo is not None:
        serie = _rectificar_pelo_fundo(serie)

    extracao = algoritmo.extrair(serie, config)
    if extracao.falhou:
        return Falha(extracao.erro)
    pulso = extracao.desempacotar()

    # Guarda contra entrada degenerada. Se a região medida não varia nada (uma
    # parede lisa no lugar do rosto, ou uma imagem estourada em que todos os
    # pixels saturaram em 255), o que sobra depois da filtragem é apenas erro de
    # arredondamento. O espectro disso tem um pico como qualquer outro, e sem
    # esta verificação o sistema anunciaria um valor com confiança máxima. Um
    # medidor que não sabe dizer "não sei" é pior que inútil.
    escala_entrada = float(np.mean(np.abs(serie.como_matriz())))
    limiar = 1e-9 * max(escala_entrada, 1.0)
    if float(np.std(pulso.amostras)) < limiar:
        return Falha(SinalSemQualidade(float("-inf"), config.snr_minimo_db))

    espectral = analisar_espectro(pulso, config.banda)
    if espectral.falhou:
        return Falha(espectral.erro)
    analise = espectral.desempacotar()

    estimativa = EstimativaBPM.criar(
        frequencia_hz=analise.frequencia_hz,
        snr_db=analise.snr_db,
        algoritmo=algoritmo.nome,
        janela_s=serie.duracao_s,
    )

    if estimativa.snr_db < config.snr_minimo_db:
        return Falha(SinalSemQualidade(estimativa.snr_db, config.snr_minimo_db))

    indices = variabilidade(
        pulso, config.banda, frequencia_esperada_hz=analise.frequencia_hz
    )
    from cardiocam.sinais.picos import bpm_por_picos as _bpm_por_picos

    return Ok(
        AnaliseCompleta(
            estimativa=estimativa,
            pulso=pulso,
            espectro=analise.espectro,
            hrv=indices,
            bpm_por_picos=_bpm_por_picos(
                pulso, config.banda, frequencia_esperada_hz=analise.frequencia_hz
            ),
        )
    )


@dataclass
class EstadoQuadro:
    """O que aconteceu ao processar um quadro. Alimenta a interface."""

    caixa: Retangulo | None = None
    amostra: AmostraQuadro | None = None
    analise: AnaliseCompleta | None = None
    bpm_exibido: float | None = None
    mensagem: str = ""
    progresso: float = 0.0
    """Fração da janela já preenchida, de 0 a 1."""

    @property
    def tem_rosto(self) -> bool:
        return self.caixa is not None


class MonitorCardiaco:
    """Mantém o estado da medição ao longo do tempo.

    Existe para separar a lógica de acompanhamento (janela, suavização, perda de
    rosto) da interface gráfica e da linha de comando, que apenas consomem
    `EstadoQuadro`.
    """

    def __init__(
        self,
        fps: float,
        config: ConfiguracaoAnalise | None = None,
        detector: DetectorFace | None = None,
        extrator: ExtratorRGB | None = None,
        rastreador: RastreadorRosto | None = None,
        algoritmo: AlgoritmoRPPG | None = None,
    ) -> None:
        self.config = config or ConfiguracaoAnalise()
        self.algoritmo = algoritmo or criar_algoritmo(self.config.algoritmo)
        self.extrator = extrator or ExtratorRGB()
        # Detectar a cada dois quadros divide por dois o custo dominante do
        # laço sem prejuízo perceptível: em 33 ms um rosto humano praticamente
        # não sai do lugar, e o rastreador reaproveita a caixa no quadro
        # intermediário.
        self.rastreador = rastreador or RastreadorRosto(
            detector or DetectorHaar(), intervalo_deteccao=2
        )
        self.janela = JanelaDeslizante(fps, self.config)

        self._bpm_suavizado: float | None = None
        self._ultima_analise: AnaliseCompleta | None = None
        self._historico: list[EstimativaBPM] = []
        self._quadros_processados = 0

    @property
    def bpm_atual(self) -> float | None:
        return self._bpm_suavizado

    @property
    def ultima_analise(self) -> AnaliseCompleta | None:
        return self._ultima_analise

    @property
    def historico(self) -> list[EstimativaBPM]:
        return list(self._historico)

    @property
    def quadros_processados(self) -> int:
        return self._quadros_processados

    def _suavizar(self, bpm: float) -> float:
        """Média exponencial do BPM exibido.

        Sem isso o número pisca alguns batimentos para cima e para baixo a cada
        atualização, o que passa a impressão de instabilidade mesmo quando a
        medição está correta.
        """
        peso = float(np.clip(self.config.suavizacao_bpm, 0.0, 1.0))
        if self._bpm_suavizado is None or peso >= 1.0:
            self._bpm_suavizado = bpm
        else:
            self._bpm_suavizado = (1.0 - peso) * self._bpm_suavizado + peso * bpm
        return self._bpm_suavizado

    def reiniciar(self) -> None:
        """Zera a medição. Usado quando o rosto se perde por tempo demais."""
        self.janela.limpar()
        self.rastreador.reiniciar()
        self.extrator.reiniciar()
        self._bpm_suavizado = None
        self._ultima_analise = None

    def processar(self, quadro: np.ndarray, instante: float) -> EstadoQuadro:
        """Consome um quadro e devolve o estado atualizado."""
        self._quadros_processados += 1
        estado = EstadoQuadro(bpm_exibido=self._bpm_suavizado)

        deteccao = self.rastreador.atualizar(quadro)
        if deteccao.falhou:
            if self.rastreador.perdeu_o_rosto and len(self.janela):
                self.janela.limpar()
                self._bpm_suavizado = None
                self._ultima_analise = None
                estado.bpm_exibido = None
            estado.mensagem = "Rosto não encontrado. Olhe para a câmera."
            return estado

        estado.caixa = deteccao.desempacotar()

        extracao = self.extrator.extrair(quadro, estado.caixa)
        if extracao.falhou:
            estado.mensagem = str(extracao.erro)
            return estado

        amostra = extracao.desempacotar()
        estado.amostra = amostra
        self.janela.adicionar(
            amostra.vermelho, amostra.verde, amostra.azul, instante, amostra.fundo
        )
        estado.progresso = min(1.0, len(self.janela) / self.janela.capacidade)

        if not self.janela.deve_emitir():
            if not self.janela.cheia:
                faltam = self.janela.capacidade - len(self.janela)
                segundos = faltam / max(1e-6, self.janela.fps_efetivo())
                estado.mensagem = f"Coletando sinal, faltam {segundos:.0f} s."
            else:
                estado.mensagem = "Medindo."
            estado.analise = self._ultima_analise
            return estado

        self.janela.marcar_emissao()
        resultado = estimar_de_serie(self.janela.serie(), self.config, self.algoritmo)

        if resultado.falhou:
            estado.mensagem = "Sinal fraco. Fique parado e melhore a iluminação."
            estado.analise = self._ultima_analise
            return estado

        analise = resultado.desempacotar()
        self._ultima_analise = analise
        self._historico.append(analise.estimativa)
        estado.analise = analise
        estado.bpm_exibido = self._suavizar(analise.estimativa.bpm)
        estado.mensagem = f"Confiança {analise.estimativa.confianca.value}."
        return estado


@dataclass
class RelatorioSessao:
    """Resumo de uma sessão inteira de medição."""

    estimativas: list[EstimativaBPM] = field(default_factory=list)
    quadros_processados: int = 0
    quadros_com_rosto: int = 0
    ultima_analise: AnaliseCompleta | None = None

    @property
    def total_estimativas(self) -> int:
        return len(self.estimativas)

    @property
    def taxa_deteccao(self) -> float:
        if self.quadros_processados == 0:
            return 0.0
        return self.quadros_com_rosto / self.quadros_processados

    @property
    def bpm_mediano(self) -> float:
        """Mediana das janelas aproveitáveis.

        Preferimos a mediana à média porque uma única janela contaminada por
        movimento pode ir parar longe, e a mediana ignora esse tipo de excursão.
        """
        validos = [e.bpm for e in self.estimativas if e.aproveitavel]
        if not validos:
            return float("nan")
        return float(np.median(validos))

    @property
    def desvio_bpm(self) -> float:
        validos = [e.bpm for e in self.estimativas if e.aproveitavel]
        if len(validos) < 2:
            return float("nan")
        return float(np.std(validos))

    @property
    def snr_mediano_db(self) -> float:
        valores = [e.snr_db for e in self.estimativas if np.isfinite(e.snr_db)]
        if not valores:
            return float("nan")
        return float(np.median(valores))

    @property
    def confianca_predominante(self) -> Confianca:
        if not self.estimativas:
            return Confianca.DESCARTADA
        contagem: dict[Confianca, int] = {}
        for estimativa in self.estimativas:
            contagem[estimativa.confianca] = contagem.get(estimativa.confianca, 0) + 1
        return max(contagem.items(), key=lambda par: par[1])[0]


def analisar_fonte(
    fonte,
    config: ConfiguracaoAnalise | None = None,
    detector: DetectorFace | None = None,
    extrator: ExtratorRGB | None = None,
    rastreador: RastreadorRosto | None = None,
    algoritmo: AlgoritmoRPPG | None = None,
    limite_quadros: int | None = None,
) -> RelatorioSessao:
    """Processa uma fonte de vídeo do início ao fim.

    Caminho usado para analisar arquivos gravados e para os testes de ponta a
    ponta, onde a frequência verdadeira é conhecida.
    """
    config = config or ConfiguracaoAnalise()
    monitor = MonitorCardiaco(
        fps=getattr(fonte, "fps", 30.0) or 30.0,
        config=config,
        detector=detector,
        extrator=extrator,
        rastreador=rastreador,
        algoritmo=algoritmo,
    )

    relatorio = RelatorioSessao()
    for indice, (quadro, instante) in enumerate(fonte.quadros()):
        if limite_quadros is not None and indice >= limite_quadros:
            break
        estado = monitor.processar(quadro, instante)
        relatorio.quadros_processados += 1
        if estado.tem_rosto:
            relatorio.quadros_com_rosto += 1

    relatorio.estimativas = monitor.historico
    relatorio.ultima_analise = monitor.ultima_analise
    return relatorio
