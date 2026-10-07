"""O laço de medição, rodando fora da linha da interface.

Separado em thread própria por um motivo que não é de organização: a cascata de
Haar custa dezenas de milissegundos por quadro, e qualquer coisa que demore isso
na linha da interface congela a janela e a sobreposição. Sobreposição que trava
é pior que sobreposição nenhuma, porque passa a impressão de que o computador
inteiro travou.

A comunicação de volta é por sinal do Qt, que é a forma segura de atravessar
thread: a interface nunca lê o estado do medidor diretamente.

**Duas decisões sobre não piorar a imagem.** A captura é feita na resolução
nativa da tela, sem redimensionar nada antes da análise, e os pixels vão para o
pipeline como vieram. A única redução que existe é a que o próprio detector faz
internamente para procurar o rosto, e ela não toca nos pixels de onde a cor é
medida.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import cv2
import numpy as np
from PySide6.QtCore import QThread, Signal

from cardiocam.desktop.janelas import JanelaDaTela, reler
from cardiocam.desktop.sobreposicao import LeituraNaTela
from cardiocam.desktop.qualidade_ao_vivo import JuizDeQualidade
from cardiocam.dominio.config import ConfiguracaoAnalise
from cardiocam.pipeline.analisador import MonitorCardiaco

# A taxa que o laço tenta sustentar. Vinte é o mesmo alvo da versão web, e pelo
# mesmo motivo medido: a banda cardíaca vai a 3,3 Hz, então vinte são três vezes
# Nyquist, e pedir mais custa processamento sem comprar resolução que o pulso
# use.
QUADROS_POR_SEGUNDO = 20.0

# De quanto em quanto tempo a posição da janela capturada é relida. A pessoa
# move e redimensiona a janela da reunião no meio da conversa, e capturar o
# retângulo antigo passaria a medir o que estiver por baixo, sem nada avisar.
INTERVALO_DE_RELEITURA_S = 1.0

# Largura máxima do quadro entregue ao pipeline, na captura de tela.
#
# Reduzir aqui **não piora a imagem**: com `INTER_AREA` cada pixel de saída é a
# média dos de entrada, e média espacial reduz ruído de leitura. É o mesmo passo
# que a medição já fazia internamente. O que ela compra é tempo de detecção, que
# cresce com a área: medido numa janela de 1920x1032, a captura inteira rendeu
# 11,2 quadros por segundo e a mesma reduzida a 1280 rendeu 13,7, com a mesma
# proporção de quadros em que o rosto foi encontrado.
#
# O teto é 1280 e não 960 porque abaixo disso o rosto começa a sumir: a 960 a
# detecção caiu de 94% dos quadros para 86%, e rosto não encontrado é janela
# perdida.
LARGURA_MAXIMA_DA_TELA = 1280

# A cascata de Haar roda a cada N quadros, e o rastreador reaproveita a caixa
# nos intermediários. O padrão do pipeline é 2, pensado para webcam. Na captura
# de tela o quadro é bem maior e a detecção domina o custo: medido, passar de 2
# para 4 levou de 6,6 para 10,9 quadros por segundo **e melhorou** a proporção
# de quadros com rosto, de 85% para 97%, porque sobra tempo para não atrasar. A
# 6 a taxa sobe mais e o rosto começa a se perder.
#
# O custo é legítimo: num tile de reunião o rosto quase não se move entre
# quadros, que é a mesma razão pela qual o padrão já é maior que 1.
DETECCAO_A_CADA_N_QUADROS = 4

# Tempo gasto medindo a taxa antes de dimensionar a janela de análise.
#
# A janela é dimensionada em **amostras**, por `janela_s * fps`. Chutar 20 e
# receber 12 faria a janela de dez segundos durar dezesseis, e a barra de
# progresso mentir na mesma proporção. A análise em si não erra por isso, porque
# ela reamostra pelos carimbos de tempo de verdade, mas o que a pessoa vê erra.
SEGUNDOS_PARA_MEDIR_A_TAXA = 2.0


def confianca_de(snr_db: float | None) -> str:
    """Os mesmos limiares da versão web, para as duas dizerem a mesma coisa."""
    if snr_db is None:
        return "aguardando"
    if snr_db >= 6:
        return "alta"
    if snr_db >= 2:
        return "média"
    if snr_db >= 0:
        return "baixa"
    return "descartada"


@dataclass
class Origem:
    """De onde os quadros vêm. Uma das duas, nunca as duas."""

    camera: int | None = None
    janela: JanelaDaTela | None = None

    @property
    def descricao(self) -> str:
        if self.janela is not None:
            return self.janela.titulo
        return "Câmera do computador"


class LacoDeMedicao(QThread):
    """Lê quadros, alimenta o pipeline e devolve o que mostrar."""

    leitura_pronta = Signal(object)
    falhou = Signal(str)

    def __init__(self, origem: Origem, config: ConfiguracaoAnalise | None = None) -> None:
        super().__init__()
        self.origem = origem
        self.config = config or ConfiguracaoAnalise()
        self._rodando = False

    def parar(self) -> None:
        self._rodando = False

    # ------------------------------------------------------------------ laço
    def run(self) -> None:  # noqa: N802  (nome da API do Qt)
        self._rodando = True
        try:
            if self.origem.janela is not None:
                self._medir_janela()
            else:
                self._medir_camera()
        except Exception as erro:  # noqa: BLE001
            # Qualquer falha aqui precisa chegar à interface. Thread que morre
            # calada deixa o botão dizendo "ligado" com nada acontecendo.
            self.falhou.emit(str(erro))

    def _medir_camera(self) -> None:
        from cardiocam.fontes.webcam import abrir_webcam

        abertura = abrir_webcam(indice=self.origem.camera or 0)
        if abertura.falhou:
            self.falhou.emit(str(abertura.erro))
            return
        fonte = abertura.desempacotar()
        monitor = MonitorCardiaco(fps=fonte.fps, config=self.config)
        juiz = JuizDeQualidade(self.config.amostras_por_janela(fonte.fps))
        try:
            for quadro, instante in fonte.quadros():
                if not self._rodando:
                    break
                estado = monitor.processar(quadro, instante)
                juiz.registrar_quadro(quadro, estado)
                self._publicar(estado, juiz)
        finally:
            fonte.fechar()

    @staticmethod
    def _encolher(quadro: np.ndarray) -> np.ndarray:
        """Reduz a largura ao teto, promediando. Nunca amplia."""
        largura = quadro.shape[1]
        if largura <= LARGURA_MAXIMA_DA_TELA:
            return quadro
        altura = round(quadro.shape[0] * LARGURA_MAXIMA_DA_TELA / largura)
        return cv2.resize(
            quadro,
            (LARGURA_MAXIMA_DA_TELA, max(1, altura)),
            interpolation=cv2.INTER_AREA,
        )

    def _medir_taxa(self, captura, regiao: dict[str, int]) -> float:
        """Conta quadros por um instante, para dimensionar a janela de análise."""
        quadros = 0
        inicio = time.perf_counter()
        while (
            self._rodando
            and time.perf_counter() - inicio < SEGUNDOS_PARA_MEDIR_A_TAXA
        ):
            bruto = np.asarray(captura.grab(regiao))
            self._encolher(cv2.cvtColor(bruto, cv2.COLOR_BGRA2BGR))
            quadros += 1
        gasto = time.perf_counter() - inicio
        if quadros < 3 or gasto <= 0:
            return QUADROS_POR_SEGUNDO
        return min(QUADROS_POR_SEGUNDO, max(5.0, quadros / gasto))

    def _medir_janela(self) -> None:
        import mss

        from cardiocam.visao.detector_face import DetectorHaar
        from cardiocam.visao.rastreador import RastreadorRosto

        janela = self.origem.janela
        assert janela is not None

        with mss.MSS() as captura:
            taxa = self._medir_taxa(captura, janela.regiao)
        if not self._rodando:
            return

        monitor = MonitorCardiaco(
            fps=taxa,
            config=self.config,
            rastreador=RastreadorRosto(
                DetectorHaar(), intervalo_deteccao=DETECCAO_A_CADA_N_QUADROS
            ),
        )
        juiz = JuizDeQualidade(self.config.amostras_por_janela(taxa))
        intervalo = 1.0 / taxa
        inicio = time.perf_counter()
        ultima_releitura = 0.0

        with mss.MSS() as captura:
            while self._rodando:
                agora = time.perf_counter()

                if agora - ultima_releitura >= INTERVALO_DE_RELEITURA_S:
                    ultima_releitura = agora
                    atual = reler(janela)
                    if atual is None:
                        self.falhou.emit(
                            f'A janela "{janela.titulo}" foi fechada ou minimizada.'
                        )
                        return
                    janela = atual

                bruto = np.asarray(captura.grab(janela.regiao))
                # O mss entrega BGRA; o pipeline inteiro trabalha em BGR. A
                # conversão descarta só o canal alfa, que é constante.
                quadro = self._encolher(cv2.cvtColor(bruto, cv2.COLOR_BGRA2BGR))
                estado = monitor.processar(quadro, agora - inicio)
                juiz.registrar_quadro(quadro, estado)
                self._publicar(estado, juiz)

                resto = intervalo - (time.perf_counter() - agora)
                if resto > 0:
                    time.sleep(resto)

    # ------------------------------------------------------------- publicar
    def _publicar(self, estado, juiz: JuizDeQualidade) -> None:
        analise = monitor_analise(estado)
        snr = analise.estimativa.snr_db if analise is not None else None
        veredito = juiz.julgar(analise)
        # `analise.pulso` é um `SinalPulso`, não uma lista: o sinal mora em
        # `.amostras`. Fatiar o objeto direto levantava `not subscriptable` e
        # derrubava a thread **na primeira janela emitida**, que é o pior
        # instante possível: o laço rodava bonito até o momento em que teria
        # algo a dizer.
        pulso = (
            [float(v) for v in analise.pulso.amostras[-240:]]
            if analise is not None
            else []
        )
        # O modelo tem a última palavra sobre mostrar o número, e não sobre o
        # selo: o selo diz o que a relação sinal-ruído mostra, e a recusa diz o
        # que o modelo de qualidade decidiu. São duas informações diferentes, e
        # juntá-las numa só esconderia qual das duas reprovou a janela.
        recusado = veredito is not None and veredito.recusa
        self.leitura_pronta.emit(
            LeituraNaTela(
                bpm=None if recusado else estado.bpm_exibido,
                confianca="descartada" if recusado else confianca_de(snr),
                snr_db=snr,
                progresso=estado.progresso,
                mensagem=(
                    f"Recusada pelo modelo de qualidade ({veredito.texto})."
                    if recusado
                    else estado.mensagem
                ),
                pulso=pulso,
                qualidade=None if veredito is None else veredito.probabilidade,
            )
        )


def monitor_analise(estado):
    """A análise do quadro, quando houve uma.

    Fica em função própria porque o estado só traz análise nos quadros em que a
    janela emitiu, e o resto do código não deveria precisar saber disso.
    """
    return getattr(estado, "analise", None)
